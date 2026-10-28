import type { NextRequest } from "next/server";
/** 登录态 cookie 名称 */
export const AUTH_COOKIE = "k_token";

/** JWT 有效期 */
export const AUTH_EXPIRES_IN = "7d";

/** 登录用户信息(存入 JWT 的载荷) */
export interface SessionUser {
    userId: string;
    username: string;
    nickname?: string | null;
    roles: string[];
    perms: string[];
}

/** 校验登录态: 请求后端 /api/auth/me, 成功返回用户信息, 失败返回 null */
export const verifyToken = async (token?: string | null): Promise<SessionUser | null> => {
    if (!token) {
        return null;
    }
    try {
        const base = (process.env.PYTHON_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
        const res = await fetch(`${base}/api/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
            cache: "no-store",
        });
        if (!res.ok) {
            return null;
        }
        const resp = await res.json();
        console.log('suicces', resp)
        const data = resp?.data ?? resp;
        if (!data) {
            return null;
        }
        console.log('suicces')
        return {
            userId: String(data.userId ?? ""),
            username: String(data.username ?? ""),
            nickname: (data.nickname as string | null) ?? null,
            roles: (data.roles as string[] | undefined) ?? [],
            perms: (data.perms as string[] | undefined) ?? [],
        };
    } catch {
        return null;
    }
};

/** 页面权限码, 如 page:/strategy/sword */
export const pagePermCode = (pathname: string): string => `page:${pathname}`;

/** 接口权限码, 如 api:POST:/api/data */
export const apiPermCode = (method: string, pathname: string): string =>
    `api:${method.toUpperCase()}:${pathname}`;

/** 判断登录用户是否拥有权限(支持 "*" 通配) */
export const hasPermission = (session: SessionUser | null, code: string): boolean => {
    if (!session) {
        return false;
    }
    return session.perms.includes("*") || session.perms.includes(code);
};

/**
 * 判断当前请求是否为 HTTPS
 * 兼容反向代理场景(读取 x-forwarded-proto), 避免 HTTP 部署时 cookie 的 Secure 属性被浏览器丢弃
 */
export const isHttpsRequest = (request: NextRequest): boolean => {
    const forwarded = (request.headers.get("x-forwarded-proto") ?? "").split(",")[0].trim();
    const protocol = forwarded || request.nextUrl.protocol.replace(":", "");
    return protocol === "https";
};
