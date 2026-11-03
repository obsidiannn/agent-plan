from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKeyConstraint, Index, Integer, LargeBinary, PrimaryKeyConstraint, SmallInteger, String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import datetime

class Base(DeclarativeBase):
    pass


class AgentCheckpoint(Base):
    __tablename__ = 'agent_checkpoint'
    __table_args__ = (
        PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id', name='agent_checkpoint_pkey'),
    )

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True, comment='会话 ID(thread_id)')
    checkpoint_ns: Mapped[str] = mapped_column(String(255), primary_key=True, comment='检查点命名空间')
    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='检查点 ID(uuid6, 单调递增)')
    serde_type: Mapped[str] = mapped_column(String(32), comment='序列化类型')
    checkpoint_data: Mapped[bytes] = mapped_column(LargeBinary, comment='检查点数据')
    metadata_type: Mapped[str] = mapped_column(String(32), comment='元数据序列化类型')
    metadata_data: Mapped[bytes] = mapped_column(LargeBinary, comment='元数据(来源/步数/父节点等)')
    parent_checkpoint_id: Mapped[Optional[str]] = mapped_column(String(64), comment='父检查点 ID')
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)


class AgentCheckpointBlob(Base):
    __tablename__ = 'agent_checkpoint_blob'
    __table_args__ = (
        PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'channel', 'channel_version', name='agent_checkpoint_blob_pkey'),
    )

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(255), primary_key=True)
    channel: Mapped[str] = mapped_column(String(255), primary_key=True, comment='通道名, 如 messages')
    channel_version: Mapped[str] = mapped_column(String(64), primary_key=True, comment='通道版本')
    serde_type: Mapped[str] = mapped_column(String(32), comment='序列化类型, empty 表示该通道本次无值')
    blob_data: Mapped[bytes] = mapped_column(LargeBinary, comment='通道值数据')
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)


class AgentCheckpointWrite(Base):
    __tablename__ = 'agent_checkpoint_write'
    __table_args__ = (
        PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id', 'task_id', 'write_idx', name='agent_checkpoint_write_pkey'),
    )

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(255), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(128), primary_key=True, comment='任务 ID')
    write_idx: Mapped[int] = mapped_column(Integer, primary_key=True, comment='写入序号, 特殊通道为负')
    channel: Mapped[str] = mapped_column(String(255), comment='通道名')
    serde_type: Mapped[str] = mapped_column(String(32), comment='序列化类型')
    blob_data: Mapped[bytes] = mapped_column(LargeBinary, comment='写入值数据')
    task_path: Mapped[Optional[str]] = mapped_column(String(512), comment='任务路径, 用于还原写入顺序')
    create_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)


class ClasTaskDetail(Base):
    __tablename__ = 'clas_task_detail'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='clas_task_detail_pkey'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[Optional[int]] = mapped_column(Integer)
    claw_param: Mapped[Optional[str]] = mapped_column(String(255))


class ClawTask(Base):
    __tablename__ = 'claw_task'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='claw_task_pkey'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_code: Mapped[Optional[str]] = mapped_column(String(255))
    task_name: Mapped[Optional[str]] = mapped_column(String(255))
    active: Mapped[Optional[bool]] = mapped_column(Boolean)


class SysPermission(Base):
    __tablename__ = 'sys_permission'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='sys_permission_pkey'),
        Index('idx_sys_permission_parent_id', 'parent_id'),
        Index('idx_sys_permission_type', 'perm_type'),
        Index('unq_sys_permission_code', 'perm_code', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    perm_code: Mapped[str] = mapped_column(String(160))
    perm_name: Mapped[str] = mapped_column(String(128))
    perm_type: Mapped[str] = mapped_column(String(16))
    parent_id: Mapped[int] = mapped_column(BigInteger)
    sort: Mapped[int] = mapped_column(Integer)
    status: Mapped[int] = mapped_column(SmallInteger)
    create_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=6))
    update_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=6))
    path: Mapped[Optional[str]] = mapped_column(String(255))
    method: Mapped[Optional[str]] = mapped_column(String(16))

    sys_role_permission: Mapped[List['SysRolePermission']] = relationship('SysRolePermission', back_populates='perm')


class SysRole(Base):
    __tablename__ = 'sys_role'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='sys_role_pkey'),
        Index('unq_sys_role_code', 'role_code', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_code: Mapped[str] = mapped_column(String(64))
    role_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[int] = mapped_column(SmallInteger)
    create_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=6))
    update_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=6))
    description: Mapped[Optional[str]] = mapped_column(String(255))

    sys_role_permission: Mapped[List['SysRolePermission']] = relationship('SysRolePermission', back_populates='role')
    sys_user_role: Mapped[List['SysUserRole']] = relationship('SysUserRole', back_populates='role')


class SysUser(Base):
    __tablename__ = 'sys_user'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='sys_user_pkey'),
        Index('unq_sys_user_username', 'username', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    password: Mapped[str] = mapped_column(String(255))
    status: Mapped[int] = mapped_column(SmallInteger)
    create_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=6))
    update_time: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=6))
    nickname: Mapped[Optional[str]] = mapped_column(String(64))
    email: Mapped[Optional[str]] = mapped_column(String(128))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    avatar: Mapped[Optional[str]] = mapped_column(String(512))
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP(precision=6))

    sys_user_role: Mapped[List['SysUserRole']] = relationship('SysUserRole', back_populates='user')


class SysRolePermission(Base):
    __tablename__ = 'sys_role_permission'
    __table_args__ = (
        ForeignKeyConstraint(['perm_id'], ['sys_permission.id'], name='sys_role_permission_perm_id_fkey'),
        ForeignKeyConstraint(['role_id'], ['sys_role.id'], name='sys_role_permission_role_id_fkey'),
        PrimaryKeyConstraint('id', name='sys_role_permission_pkey'),
        Index('idx_sys_role_permission_perm_id', 'perm_id'),
        Index('unq_sys_role_permission', 'role_id', 'perm_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger)
    perm_id: Mapped[int] = mapped_column(BigInteger)

    perm: Mapped['SysPermission'] = relationship('SysPermission', back_populates='sys_role_permission')
    role: Mapped['SysRole'] = relationship('SysRole', back_populates='sys_role_permission')


class SysUserRole(Base):
    __tablename__ = 'sys_user_role'
    __table_args__ = (
        ForeignKeyConstraint(['role_id'], ['sys_role.id'], name='sys_user_role_role_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['sys_user.id'], name='sys_user_role_user_id_fkey'),
        PrimaryKeyConstraint('id', name='sys_user_role_pkey'),
        Index('idx_sys_user_role_role_id', 'role_id'),
        Index('unq_sys_user_role', 'user_id', 'role_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    role_id: Mapped[int] = mapped_column(BigInteger)

    role: Mapped['SysRole'] = relationship('SysRole', back_populates='sys_user_role')
    user: Mapped['SysUser'] = relationship('SysUser', back_populates='sys_user_role')
