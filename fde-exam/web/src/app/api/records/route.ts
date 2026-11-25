import { requireSessionUser } from "@/lib/auth";
import { errorResponse, ok } from "@/lib/api";
import { listRecords } from "@/lib/exam-service";

export async function GET(request: Request) {
  try {
    const user = await requireSessionUser();
    const url = new URL(request.url);
    const page = Number.parseInt(url.searchParams.get("page") || "1", 10);
    const pageSize = Number.parseInt(url.searchParams.get("pageSize") || "20", 10);
    const result = await listRecords(user.id, page, pageSize);
    return ok(result);
  } catch (error) {
    return errorResponse(error);
  }
}
