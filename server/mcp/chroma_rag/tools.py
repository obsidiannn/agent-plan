# coding: utf-8
"""RAG 知识库的 MCP 工具注册

- search_documents: 向量检索文档切片, 返回命中片段 + 来源(JSON)
- list_documents:   已录入文档清单(文件名/切片数/导入时间)
- get_document_info: 单篇文档的索引信息
- ingest_document:  把文本拆词后写入 Chroma(上传接口同一实现)

Agent 侧(server/core/chroma_rag.py)进程内调用这些工具, 再转成前端 SSE 事件。
"""
from __future__ import annotations

import asyncio
import json

from mcp.server import MCPServer

from . import service


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def search_documents(query: str, document: str = "") -> str:
        """在已录入的知识库文档中检索与问题相关的片段。

        回答任何文档内容类问题前必须先调用本工具, 依据返回片段作答。

        Args:
            query: 用于向量检索的自然语言问题
            document: 文档名(如 三体.txt), 留空表示在整个知识库中检索
        """
        payload = await asyncio.to_thread(
            service.search_answer, query, document or None)
        return json.dumps(payload, ensure_ascii=False)

    @mcp.tool()
    async def list_documents() -> str:
        """查询知识库里已录入的文档清单(文件名 / 切片数 / 字数 / 导入时间)。

        用户问"有哪些文档 / 知识库里有什么"时调用。
        """
        documents = await asyncio.to_thread(service.list_documents)
        return json.dumps({"documents": documents}, ensure_ascii=False)

    @mcp.tool()
    async def get_document_info(document: str) -> str:
        """查询某一篇文档的索引信息(切片数 / 字数 / 导入时间 / 开头预览)。

        Args:
            document: 文档名, 如 三体.txt
        """
        info = await asyncio.to_thread(service.get_document_info, document)
        if info is None:
            return json.dumps(
                {"error": f"知识库中没有名为 {document} 的文档"},
                ensure_ascii=False)
        return json.dumps(info, ensure_ascii=False)

    @mcp.tool()
    async def ingest_document(filename: str, content: str) -> str:
        """把一段文本按固定长度拆词后写入知识库(有副作用)。

        仅当用户明确要求导入/更新文档时调用; 同名文档会被整体覆盖。

        Args:
            filename: 文档名, 建议以 .txt 结尾, 如 三体.txt
            content: 文档完整文本
        """
        result = await asyncio.to_thread(
            service.ingest_text, filename, content)
        return json.dumps(result, ensure_ascii=False)
