# coding: utf-8
"""鉴权服务: 用户查询、角色权限聚合、登录时间更新

对应 k-training 的 src/api/service/auth.service.ts
"""
from datetime import datetime

from sqlalchemy.orm import joinedload

from server.core.logs import logger
from server.db.stocking_engine import SessionLocal
from server.db.stocking_models import (
    SysPermission,
    SysRole,
    SysRolePermission,
    SysUser,
    SysUserRole,
)


def find_login_user_by_username(username: str):
    """按用户名查询用户, 聚合启用角色的权限码"""
    session = SessionLocal()
    try:
        user = (
            session.query(SysUser)
            .options(
                joinedload(SysUser.user_roles)
                .joinedload(SysUserRole.role)
                .joinedload(SysRole.role_permissions)
                .joinedload(SysRolePermission.perm)
            )
            .filter(SysUser.username == username)
            .first()
        )
        if not user:
            return None
        
        logger.info(f"Found user: {user.username}, {user.user_roles}")
        roles = []
        perms = set()
        for ur in user.user_roles:
            if ur.role.status != 1:
                continue
            roles.append(ur.role.role_code)
            for rp in ur.role.role_permissions:
                if rp.perm.status == 1:
                    perms.add(rp.perm.perm_code)

        return {
            "userId": str(user.id),
            "username": user.username,
            "nickname": user.nickname,
            "roles": roles,
            "perms": list(perms),
            "password": user.password,
            "status": user.status,
        }
    finally:
        SessionLocal.remove()


def update_last_login(user_id: str) -> None:
    session = SessionLocal()
    try:
        user = session.query(SysUser).filter(SysUser.id == int(user_id)).first()
        if user:
            user.last_login_at = datetime.now()
            session.commit()
    finally:
        SessionLocal.remove()
