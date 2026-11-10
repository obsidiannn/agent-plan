# coding: utf-8
"""股吧领域能力实现

数据来源是 claw_graph 落库的股吧集合(guba_posts):
- document 存 "标题 + 立场 + 时间"(claw_graph.build_doc_text)
- metadata 存 标题/作者/时间/立场/股票 等

检索 / 统计 / 参数清单在这里实现, 供 MCP 工具(server/mcp/claw/tools.py)
与对话 Agent(server/core/claw_chat.py)共用。
"""
from __future__ import annotations

import json
import os
import threading
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from server.core import claw
from server.core.chroma_rag import (
    CHROMA_HOST,
    CHROMA_PORT,
    ChineseOnnxEmbeddings,
    configure_proxy,
)

# 与 claw_graph 落库的集合保持一致, 可用同一环境变量覆盖
COLLECTION_NAME = os.environ.get("CLAW_COLLECTION", "guba_posts")
TOP_K = 5          # 每次检索返回的帖子数
FETCH_K = 20       # MMR 先取候选集大小, 兼顾相关性与多样性
STANCE_ORDER = ("积极", "消极", "中性")


def _collection():
    """连接 Chroma Server 并取(或建)股吧集合"""
    configure_proxy()  # 让 localhost 走直连, 不走 HTTP_PROXY
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return client.get_or_create_collection(COLLECTION_NAME)


def _all_metadatas() -> list[dict]:
    """读取集合全量元数据(用于立场统计与参数聚合)"""
    return _collection().get(include=["metadatas"]).get("metadatas") or []


def stance_overview(claw_param: str | None = None) -> dict:
    """立场分布, 形如 {"total": n, "claw_param": p, "stance": {"积极": x, "消极": y, "中性": z}}

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


def data_answer(claw_param: str | None = None) -> str:
    """基于向量库元数据如实汇总已采集的数据信息, 供对话直接作答(不经 LLM 检索)。

    不传 claw_param 时汇总全库并按参数列出; 传则只统计该参数。
    """
    metas = [m or {} for m in _all_metadatas()]
    if claw_param:
        rows = [m for m in metas if m.get("claw_param") == claw_param]
        if not rows:
            return (f"参数 {claw_param} 目前还没有已入库的数据, 可以说"
                    f"\"帮我拉取 {claw_param} <日期> 的数据\"来采集。")
        dist = Counter(m.get("stance") or "未知" for m in rows)
        dates = sorted({(m.get("publish_time") or "")[:5]
                        for m in rows if m.get("publish_time")})
        latest = max((m.get("publish_time") or "" for m in rows), default="")
        crawled = max((m.get("crawled_at") or "" for m in rows), default="")
        lines = [
            f"参数 {claw_param} 已入库 {len(rows)} 条帖子。",
            f"立场分布: 积极 {dist.get('积极', 0)} / 消极 {dist.get('消极', 0)} "
            f"/ 中性 {dist.get('中性', 0)}。",
        ]
        if dates:
            lines.append(f"覆盖发布日期: {'、'.join(dates)}。")
        if latest:
            lines.append(f"最近一条发布时间: {latest}。")
        if crawled:
            lines.append(f"最近采集时间: {crawled}。")
        samples = sorted(rows, key=lambda m: m.get("publish_time") or "",
                         reverse=True)[:5]
        titles = [m.get("title", "") for m in samples if m.get("title")]
        if titles:
            lines.append("最近标题: " + "; ".join(titles))
        return "\n".join(lines)

    if not metas:
        return "股吧向量库暂无已入库数据, 可以说\"帮我拉取 <代码> <日期> 的数据\"来采集。"
    counts = Counter(m.get("claw_param") or "" for m in metas)
    dist = Counter(m.get("stance") or "未知" for m in metas)
    lines = [f"股吧向量库共 {len(metas)} 条帖子, 覆盖 {len(counts)} 个参数:"]
    for param, count in counts.most_common():
        lines.append(f"- {param or '(无参数)'}: {count} 条")
    lines.append(f"整体立场分布: 积极 {dist.get('积极', 0)} / 消极 {dist.get('消极', 0)} "
                 f"/ 中性 {dist.get('中性', 0)}。")
    return "\n".join(lines)


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


_vectorstore = None
_init_lock = threading.Lock()


def get_vectorstore() -> Chroma:
    """懒加载: 首次调用才加载 ONNX 模型并连接 Chroma(与 chroma_rag 一致的策略)"""
    global _vectorstore
    if _vectorstore is None:
        with _init_lock:
            if _vectorstore is None:
                configure_proxy()
                _vectorstore = Chroma(
                    collection_name=COLLECTION_NAME,
                    embedding_function=_build_embeddings(),
                    host=CHROMA_HOST,
                    port=CHROMA_PORT,
                )
    return _vectorstore


def _retrieve(vectorstore, question: str, claw_param: str | None) -> list[Document]:
    """MMR 检索: 兼顾相关性与多样性; 传 claw_param 时只在该参数的帖子内检索"""
    where = {"claw_param": claw_param} if claw_param else None
    return vectorstore.max_marginal_relevance_search(
        question, k=TOP_K, fetch_k=FETCH_K, filter=where)


def search_answer(query: str, claw_param: str | None = None) -> dict:
    """检索帖子并汇总立场, 返回 {"overview", "sources", "text"}

    text 为交给模型的资料正文; overview/sources 供前端展示(Agent 侧转成 SSE 事件)。
    """
    overview = stance_overview(claw_param)
    if not overview["total"]:
        text = (f"参数 {claw_param} 暂无已入库的帖子, 请先采集再提问。" if claw_param
                else "股吧向量库暂无数据, 请先采集再提问。")
        return {"overview": overview, "sources": [], "text": text}

    docs = _retrieve(get_vectorstore(), query, claw_param)
    stance_text = json.dumps(overview["stance"], ensure_ascii=False)
    return {
        "overview": overview,
        "sources": _sources(docs),
        "text": f"全库立场分布(积极/消极/中性): {stance_text}\n\n资料:\n{_format_docs(docs)}",
    }


_progress_sink: ContextVar[Callable[[dict], None] | None] = ContextVar(
    "claw_progress_sink", default=None)


@contextmanager
def relay_progress(sink: Callable[[dict], None]) -> Iterator[None]:
    """进程内调用 MCP 采集工具时, 把进度事件实时转给前端(custom 流)"""
    token = _progress_sink.set(sink)
    try:
        yield
    finally:
        _progress_sink.reset(token)


def emit_progress(event: dict) -> None:
    """采集进度: 有订阅者(Agent 进程内调用)就实时转发, 否则忽略"""
    sink = _progress_sink.get()
    if sink is not None:
        sink(event)
