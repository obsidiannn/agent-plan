import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { getOrCreateAttempt } from "@/lib/exam-service";

export async function POST() {
  try {
    const user = await requireSessionUser();
    const result = await getOrCreateAttempt(user.id);
    return ok(result);
  } catch (error) {
    return errorResponse(error);
  }
}
