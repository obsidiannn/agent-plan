import { prisma } from "@/lib/db";

export const dynamic = "force-dynamic";

function formatDate(value: Date | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

export default async function AdminRunsPage() {
  const [runs, candidateStats] = await Promise.all([
    prisma.generationRun.findMany({
      orderBy: { startedAt: "desc" },
      take: 50,
      include: {
        _count: { select: { questions: true, candidates: true } },
      },
    }),
    prisma.questionCandidate.groupBy({
      by: ["status"],
      _count: { _all: true },
    }),
  ]);

  const stats = Object.fromEntries(
    candidateStats.map((item) => [item.status, item._count._all]),
  );

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · Generation Runs</div>
          <h1>生成批次</h1>
          <p>查看每次 PDF 解析 / 题目生成 / 去重质检的结果。</p>
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 22 }}>
        <div className="stat">
          <div className="stat-label">候选总数</div>
          <div className="stat-value">
            {Object.values(stats).reduce((sum, value) => sum + value, 0)}
          </div>
          <div className="stat-hint">包含被拒绝的候选题</div>
        </div>
        <div className="stat">
          <div className="stat-label">已接受</div>
          <div className="stat-value">{stats.ACCEPTED || 0}</div>
          <div className="stat-hint">进入题库待审</div>
        </div>
        <div className="stat">
          <div className="stat-label">精确/近似重复</div>
          <div className="stat-value">
            {(stats.DUP_EXACT || 0) + (stats.DUP_NEAR || 0) + (stats.DUP_CLAIM || 0)}
          </div>
          <div className="stat-hint">被去重层拦截</div>
        </div>
        <div className="stat">
          <div className="stat-label">质量/规则拒绝</div>
          <div className="stat-value">
            {(stats.QUALITY_REJECTED || 0) + (stats.RULE_REJECTED || 0)}
          </div>
          <div className="stat-hint">未通过自动质检</div>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="card empty">
          <h3>还没有生成批次</h3>
          <p>
            在 <span className="mono">fde-exam/generator</span> 目录运行{" "}
            <span className="mono">uv run fde-gen run</span> 即可开始正式生成。
          </p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>批次</th>
                <th>模型</th>
                <th>Prompt</th>
                <th>状态</th>
                <th>目标</th>
                <th>生成</th>
                <th>通过</th>
                <th>拒绝</th>
                <th>开始时间</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td className="mono small">{run.id.slice(0, 10)}</td>
                  <td>{run.model}</td>
                  <td className="small muted">{run.promptVersion}</td>
                  <td>
                    <span
                      className={`badge ${
                        run.status === "SUCCESS"
                          ? "badge-green"
                          : run.status === "FAILED"
                            ? "badge-red"
                            : "badge-amber"
                      }`}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td>{run.targetCount}</td>
                  <td>{run.generatedCount}</td>
                  <td>{run.acceptedCount}</td>
                  <td>{run.rejectedCount}</td>
                  <td>{formatDate(run.startedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
