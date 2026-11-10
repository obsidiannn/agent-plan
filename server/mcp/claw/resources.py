# coding: utf-8
from __future__ import annotations

import json

from mcp.server import MCPServer

from . import service


def register(mcp: MCPServer) -> None:
    @mcp.resource("claw://params", description="可选采集参数及已入库条数")
    def params() -> str:
        """采集参数清单(claw_task_detail.claw_param)与条数"""
        return json.dumps(service.list_params(), ensure_ascii=False)

    @mcp.resource("claw://overview", description="全库立场分布")
    def overview() -> str:
        """全库帖子的积极/消极/中性分布"""
        return json.dumps(service.stance_overview(), ensure_ascii=False)

    @mcp.resource("claw://overview/{claw_param}", description="指定参数的立场分布")
    def overview_of(claw_param: str) -> str:
        """某个采集参数(如股票代码)下的立场分布"""
        return json.dumps(service.stance_overview(claw_param), ensure_ascii=False)
