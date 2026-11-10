# coding: utf-8
"""股吧领域 MCP 能力(工具 + claw:// 资源)"""
from __future__ import annotations

from mcp.server import MCPServer

from . import resources, tools


def register(mcp: MCPServer) -> None:
    tools.register(mcp)
    resources.register(mcp)
