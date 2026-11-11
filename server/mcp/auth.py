# coding: utf-8
"""MCP 能力鉴权: 复用 REST 那套 JWT + RBAC

权限码与 page:/api: 并列, 统一存 sys_permission:
    mcp:<域>:<能力>          调用工具, 如 mcp:claw:search_posts
    mcp:<域>:res:<authority> 读资源, authority 取 URI 的 // 到第一个 / 之间
    mcp:<域>:prompt:<name>   取提示词

两个入口都要过这里:
- HTTP(streamable http) 由 MCPPermissionMiddleware 在 ServerMiddleware 层拦
- Agent 进程内调 claw_mcp.call_tool 不经过 middleware, 由 require_tool_permission 拦
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from mcp.server.context import ServerRequestContext
from mcp.shared.exceptions import MCPError

from server.core.auth import (
    AUTH_COOKIE,
    ApiError,
    SessionUser,
    has_permission,
    verify_token,
)

# JSON-RPC 层没有 401, 统一用 INVALID_REQUEST 带明确 message。
# 不用 -32001: SDK 把它当请求超时, 客户端会误判。
UNAUTHORIZED = -32600

# 能力名 -> 所属域, 没登记的走 unknown 域, 默认无人拥有该权限(fail closed)
TOOL_DOMAIN = {
    "search_posts": "claw",
    "get_data_info": "claw",
    "crawl_guba": "claw",
    "add_note": "notes",
}

PROMPT_DOMAIN = {
    "summarize_note": "notes",
}

GUARDED_METHODS = {"tools/call", "tools/list", "resources/read", "prompts/get"}


def mcp_perm_code(domain: str, capability: str) -> str:
    return f"mcp:{domain}:{capability}"


def tool_perm_code(name: str) -> str:
    return mcp_perm_code(TOOL_DOMAIN.get(name, "unknown"), name)


def resource_perm_code(uri: str) -> str:
    parts = urlsplit(uri)
    return mcp_perm_code(parts.scheme or "unknown",
                         f"res:{parts.netloc or 'root'}")


def prompt_perm_code(name: str) -> str:
    return mcp_perm_code(PROMPT_DOMAIN.get(name, "unknown"), f"prompt:{name}")


def permission_of(method: str, params: dict[str, Any]) -> str | None:
    """把一次 MCP 请求映射成权限码, 映射不出来返回 None"""
    if method == "tools/call":
        return tool_perm_code(str(params.get("name") or ""))
    if method == "resources/read":
        return resource_perm_code(str(params.get("uri") or ""))
    if method == "prompts/get":
        return prompt_perm_code(str(params.get("name") or ""))
    return None


def session_of(request: Any) -> SessionUser | None:
    """从 HTTP 请求里认身份: Bearer 优先(外部 MCP 客户端), 其次登录 cookie"""
    if request is None:  # stdio 传输没有请求头
        return None
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return verify_token(header[7:].strip())
    return verify_token(request.cookies.get(AUTH_COOKIE))


class MCPPermissionMiddleware:
    """MCP 层闸门: 先认身份, 再按能力名查权限码

    只拦工具/资源/提示词, initialize 等握手放行; 否则客户端还没连上就报错,
    排查时看不出是鉴权问题。
    """

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next):
        if ctx.method not in GUARDED_METHODS:
            return await call_next(ctx)

        session = session_of(ctx.request)
        if session is None:
            raise MCPError(UNAUTHORIZED, "未登录或登录已过期")

        # 能力发现也要收敛: 没权限的工具直接不返回。
        # 注意 middleware 拿到的已是 wire 形态的 dict, 不是 ListToolsResult 模型
        if ctx.method == "tools/list":
            result = await call_next(ctx)
            if isinstance(result, dict):
                result["tools"] = [
                    t for t in result.get("tools") or []
                    if has_permission(session, tool_perm_code(t.get("name", "")))
                ]
            return result

        code = permission_of(ctx.method, dict(ctx.params or {}))
        if code and not has_permission(session, code):
            raise MCPError(UNAUTHORIZED, f"无权限: {code}",
                           data={"code": code})
        return await call_next(ctx)


def require_tool_permission(user: SessionUser | None, name: str) -> None:
    """进程内调工具时的鉴权, 与 HTTP 路径保持同一套权限码"""
    code = tool_perm_code(name)
    if not has_permission(user, code):
        raise ApiError(403, {"error": "forbidden",
                             "message": "无权限调用该工具", "code": code})
