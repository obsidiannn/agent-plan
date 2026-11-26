import { requireAdmin } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { prisma } from "@/lib/db";

export async function GET(request: Request) {
  try {
    await requireAdmin();
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || "";
    const type = url.searchParams.get("type") || "";
    const style = url.searchParams.get("style") || "";
    const chapterId = url.searchParams.get("chapterId") || "";
    const q = url.searchParams.get("q") || "";
    const page = Math.max(1, Number.parseInt(url.searchParams.get("page") || "1", 10));
    const pageSize = Math.min(
      100,
      Math.max(1, Number.parseInt(url.searchParams.get("pageSize") || "20", 10)),
    );

    const where = {
      ...(status ? { status } : {}),
      ...(type ? { type } : {}),
      ...(style ? { style } : {}),
      ...(chapterId ? { chapterId } : {}),
      ...(q ? { stem: { contains: q } } : {}),
    };

    const [total, items, chapters] = await Promise.all([
      prisma.question.count({ where }),
      prisma.question.findMany({
        where,
        orderBy: { createdAt: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
        include: {
          chapter: { select: { title: true, orderNo: true } },
          generationRun: {
            select: { id: true, model: true, promptVersion: true },
          },
        },
      }),
      prisma.chapter.findMany({
        orderBy: { orderNo: "asc" },
        select: { id: true, title: true, orderNo: true },
      }),
    ]);

    return ok({
      items,
      chapters,
      total,
      page,
      pageSize,
      totalPages: Math.max(1, Math.ceil(total / pageSize)),
    });
  } catch (error) {
    return errorResponse(error);
  }
}
