# coding: utf-8
"""股吧领域的 MCP 工具注册

三个能力与对话 Agent 原来的一一对应:
- search_posts:  MMR 检索帖子 -> 返回立场分布 + 来源 + 资料正文(JSON)
- get_data_info: 读 Chroma 元数据汇总, 数字真实
- crawl_guba:    驱动 claw_graph 采集并写库(有副作用)

Agent 侧(server/core/claw_chat.py)进程内调用这些工具, 再转成前端 SSE 事件。
"""
from __future__ import annotations

import asyncio
import json

from mcp.server import MCPServer

from server.core import claw_crawl

from . import service


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def search_posts(query: str, claw_param: str = "") -> str:
        """检索已入库的股吧帖子, 用于回答帖子内容 / 市场情绪 / 用户倾向类问题。

        Args:
            query: 用于向量检索的自然语言问题
            claw_param: 6 位股票代码, 如 002526; 留空表示全库
        """
        payload = await asyncio.to_thread(
            service.search_answer, query, claw_param or None)
        return json.dumps(payload, ensure_ascii=False)

    @mcp.tool()
    async def get_data_info(claw_param: str = "") -> str:
        """查询已采集数据的统计信息(总条数 / 覆盖日期 / 立场分布 / 最近采集时间)。

        用户询问"有多少条 / 有哪些票 / 采集了多少 / 数据概览"时调用, 数字直接来自向量库元数据。

        Args:
            claw_param: 6 位股票代码, 如 002526; 留空表示全库
        """
        return await asyncio.to_thread(service.data_answer, claw_param or None)

    @mcp.tool()
    async def crawl_guba(claw_param: str, date: str = "") -> str:
        """采集(拉取)指定股票代码的股吧帖子并写入向量库。

        仅当用户明确要求采集时调用; 进程内调用时会实时推送各节点进度。

        Args:
            claw_param: 6 位股票代码, 如 002526
            date: 可选, 8 位日期 YYYYMMDD, 只采集该日期发布的帖子; 留空表示不限日期
        """
        if not claw_param:
            return ("没识别到股票代码, 请让用户说得具体些, "
                    "例如: 帮我拉取 002526 20261105 的数据")

        summary = None
        async for event in claw_crawl.astream_crawl(claw_param, date or None):
            service.emit_progress(event)
            if event["event"] == "crawl_result":
                summary = json.loads(event["data"])

        if not summary:
            return f"{claw_param} 采集结束, 但没有拿到结果。"
        return summary.get("message") or f"{claw_param} 采集结束。"
