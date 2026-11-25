import { clearSessionCookie, requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";

export async function POST() {
  try {
    await requireSessionUser();
    await clearSessionCookie();
    return ok({ loggedOut: true });
  } catch (error) {
    return errorResponse(error);
  }
}
