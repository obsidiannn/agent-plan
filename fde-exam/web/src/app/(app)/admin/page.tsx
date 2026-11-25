import Link from "next/link";
import { prisma } from "@/lib/db";
import { examConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

export default async function AdminHomePage() {
  const [byStatus, byType, chapters, attempts, users, runs, chunks, demoCount] =
    await Promise.all([
      prisma.question.groupBy({ by: ["status"], _count: { _all: true } }),
      prisma.question.groupBy({ by: ["type"], _count: { _all: true } }),
      prisma.chapter.findMany({
        orderBy: { orderNo: "asc" },
        select: {
          id: true,
          title: true,
          pageStart: true,
          pageEnd: true,
          _count: { select: { questions: true, chunks: true } },
        },
      }),
      prisma.examAttempt.count({ where: { status: "SUBMITTED" } }),
      prisma.user.count(),
      prisma.generationRun.findMany({
        orderBy: { startedAt: "desc" },
        take: 3,
      }),
      prisma.sourceChunk.count(),
      prisma.question.count({ where: { promptVersion: "demo-v1" } }),
    ]);

  const statusMap = Object.fromEntries(
    byStatus.map((item) => [item.status, item._count._all]),
  );
  const typeMap = Object.fromEntries(
    byType.map((item) => [item.type, item._count._all]),
  );
  const single = typeMap.SINGLE || 0;
  const multiple = typeMap.MULTIPLE || 0;
  const ready =
    single >= examConfig.singleCount && multiple >= examConfig.multipleCount;

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · Question Bank</div>
          <h1>题库管理</h1>
          <p>查看题库状态、审核生成题目、检查每条生成批次的质检结果。</p>
        </div>
        <Link className="btn btn-primary" href="/admin/questions">
          去审核题目
        </Link>
      </div>

      {demoCount > 0 ? (
        <div className="alert alert-warn" style={{ marginBottom: 18 }}>
          当前题库包含 <strong>{demoCount}</strong> 道结构型演示题（目录归属类）。
          它们用于在没有 LLM Key 时跑通系统；正式使用前请在{" "}
          <span className="mono">generator/.env</span> 配置{" "}
          <span className="mono">LLM_API_KEY</span>，运行正式生成并在本页审核替换。
        </div>
      ) : null}

      <div className="grid grid-4">
        <div className="stat">
          <div className="stat-label">已通过题目</div>
          <div className="stat-value">{statusMap.APPROVED || 0}</div>
          <div className="stat-hint">
            单选 {single} / 多选 {multiple}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">待审核</div>
          <div className="stat-value">{statusMap.PENDING_REVIEW || 0}</div>
          <div className="stat-hint">需要人工确认后才能入卷</div>
        </div>
        <div className="stat">
          <div className="stat-label">已拒绝/下架</div>
          <div className="stat-value">
            {(statusMap.REJECTED || 0) + (statusMap.DISABLED || 0)}
          </div>
          <div className="stat-hint">拒绝或停用的题目</div>
        </div>
        <div className="stat">
          <div className="stat-label">组卷状态</div>
          <div className="stat-value" style={{ fontSize: 22 }}>
            {ready ? "可组卷" : "题量不足"}
          </div>
          <div className="stat-hint">
            需要 {examConfig.singleCount} 单选 + {examConfig.multipleCount} 多选
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: 22 }}>
        <section className="card">
          <div className="card-head">
            <div>
              <h2>章节覆盖</h2>
              <div className="card-sub">
                共 {chapters.length} 章 · {chunks} 个原文分块
              </div>
            </div>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>章节</th>
                  <th>页码</th>
                  <th>分块</th>
                  <th>题目</th>
                </tr>
              </thead>
              <tbody>
                {chapters.map((chapter) => (
                  <tr key={chapter.id}>
                    <td>{chapter.title}</td>
                    <td className="small muted">
                      {chapter.pageStart ?? "-"}～{chapter.pageEnd ?? "-"}
                    </td>
                    <td>{chapter._count.chunks}</td>
                    <td>
                      <span
                        className={`badge ${
                          chapter._count.questions > 0 ? "badge-green" : "badge-amber"
                        }`}
                      >
                        {chapter._count.questions}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <div>
              <h2>系统概况</h2>
              <div className="card-sub">用户与考试数据</div>
            </div>
            <Link className="btn btn-outline btn-sm" href="/admin/runs">
              生成批次
            </Link>
          </div>
          <div className="grid grid-2">
            <div className="stat" style={{ boxShadow: "none" }}>
              <div className="stat-label">注册用户</div>
              <div className="stat-value">{users}</div>
            </div>
            <div className="stat" style={{ boxShadow: "none" }}>
              <div className="stat-label">已交卷</div>
              <div className="stat-value">{attempts}</div>
            </div>
          </div>
          <h3 style={{ marginTop: 20 }}>最近生成批次</h3>
          {runs.length === 0 ? (
            <p className="muted small">暂无生成记录。可运行 Python 生成器或 seed-demo。</p>
          ) : (
            <ul className="notice-list">
              {runs.map((run) => (
                <li key={run.id}>
                  <strong>{run.model}</strong> · {run.status} · 生成{" "}
                  {run.generatedCount} / 通过 {run.acceptedCount} · 拒绝{" "}
                  {run.rejectedCount}
                </li>
              ))}
            </ul>
          )}
          <div className="alert alert-info" style={{ marginTop: 16 }}>
            题库生成与去重由 <span className="mono">fde-exam/generator</span> 负责，
            详细命令见项目 README。
          </div>
        </section>
      </div>
    </div>
  );
}
