import { z } from "zod";
import { requireAdmin } from "@/lib/auth";
import { errorResponse, ok, readJson } from "@/lib/api";
import { prisma } from "@/lib/db";
import { ApiError } from "@/lib/errors";

const schema = z.object({
  action: z.enum(["APPROVE", "REJECT", "DISABLE", "ENABLE"]),
  note: z.string().max(500).optional(),
});

const statusMap: Record<string, string> = {
  APPROVE: "APPROVED",
  REJECT: "REJECTED",
  DISABLE: "DISABLED",
  ENABLE: "APPROVED",
};

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const admin = await requireAdmin();
    const { id } = await context.params;
    const body = schema.parse(await readJson(request));
    const question = await prisma.question.findUnique({ where: { id } });
    if (!question) throw new ApiError("NOT_FOUND", "题目不存在", 404);

    const updated = await prisma.question.update({
      where: { id },
      data: {
        status: statusMap[body.action],
        reviewedBy: admin.username,
        reviewedAt: new Date(),
        rejectReason: body.action === "REJECT" ? body.note || "人工退回" : null,
        reviewNote: body.note || null,
      },
    });
    return ok({ question: updated });
  } catch (error) {
    return errorResponse(error);
  }
}
