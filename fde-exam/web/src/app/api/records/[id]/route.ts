import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { getRecordDetail } from "@/lib/exam-service";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const user = await requireSessionUser();
    const { id } = await context.params;
    const detail = await getRecordDetail(id, user);
    return ok(detail);
  } catch (error) {
    return errorResponse(error);
  }
}
