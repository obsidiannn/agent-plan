# coding: utf-8
"""RAG 文档问答 Agent(路由 /api/agent/chroma 使用)

知识库能力(检索 / 清单 / 拆词导入)已注册为 MCP 能力:
- 工具: server/mcp/chroma_rag/tools.py
  (search_documents / list_documents / get_document_info / ingest_document)
- 资源: server/mcp/chroma_rag/resources.py(rag://documents)

本模块只保留 Agent 适配层: 由模型决定调哪个工具, 进程内调用 MCP 工具后
把结果转成前端 SSE 事件(sources 等), 对话记忆落 PostgreSQL, 由 thread_id 区分会话。

上下文切换: 前端选中某篇文档时传 document, 工具会自动把检索范围限定在该文档;
thread_id 也带上文档名, 即使前端漏传新的 conversation_id, 不同文档的对话也不会串。
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator

from langchain.agents import create_agent
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessageChunk
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

import server.config  # noqa: F401  加载 server/.env
from server.core.chroma_base import (  # noqa: F401  旧模块从这里导入, 保持向后兼容
    CHROMA_HOST,
    CHROMA_PORT,
    ChineseOnnxEmbeddings,
    build_embeddings,
    configure_proxy,
)
from server.db.agent_checkpoint import checkpointer
from server.mcp.chroma_rag import service

# checkpoint metadata 里的来源标签
AGENT_NAME = "ragChat"

SYSTEM_PROMPT = (
    "你是知识库文档问答助手, 资料来自用户上传并拆词入库的 Chroma 向量库。\n"
    "可用工具:\n"
    "- search_documents: 在知识库中检索与问题相关的文档片段\n"
    "- list_documents: 查看知识库里有哪些文档\n"
    "- document_info: 查看某篇文档的索引信息(切片数 / 导入时间等)\n\n"
    "规则:\n"
    "1. 涉及文档内容的问题, 必须先调用 search_documents 检索, 不得凭记忆编造。\n"
    "2. 只能依据工具返回的资料作答, 资料里没有的信息要明确说不知道。\n"
    "3. 回答时注明引用的文档名与段落序号, 方便用户核对。\n"
    "4. 当前选中的文档由系统自动限定检索范围, 无需在提问里重复文档名。\n"
    "5. 用户问\"有哪些文档 / 知识库里有什么\"时, 调用 list_documents。"
)


@dataclass
class RagContext:
    """随请求传入的运行时上下文: 前端侧边栏当前选中的文档名"""
    document: str | None = None


def _ctx_document(runtime: ToolRuntime[RagContext]) -> str | None:
    """当前请求选中的文档; 工具未显式传参时作为默认检索范围"""
    context = getattr(runtime, "context", None)
    return getattr(context, "document", None) if context else None


def _forward(runtime: ToolRuntime[RagContext], event: dict) -> None:
    """把一条已序列化的事件体经 custom 流推给前端(非流式调用时 writer 为空操作)"""
    writer = getattr(runtime, "stream_writer", None)
    if writer is not None:
        writer(event)


def _mcp():
    """延迟导入 MCP server: mcp.demo 会反向依赖 claw.service -> core.chroma_rag,
    模块顶层导入会形成循环, 首次调用时再取。"""
    from server.mcp.demo import mcp as rag_mcp
    return rag_mcp


async def _call_tool(name: str, arguments: dict) -> str:
    """进程内调用已注册的 MCP 工具, 返回文本结果

    /agent/chroma 目前与旧版一样不强制登录, 进程内调用不做权限校验;
    外部通过 HTTP 访问 MCP 时仍由 MCPPermissionMiddleware 按 mcp:rag:* 拦截。
    """
    try:
        result = await _mcp().call_tool(name, arguments)
    except Exception as exc:  # 参数校验失败 / 工具内部报错都交回模型
        return f"工具 {name} 调用失败: {exc}"
    return "\n".join(
        block.text for block in (getattr(result, "content", None) or [])
        if getattr(block, "text", "")
    )


@tool
async def search_documents(query: str, runtime: ToolRuntime[RagContext]) -> str:
    """在已录入的知识库文档中检索与问题相关的片段。

    返回命中的片段(带文档名与段落序号), 必须依据返回内容作答。

    Args:
        query: 用于向量检索的自然语言问题
    """
    text = await _call_tool("search_documents", {
        "query": query,
        "document": _ctx_document(runtime) or "",
    })
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text

    # 命中来源推给前端标注引用; 未命中时清空上一轮的来源
    _forward(runtime, {
        "event": "sources",
        "data": json.dumps({
            "document": payload.get("document", ""),
            "sources": payload.get("sources", []),
        }, ensure_ascii=False),
    })
    return payload.get("text", text)


@tool
async def list_documents(runtime: ToolRuntime[RagContext]) -> str:
    """查询知识库里已录入的文档清单(文件名 / 切片数 / 字数 / 导入时间)。

    用户问"有哪些文档 / 知识库里有什么"时调用。
    """
    return await _call_tool("list_documents", {})


@tool
async def document_info(runtime: ToolRuntime[RagContext], document: str = "") -> str:
    """查询某一篇文档的索引信息(切片数 / 字数 / 导入时间 / 开头预览)。

    Args:
        document: 文档名, 如 三体.txt; 留空表示当前选中的文档
    """
    return await _call_tool("get_document_info", {
        "document": document or _ctx_document(runtime) or "",
    })


model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
    max_tokens=1024,
    timeout=30,
)

agent = create_agent(
    model=model,
    tools=[search_documents, list_documents, document_info],
    system_prompt=SYSTEM_PROMPT,
    context_schema=RagContext,
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
                  document: str | None = None) -> AsyncIterator[dict]:
    """驱动 tool-calling Agent, 产出 SSE 事件体 {"event": 事件名, "data": JSON 字符串}

    - custom 流: 工具内推的 sources 事件, 原样透传
    - messages 流: 模型增量文本, 统一包成 on_chat_model_stream

    document 为侧边栏选中的文档名; 不传表示在整个知识库范围内问答。
    """
    # 文档名并入 thread_id: 切换文档天然开新会话, 不会复用上一篇的对话记忆
    thread_id = f"{conversation_id}@{document}" if document else conversation_id
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {"agent": AGENT_NAME},
        # "recursion_limit": 5,
    }
    async for mode, chunk in agent.astream(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
        context=RagContext(document=document),
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
                "data": json.dumps({"node": "chroma-rag", "content": text},
                                   ensure_ascii=False),
            }


# ---- 供 REST 路由调用的知识库操作(拆词导入 / 文档清单) ----

async def ingest_document(filename: str, content: str) -> dict:
    """txt 上传入口: 拆词并写入 Chroma(与 MCP ingest_document 同一实现)"""
    return await asyncio.to_thread(service.ingest_text, filename, content)


async def list_all_documents() -> list[dict]:
    """侧边栏文档清单"""
    return await asyncio.to_thread(service.list_documents)


async def delete_document(filename: str) -> dict:
    """删除整篇文档(按 source 清理全部切片)"""
    return await asyncio.to_thread(service.delete_document, filename)
