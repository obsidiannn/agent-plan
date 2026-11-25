import { z } from "zod";
import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok, readJson } from "@/lib/api";
import { saveAnswers } from "@/lib/exam-service";

const schema = z.object({
  answers: z
    .array(
      z.object({
        orderNo: z.number().int().positive(),
        selected: z.array(z.string()).max(6),
      }),
    )
    .max(60),
});

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const user = await requireSessionUser();
    const { id } = await context.params;
    const body = schema.parse(await readJson(request));
    const result = await saveAnswers(id, user.id, body.answers);
    return ok(result);
  } catch (error) {
    return errorResponse(error);
  }
}
