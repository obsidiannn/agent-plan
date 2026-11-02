# coding: utf-8
"""LangChain 版 agent(路由 /api/agent/chatline 使用)

通用对话 agent, 暂不注册工具; 相比 deepagents 的 create_deep_agent,
不带文件系统 / todo / 子 agent 等内置工具与 middleware
"""
import os

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic.v1 import tools

import server.config  # noqa: F401  加载 .env, 供下面读 OPENAI_* 环境变量
from server.db.agent_checkpoint import checkpointer

model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
)

SYSTEM_PROMPT = "你是一个乐于助人的中文 AI 助手, 回答简洁准确。"


@tool
def query_age(username: str) -> str:
    """查询年龄"""
    return f"你 {username} 28 岁"


@tool
def query_mobile(username: str) -> str:
    """查询手机号"""
    return f"你 {username} 手机号是 13800000000"


agent = create_agent(
    model=model,
    tools=[query_age, query_mobile],
    system_prompt=SYSTEM_PROMPT,
    # 会话记忆落 PostgreSQL, 由路由传入的 thread_id 区分会话
    checkpointer=checkpointer,
)
