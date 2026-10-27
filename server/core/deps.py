# coding: utf-8

from typing import Optional

from fastapi import Request

from server.core.auth import (
    AUTH_COOKIE,
    ApiError,
    SessionUser,
    api_perm_code,
    has_permission,
    verify_token,
)


def is_https_request(request: Request) -> bool:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    protocol = forwarded or request.url.scheme
    return protocol == "https"


def get_session_user(request: Request) -> Optional[SessionUser]:
    token = request.cookies.get(AUTH_COOKIE)
    return verify_token(token)


def require_auth(request: Request) -> SessionUser:
    session = get_session_user(request)
    if not session:
        raise ApiError(401, {"error": "unauthorized", "message": "未登录或登录已过期"})
    code = api_perm_code(request.method, request.url.path)
    if not has_permission(session, code):
        raise ApiError(403, {"error": "forbidden", "message": "无权限访问", "code": code})
    return session
