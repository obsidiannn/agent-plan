# coding: utf-8
"""LangGraph 论坛数据采集工作流(对应 doc/langchain/graph.md 方案)

三要素:
    State   贯穿全图的共享数据(TypedDict), 节点返回增量更新, 由 LangGraph 合并
    Node    单一职责的工作单元, 这里均为普通 Python 函数(采集/清洗/分类/存储)
    Edge    静态边按固定顺序流转; 条件边 validate 动态选择 通过->END / 不通过->fetch

流程:
    plan(采集计划) -> fetch(反爬采集) -> clean(清洗去重) -> classify(主题/关联)
    -> emotion(情绪向量) -> embed(语义向量化) -> store(向量库+元数据)
    -> validate(质检) --通过--> END
                    \--不通过且未超 MAX_RETRY--> fetch(重试)

    uv run python demo/langraph/graph.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: F401,E402  加载 demo/.env

MAX_RETRY = 3
EMOTION_DIMS = ("positive", "negative", "neutral", "angry", "happy")


class PostItem(TypedDict):
    url: str
    raw_html: str
    content: str
    topic: str
    related: list[str]
    emotion: dict[str, float]
    embedding: list[float]
    stored: bool


class State(TypedDict):
    plan: list[str]           # 待采集 URL 队列
    retry: int                # 当前重试次数
    items: list[PostItem]     # 采集到的条目
    ok: bool                  # 质检是否通过
    reason: str               # 质检不通过原因


def plan_node(state: State) -> dict:
    """根据目标论坛/主题/分类体系生成采集计划"""
    urls = [
        "https://forum.example.com/topic/ai/1",
        "https://forum.example.com/topic/ai/2",
        "https://forum.example.com/topic/quant/3",
    ]
    print(f"[plan] 生成采集计划, 共 {len(urls)} 个 URL")
    return {"plan": urls, "retry": 0, "items": []}


def fetch_node(state: State) -> dict:
    """调用反爬采集器, 获取原始 HTML/API 响应(实际接 requests/playwright + 代理轮换)"""
    retry = state.get("retry", 0) + 1
    plan = state.get("plan", [])
    print(f"[fetch] 采集 {len(plan)} 个 URL (第 {retry}/{MAX_RETRY} 次)")
    items: list[PostItem] = []
    for url in plan:
        items.append(PostItem(
            url=url,
            raw_html=f"<html>raw content of {url}</html>",
            content="",
            topic="",
            related=[],
            emotion={},
            embedding=[],
            stored=False,
        ))
    return {"items": items, "retry": retry}


def clean_node(state: State) -> dict:
    """数据清洗: boilerplate 去除、去重、发言边界还原"""
    seen: set[int] = set()
    cleaned: list[PostItem] = []
    for item in state["items"]:
        text = (item["raw_html"]
                .replace("<html>", "").replace("</html>", "").strip())
        key = hash(text)
        if key in seen:
            continue
        seen.add(key)
        item["content"] = text
        cleaned.append(item)
    print(f"[clean] 清洗去重后剩余 {len(cleaned)} 条")
    return {"items": cleaned}


def classify_node(state: State) -> dict:
    """主题层级/关联关系维护(实际可用 LLM 分类; 这里按 URL 路径推断)"""
    topics = {it["url"].split("/")[-2] for it in state["items"]}
    for item in state["items"]:
        topic = item["url"].split("/")[-2]
        item["topic"] = topic
        item["related"] = sorted(topics - {topic})
    print(f"[classify] 主题分类完成: {sorted(topics)}")
    return {"items": state["items"]}


def emotion_node(state: State) -> dict:
    """细粒度多维情绪向量提取(实际接 LLM 情感分析; 这里用随机值演示)"""
    for item in state["items"]:
        item["emotion"] = {d: round(random.random(), 3) for d in EMOTION_DIMS}
    print(f"[emotion] 情绪向量提取完成, 维度 {EMOTION_DIMS}")
    return {"items": state["items"]}


def embed_node(state: State) -> dict:
    """语义向量化(实际接 ChineseOnnxEmbeddings / langchain-chroma)"""
    for item in state["items"]:
        item["embedding"] = [round(random.random(), 4) for _ in range(8)]
    print(f"[embed] 语义向量化完成")
    return {"items": state["items"]}


def store_node(state: State) -> dict:
    """写入向量库 + 元数据落库(实际接 Chroma + PostgreSQL)"""
    for item in state["items"]:
        item["stored"] = True
    print(f"[store] 写入向量库 {len(state['items'])} 条 + 元数据落库")
    return {"items": state["items"]}


def validate_node(state: State) -> dict:
    """质检: 条目非空、均已存储、内容非空则通过"""
    items = state.get("items", [])
    ok = bool(items) and all(it["stored"] and it["content"] for it in items)
    reason = "" if ok else "存在未存储或空内容的条目"
    print(f"[validate] 质检{'通过' if ok else '不通过'}: {reason or '—'}")
    return {"ok": ok, "reason": reason}


def route_after_validate(state: State) -> str:
    """条件边: 通过 -> END; 不通过且未超 MAX_RETRY -> fetch; 否则 -> END"""
    if state.get("ok"):
        return END
    if state.get("retry", 0) >= MAX_RETRY:
        print(f"[route] 达到最大重试次数 {MAX_RETRY}, 终止")
        return END
    print("[route] 质检未通过, 回到 fetch 重试")
    return "fetch"


def build_graph():
    graph = StateGraph(State)
    graph.add_node("plan", plan_node)
    graph.add_node("fetch", fetch_node)
    graph.add_node("clean", clean_node)
    graph.add_node("classify", classify_node)
    graph.add_node("emotion", emotion_node)
    graph.add_node("embed", embed_node)
    graph.add_node("store", store_node)
    graph.add_node("validate", validate_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "fetch")
    graph.add_edge("fetch", "clean")
    graph.add_edge("clean", "classify")
    graph.add_edge("classify", "emotion")
    graph.add_edge("emotion", "embed")
    graph.add_edge("embed", "store")
    graph.add_edge("store", "validate")
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {END: END, "fetch": "fetch"},
    )
    return graph.compile()


def main() -> None:
    app = build_graph()
    final = app.invoke({})
    print("\n=== 最终状态 ===")
    print(f"条目数: {len(final['items'])}, 质检: {final['ok']}, "
          f"重试: {final['retry']}, 原因: {final['reason'] or '—'}")


if __name__ == "__main__":
    main()
