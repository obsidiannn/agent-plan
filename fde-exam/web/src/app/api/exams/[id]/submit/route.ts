import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { gradeAndSubmitAttempt } from "@/lib/exam-service";

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const user = await requireSessionUser();
    const { id } = await context.params;
    const result = await gradeAndSubmitAttempt({
      attemptId: id,
      userId: user.id,
      submitType: "MANUAL",
    });
    return ok(result);
  } catch (error) {
    return errorResponse(error);
  }
}
