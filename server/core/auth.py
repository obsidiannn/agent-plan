# coding: utf-8

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

import jwt

from server.config import JWT_SECRET, JWT_EXPIRES_DAYS

AUTH_COOKIE = "k_token"

@dataclass
class SessionUser:
    userId: str
    username: str
    nickname: Optional[str]
    roles: List[str]
    perms: List[str]

    def to_dict(self):
        return asdict(self)


class ApiError(Exception):
    """业务异常, payload 会原样作为 JSON 响应体返回"""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload


# scrypt 参数与 Node crypto.scryptSync 默认一致
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SCRYPT_MAXMEM = 32 * 1024 * 1024


def hash_password(plain: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN, maxmem=_SCRYPT_MAXMEM,
    )
    return f"scrypt${salt}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    parts = (stored or "").split("$")
    if len(parts) != 3 or parts[0] != "scrypt":
        return False
    _, salt, hash_hex = parts
    try:
        dk = hashlib.scrypt(
            plain.encode("utf-8"),
            salt=salt.encode("utf-8"),
            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN, maxmem=_SCRYPT_MAXMEM,
        )
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


def sign_token(user: SessionUser) -> str:
    now = int(time.time())
    payload = {
        "username": user.username,
        "nickname": user.nickname,
        "roles": user.roles,
        "perms": user.perms,
        "sub": user.userId,
        "iat": now,
        "exp": now + JWT_EXPIRES_DAYS * 86400,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: Optional[str]) -> Optional[SessionUser]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return SessionUser(
            userId=str(payload.get("sub", "")),
            username=str(payload.get("username", "")),
            nickname=payload.get("nickname"),
            roles=payload.get("roles") or [],
            perms=payload.get("perms") or [],
        )
    except Exception:
        return None


def page_perm_code(pathname: str) -> str:
    return f"page:{pathname}"


def api_perm_code(method: str, pathname: str) -> str:
    return f"api:{method.upper()}:{pathname}"


def has_permission(session: Optional[SessionUser], code: str) -> bool:
    if not session:
        return False
    return "*" in session.perms or code in session.perms
