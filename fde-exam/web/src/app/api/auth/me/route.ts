import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";

export async function GET() {
  try {
    const user = await requireSessionUser();
    return ok({ user });
  } catch (error) {
    return errorResponse(error);
  }
}
