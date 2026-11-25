import { requireAdmin } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { prisma } from "@/lib/db";

export async function GET() {
  try {
    await requireAdmin();
    const [byStatus, byType, chapters, attempts, users] = await Promise.all([
      prisma.question.groupBy({ by: ["status"], _count: { _all: true } }),
      prisma.question.groupBy({ by: ["type"], _count: { _all: true } }),
      prisma.chapter.findMany({
        orderBy: { orderNo: "asc" },
        select: {
          id: true,
          title: true,
          orderNo: true,
          _count: { select: { questions: true, chunks: true } },
        },
      }),
      prisma.examAttempt.count({ where: { status: "SUBMITTED" } }),
      prisma.user.count(),
    ]);
    return ok({
      byStatus: Object.fromEntries(byStatus.map((x) => [x.status, x._count._all])),
      byType: Object.fromEntries(byType.map((x) => [x.type, x._count._all])),
      chapters,
      attempts,
      users,
    });
  } catch (error) {
    return errorResponse(error);
  }
}
