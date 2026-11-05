# coding: utf-8
"""股吧舆情对话 Agent(路由 /api/agent/clawChat 使用)

数据来源是 claw_graph 落库的股吧集合(guba_posts):
- document 存 "标题 + 立场 + 时间"(claw_graph.build_doc_text)
- metadata 存 标题/作者/时间/立场/股票 等, 供前端展示来源与倾向

这里用 LangChain 的 tool-calling Agent 取代早先的关键词意图路由: 由模型自行决定
调用哪个工具, 三种能力各封装成一个工具
- search_posts:  MMR 检索帖子 -> 结合全库立场分布作答(同时把 stats/sources 推给前端)
- get_data_info: 直接读 Chroma 元数据汇总, 不经 LLM, 保证数字真实
- crawl_guba:    驱动 claw_graph 采集并实时推流进度(有副作用, 仅用户明确要求时调用)

对话记忆落 PostgreSQL(server/db/agent_checkpoint), 由 thread_id 区分会话;
采集进度/立场/来源等自定义事件经 stream_writer 走 custom 流, 前端 SSE 协议保持不变。
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from collections import Counter
from dataclasses import dataclass
from typing import AsyncIterator

import chromadb
from langchain.agents import create_agent
from langchain.tools import ToolRuntime
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessageChunk
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

import server.config  # noqa: F401  加载 server/.env
from server.core import claw, claw_crawl
from server.core.chroma_rag import (
    CHROMA_HOST,
    CHROMA_PORT,
    ChineseOnnxEmbeddings,
    configure_proxy,
)
from server.db.agent_checkpoint import checkpointer

# 与 claw_graph 落库的集合保持一致, 可用同一环境变量覆盖
COLLECTION_NAME = os.environ.get("CLAW_COLLECTION", "guba_posts")
TOP_K = 5          # 每次检索返回的帖子数
FETCH_K = 20       # MMR 先取候选集大小, 兼顾相关性与多样性
STANCE_ORDER = ("积极", "消极", "中性")

# checkpoint metadata 里的来源标签, 也是历史会话列表的过滤条件
AGENT_NAME = "clawChat"

SYSTEM_PROMPT = (
    "你是股吧舆情分析助手, 数据来自 claw_graph 采集入库的股吧帖子向量库。\n"
    "可用工具:\n"
    "- search_posts: 检索已入库帖子, 回答帖子内容 / 市场情绪 / 用户倾向类问题\n"
    "- get_data_info: 查询已采集数据的统计信息(条数 / 覆盖日期 / 立场分布 / 采集时间)\n"
    "- crawl_guba: 采集(拉取)指定股票代码的帖子入库, 有副作用\n\n"
    "规则:\n"
    "1. 涉及帖子内容、市场情绪、用户倾向的问题, 必须先调用 search_posts 检索, 不得凭记忆编造。\n"
    "2. 只能依据工具返回的资料作答, 资料里没有的信息要明确说不知道。\n"
    "3. 引用资料时带上来源标题。\n"
    "4. 用户问\"有多少条 / 有哪些票 / 采集情况\"等统计问题时, 调用 get_data_info。\n"
    "5. 仅当用户明确说\"拉取 / 采集 / 抓取 / 爬取\"某代码的数据时, 才调用 crawl_guba。\n"
    "6. 用户没写股票代码时, 直接按当前筛选参数作答(工具会自动套用), 不必反问, 也不必说明。"
)


@dataclass
class ClawContext:
    """随请求传入的运行时上下文: 前端当前选中的采集参数(如股票代码)"""
    claw_param: str | None = None


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


def _ctx_param(runtime: ToolRuntime[ClawContext]) -> str | None:
    """当前请求选中的采集参数(前端下拉框), 工具未显式传参时作为默认值"""
    context = getattr(runtime, "context", None)
    return getattr(context, "claw_param", None) if context else None


def _forward(runtime: ToolRuntime[ClawContext], event: dict) -> None:
    """把一条已序列化的事件体经 custom 流推给前端(非流式调用时 writer 为空操作)"""
    writer = getattr(runtime, "stream_writer", None)
    if writer is not None:
        writer(event)


@tool
async def search_posts(query: str, runtime: ToolRuntime[ClawContext]) -> str:
    """检索已入库的股吧帖子, 用于回答帖子内容 / 市场情绪 / 用户倾向类问题。

    返回命中的帖子(带来源标注)与全库立场分布; 必须依据返回内容作答。

    Args:
        query: 用于向量检索的自然语言问题
    """
    claw_param = _ctx_param(runtime)
    overview = await asyncio.to_thread(stance_overview, claw_param)
    _forward(runtime, {"event": "stats",
                       "data": json.dumps(overview, ensure_ascii=False)})
    if not overview["total"]:
        if claw_param:
            return f"参数 {claw_param} 暂无已入库的帖子, 请先采集再提问。"
        return "股吧向量库暂无数据, 请先采集再提问。"

    vectorstore = await asyncio.to_thread(get_vectorstore)
    docs = await asyncio.to_thread(_retrieve, vectorstore, query, claw_param)
    _forward(runtime, {"event": "sources",
                       "data": json.dumps({"sources": _sources(docs)}, ensure_ascii=False)})
    overview_text = json.dumps(overview["stance"], ensure_ascii=False)
    return f"全库立场分布(积极/消极/中性): {overview_text}\n\n资料:\n{_format_docs(docs)}"


@tool
async def get_data_info(runtime: ToolRuntime[ClawContext], claw_param: str = "") -> str:
    """查询已采集数据的统计信息(总条数 / 覆盖日期 / 立场分布 / 最近采集时间)。

    用户询问"有多少条 / 有哪些票 / 采集了多少 / 数据概览"时调用, 数字直接来自向量库元数据。

    Args:
        claw_param: 6 位股票代码, 如 002526; 留空表示当前筛选参数(全库则留空)
    """
    return await asyncio.to_thread(data_answer, claw_param or _ctx_param(runtime))


@tool
async def crawl_guba(runtime: ToolRuntime[ClawContext],
                     claw_param: str = "", date: str = "") -> str:
    """采集(拉取)指定股票代码的股吧帖子并写入向量库。

    仅当用户明确要求采集时调用; 执行期间会实时推送各节点进度。

    Args:
        claw_param: 6 位股票代码, 如 002526; 用户没写代码时留空, 不要臆测
        date: 可选, 8 位日期 YYYYMMDD, 只采集该日期发布的帖子; 留空表示不限日期
    """
    if not claw_param:
        return "没识别到股票代码, 请让用户说得具体些, 例如: 帮我拉取 002526 20261105 的数据"
    _forward(runtime, {
        "event": "intent",
        "data": json.dumps({"action": "crawl", "claw_param": claw_param,
                            "date": date or None}, ensure_ascii=False),
    })

    summary = None
    async for event in claw_crawl.astream_crawl(claw_param, date or None):
        if event["event"] == "crawl_result":
            summary = json.loads(event["data"])
        _forward(runtime, event)

    if not summary:
        return f"{claw_param} 采集结束, 但没有拿到结果。"
    return summary.get("message") or f"{claw_param} 采集结束。"


model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
    max_tokens=1024,
)

agent = create_agent(
    model=model,
    tools=[search_posts, get_data_info, crawl_guba],
    system_prompt=SYSTEM_PROMPT,
    context_schema=ClawContext,
    # 会话记忆落 PostgreSQL, 由路由传入的 thread_id 区分会话
    checkpointer=checkpointer,
)


def _text_of(message) -> str:
    """从模型增量消息里取出纯文本(部分模型 content 是分块列表)"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict))
    return ""


async def astream(conversation_id: str, question: str,
                  claw_param: str | None = None) -> AsyncIterator[dict]:
    """驱动 tool-calling Agent, 产出 SSE 事件体 {"event": 事件名, "data": JSON 字符串}

    - custom 流: 工具内推的自定义事件(intent/progress/crawl_result/stats/sources), 原样透传
    - messages 流: 模型增量文本, 统一包成 on_chat_model_stream(工具调用阶段的空内容不推)

    claw_param 用于把问答限定在某个采集参数(如股票代码)的帖子上, 不传表示全库。
    """
    context = ClawContext(claw_param=claw_param)
    config = {
        "configurable": {"thread_id": conversation_id},
        "metadata": {"agent": AGENT_NAME},
    }
    async for mode, chunk in agent.astream(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
        context=context,
        stream_mode=["messages", "custom"],
    ):
        if mode == "custom":
            if isinstance(chunk, dict) and "event" in chunk:
                yield chunk
            continue
        message, _metadata = chunk
        if not isinstance(message, AIMessageChunk):
            continue
        text = _text_of(message)
        if text:
            yield {
                "event": "on_chat_model_stream",
                "data": json.dumps({"node": "claw-chat", "content": text},
                                   ensure_ascii=False),
            }
