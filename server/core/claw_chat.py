# coding: utf-8
"""股吧舆情对话 Agent(路由 /api/agent/clawChat 使用)

股吧能力(检索 / 统计 / 采集)已注册为 MCP 能力:
- 工具: server/mcp/claw/tools.py(search_posts / get_data_info / crawl_guba)
- 资源: server/mcp/claw/resources.py(claw://params / claw://overview)

本模块只保留 Agent 适配层: 由模型决定调哪个工具, 进程内调用 MCP 工具后
把结果转成前端 SSE 事件(stats/sources/progress/intent/crawl_result),
对话记忆落 PostgreSQL, 由 thread_id 区分会话。SSE 协议保持不变。
"""
from __future__ import annotations

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
from server.core.auth import SessionUser
from server.db.agent_checkpoint import checkpointer
from server.mcp.auth import require_tool_permission
from server.mcp.claw import service
from server.mcp.demo import mcp as claw_mcp

# checkpoint metadata 里的来源标签, 也是历史会话列表的过滤条件
AGENT_NAME = "clawChat"

SYSTEM_PROMPT = (
    "你是股吧舆情分析助手, 数据来自 claw_graph 采集入库的股吧帖子向量库。\n"
    "可用工具:\n"
    "- search_posts: 检索已入库帖子, 回答帖子内容 / 市场情绪 / 用户倾向类问题\n"
    "- get_data_info: 查询已采集数据的统计信息(条数 / 覆盖日期 / 立场分布 / 采集时间)\n"
    "- crawl_guba: 采集(拉取)指定股票代码的帖子入库, 有副作用\n\n"
    "规则:\n"
    "1. 涉及帖子内容、市场情绪、用户倾向的问题, 必须先调用 search_posts 检索, 不得凭记忆编造。\n"
    "2. 只能依据工具返回的资料作答, 资料里没有的信息要明确说不知道。\n"
    "3. 引用资料时带上来源标题。\n"
    "4. 用户问\"有多少条 / 有哪些票 / 采集情况\"等统计问题时, 调用 get_data_info。\n"
    "5. 仅当用户明确说\"拉取 / 采集 / 抓取 / 爬取\"某代码的数据时, 才调用 crawl_guba。\n"
    "6. 用户没写股票代码时, 直接按当前筛选参数作答(工具会自动套用), 不必反问, 也不必说明。"
)


@dataclass
class ClawContext:
    """随请求传入的运行时上下文: 前端当前选中的采集参数(如股票代码)与登录用户"""
    claw_param: str | None = None
    user: SessionUser | None = None


def _ctx_param(runtime: ToolRuntime[ClawContext]) -> str | None:
    """当前请求选中的采集参数(前端下拉框), 工具未显式传参时作为默认值"""
    context = getattr(runtime, "context", None)
    return getattr(context, "claw_param", None) if context else None


def _forward(runtime: ToolRuntime[ClawContext], event: dict) -> None:
    """把一条已序列化的事件体经 custom 流推给前端(非流式调用时 writer 为空操作)"""
    writer = getattr(runtime, "stream_writer", None)
    if writer is not None:
        writer(event)


def _ctx_user(runtime: ToolRuntime[ClawContext]) -> SessionUser | None:
    """当前请求的登录用户; 进程内调 MCP 工具时用它做鉴权"""
    context = getattr(runtime, "context", None)
    return getattr(context, "user", None) if context else None


async def _call_tool(name: str, arguments: dict,
                     runtime: ToolRuntime[ClawContext]) -> str:
    """进程内调用已注册的 MCP 工具, 返回文本结果

    采集进度等副作用由 MCP 工具经 service.emit_progress 实时回传,
    这里只负责把最终文本交回模型。
    进程内调用不经过 MCP 的 middleware, 所以权限在这里补一次。
    """
    require_tool_permission(_ctx_user(runtime), name)
    try:
        result = await claw_mcp.call_tool(name, arguments)
    except Exception as exc:  # 参数校验失败 / 工具内部报错都交回模型
        return f"工具 {name} 调用失败: {exc}"
    return "\n".join(
        block.text for block in (getattr(result, "content", None) or [])
        if getattr(block, "text", "")
    )


@tool
async def search_posts(query: str, runtime: ToolRuntime[ClawContext]) -> str:
    """检索已入库的股吧帖子, 用于回答帖子内容 / 市场情绪 / 用户倾向类问题。

    返回命中的帖子(带来源标注)与全库立场分布; 必须依据返回内容作答。

    Args:
        query: 用于向量检索的自然语言问题
    """
    text = await _call_tool("search_posts", {
        "query": query,
        "claw_param": _ctx_param(runtime) or "",
    }, runtime)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text

    _forward(runtime, {"event": "stats",
                       "data": json.dumps(payload["overview"], ensure_ascii=False)})
    if payload["overview"]["total"]:
        _forward(runtime, {"event": "sources",
                           "data": json.dumps({"sources": payload["sources"]},
                                              ensure_ascii=False)})
    return payload["text"]


@tool
async def get_data_info(runtime: ToolRuntime[ClawContext], claw_param: str = "") -> str:
    """查询已采集数据的统计信息(总条数 / 覆盖日期 / 立场分布 / 最近采集时间)。

    用户询问"有多少条 / 有哪些票 / 采集了多少 / 数据概览"时调用, 数字直接来自向量库元数据。

    Args:
        claw_param: 6 位股票代码, 如 002526; 留空表示当前筛选参数(全库则留空)
    """
    return await _call_tool("get_data_info", {
        "claw_param": claw_param or _ctx_param(runtime) or "",
    }, runtime)


@tool
async def crawl_guba(runtime: ToolRuntime[ClawContext],
                     claw_param: str = "", date: str = "") -> str:
    """采集(拉取)指定股票代码的股吧帖子并写入向量库。

    仅当用户明确要求采集时调用; 执行期间会实时推送各节点进度。

    Args:
        claw_param: 6 位股票代码, 如 002526; 用户没写代码时留空, 不要臆测
        date: 可选, 8 位日期 YYYYMMDD, 只采集该日期发布的帖子; 留空表示不限日期
    """
    if not claw_param:
        return "没识别到股票代码, 请让用户说得具体些, 例如: 帮我拉取 002526 20261105 的数据"
    _forward(runtime, {
        "event": "intent",
        "data": json.dumps({"action": "crawl", "claw_param": claw_param,
                            "date": date or None}, ensure_ascii=False),
    })

    # MCP 采集工具在进程内运行时, 通过订阅器把进度实时转成 SSE 事件
    with service.relay_progress(lambda event: _forward(runtime, event)):
        return await _call_tool("crawl_guba", {
            "claw_param": claw_param,
            "date": date,
        }, runtime)


model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
    max_tokens=512,
    timeout=30
)

agent = create_agent(
    model=model,
    tools=[search_posts, get_data_info, crawl_guba],
    system_prompt=SYSTEM_PROMPT,
    context_schema=ClawContext,
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
                  claw_param: str | None = None,
                  user: SessionUser | None = None) -> AsyncIterator[dict]:
    """驱动 tool-calling Agent, 产出 SSE 事件体 {"event": 事件名, "data": JSON 字符串}

    - custom 流: 工具内推的自定义事件(intent/progress/crawl_result/stats/sources), 原样透传
    - messages 流: 模型增量文本, 统一包成 on_chat_model_stream(工具调用阶段的空内容不推)

    claw_param 用于把问答限定在某个采集参数(如股票代码)的帖子上, 不传表示全库。
    user 是当前登录用户, 进程内调 MCP 工具时据此校验权限。
    """
    context = ClawContext(claw_param=claw_param, user=user)
    config = {
        "configurable": {"thread_id": conversation_id},
        "metadata": {"agent": AGENT_NAME},
        # "recursion_limit": 5,
    }
    async for mode, chunk in agent.astream(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
        context=context,
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
                "data": json.dumps({"node": "claw-chat", "content": text},
                                   ensure_ascii=False),
            }
