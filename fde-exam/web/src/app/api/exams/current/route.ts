import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { getCurrentAttempt } from "@/lib/exam-service";

export async function GET() {
  try {
    const user = await requireSessionUser();
    const attempt = await getCurrentAttempt(user.id);
    return ok({ attempt });
  } catch (error) {
    return errorResponse(error);
  }
}
