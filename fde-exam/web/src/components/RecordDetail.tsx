"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDuration } from "@/lib/json";

type Option = { key: string; content: string };
type Item = {
  orderNo: number;
  type: string;
  stem: string;
  options: Option[];
  answer: string[];
  selected: string[];
  explanation: string | null;
  chapterTitle: string | null;
  knowledgePoint: string | null;
  evidenceQuote: string | null;
  sourcePage: number | null;
  isCorrect: boolean | null;
  score: number;
  maxScore: number;
};
type Detail = {
  attempt: {
    id: string;
    startedAt: string;
    submittedAt: string | null;
    durationSeconds: number | null;
    score: number | null;
    totalScore: number;
    passed: boolean | null;
    correctCount: number | null;
    questionCount: number;
    submitType: string | null;
  };
  items: Item[];
};

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function typeLabel(type: string) {
  return type === "MULTIPLE" ? "多选题" : "单选题";
}

export function RecordDetail({ detail }: { detail: Detail }) {
  const [filter, setFilter] = useState<"all" | "wrong">("all");
  const { attempt } = detail;
  const percent = Math.round(
    ((attempt.score ?? 0) / Math.max(1, attempt.totalScore)) * 100,
  );
  const wrongCount = detail.items.filter((item) => !item.isCorrect).length;
  const visible = useMemo(
    () =>
      filter === "all"
        ? detail.items
        : detail.items.filter((item) => !item.isCorrect),
    [detail.items, filter],
  );

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">Exam Record · Review</div>
          <h1>做题详情</h1>
          <p>
            交卷时间 {formatDate(attempt.submittedAt)} · 试卷编号{" "}
            <span className="mono">{attempt.id.slice(0, 10)}</span>
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Link className="btn btn-outline" href="/records">
            返回记录
          </Link>
          <Link className="btn btn-primary" href="/">
            回到首页
          </Link>
        </div>
      </div>

      <section className="result-hero">
        <div
          className="score-ring"
          style={{ "--score": `${percent}%` } as React.CSSProperties}
        >
          <div className="score-ring-inner">
            <div>
              <strong>{(attempt.score ?? 0).toFixed(1)}</strong>
              <span>满分 {attempt.totalScore}</span>
            </div>
          </div>
        </div>
        <div>
          <div className="eyebrow" style={{ color: "#93c5fd" }}>
            {attempt.passed ? "Passed · 已及格" : "Not Passed · 未及格"}
          </div>
          <h2 style={{ margin: "4px 0 0", fontSize: 26, color: "#fff" }}>
            {attempt.passed ? "这次通过了，继续保持。" : "还差一点，复盘后再来一次。"}
          </h2>
          <div className="result-facts">
            <div>
              <span>正确题数</span>
              <strong>
                {attempt.correctCount ?? 0} / {attempt.questionCount}
              </strong>
            </div>
            <div>
              <span>用时</span>
              <strong>{formatDuration(attempt.durationSeconds)}</strong>
            </div>
            <div>
              <span>交卷方式</span>
              <strong>{attempt.submitType === "TIMEOUT" ? "超时自动" : "手动"}</strong>
            </div>
            <div>
              <span>错题</span>
              <strong>{wrongCount}</strong>
            </div>
          </div>
        </div>
      </section>

      <div
        className="card-head"
        style={{ marginTop: 26, marginBottom: 12, flexWrap: "wrap" }}
      >
        <div>
          <h2>逐题复盘</h2>
          <div className="card-sub">正确答案、解析和原文页码均可回查</div>
        </div>
        <div className="filter-tabs">
          <button
            className={`filter-tab ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            全部 {detail.items.length}
          </button>
          <button
            className={`filter-tab ${filter === "wrong" ? "active" : ""}`}
            onClick={() => setFilter("wrong")}
          >
            错题 {wrongCount}
          </button>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="card empty">
          <h3>没有错题</h3>
          <p>这次全部答对了。</p>
        </div>
      ) : (
        visible.map((item) => (
          <article
            key={item.orderNo}
            className={`review-item ${item.isCorrect ? "" : "wrong"}`}
          >
            <div className="review-head">
              <div className="question-meta" style={{ marginBottom: 0 }}>
                <span className="badge badge-blue">第 {item.orderNo} 题</span>
                <span className="badge badge-gray">{typeLabel(item.type)}</span>
                {item.chapterTitle ? (
                  <span className="badge badge-gray">{item.chapterTitle}</span>
                ) : null}
                {item.sourcePage ? (
                  <span className="badge badge-gray">PDF 第 {item.sourcePage} 页</span>
                ) : null}
              </div>
              <div style={{ textAlign: "right" }}>
                <span
                  className={`badge ${item.isCorrect ? "badge-green" : "badge-red"}`}
                >
                  {item.isCorrect ? `正确 +${item.score}` : `错误 0/${item.maxScore}`}
                </span>
              </div>
            </div>

            <div style={{ fontWeight: 650, fontSize: 16 }}>{item.stem}</div>
            <div className="review-options">
              {item.options.map((option) => {
                const isCorrect = item.answer.includes(option.key);
                const isChosen = item.selected.includes(option.key);
                const classes = [
                  "review-option",
                  isCorrect ? "correct" : "",
                  isChosen && isCorrect ? "chosen" : "",
                  isChosen && !isCorrect ? "chosen-wrong" : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <div key={option.key} className={classes}>
                    <strong>{option.key}.</strong> {option.content}
                    {isCorrect ? (
                      <span className="badge badge-green" style={{ marginLeft: 8 }}>
                        正确答案
                      </span>
                    ) : null}
                    {isChosen ? (
                      <span
                        className={`badge ${isCorrect ? "badge-blue" : "badge-red"}`}
                        style={{ marginLeft: 6 }}
                      >
                        你的选择
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>

            <div className="explain">
              <strong>解析：</strong>
              {item.explanation || "暂无解析。"}
              {item.evidenceQuote ? (
                <div className="tiny muted" style={{ marginTop: 6 }}>
                  原文证据：{item.evidenceQuote}
                  {item.sourcePage ? `（第 ${item.sourcePage} 页）` : ""}
                </div>
              ) : null}
            </div>
          </article>
        ))
      )}
    </main>
  );
}
