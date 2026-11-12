# coding: utf-8
"""请求体 Pydantic 模型"""
from typing import List, Optional

from pydantic import BaseModel, Field
from typing import Optional, Literal


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


class AnalyzeRequest(BaseModel):
    # ---- 会话与追踪 ----
    request_id: Optional[str] = Field(
        None, description="本次请求唯一 ID，原样回传在 SSE 事件里，便于前端对账")
    conversation_id: Optional[str] = Field(
        None, description="多轮会话 ID；首次不传，后端生成后在首个事件里返回。映射到 LangGraph thread_id")

    # ---- 核心三元组 ----
    prompt: str = Field(..., description="用户额外的问题描述")


class GraphDecisionRequest(BaseModel):
    """LangGraph 人工审批结果，用于恢复被 interrupt 挂起的工作流"""
    request_id: Optional[str] = Field(None, description="本次请求唯一 ID")
    conversation_id: str = Field(
        ..., description="待审批会话 ID，即 /agent/graph/start 返回的 conversation_id，映射到 thread_id")
    decision: Literal["approve",
                      "reject"] = Field(..., description="人工审批决定：approve 放行 / reject 拒绝")


class ClawChatRequest(AnalyzeRequest):
    """股吧舆情问答请求，在通用会话字段外增加采集参数过滤"""
    claw_param: Optional[str] = Field(
        None, description="按 claw_task_detail.claw_param 过滤(如股票代码 002526)；不传表示全库")


class RagChatRequest(AnalyzeRequest):
    """RAG 知识库问答请求，在通用会话字段外增加选中文档"""
    document: Optional[str] = Field(
        None, description="侧边栏选中的文档名(如 三体.txt)；不传表示在整个知识库中检索")
