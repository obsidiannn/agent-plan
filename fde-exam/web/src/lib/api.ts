import { NextResponse } from "next/server";
import { ZodError } from "zod";
import { ApiError } from "@/lib/errors";

export function ok<T>(data: T, status = 200) {
  return NextResponse.json({ ok: true, data }, { status });
}

export function fail(code: string, message: string, status = 400, details?: unknown) {
  return NextResponse.json(
    { ok: false, error: { code, message, details } },
    { status },
  );
}

export function errorResponse(error: unknown) {
  if (error instanceof ApiError) {
    return fail(error.code, error.message, error.status, error.details);
  }
  if (error instanceof ZodError) {
    return fail("VALIDATION_ERROR", "请求参数不合法", 400, error.issues);
  }
  const maybePrisma = error as { code?: string; meta?: unknown };
  if (maybePrisma?.code === "P2002") {
    return fail("CONFLICT", "数据已存在", 409, maybePrisma.meta);
  }
  console.error("[api] unhandled error", error);
  return fail("INTERNAL_ERROR", "服务器内部错误", 500);
}

export async function readJson<T>(request: Request): Promise<T> {
  try {
    return (await request.json()) as T;
  } catch {
    throw new ApiError("VALIDATION_ERROR", "请求体必须是合法 JSON", 400);
  }
}
