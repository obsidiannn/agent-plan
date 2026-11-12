# coding: utf-8
from __future__ import annotations

import json

from mcp.server import MCPServer

from . import service


def register(mcp: MCPServer) -> None:
    @mcp.resource("rag://documents", description="已录入的知识库文档清单")
    def documents() -> str:
        """文档清单: 文件名 / 切片数 / 字数 / 导入时间"""
        return json.dumps(
            {"documents": service.list_documents()}, ensure_ascii=False)

    @mcp.resource("rag://documents/{document}", description="单篇文档的索引信息")
    def document_info(document: str) -> str:
        """某篇文档的切片数 / 字数 / 导入时间 / 开头预览"""
        info = service.get_document_info(document)
        if info is None:
            return json.dumps(
                {"error": f"知识库中没有名为 {document} 的文档"},
                ensure_ascii=False)
        return json.dumps(info, ensure_ascii=False)
