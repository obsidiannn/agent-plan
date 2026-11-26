"use client";

import { useCallback, useEffect, useState } from "react";

type Option = { key: string; content: string };
type Question = {
  id: string;
  type: string;
  style: string | null;
  stem: string;
  optionsJson: string;
  answerJson: string;
  explanation: string;
  difficulty: string;
  knowledgePoint: string | null;
  sourcePage: number | null;
  evidenceQuote: string | null;
  status: string;
  qualityScore: number | null;
  rejectReason: string | null;
  createdAt: string;
  chapter: { title: string; orderNo: number } | null;
  generationRun: { id: string; model: string; promptVersion: string } | null;
};
type Chapter = { id: string; title: string; orderNo: number };

const statusLabels: Record<string, string> = {
  PENDING_REVIEW: "待审核",
  APPROVED: "已通过",
  REJECTED: "已拒绝",
  DISABLED: "已下架",
};

const statusClasses: Record<string, string> = {
  PENDING_REVIEW: "badge-amber",
  APPROVED: "badge-green",
  REJECTED: "badge-red",
  DISABLED: "badge-gray",
};

function parseJson<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function QuestionAdmin() {
  const [items, setItems] = useState<Question[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [style, setStyle] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        page: String(page),
        pageSize: "20",
      });
      if (status) params.set("status", status);
      if (type) params.set("type", type);
      if (style) params.set("style", style);
      if (chapterId) params.set("chapterId", chapterId);
      if (q.trim()) params.set("q", q.trim());
      const response = await fetch(`/api/admin/questions?${params.toString()}`);
      const json = await response.json();
      if (!response.ok || !json.ok) {
        setError(json?.error?.message || "加载题目失败");
        return;
      }
      setItems(json.data.items);
      setChapters(json.data.chapters);
      setTotal(json.data.total);
      setTotalPages(json.data.totalPages);
    } catch {
      setError("网络错误，加载题目失败");
    } finally {
      setLoading(false);
    }
  }, [chapterId, page, q, status, style, type]);

  useEffect(() => {
    load();
  }, [load]);

  async function action(id: string, nextAction: string) {
    let note = "";
    if (nextAction === "REJECT") {
      note = window.prompt("请输入退回原因（可留空）") || "";
    }
    const response = await fetch(`/api/admin/questions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: nextAction, note }),
    });
    const json = await response.json();
    if (!response.ok || !json.ok) {
      setError(json?.error?.message || "操作失败");
      return;
    }
    await load();
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <div className="eyebrow">Admin · Review Queue</div>
          <h1>题目审核</h1>
          <p>只有状态为「已通过」的题目才会进入组卷池。</p>
        </div>
        <span className="badge badge-blue">共 {total} 题</span>
      </div>

      <div className="filter-bar">
        <select
          className="select"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">全部状态</option>
          <option value="PENDING_REVIEW">待审核</option>
          <option value="APPROVED">已通过</option>
          <option value="REJECTED">已拒绝</option>
          <option value="DISABLED">已下架</option>
        </select>
        <select
          className="select"
          value={type}
          onChange={(event) => {
            setType(event.target.value);
            setPage(1);
          }}
        >
          <option value="">全部题型</option>
          <option value="SINGLE">单选题</option>
          <option value="MULTIPLE">多选题</option>
        </select>
        <select
          className="select"
          value={style}
          onChange={(event) => {
            setStyle(event.target.value);
            setPage(1);
          }}
        >
          <option value="">全部风格</option>
          <option value="SCENARIO">场景决策</option>
          <option value="TROUBLESHOOTING">故障排查</option>
          <option value="COMPARISON">对比选型</option>
          <option value="PROCESS">流程阶段</option>
          <option value="CALCULATION">成本口径</option>
          <option value="JUDGMENT">规则判断</option>
        </select>
        <select
          className="select"
          value={chapterId}
          onChange={(event) => {
            setChapterId(event.target.value);
            setPage(1);
          }}
        >
          <option value="">全部章节</option>
          {chapters.map((chapter) => (
            <option key={chapter.id} value={chapter.id}>
              {chapter.title}
            </option>
          ))}
        </select>
        <input
          className="input"
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setPage(1);
          }}
          placeholder="搜索题干"
        />
        <button className="btn btn-outline btn-sm" onClick={() => load()}>
          刷新
        </button>
      </div>

      {error ? <div className="alert alert-error">{error}</div> : null}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>题目</th>
              <th>章节</th>
              <th>题型</th>
              <th>质量分</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="muted">
                  正在加载...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7} className="muted">
                  没有符合条件的题目。
                </td>
              </tr>
            ) : (
              items.map((item) => {
                const options = parseJson<Option[]>(item.optionsJson, []);
                const answer = parseJson<string[]>(item.answerJson, []);
                return (
                  <tr key={item.id}>
                    <td className="question-preview">
                      <div className="stem">{item.stem}</div>
                      <details>
                        <summary className="tiny muted" style={{ cursor: "pointer" }}>
                          查看选项 / 答案 / 解析
                        </summary>
                        <div style={{ marginTop: 8 }}>
                          {options.map((option) => (
                            <div key={option.key} className="option-inline">
                              <strong>{option.key}.</strong> {option.content}
                            </div>
                          ))}
                          <div className="tiny" style={{ marginTop: 6 }}>
                            答案：<strong>{answer.join(", ") || "-"}</strong>
                          </div>
                          <div className="tiny muted" style={{ marginTop: 4 }}>
                            {item.explanation}
                          </div>
                          {item.evidenceQuote ? (
                            <div className="tiny muted" style={{ marginTop: 4 }}>
                              证据：{item.evidenceQuote}
                              {item.sourcePage ? `（第 ${item.sourcePage} 页）` : ""}
                            </div>
                          ) : null}
                        </div>
                      </details>
                    </td>
                    <td className="small">{item.chapter?.title || "-"}</td>
                    <td>
                      <span className="badge badge-gray">
                        {item.type === "MULTIPLE" ? "多选" : "单选"}
                      </span>
                      <div className="tiny muted" style={{ marginTop: 3 }}>
                        {item.difficulty}
                        {item.style ? ` · ${item.style}` : ""}
                      </div>
                    </td>
                    <td>{item.qualityScore != null ? item.qualityScore.toFixed(2) : "-"}</td>
                    <td>
                      <span
                        className={`badge ${statusClasses[item.status] || "badge-gray"}`}
                      >
                        {statusLabels[item.status] || item.status}
                      </span>
                      {item.rejectReason ? (
                        <div className="tiny muted" style={{ marginTop: 3 }}>
                          {item.rejectReason}
                        </div>
                      ) : null}
                    </td>
                    <td className="tiny muted">{formatDate(item.createdAt)}</td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {item.status !== "APPROVED" ? (
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => action(item.id, "APPROVE")}
                          >
                            通过
                          </button>
                        ) : null}
                        {item.status === "PENDING_REVIEW" ? (
                          <button
                            className="btn btn-outline btn-sm"
                            onClick={() => action(item.id, "REJECT")}
                          >
                            退回
                          </button>
                        ) : null}
                        {item.status === "APPROVED" ? (
                          <button
                            className="btn btn-outline btn-sm"
                            onClick={() => action(item.id, "DISABLE")}
                          >
                            下架
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <span className="muted small">
          第 {page} / {totalPages} 页，共 {total} 题
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-outline btn-sm"
            disabled={page <= 1}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            上一页
          </button>
          <button
            className="btn btn-outline btn-sm"
            disabled={page >= totalPages}
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  );
}
