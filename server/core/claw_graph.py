# coding: utf-8
"""LangGraph 驱动的股吧数据采集工作流

复用 claw.py 的采集能力, 三要素:
    State   贯穿全图的共享数据(TypedDict), 节点返回增量更新, 由 LangGraph 合并
    Node    单一职责的工作单元
            plan   -> 从 claw_task / clas_task_detail 读取采集目标(claw.load_targets)
            fetch  -> 运行 Scrapy 爬虫采集条目(claw.collect)
            stance -> 用 FinBERT 判定用户立场(看多/看空/中性)
            embed  -> 对(标题+立场+时间)做中文语义向量化
            store  -> 写入 Chroma 向量库并落元数据
            其余为清洗/分类/质检
    Edge    静态边按固定顺序流转; 条件边 validate 动态选择 通过->END / 不通过->fetch

流程:
    plan(采集计划) -> fetch(Scrapy采集) -> clean(清洗去重) -> classify(主题/关联)
    -> stance(FinBERT立场) -> embed(语义向量化) -> store(Chroma落库)
    -> validate(质检) --通过--> END
                    \\--不通过且未超 MAX_RETRY--> fetch(重试)

    uv run python -m server.core.claw_graph
"""
from __future__ import annotations

import os
import threading
from collections import Counter
from typing import TypedDict

import chromadb
from langgraph import graph

from server.core import claw, logs
from server.core.chroma_rag import (
    CHROMA_HOST,
    CHROMA_PORT,
    ChineseOnnxEmbeddings,
    configure_proxy,
)
from server.core.stance import get_stance

MAX_RETRY = 3
# 股吧帖子的向量集合, 可用环境变量覆盖
COLLECTION_NAME = os.environ.get("CLAW_COLLECTION", "guba_posts")


class PostItem(TypedDict, total=False):
    """采集条目: 前半部分来自爬虫, 后半部分由后续节点补全"""
    task_code: str
    task_name: str
    claw_param: str
    title: str
    url: str
    author: str
    read_count: str
    comment_count: str
    publish_time: str
    content: str
    topic: str
    related: list[str]
    stance: str                    # 用户立场: 看多/看空/中性(FinBERT 判定)
    sentiment: dict[str, float]    # FinBERT 三分类概率
    doc_text: str                  # 实际进向量库的文本(标题+立场+时间)
    embedding: list[float]
    stored: bool


class State(TypedDict):
    targets: list[dict]        # 待采集目标(库中任务 + 明细参数)
    retry: int                 # 当前重试次数
    items: list[PostItem]      # 采集到的条目
    ok: bool                   # 质检是否通过
    reason: str                # 质检不通过原因


def plan_node(state: State) -> dict:
    """从 claw_task / clas_task_detail 读取激活任务, 生成采集计划"""
    targets = claw.load_targets()
    logs.logger.info(f"[plan] 生成采集计划, 共 {len(targets)} 个目标")
    return {"targets": targets, "retry": 0, "items": []}


def fetch_node(state: State) -> dict:
    """调用 claw 的 Scrapy 采集器获取条目"""
    retry = state.get("retry", 0) + 1
    targets = state.get("targets", [])
    logs.logger.info(
        f"[fetch] 采集 {len(targets)} 个目标 (第 {retry}/{MAX_RETRY} 次)")
    items = claw.collect(targets)
    logs.logger.info(f"[fetch] 采集到 {len(items)} 条")
    return {"items": items, "retry": retry}


def clean_node(state: State) -> dict:
    """数据清洗: 丢弃无标题条目, 按 URL 去重"""
    seen: set[str] = set()
    cleaned: list[PostItem] = []
    for item in state.get("items", []):
        url = item.get("url")
        if not item.get("title") or not url or url in seen:
            continue
        seen.add(url)
        # 详情页正文优先, 抓不到时才退回标题, 避免把标题又塞回正文
        if not item.get("content"):
            item["content"] = item["title"]
        cleaned.append(item)
    logs.logger.info(f"[clean] 清洗去重后剩余 {len(cleaned)} 条")
    return {"items": cleaned}


def classify_node(state: State) -> dict:
    """主题层级/关联关系维护(按任务编码归类, 实际可用 LLM 分类)"""
    items = state["items"]
    topics = {it.get("task_code") or "" for it in items}
    for item in items:
        topic = item.get("task_code") or ""
        item["topic"] = topic
        item["related"] = sorted(topics - {topic})
    logs.logger.info(f"[classify] 主题分类完成: {sorted(topics)}")
    return {"items": items}


def stance_node(state: State) -> dict:
    """用 FinBERT 判定用户立场(看多/看空/中性)并给出三分类概率"""
    items = state["items"]
    if items:
        results = get_stance().classify(
            [it.get("title", "") for it in items])
        for item, res in zip(items, results):
            item["stance"] = res["stance"]
            item["sentiment"] = res["sentiment"]
    dist = Counter(it.get("stance") for it in items)
    logs.logger.info(f"[stance] 立场判定完成: {dict(dist)}")
    return {"items": items}


_embeddings: ChineseOnnxEmbeddings | None = None
_embed_lock = threading.Lock()


def get_embeddings() -> ChineseOnnxEmbeddings:
    """懒加载中文 ONNX Embedding 模型(bge-small-zh-v1.5, 首次会下载)"""
    global _embeddings
    if _embeddings is None:
        with _embed_lock:
            if _embeddings is None:
                configure_proxy()
                _embeddings = ChineseOnnxEmbeddings()
    return _embeddings


def build_doc_text(item: PostItem) -> str:
    """拼出待向量化的文本: 标题 + 用户立场 + 发布时间"""
    return (f"{item.get('title', '')} "
            f"立场:{item.get('stance', '')} "
            f"时间:{item.get('publish_time', '')}")


def embed_node(state: State) -> dict:
    """语义向量化: 对(标题+立场+时间)文本做中文 Embedding"""
    items = state["items"]
    if items:
        texts = [build_doc_text(it) for it in items]
        vectors = get_embeddings().embed_documents(texts)
        for item, text, vector in zip(items, texts, vectors):
            item["doc_text"] = text
            item["embedding"] = vector
    dim = len(items[0]["embedding"]) if items else 0
    logs.logger.info(f"[embed] 语义向量化完成, 共 {len(items)} 条, 维度 {dim}")
    return {"items": items}


def _get_collection():
    """连接 Chroma Server 并取(或建)集合"""
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def _metadata(item: PostItem) -> dict:
    """写入 Chroma 的元数据(值只允许 str/int/float/bool)"""
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "author": item.get("author", ""),
        "publish_time": item.get("publish_time", ""),
        "stance": item.get("stance", ""),
        "task_code": item.get("task_code", ""),
        "claw_param": item.get("claw_param", ""),
        "read_count": item.get("read_count", ""),
        "comment_count": item.get("comment_count", ""),
    }


def store_node(state: State) -> dict:
    """把向量与元数据写入 Chroma(以 url 为 id, upsert 保证重试幂等)"""
    items = state["items"]
    to_store = [it for it in items if it.get("url") and it.get("embedding")]
    if to_store:
        _get_collection().upsert(
            ids=[it["url"] for it in to_store],
            documents=[it["doc_text"] for it in to_store],
            embeddings=[it["embedding"] for it in to_store],
            metadatas=[_metadata(it) for it in to_store],
        )
    stored_urls = {it["url"] for it in to_store}
    for item in items:
        item["stored"] = item.get("url") in stored_urls
    logs.logger.info(
        f"[store] 写入向量库 {len(to_store)} 条 -> {COLLECTION_NAME}")
    return {"items": items}


def validate_node(state: State) -> dict:
    """质检: 条目非空、均已存储、标题非空则通过"""
    items = state.get("items", [])
    ok = bool(items) and all(it.get("stored") and it.get("content")
                             for it in items)
    reason = "" if ok else "采集结果为空或存在未落库/空标题条目"
    logs.logger.info(f"[validate] 质检{'通过' if ok else '不通过'}: {reason or '—'}")
    return {"ok": ok, "reason": reason}


def route_after_validate(state: State) -> str:
    """条件边: 通过 -> END; 不通过且未超 MAX_RETRY -> fetch; 否则 -> END"""
    if state.get("ok"):
        return graph.END
    if state.get("retry", 0) >= MAX_RETRY:
        logs.logger.info(f"[route] 达到最大重试次数 {MAX_RETRY}, 终止")
        return graph.END
    logs.logger.info("[route] 质检未通过, 回到 fetch 重试")
    return "fetch"


def build_graph():
    gh = graph.StateGraph(State)
    gh.add_node("plan", plan_node)
    gh.add_node("fetch", fetch_node)
    gh.add_node("clean", clean_node)
    gh.add_node("classify", classify_node)
    gh.add_node("stance", stance_node)
    gh.add_node("embed", embed_node)
    gh.add_node("store", store_node)
    gh.add_node("validate", validate_node)

    gh.add_edge(graph.START, "plan")
    gh.add_edge("plan", "fetch")
    gh.add_edge("fetch", "clean")
    gh.add_edge("clean", "classify")
    gh.add_edge("classify", "stance")
    gh.add_edge("stance", "embed")
    gh.add_edge("embed", "store")
    gh.add_edge("store", "validate")
    gh.add_conditional_edges(
        "validate",
        route_after_validate,
        {graph.END: graph.END, "fetch": "fetch"},
    )
    return gh.compile()


def main() -> None:
    app = build_graph()
    final = app.invoke({})
    logs.logger.info("=== 最终状态 ===")
    logs.logger.info(
        f"条目数: {len(final['items'])}, 质检: {final['ok']}, "
        f"重试: {final['retry']}, 原因: {final['reason'] or '—'}"
    )


if __name__ == "__main__":
    main()
