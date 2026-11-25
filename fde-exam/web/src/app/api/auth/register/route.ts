import { z } from "zod";
import { prisma } from "@/lib/db";
import { ApiError } from "@/lib/errors";
import { errorResponse, ok, readJson } from "@/lib/api";
import { hashPassword, setSessionCookie } from "@/lib/auth";

const schema = z.object({
  username: z
    .string()
    .trim()
    .min(3, "用户名至少 3 个字符")
    .max(32, "用户名最多 32 个字符"),
  password: z.string().min(8, "密码至少 8 位").max(128),
  nickname: z.string().trim().max(32).optional(),
});

export async function POST(request: Request) {
  try {
    const body = schema.parse(await readJson(request));
    const existing = await prisma.user.findUnique({
      where: { username: body.username },
    });
    if (existing) {
      throw new ApiError("CONFLICT", "用户名已存在", 409);
    }
    const user = await prisma.user.create({
      data: {
        username: body.username,
        passwordHash: await hashPassword(body.password),
        nickname: body.nickname || body.username,
      },
      select: {
        id: true,
        username: true,
        nickname: true,
        role: true,
        status: true,
      },
    });
    await setSessionCookie(user);
    return ok({ user }, 201);
  } catch (error) {
    return errorResponse(error);
  }
}
