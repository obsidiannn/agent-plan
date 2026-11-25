import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { getExamPayload } from "@/lib/exam-service";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const user = await requireSessionUser();
    const { id } = await context.params;
    const payload = await getExamPayload(id, user.id);
    return ok(payload);
  } catch (error) {
    return errorResponse(error);
  }
}
