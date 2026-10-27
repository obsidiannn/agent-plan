
# coding: utf-8
"""命令行流式聊天机器人(基于 langchain create_agent)
    uv run python demo/langchain/agent.py
"""
import asyncio
import os
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: F401,E402  加载 demo/.env

SYSTEM_PROMPT = "你是一个乐于助人的中文 AI 助手, 回答简洁准确。"

model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
    max_tokens=8192,
)

agent = create_agent(
    model=model,
    tools=[],
    system_prompt=SYSTEM_PROMPT,
)

RUN_CONFIG = {
    "run_name": "cli-chat-agent",
    "tags": ["cli", "deepseek-flash"],
    "metadata": {"thread_id": "cli-session"},
}

messages: list = []


async def stream_reply(user_input: str) -> None:
    """追加用户输入, 流式打印模型输出, 并把结果写回历史"""
    messages.append(HumanMessage(content=user_input))
    print("AI: ", end="", flush=True)
    reply = ""
    async for chunk, _metadata in agent.astream(
        {"messages": messages}, stream_mode="messages", config=RUN_CONFIG
    ):
        text = chunk.content
        if isinstance(text, str) and text:
            reply += text
            print(text, end="", flush=True)
    messages.append(AIMessage(content=reply))


async def main() -> None:
    print("exit/quit 退出, /clear 清空历史")
    while True:
        try:
            user_input = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        if user_input == "/clear":
            messages.clear()
            print("已清空会话历史")
            continue
        try:
            await stream_reply(user_input)
        except Exception as exc:  # noqa: BLE001
            print(f"请求出错: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
