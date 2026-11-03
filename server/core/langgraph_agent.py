# coding: utf-8
"""LangGraph 人工审批工作流(路由 /api/agent/graph* 使用)

流程: request(接收请求) -> approval(interrupt 挂起等人工审批) -> execute(执行)

与命令行 demo(demo/langraph/graph2.py)的区别:
- 检查点落 PostgreSQL(server/db/agent_checkpoint), 服务重启后仍能恢复审批
- 审批拆成两次请求: 前端先调 /agent/graphChat 触发挂起, 人工点按钮后再调
  /agent/graph/resume 带上 Command(resume=决定) 恢复执行

interrupt 不会阻塞进程: 它让本次调用在审批节点处返回并把状态存进检查点,
后续用同一个 thread_id 恢复即可。是否处于挂起状态看 snapshot.next 是否非空。

会话检查点与 langchain agent 共用同一批表, 因此每次调用都在 metadata 里打上
agent=graphChat 标签, 历史列表按该标签过滤, 避免混入其它 agent 的会话。
"""

from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt

from server.db.agent_checkpoint import checkpointer

# checkpoint metadata 里的来源标签, 也是历史列表的过滤条件
AGENT_NAME = "graphChat"
# 列表里标题的截断长度
TITLE_MAX = 24


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


def _config(thread_id: str) -> dict:
    """统一的运行配置: thread_id 区分会话, metadata 打来源标签供历史列表过滤"""
    return {
        "configurable": {"thread_id": thread_id},
        "metadata": {"agent": AGENT_NAME},
    }


def _title(messages: list[dict]) -> str:
    """取首条用户消息作为会话标题"""
    for m in messages:
        if m["role"] == "user" and m["content"]:
            text = m["content"].strip().replace("\n", " ")
            return text[:TITLE_MAX] + ("..." if len(text) > TITLE_MAX else "")
    return "(空会话)"


def _is_interrupted(tup) -> bool:
    """挂起时 LangGraph 会把 __interrupt__ 通道写成待写入项"""
    return any(write[1] == "__interrupt__" for write in tup.pending_writes)


async def start(thread_id: str, prompt: str) -> dict:
    """提交请求, 图会在 approval 节点的 interrupt 处挂起"""
    config = _config(thread_id)
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]}, config=config)
    return _to_result(thread_id, await graph.aget_state(config))


async def resume(thread_id: str, decision: str) -> dict:
    """带上人工决定恢复执行(approve 放行 / 其他视为拒绝)"""
    config = _config(thread_id)
    await graph.ainvoke(Command(resume=decision), config=config)
    return _to_result(thread_id, await graph.aget_state(config))


async def history(thread_id: str) -> dict:
    """读取单个会话的完整消息与挂起状态, 用于前端点击历史会话时加载"""
    return _to_result(thread_id, await graph.aget_state(_config(thread_id)))


async def list_sessions() -> list[dict]:
    """列出本工作流的历史会话(按最近更新倒序), 只返回摘要, 不含完整消息"""
    # checkpoint_id 是 uuid6, 字典序即时间序; 全局倒序遍历时每个 thread 首次出现即最新一条
    tuples = [t async for t in checkpointer.alist(None, filter={"agent": AGENT_NAME})]
    sessions: list[dict] = []
    seen: set[str] = set()
    for tup in tuples:
        thread_id: str = tup.config["configurable"]["thread_id"]
        if thread_id in seen:
            continue
        seen.add(thread_id)
        messages = _serialize_messages(
            tup.checkpoint.get("channel_values", {}).get("messages", []))
        sessions.append({
            "conversation_id": thread_id,
            "title": _title(messages),
            "updated_at": tup.checkpoint.get("ts"),
            "message_count": len(messages),
            "status": "interrupted" if _is_interrupted(tup) else "finished",
        })
    return sessions
