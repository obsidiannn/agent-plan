from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import json
from server.schemas import requests

from server.core import langchain as agent_core  # langchain 版 agent 实例
from server.core.deps import require_auth
import uuid

router = APIRouter(
    prefix="/api", tags=["agent"], dependencies=[Depends(require_auth)])

# @router.post("/agent/chatline")
# async def analyze_stream(request: requests.AnalyzeRequest):
#     async def event_generator():
#         try:
#             async for event in deepagent.agent.astream_events(
#                 {"messages": [{"role": "user", "content": request.prompt}]},
#                 version="v3",
#             ):
#                 # 按需过滤事件类型，不要一股脑全推
#                 event_type = event["event"]
#                 if event_type in ("on_chat_model_stream", "on_tool_start", "on_tool_end"):
#                     yield {
#                         "event": event_type,
#                         "data": json.dumps({
#                             "node": event.get("name"),
#                             "content": event["data"].get("chunk", {}).content
#                             if event_type == "on_chat_model_stream" else None,
#                         }),
#                     }
#         except Exception as e:
#             yield {"event": "error", "data": json.dumps({"message": str(e)})}


#     return EventSourceResponse(event_generator())



@router.post("/agent/chatline")
async def analyze_stream(request: requests.AnalyzeRequest):
    conversation_id = request.conversation_id or f"conv_{uuid.uuid4().hex}"   # 需 import uuid

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

