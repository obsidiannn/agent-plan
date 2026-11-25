import { z } from "zod";
import { prisma } from "@/lib/db";
import { ApiError } from "@/lib/errors";
import { errorResponse, ok, readJson } from "@/lib/api";
import { setSessionCookie, verifyPassword } from "@/lib/auth";
import {
  checkLoginLimit,
  clearLoginFailures,
  loginKey,
  recordLoginFailure,
} from "@/lib/rate-limit";

const schema = z.object({
  username: z.string().trim().min(1),
  password: z.string().min(1),
});

export async function POST(request: Request) {
  try {
    const body = schema.parse(await readJson(request));
    const key = loginKey(request, body.username);
    const limit = checkLoginLimit(key);
    if (!limit.allowed) {
      throw new ApiError(
        "TOO_MANY_REQUESTS",
        `登录尝试过于频繁，请 ${limit.retryAfter} 秒后再试`,
        429,
      );
    }
    const user = await prisma.user.findUnique({
      where: { username: body.username },
    });
    if (!user || !(await verifyPassword(body.password, user.passwordHash))) {
      recordLoginFailure(key);
      throw new ApiError("UNAUTHORIZED", "用户名或密码错误", 401);
    }
    if (user.status !== "ACTIVE") {
      throw new ApiError("FORBIDDEN", "账号已被禁用", 403);
    }
    clearLoginFailures(key);
    const sessionUser = {
      id: user.id,
      username: user.username,
      nickname: user.nickname,
      role: user.role,
      status: user.status,
    };
    await setSessionCookie(sessionUser);
    return ok({ user: sessionUser });
  } catch (error) {
    return errorResponse(error);
  }
}
