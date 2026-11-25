import Link from "next/link";
import { redirect } from "next/navigation";
import { getPageUser } from "@/lib/page-auth";
import { getRecordDetail } from "@/lib/exam-service";
import { ApiError } from "@/lib/errors";
import { RecordDetail } from "@/components/RecordDetail";

export const dynamic = "force-dynamic";

export default async function RecordDetailPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const user = await getPageUser();
  const { attemptId } = await params;
  try {
    const detail = await getRecordDetail(attemptId, user);
    return <RecordDetail detail={JSON.parse(JSON.stringify(detail))} />;
  } catch (error) {
    if (error instanceof ApiError && error.code === "CONFLICT") {
      redirect(`/exam/${attemptId}`);
    }
    return (
      <main className="page">
        <div className="card">
          <h2>
            {error instanceof ApiError && error.code === "FORBIDDEN"
              ? "无权查看"
              : "记录不存在"}
          </h2>
          <p className="muted">
            {error instanceof ApiError ? error.message : "加载记录失败"}
          </p>
          <Link className="btn btn-primary" href="/records">
            返回做题记录
          </Link>
        </div>
      </main>
    );
  }
}
