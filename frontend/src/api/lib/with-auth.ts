import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE, SessionUser, apiPermCode, hasPermission, verifyToken } from "./auth";

/** 从 cookie 中读取当前登录用户(仅可用于 Route Handler / Server Component) */
export const getSession = async (): Promise<SessionUser | null> => {
    const store = await cookies();
    return await verifyToken(store.get(AUTH_COOKIE)?.value);
};

export type AuthedHandler = (
    request: NextRequest,
    ctx: any,
    session: SessionUser
) => Promise<Response> | Response;

/**
 * 接口鉴权包装器
 * - 未登录返回 401
 * - 无权限返回 403
 * - 未显式传入 permCode 时, 按 `api:{METHOD}:{pathname}` 自动推断
 */
export const withAuth = (handler: AuthedHandler, permCode?: string) => {
    return async (request: NextRequest, ctx: any): Promise<Response> => {
        const session = await getSession();
        if (!session) {
            return NextResponse.json({ error: "unauthorized", message: "未登录或登录已过期" }, { status: 401 });
        }
        const code = permCode ?? apiPermCode(request.method, request.nextUrl.pathname);
        if (!hasPermission(session, code)) {
            return NextResponse.json({ error: "forbidden", message: "无权限访问", code }, { status: 403 });
        }
        return await handler(request, ctx, session);
    };
};
