import Link from "next/link";
import { getPageUser } from "@/lib/page-auth";
import { prisma } from "@/lib/db";
import { listRecords } from "@/lib/exam-service";
import { formatDuration } from "@/lib/json";

export const dynamic = "force-dynamic";

function formatDate(value: Date | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

export default async function RecordsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const user = await getPageUser();
  const params = await searchParams;
  const page = Math.max(1, Number.parseInt(params.page || "1", 10));
  const [records, aggregate, passedCount] = await Promise.all([
    listRecords(user.id, page, 20),
    prisma.examAttempt.aggregate({
      where: { userId: user.id, status: "SUBMITTED" },
      _max: { score: true },
      _avg: { score: true },
    }),
    prisma.examAttempt.count({
      where: { userId: user.id, status: "SUBMITTED", passed: true },
    }),
  ]);

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">History · Results</div>
          <h1>做题记录</h1>
          <p>查看历次模拟考试的成绩、用时和逐题作答情况。</p>
        </div>
        <Link className="btn btn-primary" href="/">
          开始新考试
        </Link>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 22 }}>
        <div className="stat">
          <div className="stat-label">累计交卷</div>
          <div className="stat-value">{records.total}</div>
          <div className="stat-hint">已完成试卷总数</div>
        </div>
        <div className="stat">
          <div className="stat-label">最高分</div>
          <div className="stat-value">
            {aggregate._max.score != null ? aggregate._max.score.toFixed(1) : "-"}
          </div>
          <div className="stat-hint">历史最高得分</div>
        </div>
        <div className="stat">
          <div className="stat-label">平均分</div>
          <div className="stat-value">
            {aggregate._avg.score != null ? aggregate._avg.score.toFixed(1) : "-"}
          </div>
          <div className="stat-hint">所有已交卷记录</div>
        </div>
        <div className="stat">
          <div className="stat-label">及格次数</div>
          <div className="stat-value">{passedCount}</div>
          <div className="stat-hint">≥ 70 分</div>
        </div>
      </div>

      {records.items.length === 0 ? (
        <div className="card empty">
          <h3>还没有做题记录</h3>
          <p>完成第一次模拟考试后，成绩和逐题解析会显示在这里。</p>
          <Link className="btn btn-primary" href="/">
            开始模拟考试
          </Link>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>试卷</th>
                  <th>开始时间</th>
                  <th>交卷时间</th>
                  <th>用时</th>
                  <th>得分</th>
                  <th>正确</th>
                  <th>结果</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {records.items.map((item) => (
                  <tr key={item.id}>
                    <td className="mono small">{item.id.slice(0, 10)}</td>
                    <td>{formatDate(item.startedAt)}</td>
                    <td>{formatDate(item.submittedAt)}</td>
                    <td>{formatDuration(item.durationSeconds)}</td>
                    <td>
                      <strong>{(item.score ?? 0).toFixed(1)}</strong>
                      <span className="muted tiny"> / {item.totalScore}</span>
                    </td>
                    <td>
                      {item.correctCount ?? 0}/{item.questionCount}
                    </td>
                    <td>
                      <span
                        className={`badge ${item.passed ? "badge-green" : "badge-red"}`}
                      >
                        {item.passed ? "及格" : "未及格"}
                      </span>
                      {item.submitType === "TIMEOUT" ? (
                        <span className="badge badge-amber" style={{ marginLeft: 4 }}>
                          超时
                        </span>
                      ) : null}
                    </td>
                    <td>
                      <Link className="btn btn-outline btn-sm" href={`/records/${item.id}`}>
                        查看详情
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span className="muted small">
              第 {records.page} / {records.totalPages} 页，共 {records.total} 条
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              {records.page > 1 ? (
                <Link
                  className="btn btn-outline btn-sm"
                  href={`/records?page=${records.page - 1}`}
                >
                  上一页
                </Link>
              ) : null}
              {records.page < records.totalPages ? (
                <Link
                  className="btn btn-outline btn-sm"
                  href={`/records?page=${records.page + 1}`}
                >
                  下一页
                </Link>
              ) : null}
            </div>
          </div>
        </>
      )}
    </main>
  );
}
