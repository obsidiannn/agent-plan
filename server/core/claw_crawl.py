# coding: utf-8
"""对话触发的股吧采集

由 claw_chat 的 crawl_guba 工具调用: 确保参数已存在于 clas_task_detail
(不存在则新建), 再执行 claw_graph 工作流, 并把每个节点的进度实时推给前端。
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import AsyncIterator

from server.core import claw, claw_graph

# 工作流节点 -> 前端展示名
NODE_LABELS = {
    "plan": "生成采集计划",
    "fetch": "采集帖子(Scrapy)",
    "clean": "清洗去重",
    "classify": "主题分类",
    "stance": "立场判定",
    "embed": "语义向量化",
    "store": "写入向量库",
    "validate": "质检",
}

_APP = None


def _app():
    """图本身无检查点, 编译一次即可反复调用"""
    global _APP
    if _APP is None:
        _APP = claw_graph.build_graph()
    return _APP


def _event(name: str, payload: dict) -> dict:
    return {"event": name, "data": json.dumps(payload, ensure_ascii=False)}


def _progress(node: str, update: dict) -> dict:
    """把节点返回的增量状态压成一行进度, 不把 items 全量发给前端"""
    detail = ""
    if node == "plan":
        detail = f"{len(update.get('targets', []))} 个目标"
    elif node == "fetch":
        detail = f"第 {update.get('retry', 0)} 次, 抓到 {len(update.get('items', []))} 条"
    elif node == "validate":
        detail = "通过" if update.get(
            "ok") else f"不通过({update.get('reason', '')})"
    elif node == "store":
        items = update.get("items", [])
        detail = f"入库 {sum(1 for it in items if it.get('stored'))} 条"
    elif node == "stance":
        items = update.get("items", [])
        detail = f"{len(items)} 条, {dict(Counter(it.get('stance') for it in items))}"
    elif node == "embed":
        items = update.get("items", [])
        dim = len(items[0].get("embedding") or []) if items else 0
        detail = f"{len(items)} 条, 维度 {dim}"
    else:
        detail = f"{len(update.get('items', []))} 条"
    return {
        "node": node,
        "label": NODE_LABELS.get(node, node),
        "status": "done",
        "detail": detail,
    }


async def astream_crawl(claw_param: str, date: str | None) -> AsyncIterator[dict]:
    """建参数明细 -> 跑 claw_graph -> 逐节点推进度 -> 汇总结果

    date 为 8 位 YYYYMMDD(可空), 只入库该日期发布的帖子。
    """
    target = await asyncio.to_thread(claw.ensure_target, claw_param)
    yield _event("progress", {
        "node": "target",
        "label": "准备采集目标",
        "status": "done",
        "detail": f"{target['claw_param']} · {target['task_name']}",
    })

    summary = {
        "claw_param": claw_param,
        "date": date or "",
        "fetched": 0,
        "stored": 0,
        "ok": False,
        "reason": "",
        "retry": 0,
    }
    state = {"targets": [target], "date": date or ""}
    async for chunk in _app().astream(state, stream_mode="updates"):
        for node, update in (chunk or {}).items():
            update = update or {}
            if node == "fetch":
                summary["fetched"] = len(update.get("items", []))
                summary["retry"] = update.get("retry", 0)
            elif node == "store":
                summary["stored"] = sum(
                    1 for it in update.get("items", []) if it.get("stored"))
            elif node == "validate":
                summary["ok"] = bool(update.get("ok"))
                summary["reason"] = update.get("reason", "")
            yield _event("progress", _progress(node, update))

    if summary["ok"]:
        summary["message"] = f"已完成 {claw_param} 的采集, 入库 {summary['stored']} 条"
    elif date:
        summary["message"] = (
            f"{claw_param} 在 {date} 没有匹配的帖子(本次抓到 {summary['fetched']} 条, 均非该日期)")
    else:
        summary["message"] = f"{claw_param} 采集未通过: {summary['reason']}"
    yield _event("crawl_result", summary)
