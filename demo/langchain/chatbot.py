# coding: utf-8

import os
import sys
from pathlib import Path

from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)
from langchain_core.messages import HumanMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: F401,E402  加载 demo/.env, 供下面读 OPENAI_* 环境变量

SESSION_ID = "cli-session"
store: dict[str, BaseChatMessageHistory] = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]


model = ChatOpenAI(
    model="deepseek-flash",
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
)

with_message_history = RunnableWithMessageHistory(model, get_session_history)


def main() -> None:
    run_config = {"configurable": {"session_id": SESSION_ID}}
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
            store.pop(SESSION_ID, None)
            continue
        try:
            reply = with_message_history.invoke(
                [HumanMessage(content=user_input)], config=run_config
            )
        except Exception as exc:
            continue
        print(f"AI: {reply.content}")


if __name__ == "__main__":
    main()
