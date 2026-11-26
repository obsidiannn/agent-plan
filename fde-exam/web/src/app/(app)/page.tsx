import Link from "next/link";
import { getPageUser } from "@/lib/page-auth";
import { prisma } from "@/lib/db";
import { getCurrentAttempt, listRecords } from "@/lib/exam-service";
import { examConfig } from "@/lib/config";
import { formatDuration } from "@/lib/json";
import { StartExamButton } from "@/components/StartExamButton";

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

export default async function HomePage() {
  const user = await getPageUser();
  const [active, records, approved, chapters] = await Promise.all([
    getCurrentAttempt(user.id),
    listRecords(user.id, 1, 5),
    prisma.question.groupBy({
      by: ["type"],
      where: { status: "APPROVED" },
      _count: { _all: true },
    }),
    prisma.chapter.count(),
  ]);

  const singleCount =
    approved.find((item) => item.type === "SINGLE")?._count._all ?? 0;
  const multipleCount =
    approved.find((item) => item.type === "MULTIPLE")?._count._all ?? 0;
  const poolReady =
    singleCount >= examConfig.singleCount &&
    multipleCount >= examConfig.multipleCount;

  const bestScore = records.items.reduce(
    (best, item) => Math.max(best, item.score ?? 0),
    0,
  );
  const passedCount = records.items.filter((item) => item.passed).length;

  return (
    <main className="page">
      <section className="hero">
        <div className="eyebrow">FDE Certification · Mock Exam</div>
        <h1>
          {active ? "继续你的模拟考试" : "准备好了吗？开始一次完整模拟"}
        </h1>
        <p>
          每套试卷 60 题：40 道单选（1.5 分）+ 20 道多选（2 分），满分 100
          分，70 分及格。作答会自动保存，未交卷下次可继续。
        </p>
        <div className="hero-actions">
          {active ? (
            <>
              <Link className="btn btn-light" href={`/exam/${active.attemptId}`}>
                继续答题
              </Link>
              <span className="small" style={{ color: "#bfdbfe" }}>
                剩余时间约 {formatDuration(active.remainingSeconds)}
              </span>
            </>
          ) : poolReady ? (
            <StartExamButton />
          ) : (
            <span className="alert alert-warn">
              题库尚未准备完成：当前单选 {singleCount}/{examConfig.singleCount}，
              多选 {multipleCount}/{examConfig.multipleCount}。请先运行生成器或让管理员导入题库。
            </span>
          )}
          <Link
            href="/records"
            className="btn"
            style={{ color: "#dbeafe", background: "rgba(255,255,255,.1)" }}
          >
            查看做题记录
          </Link>
        </div>
        <div className="hero-meta">
          <span>
            <strong>{examConfig.durationMinutes}</strong> 分钟
          </span>
          <span>
            <strong>{examConfig.passScore}</strong> 分及格
          </span>
          <span>
            <strong>{chapters}</strong> 个章节
          </span>
          <span>
            题库已就绪 <strong>{singleCount + multipleCount}</strong> 题
          </span>
        </div>
      </section>

      <div className="grid grid-4" style={{ marginTop: 22 }}>
        <div className="stat">
          <div className="stat-label">已完成模拟</div>
          <div className="stat-value">{records.total}</div>
          <div className="stat-hint">累计交卷次数</div>
        </div>
        <div className="stat">
          <div className="stat-label">最高分</div>
          <div className="stat-value">{records.total ? bestScore.toFixed(1) : "-"}</div>
          <div className="stat-hint">最近 5 次记录中的最高分</div>
        </div>
        <div className="stat">
          <div className="stat-label">及格次数</div>
          <div className="stat-value">{passedCount}</div>
          <div className="stat-hint">最近 5 次记录中 ≥ 70 分</div>
        </div>
        <div className="stat">
          <div className="stat-label">当前状态</div>
          <div className="stat-value" style={{ fontSize: 22 }}>
            {active ? "答题中" : "可开新卷"}
          </div>
          <div className="stat-hint">
            {active ? "未交卷前不会生成第二份试卷" : "系统将随机组卷"}
          </div>
        </div>
      </div>

      {!poolReady ? (
        <div className="alert alert-warn" style={{ marginTop: 22 }}>
          题库数量不足，暂时无法组出完整试卷。管理员可在{" "}
          <span className="mono">fde-exam/generator</span> 配置 LLM 后运行{" "}
          <span className="mono">uv run fde-gen run</span> 生成并审核题目。
          {user.role === "ADMIN" ? (
            <>
              {" "}
              <Link href="/admin" style={{ textDecoration: "underline" }}>
                前往题库管理
              </Link>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-2" style={{ marginTop: 22 }}>
        <section className="card">
          <div className="card-head">
            <div>
              <h2>最近做题记录</h2>
              <div className="card-sub">按交卷时间倒序，最多显示 5 条</div>
            </div>
            <Link href="/records" className="btn btn-outline btn-sm">
              全部记录
            </Link>
          </div>
          {records.items.length === 0 ? (
            <div className="empty">
              <h3>还没有做题记录</h3>
              <p>完成第一次模拟考试后，成绩会显示在这里。</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>交卷时间</th>
                    <th>得分</th>
                    <th>结果</th>
                    <th>用时</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {records.items.map((item) => (
                    <tr key={item.id}>
                      <td>{formatDate(item.submittedAt)}</td>
                      <td>
                        <strong>{item.score?.toFixed(1)}</strong>
                        <span className="muted tiny"> / {item.totalScore}</span>
                      </td>
                      <td>
                        <span
                          className={`badge ${item.passed ? "badge-green" : "badge-red"}`}
                        >
                          {item.passed ? "及格" : "未及格"}
                        </span>
                      </td>
                      <td>{formatDuration(item.durationSeconds)}</td>
                      <td>
                        <Link
                          className="btn btn-ghost btn-sm"
                          href={`/records/${item.id}`}
                        >
                          查看
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card">
          <div className="card-head">
            <div>
              <h2>考试说明</h2>
              <div className="card-sub">开始前请确认以下规则</div>
            </div>
          </div>
          <ul className="notice-list">
            <li>共 60 题，单选 40 题（1.5 分/题），多选 20 题（2 分/题）。</li>
            <li>多选题默认全对得分，少选/多选/错选均为 0 分。</li>
            <li>考试时长 {examConfig.durationMinutes} 分钟，超时自动交卷。</li>
            <li>同一时间只能有一份进行中的试卷，刷新后可继续作答。</li>
            <li>答题过程中不会返回正确答案，交卷后可在记录中查看解析。</li>
            <li>组卷时题目和选项顺序都会随机打乱。</li>
          </ul>
        </section>
      </div>
    </main>
  );
}
