from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
from server.schemas import requests

from server.core import langchain as agent_core  # langchain 版 agent 实例
from server.core import chroma_rag as chroma_core  # RAG 版 agent(Chroma 检索)
from server.core import claw_chat as claw_chat_core  # 股吧舆情对话(Chroma 检索 + 立场统计)
# 股吧能力的实现层(MCP 工具/资源共用), 供参数清单与立场分布查询
from server.mcp.claw import service as claw_service
# 人工审批工作流(检查点落 PostgreSQL)
from server.core import langgraph_agent as graph_core
from server.core.auth import SessionUser
from server.core.deps import require_auth
import uuid

router = APIRouter(
    prefix="/api", tags=["agent"], )


@router.post("/agent/chroma")
async def chroma_stream(request: requests.AnalyzeRequest):
    """RAG 问答(Chroma 检索 + LLM 流式作答), 以 SSE 流式返回。

    事件协议与 /agent/chatline 一致, 前端可直接复用:
    - conversation: 首个事件, 回传后端会话 ID(前端未传时)
    - on_chat_model_stream: 增量文本, data.content 为本次新增片段
    - error: 生成失败时的错误信息
    """
    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex}"

    async def event_generator():
        yield {"event": "conversation", "data": json.dumps({"conversation_id": conversation_id})}
        try:
            async for text in chroma_core.astream_answer(conversation_id, request.prompt):
                yield {
                    "event": "on_chat_model_stream",
                    "data": json.dumps({"node": "chroma-rag", "content": text}),
                }
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@router.post("/agent/chatline")
async def analyze_stream(request: requests.AnalyzeRequest):
    # 需 import uuid
    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex}"

    async def event_generator():
        # 可选: 回传会话 ID(前端也自己生成了一份, 不传也能用)
        yield {"event": "conversation", "data": json.dumps({"conversation_id": conversation_id})}
        try:
            async for event in agent_core.agent.astream_events(
                {"messages": [{"role": "user", "content": request.prompt}]},
                config={"configurable": {"thread_id": conversation_id}},
                version="v2",
            ):
                event_type = event["event"]
                if event_type in ("on_chat_model_stream", "on_tool_start", "on_tool_end"):
                    yield {
                        "event": event_type,
                        "data": json.dumps({
                            "node": event.get("name"),
                            "content": event["data"].get("chunk", {}).content
                            if event_type == "on_chat_model_stream" else None,
                        }),
                    }
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@router.post("/agent/graphChat")
async def graph_start(request: requests.AnalyzeRequest):
    """提交审批请求: 图跑到 approval 节点会 interrupt 挂起。

    返回 { conversation_id, status, pending, messages }:
    - status = interrupted 时 pending 为待审批内容, 前端据此弹出审批按钮
    - 恢复执行请用同一个 conversation_id 调 /agent/graph/resume
    """
    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex}"
    return await graph_core.start(conversation_id, request.prompt)


@router.post("/agent/graph/resume")
async def graph_resume(request: requests.GraphDecisionRequest):
    """人工审批后恢复执行: decision = approve 放行 / reject 拒绝。

    恢复后可能再次挂起(返回 interrupted), 也可能跑完(返回 finished), 由前端按 status 判断。
    """
    return await graph_core.resume(request.conversation_id, request.decision)


@router.get("/agent/graph/sessions")
async def graph_sessions():
    """历史会话列表(按最近更新倒序), 供前端左侧列表展示"""
    return {"sessions": await graph_core.list_sessions()}


@router.get("/agent/graph/history")
async def graph_history(conversation_id: str):
    """按 conversation_id 读取某个历史会话的完整消息与挂起状态"""
    return await graph_core.history(conversation_id)


@router.post("/agent/clawChat")
async def claw_chat_stream(request: requests.ClawChatRequest,
                           session: SessionUser = Depends(require_auth)):
    """股吧舆情问答: 检索已入库帖子 + 立场统计, 以 SSE 流式返回。

    claw_param 可把问答限定在某个采集参数(如股票代码)的帖子上, 不传表示全库。
    事件协议:
    - conversation: 首个事件, 回传后端会话 ID
    - stats: 立场分布(积极/消极/中性)与 total, 前端右侧面板使用
    - sources: 本轮命中的帖子(标题/作者/时间/立场), 供来源核对
    - on_chat_model_stream: 增量文本, data.content 为本次新增片段
    - error: 生成失败或该参数下向量库为空时的提示
    """
    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex}"

    async def event_generator():
        yield {"event": "conversation", "data": json.dumps({"conversation_id": conversation_id})}
        try:
            async for event in claw_chat_core.astream(
                    conversation_id, request.prompt, request.claw_param, session):
                yield event
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@router.get("/agent/claw/params")
async def claw_params(session: SessionUser = Depends(require_auth)):
    """可选采集参数(claw_task_detail.claw_param)及已入库条数, 供前端按票切换"""
    return await asyncio.to_thread(claw_service.list_params)


@router.get("/agent/claw/overview")
async def claw_overview(claw_param: str | None = None,
                        session: SessionUser = Depends(require_auth)):
    """立场分布, 供前端右侧面板首次加载; 传 claw_param 则只统计该参数"""
    return await asyncio.to_thread(claw_service.stance_overview, claw_param)
