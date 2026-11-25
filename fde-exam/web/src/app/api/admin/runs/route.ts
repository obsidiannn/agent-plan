import { requireAdmin } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { prisma } from "@/lib/db";

export async function GET() {
  try {
    await requireAdmin();
    const runs = await prisma.generationRun.findMany({
      orderBy: { startedAt: "desc" },
      take: 50,
      include: {
        _count: { select: { questions: true, candidates: true } },
      },
    });
    return ok({ runs });
  } catch (error) {
    return errorResponse(error);
  }
}
