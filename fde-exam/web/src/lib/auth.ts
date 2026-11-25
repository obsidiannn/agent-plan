import { cookies } from "next/headers";
import { SignJWT, jwtVerify } from "jose";
import bcrypt from "bcryptjs";
import { authConfig } from "@/lib/config";
import { prisma } from "@/lib/db";
import { ApiError } from "@/lib/errors";

export type SessionUser = {
  id: string;
  username: string;
  nickname: string | null;
  role: string;
  status: string;
};

const secret = new TextEncoder().encode(authConfig.secret);

export async function hashPassword(password: string) {
  return bcrypt.hash(password, 11);
}

export async function verifyPassword(password: string, hash: string) {
  return bcrypt.compare(password, hash);
}

export async function createSessionToken(user: SessionUser) {
  return new SignJWT({ role: user.role, username: user.username })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(user.id)
    .setIssuedAt()
    .setExpirationTime(`${authConfig.tokenTtlDays}d`)
    .sign(secret);
}

export async function readSessionToken(token: string) {
  const { payload } = await jwtVerify(token, secret, { algorithms: ["HS256"] });
  if (!payload.sub) throw new Error("invalid token");
  return payload;
}

export async function setSessionCookie(user: SessionUser) {
  const token = await createSessionToken(user);
  const store = await cookies();
  store.set(authConfig.cookieName, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: authConfig.tokenTtlDays * 24 * 60 * 60,
  });
}

export async function clearSessionCookie() {
  const store = await cookies();
  store.set(authConfig.cookieName, "", { path: "/", maxAge: 0 });
}

export async function getSessionUser(): Promise<SessionUser | null> {
  const store = await cookies();
  const token = store.get(authConfig.cookieName)?.value;
  if (!token) return null;
  try {
    const payload = await readSessionToken(token);
    const user = await prisma.user.findUnique({
      where: { id: String(payload.sub) },
      select: {
        id: true,
        username: true,
        nickname: true,
        role: true,
        status: true,
      },
    });
    if (!user || user.status !== "ACTIVE") return null;
    return user;
  } catch {
    return null;
  }
}

export async function requireSessionUser(): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) throw new ApiError("UNAUTHORIZED", "请先登录", 401);
  return user;
}

export async function requireAdmin(): Promise<SessionUser> {
  const user = await requireSessionUser();
  if (user.role !== "ADMIN") {
    throw new ApiError("FORBIDDEN", "需要管理员权限", 403);
  }
  return user;
}
