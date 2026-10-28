# coding: utf-8
"""LangGraph 会话检查点(多轮会话记忆)的 PostgreSQL 持久化

langgraph 官方只提供 SQLite / PostgreSQL 的 checkpointer, 这里按官方
BaseCheckpointSaver 协议自实现, 存储结构对齐官方版本三张表:
agent_checkpoint / agent_checkpoint_blob / agent_checkpoint_write

用法:
    from server.db.agent_checkpoint import checkpointer
    agent = create_agent(..., checkpointer=checkpointer)
    await agent.astream_events(..., config={"configurable": {"thread_id": "xxx"}})

注意: 图在 async 调用时会走 aget_tuple/aput 等异步分支, 这里用 asyncio.to_thread
包住同步实现, 避免阻塞 FastAPI 事件循环
"""
import asyncio
import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
    writes_sort_key,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from server.db.server_engine import engine
from server.db.server_models import (
    AgentCheckpoint,
    AgentCheckpointBlob,
    AgentCheckpointWrite,
)

Session = sessionmaker(bind=engine, expire_on_commit=False)


def _as_config(thread_id: str, checkpoint_ns: str,
               checkpoint_id: str | None = None) -> RunnableConfig:
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns,
    }
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


class PostgresCheckpointSaver(BaseCheckpointSaver):
    """把 checkpoints / blobs / writes 落到 PostgreSQL( 库)"""

    def _load_blobs(self, session, thread_id: str, checkpoint_ns: str,
                    versions: ChannelVersions) -> dict[str, Any]:
        """按通道版本取回该检查点的 channel_values"""
        if not versions:
            return {}
        rows = session.execute(
            select(AgentCheckpointBlob).where(
                AgentCheckpointBlob.thread_id == thread_id,
                AgentCheckpointBlob.checkpoint_ns == checkpoint_ns,
                AgentCheckpointBlob.channel.in_(list(versions.keys())),
            )
        ).scalars()
        stored = {(r.channel, str(r.channel_version)): r for r in rows}
        values: dict[str, Any] = {}
        for channel, version in versions.items():
            row = stored.get((channel, str(version)))
            if row is None or row.serde_type == "empty":
                continue
            values[channel] = self.serde.loads_typed((row.serde_type, bytes(row.blob_data)))
        return values

    def _row_to_tuple(self, session, row: AgentCheckpoint) -> CheckpointTuple:
        checkpoint: Checkpoint = self.serde.loads_typed(
            (row.serde_type, bytes(row.checkpoint_data)))
        metadata: CheckpointMetadata = self.serde.loads_typed(
            (row.metadata_type, bytes(row.metadata_data)))
        records = session.execute(
            select(AgentCheckpointWrite).where(
                AgentCheckpointWrite.thread_id == row.thread_id,
                AgentCheckpointWrite.checkpoint_ns == row.checkpoint_ns,
                AgentCheckpointWrite.checkpoint_id == row.checkpoint_id,
            )
        ).scalars().all()
        # 顺序必须与执行时一致, 否则有顺序要求的 reducer 会还原出不同的值
        records.sort(key=lambda w: writes_sort_key(w.task_path or "", w.task_id, w.write_idx))
        return CheckpointTuple(
            config=_as_config(row.thread_id, row.checkpoint_ns, row.checkpoint_id),
            checkpoint={
                **checkpoint,
                "channel_values": self._load_blobs(
                    session, row.thread_id, row.checkpoint_ns,
                    checkpoint.get("channel_versions", {})),
            },
            metadata=metadata,
            parent_config=(
                _as_config(row.thread_id, row.checkpoint_ns, row.parent_checkpoint_id)
                if row.parent_checkpoint_id else None
            ),
            pending_writes=[
                (w.task_id, w.channel, self.serde.loads_typed((w.serde_type, bytes(w.blob_data))))
                for w in records
            ],
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        stmt = select(AgentCheckpoint).where(
            AgentCheckpoint.thread_id == thread_id,
            AgentCheckpoint.checkpoint_ns == checkpoint_ns,
        )
        if checkpoint_id:
            stmt = stmt.where(AgentCheckpoint.checkpoint_id == checkpoint_id)
        else:
            # checkpoint_id 是 uuid6, 字典序即时间序
            stmt = stmt.order_by(AgentCheckpoint.checkpoint_id.desc()).limit(1)
        with Session() as session:
            row = session.execute(stmt).scalars().first()
            return self._row_to_tuple(session, row) if row is not None else None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        stmt = select(AgentCheckpoint)
        if config is not None:
            thread_id = config["configurable"]["thread_id"]
            checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
            stmt = stmt.where(
                AgentCheckpoint.thread_id == thread_id,
                AgentCheckpoint.checkpoint_ns == checkpoint_ns,
            )
        if before is not None and (before_id := get_checkpoint_id(before)):
            stmt = stmt.where(AgentCheckpoint.checkpoint_id < before_id)
        stmt = stmt.order_by(AgentCheckpoint.checkpoint_id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        with Session() as session:
            for row in session.execute(stmt).scalars().all():
                item = self._row_to_tuple(session, row)
                if filter and any(item.metadata.get(k) != v for k, v in filter.items()):
                    continue
                yield item

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        serialized = checkpoint.copy()
        values: dict[str, Any] = serialized.pop("channel_values", {}) or {}
        with Session() as session:
            for channel, version in (new_versions or {}).items():
                if channel in values:
                    serde_type, blob = self.serde.dumps_typed(values[channel])
                else:
                    serde_type, blob = "empty", b""
                session.merge(AgentCheckpointBlob(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    channel=channel,
                    channel_version=str(version),
                    serde_type=serde_type,
                    blob_data=blob,
                ))
            serde_type, blob = self.serde.dumps_typed(serialized)
            metadata_type, metadata_blob = self.serde.dumps_typed(
                get_checkpoint_metadata(config, metadata))
            session.merge(AgentCheckpoint(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint["id"],
                parent_checkpoint_id=parent_checkpoint_id,
                serde_type=serde_type,
                checkpoint_data=blob,
                metadata_type=metadata_type,
                metadata_data=metadata_blob,
            ))
            session.commit()
        return _as_config(thread_id, checkpoint_ns, checkpoint["id"])

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id: str = config["configurable"]["checkpoint_id"]
        with Session() as session:
            existing = set(session.execute(
                select(AgentCheckpointWrite.task_id, AgentCheckpointWrite.write_idx).where(
                    AgentCheckpointWrite.thread_id == thread_id,
                    AgentCheckpointWrite.checkpoint_ns == checkpoint_ns,
                    AgentCheckpointWrite.checkpoint_id == checkpoint_id,
                )
            ).all())
            for idx, (channel, value) in enumerate(writes):
                # 特殊通道(ERROR/INTERRUPT 等)序号为负, 每次都要覆盖
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                if write_idx >= 0 and (task_id, write_idx) in existing:
                    continue
                serde_type, blob = self.serde.dumps_typed(value)
                session.merge(AgentCheckpointWrite(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    task_id=task_id,
                    write_idx=write_idx,
                    channel=channel,
                    serde_type=serde_type,
                    blob_data=blob,
                    task_path=task_path,
                ))
            session.commit()

    def delete_thread(self, thread_id: str) -> None:
        with Session() as session:
            for model in (AgentCheckpoint, AgentCheckpointBlob, AgentCheckpointWrite):
                session.execute(delete(model).where(model.thread_id == thread_id))
            session.commit()

    def get_next_version(self, current: str | int | None, channel: str | None = None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        return f"{current_v + 1:032}.{random.random():016}"

    # --- 异步分支: 图在 async 调用时会走这些方法, 放到线程池执行避免阻塞事件循环 ---

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        items = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit)))
        for item in items:
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        return await asyncio.to_thread(self.delete_thread, thread_id)


def init_agent_checkpoint_tables() -> None:
    """建表(幂等): 需要时手动调用, 不在 import 期执行以免应用启动依赖数据库"""
    for model in (AgentCheckpoint, AgentCheckpointBlob, AgentCheckpointWrite):
        model.__table__.create(engine, checkfirst=True)


checkpointer = PostgresCheckpointSaver()
