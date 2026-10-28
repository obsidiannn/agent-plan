# coding: utf-8
"""鉴权路由: /api/auth/login | logout | me

"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from server.core.auth import (
    AUTH_COOKIE,
    ApiError,
    SessionUser,
    sign_token,
    verify_password,
)
from server.core.deps import get_session_user, is_https_request
from server.schemas.requests import LoginRequest
from server.services.auth_service import find_login_user_by_username, update_last_login

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_MAX_AGE = 60 * 60 * 24 * 7


@router.post("/login")
def login(body: LoginRequest, request: Request):
    username = (body.username or "").strip()
    password = body.password or ""
    if not username or not password:
        raise ApiError(
            400, {"error": "invalid_param", "message": "用户名和密码不能为空"})

    user = find_login_user_by_username(username)
    print(user)
    if not user or not verify_password(password, user["password"]):
        raise ApiError(401, {"error": "bad_credential", "message": "用户名或密码错误"})
    if user["status"] != 1:
        raise ApiError(403, {"error": "disabled", "message": "账号已被禁用"})

    session = SessionUser(
        userId=user["userId"],
        username=user["username"],
        nickname=user["nickname"],
        roles=user["roles"],
        perms=user["perms"],
    )
    token = sign_token(session)

    response = JSONResponse({"data": session.to_dict()})
    response.set_cookie(
        AUTH_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=COOKIE_MAX_AGE,
        secure=is_https_request(request),
    )
    update_last_login(session.userId)
    return response


@router.post("/logout")
def logout(request: Request):
    response = JSONResponse({"data": True})
    response.set_cookie(
        AUTH_COOKIE,
        "",
        httponly=True,
        samesite="lax",
        path="/",
        max_age=0,
        secure=is_https_request(request),
    )
    return response


@router.get("/me")
def me(request: Request):
    session = get_session_user(request)
    return {"data": session.to_dict() if session else None}
