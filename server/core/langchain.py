# coding: utf-8
"""LangChain 版 agent(替代 deepagents 版, 路由 /api/agent/chatline 使用)

相比 deepagents 的 create_deep_agent, 这里只注册业务需要的 5 个工具,
不带文件系统 / todo / 子 agent 等内置工具与 middleware
"""
import os
from pathlib import Path

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

import server.config  # noqa: F401  加载 .env, 供下面读 OPENAI_* 环境变量
from server.core.tools import (
    get_stock_indices,
    query_index_day,
    query_index_week,
    query_kline_day,
    query_kline_week,
)
from server.db.agent_checkpoint import checkpointer

model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
)

# 系统提示词取自项目根目录 doc/promot.md
PROMPT_FILE = Path(__file__).resolve().parents[2] / "doc" / "promot.md"

agent = create_agent(
    model=model,
    tools=[query_kline_day, query_kline_week, query_index_day, query_index_week, get_stock_indices],
    system_prompt=PROMPT_FILE.read_text(encoding="utf-8"),
    # 会话记忆落 PostgreSQL, 由路由传入的 thread_id 区分会话
    checkpointer=checkpointer,
)
