# coding: utf-8
"""RAG 知识库领域 MCP 能力(工具 + rag:// 资源)"""
from __future__ import annotations

from mcp.server import MCPServer

from . import resources, tools


def register(mcp: MCPServer) -> None:
    tools.register(mcp)
    resources.register(mcp)
