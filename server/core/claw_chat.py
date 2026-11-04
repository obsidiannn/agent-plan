# coding: utf-8
"""股吧舆情对话(Chroma 检索 + 立场统计), 供路由 /api/agent/clawChat 使用

数据来源是 claw_graph 落库的股吧集合(guba_posts):
- document 存 "标题 + 立场 + 时间"(claw_graph.build_doc_text)
- metadata 存 标题/作者/时间/立场/股票 等, 供前端展示来源与倾向

回答流程: 向量检索命中帖子 -> 先推立场分布与来源 -> LLM 结合二者流式作答
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from collections import Counter
from typing import AsyncIterator

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

import server.config  # noqa: F401  加载 server/.env
from server.core import claw
from server.core.chroma_rag import (
    CHROMA_HOST,
    CHROMA_PORT,
    ChineseOnnxEmbeddings,
    configure_proxy,
)

# 与 claw_graph 落库的集合保持一致, 可用同一环境变量覆盖
COLLECTION_NAME = os.environ.get("CLAW_COLLECTION", "guba_posts")
MAX_HISTORY = 20   # 单会话保留的最大消息条数
TOP_K = 5          # 每次检索返回的帖子数
FETCH_K = 20       # MMR 先取候选集大小, 兼顾相关性与多样性
STANCE_ORDER = ("看多", "看空", "中性")

SYSTEM_PROMPT = (
    "你是股吧舆情分析助手。只能依据下面的资料回答, 资料中没有的信息要明确说不知道。\n"
    "资料每段都标注了 [来源: 标题 | 作者 | 时间 | 立场], 回答时请引用来源标题。\n"
    "若问题涉及市场情绪或用户倾向, 请结合\"全库立场分布\"说明看多/看空/中性的整体占比。\n\n"
    "全库立场分布(看多/看空/中性):\n{overview}\n\n"
    "资料:\n{context}"
)


def _collection():
    """连接 Chroma Server 并取(或建)股吧集合"""
    configure_proxy()  # 让 localhost 走直连, 不走 HTTP_PROXY
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return client.get_or_create_collection(COLLECTION_NAME)


def _all_metadatas() -> list[dict]:
    """读取集合全量元数据(用于立场统计与参数聚合)"""
    return _collection().get(include=["metadatas"]).get("metadatas") or []


def stance_overview(claw_param: str | None = None) -> dict:
    """立场分布, 形如 {"total": n, "claw_param": p, "stance": {"看多": x, "看空": y, "中性": z}}

    传 claw_param(如股票代码 002526)时只统计该参数的帖子, 不传则统计全库。
    """
    metadatas = _all_metadatas()
    if claw_param:
        metadatas = [
            m for m in metadatas if (m or {}).get("claw_param") == claw_param]
    dist = Counter((m or {}).get("stance") or "未知" for m in metadatas)
    counts = {label: dist.get(label, 0) for label in STANCE_ORDER}
    for label, count in dist.items():
        if label not in counts:
            counts[label] = count
    return {"total": len(metadatas), "claw_param": claw_param or "", "stance": counts}


def list_params() -> list[dict]:
    """可选采集参数(claw_task_detail.claw_param)及其已入库条数, 供前端下拉选择。

    参数清单来自库中激活任务, 条数来自向量库(未采集的参数条数为 0)。
    """
    counts = Counter((m or {}).get("claw_param")
                     or "" for m in _all_metadatas())
    params: list[dict] = []
    seen: set[str] = set()
    for target in claw.load_targets():
        param = target["claw_param"]
        if param in seen:
            continue
        seen.add(param)
        params.append({
            "claw_param": param,
            "task_code": target["task_code"],
            "task_name": target["task_name"],
            "count": counts.get(param, 0),
        })
    return params


def _format_docs(docs: list[Document]) -> str:
    """把命中的帖子拼成带来源标注的上下文"""
    blocks = []
    for doc in docs:
        meta = doc.metadata or {}
        blocks.append(
            f"[来源: {meta.get('title', '')} | 代码: {meta.get('claw_param', '')} "
            f"| 作者: {meta.get('author', '')} | 时间: {meta.get('publish_time', '')} "
            f"| 立场: {meta.get('stance', '')}]\n"
            f"{doc.page_content}"
        )
    return "\n\n".join(blocks) or "(无命中资料)"


def _sources(docs: list[Document]) -> list[dict]:
    """命中帖子的摘要, 供前端右侧面板核对来源"""
    sources = []
    for doc in docs:
        meta = doc.metadata or {}
        sources.append({
            "title": meta.get("title", ""),
            "url": meta.get("url", ""),
            "author": meta.get("author", ""),
            "publish_time": meta.get("publish_time", ""),
            "stance": meta.get("stance", ""),
            "task_code": meta.get("task_code", ""),
            "claw_param": meta.get("claw_param", ""),
            "snippet": doc.page_content[:120],
        })
    return sources


def _build_embeddings() -> Embeddings:
    return ChineseOnnxEmbeddings()


_chain = None
_vectorstore = None
_init_lock = threading.Lock()

# 会话历史: {conversation_id: [HumanMessage/AIMessage, ...]}(进程内, 重启即清空)
_histories: dict[str, list] = {}


def get_chain():
    """懒加载: 首次调用才加载 ONNX 模型并连接 Chroma(与 chroma_rag 一致的策略)

    返回 (链, 向量库)。检索条件每次请求都可能不同(按 claw_param 过滤), 所以不缓存 retriever。
    """
    global _chain, _vectorstore
    if _chain is None:
        with _init_lock:
            if _chain is None:
                configure_proxy()
                _vectorstore = Chroma(
                    collection_name=COLLECTION_NAME,
                    embedding_function=_build_embeddings(),
                    host=CHROMA_HOST,
                    port=CHROMA_PORT,
                )
                llm = ChatOpenAI(
                    model="deepseek-flash",
                    api_key=os.environ["OPENAI_API_KEY"],
                    base_url=os.environ["OPENAI_BASE_URL"],
                    max_tokens=1024,
                )
                prompt = ChatPromptTemplate.from_messages([
                    ("system", SYSTEM_PROMPT),
                    MessagesPlaceholder("history"),
                    ("human", "{question}"),
                ])
                _chain = prompt | llm | StrOutputParser()
    return _chain, _vectorstore


def _retrieve(vectorstore, question: str, claw_param: str | None) -> list[Document]:
    """MMR 检索: 兼顾相关性与多样性; 传 claw_param 时只在该参数的帖子内检索"""
    where = {"claw_param": claw_param} if claw_param else None
    return vectorstore.max_marginal_relevance_search(
        question, k=TOP_K, fetch_k=FETCH_K, filter=where)


def _history(conversation_id: str) -> list:
    return _histories.setdefault(conversation_id, [])


async def astream(conversation_id: str, question: str, claw_param: str | None = None) -> AsyncIterator[dict]:
    """检索 -> 推立场分布/来源 -> 流式生成, 结束后把本轮问答写回历史。

    claw_param 用于把问答限定在某个采集参数(如股票代码)的帖子上, 不传表示全库。
    产出即为 SSE 事件体: {"event": 事件名, "data": JSON 字符串}
    事件: stats(立场分布) / sources(命中帖子) / on_chat_model_stream(增量文本) / error
    """
    overview = await asyncio.to_thread(stance_overview, claw_param)
    yield {
        "event": "stats",
        "data": json.dumps(overview, ensure_ascii=False),
    }
    if not overview["total"]:
        message = (f"参数 {claw_param} 暂无已入库的帖子, 请先运行 "
                   "python -m server.core.claw_graph 采集.") if claw_param else (
            "股吧向量库暂无数据, 请先运行 python -m server.core.claw_graph 采集.")
        yield {
            "event": "error",
            "data": json.dumps({"message": message}, ensure_ascii=False),
        }
        return

    chain, vectorstore = get_chain()
    docs = await asyncio.to_thread(_retrieve, vectorstore, question, claw_param)
    yield {
        "event": "sources",
        "data": json.dumps({"sources": _sources(docs)}, ensure_ascii=False),
    }

    history = _history(conversation_id)
    answer = ""
    async for chunk in chain.astream({
        "overview": json.dumps(overview["stance"], ensure_ascii=False),
        "context": _format_docs(docs),
        "question": question,
        "history": history,
    }):
        if chunk:
            answer += chunk
            yield {
                "event": "on_chat_model_stream",
                "data": json.dumps(
                    {"node": "claw-chat", "content": chunk}, ensure_ascii=False),
            }

    history.append(HumanMessage(content=question))
    history.append(AIMessage(content=answer))
    del history[:-MAX_HISTORY]  # 只保留最近 MAX_HISTORY 条, 防止无限增长
