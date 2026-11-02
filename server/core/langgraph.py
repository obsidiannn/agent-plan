# coding: utf-8
"""LangGraph 人工审批工作流(路由 /api/agent/graph/* 使用)

流程: request(接收请求) -> approval(interrupt 挂起等人工审批) -> execute(执行)

与命令行 demo(demo/langraph/graph2.py)的区别:
- 检查点落 PostgreSQL(server/db/agent_checkpoint), 服务重启后仍能恢复审批
- 审批拆成两次请求: 前端先调 /agent/graph/start 触发挂起, 人工点按钮后再调
  /agent/graph/resume 带上 Command(resume=决定) 恢复执行

interrupt 不会阻塞进程: 它让本次调用在审批节点处返回并把状态存进检查点,
后续用同一个 thread_id 恢复即可。是否处于挂起状态看 snapshot.next 是否非空。
"""
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

from server.db.agent_checkpoint import checkpointer


def request_node(state: MessagesState) -> dict:
    """接收用户请求(入参已是 HumanMessage, 无需改动状态)"""
    return {}


def approval_node(state: MessagesState) -> dict:
    """审批节点: interrupt 挂起当前线程, 等 resume 传回人工决定"""
    last_msg = state["messages"][-1].content

    human_decision = interrupt({
        "question": "是否批准执行以下操作？",
        "action": last_msg,
    })

    if human_decision == "approve":
        return {"messages": [{"role": "assistant", "content": f"操作已批准：{last_msg}"}]}
    return {"messages": [{"role": "assistant", "content": "操作已被拒绝。"}]}


def execute_node(state: MessagesState) -> dict:
    """执行节点(真实场景替换为具体动作)"""
    return {"messages": [{"role": "assistant", "content": "任务执行完成！"}]}


def build_graph():
    builder = StateGraph(MessagesState)
    builder.add_node("request", request_node)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", execute_node)
    builder.add_edge(START, "request")
    builder.add_edge("request", "approval")
    builder.add_edge("approval", "execute")
    builder.add_edge("execute", END)
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()


def _serialize_messages(messages) -> list[dict]:
    """只暴露对话双方可见的消息, 前端按 role 渲染"""
    return [
        {"role": "user" if m.type == "human" else "assistant", "content": m.content}
        for m in messages
        if m.type in ("human", "ai")
    ]


def _to_result(thread_id: str, snapshot) -> dict:
    """把 StateSnapshot 转成前端可用的结构; next 非空说明停在审批节点等人工决定"""
    pending = None
    if snapshot.next:
        for task in snapshot.tasks:
            if task.interrupts:
                pending = task.interrupts[0].value
                break
    return {
        "conversation_id": thread_id,
        "status": "interrupted" if snapshot.next else "finished",
        "pending": pending,
        "messages": _serialize_messages(snapshot.values.get("messages", [])),
    }


async def start(thread_id: str, prompt: str) -> dict:
    """提交请求, 图会在 approval 节点的 interrupt 处挂起"""
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]}, config=config)
    return _to_result(thread_id, await graph.aget_state(config))


async def resume(thread_id: str, decision: str) -> dict:
    """带上人工决定恢复执行(approve 放行 / 其他视为拒绝)"""
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(Command(resume=decision), config=config)
    return _to_result(thread_id, await graph.aget_state(config))
