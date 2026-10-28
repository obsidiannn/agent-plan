# coding: utf-8
""" 库 RBAC 模型: 用户 / 角色 / 权限

表: sys_user, sys_role, sys_user_role, sys_permission, sys_role_permission
"""
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

from typing import Any, Optional
import decimal

from sqlalchemy import (
    DateTime,
    BigInteger, Column, DECIMAL, Float, Index, Integer, String, Enum as SQLEnum,
)
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy import BigInteger, Boolean, DECIMAL, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.mysql import VARCHAR, ENUM
from sqlalchemy import LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from datetime import datetime

Base = declarative_base()


class SysUser(Base):
    __tablename__ = "sys_user"

    id = Column(BigInteger, primary_key=True)
    username = Column(String(64), unique=True)
    password = Column(String(255))
    nickname = Column(String(64))
    email = Column(String(128))
    phone = Column(String(32))
    avatar = Column(String(512))
    status = Column(Integer, default=1)  # 1 启用 / 0 禁用
    last_login_at = Column(DateTime)
    create_time = Column(DateTime)
    update_time = Column(DateTime)

    user_roles = relationship("SysUserRole", back_populates="user")


class SysRole(Base):
    __tablename__ = "sys_role"

    id = Column(BigInteger, primary_key=True)
    role_code = Column(String(64), unique=True)
    role_name = Column(String(64))
    description = Column(String(255))
    status = Column(Integer, default=1)
    create_time = Column(DateTime)
    update_time = Column(DateTime)

    user_roles = relationship("SysUserRole", back_populates="role")
    role_permissions = relationship("SysRolePermission", back_populates="role")


class SysUserRole(Base):
    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="unq_sys_user_role"),
    )

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("sys_user.id"))
    role_id = Column(BigInteger, ForeignKey("sys_role.id"))

    user = relationship("SysUser", back_populates="user_roles")
    role = relationship("SysRole", back_populates="user_roles")


class SysPermission(Base):
    __tablename__ = "sys_permission"

    id = Column(BigInteger, primary_key=True)
    perm_code = Column(String(160), unique=True)
    perm_name = Column(String(128))
    perm_type = Column(String(16))  # page | api
    parent_id = Column(BigInteger, default=0)
    path = Column(String(255))
    method = Column(String(16))
    sort = Column(Integer, default=0)
    status = Column(Integer, default=1)
    create_time = Column(DateTime)
    update_time = Column(DateTime)

    role_permissions = relationship("SysRolePermission", back_populates="perm")


class SysRolePermission(Base):
    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "perm_id", name="unq_sys_role_permission"),
    )

    id = Column(BigInteger, primary_key=True)
    role_id = Column(BigInteger, ForeignKey("sys_role.id"))
    perm_id = Column(BigInteger, ForeignKey("sys_permission.id"))

    role = relationship("SysRole", back_populates="role_permissions")
    perm = relationship("SysPermission", back_populates="role_permissions")



class AgentCheckpoint(Base):
    """LangGraph 会话检查点: 每个超级步一行, 对应一个 thread_id

    checkpoint_data 存的是序列化后的检查点(已剔除 channel_values),
    channel_values 按通道拆到 agent_checkpoint_blob
    """
    __tablename__ = 'agent_checkpoint'

    thread_id: Mapped[str] = mapped_column(VARCHAR(128), primary_key=True, comment='会话 ID(thread_id)')
    checkpoint_ns: Mapped[str] = mapped_column(VARCHAR(255), primary_key=True, default='', comment='检查点命名空间')
    checkpoint_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True, comment='检查点 ID(uuid6, 单调递增)')
    parent_checkpoint_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), comment='父检查点 ID')
    serde_type: Mapped[str] = mapped_column(VARCHAR(32), comment='序列化类型')
    checkpoint_data: Mapped[bytes] = mapped_column(LargeBinary, comment='检查点数据')
    metadata_type: Mapped[str] = mapped_column(VARCHAR(32), comment='元数据序列化类型')
    metadata_data: Mapped[bytes] = mapped_column(LargeBinary, comment='元数据(来源/步数/父节点等)')
    create_time: Mapped[Optional[Any]] = mapped_column(DateTime, default=datetime.now)


class AgentCheckpointBlob(Base):
    """检查点通道值: 一个检查点的某个通道在某个版本下的值"""
    __tablename__ = 'agent_checkpoint_blob'

    thread_id: Mapped[str] = mapped_column(VARCHAR(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(VARCHAR(255), primary_key=True, default='')
    channel: Mapped[str] = mapped_column(VARCHAR(255), primary_key=True, comment='通道名, 如 messages')
    channel_version: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True, comment='通道版本')
    serde_type: Mapped[str] = mapped_column(VARCHAR(32), comment='序列化类型, empty 表示该通道本次无值')
    blob_data: Mapped[bytes] = mapped_column(LargeBinary, comment='通道值数据')
    create_time: Mapped[Optional[Any]] = mapped_column(DateTime, default=datetime.now)


class AgentCheckpointWrite(Base):
    """检查点待写入项: 单个任务(节点)在某个超级步对通道的写入"""
    __tablename__ = 'agent_checkpoint_write'

    thread_id: Mapped[str] = mapped_column(VARCHAR(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(VARCHAR(255), primary_key=True, default='')
    checkpoint_id: Mapped[str] = mapped_column(VARCHAR(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(VARCHAR(128), primary_key=True, comment='任务 ID')
    write_idx: Mapped[int] = mapped_column(Integer, primary_key=True, comment='写入序号, 特殊通道为负')
    channel: Mapped[str] = mapped_column(VARCHAR(255), comment='通道名')
    serde_type: Mapped[str] = mapped_column(VARCHAR(32), comment='序列化类型')
    blob_data: Mapped[bytes] = mapped_column(LargeBinary, comment='写入值数据')
    task_path: Mapped[Optional[str]] = mapped_column(VARCHAR(512), comment='任务路径, 用于还原写入顺序')
    create_time: Mapped[Optional[Any]] = mapped_column(DateTime, default=datetime.now)

