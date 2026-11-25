"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Option = { key: string; content: string };
type Item = {
  orderNo: number;
  type: string;
  stem: string;
  options: Option[];
  selected: string[];
  maxScore: number;
  chapterTitle: string | null;
  knowledgePoint: string | null;
};
type Payload = {
  attempt: {
    id: string;
    startedAt: string;
    expiresAt: string;
    remainingSeconds: number;
    questionCount: number;
    totalScore: number;
  };
  items: Item[];
};

function formatTime(seconds: number) {
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function typeLabel(type: string) {
  return type === "MULTIPLE" ? "多选题" : "单选题";
}

export function ExamRunner({ attemptId }: { attemptId: string }) {
  const router = useRouter();
  const [data, setData] = useState<Payload | null>(null);
  const [answers, setAnswers] = useState<Record<number, string[]>>({});
  const [current, setCurrent] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const answersRef = useRef<Record<number, string[]>>({});
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submittingRef = useRef(false);
  const draftKey = `fde-exam-draft-${attemptId}`;

  const persist = useCallback(
    async (next: Record<number, string[]>, keepalive = false) => {
      if (!data) return;
      setSaveState("saving");
      try {
        const response = await fetch(`/api/exams/${attemptId}/answers`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            answers: Object.entries(next).map(([orderNo, selected]) => ({
              orderNo: Number(orderNo),
              selected,
            })),
          }),
          keepalive,
        });
        const json = await response.json();
        if (!response.ok || !json.ok) {
          setSaveState("error");
          if (json?.error?.code === "ATTEMPT_EXPIRED") {
            router.push(`/records/${attemptId}`);
          }
          return;
        }
        setSaveState("saved");
      } catch {
        setSaveState("error");
      }
    },
    [attemptId, data, router],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const response = await fetch(`/api/exams/${attemptId}`);
        const json = await response.json();
        if (cancelled) return;
        if (!response.ok || !json.ok) {
          if (json?.error?.code === "ATTEMPT_EXPIRED") {
            router.replace(`/records/${attemptId}`);
            return;
          }
          if (json?.error?.code === "CONFLICT") {
            router.replace(`/records/${attemptId}`);
            return;
          }
          setError(json?.error?.message || "加载试卷失败");
          return;
        }
        const payload = json.data as Payload;
        const initial: Record<number, string[]> = {};
        for (const item of payload.items) {
          initial[item.orderNo] = item.selected || [];
        }
        try {
          const draft = localStorage.getItem(draftKey);
          if (draft) {
            const parsed = JSON.parse(draft) as Record<string, string[]>;
            for (const [key, value] of Object.entries(parsed)) {
              const orderNo = Number(key);
              if (
                Array.isArray(value) &&
                (initial[orderNo] || []).length === 0 &&
                value.length > 0
              ) {
                initial[orderNo] = value;
              }
            }
          }
        } catch {
          // ignore draft errors
        }
        answersRef.current = initial;
        setAnswers(initial);
        setData(payload);
        setRemaining(payload.attempt.remainingSeconds);
      } catch {
        if (!cancelled) setError("网络错误，无法加载试卷");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [attemptId, draftKey, router]);

  const submit = useCallback(
    async (auto = false) => {
      if (submittingRef.current) return;
      if (!auto) {
        const unanswered = Object.values(answersRef.current).filter(
          (value) => value.length === 0,
        ).length;
        const message =
          unanswered > 0
            ? `还有 ${unanswered} 题未作答，确定要交卷吗？`
            : "确定要交卷吗？交卷后不能修改答案。";
        if (!window.confirm(message)) return;
      }
      submittingRef.current = true;
      setSubmitting(true);
      setSubmitError("");
      try {
        const response = await fetch(`/api/exams/${attemptId}/submit`, {
          method: "POST",
        });
        const json = await response.json();
        if (!response.ok || !json.ok) {
          if (
            json?.error?.code === "ATTEMPT_EXPIRED" ||
            json?.error?.code === "CONFLICT"
          ) {
            localStorage.removeItem(draftKey);
            router.push(`/records/${attemptId}`);
            return;
          }
          setSubmitError(json?.error?.message || "交卷失败");
          return;
        }
        localStorage.removeItem(draftKey);
        router.push(`/records/${attemptId}`);
      } catch {
        setSubmitError("网络错误，交卷失败，请重试");
      } finally {
        submittingRef.current = false;
        setSubmitting(false);
      }
    },
    [attemptId, draftKey, router],
  );

  const submitRef = useRef(submit);
  submitRef.current = submit;

  useEffect(() => {
    if (!data) return;
    const expiresAt = new Date(data.attempt.expiresAt).getTime();
    const tick = () => {
      const seconds = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
      setRemaining(seconds);
      if (seconds <= 0) {
        submitRef.current(true);
      }
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [data]);

  useEffect(() => {
    function flush() {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (document.visibilityState === "hidden" && data) {
        persist(answersRef.current, true);
      }
    }
    document.addEventListener("visibilitychange", flush);
    window.addEventListener("beforeunload", flush);
    return () => {
      document.removeEventListener("visibilitychange", flush);
      window.removeEventListener("beforeunload", flush);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [data, persist]);

  const items = data?.items || [];
  const item = items[current];

  const answeredCount = useMemo(
    () => items.filter((entry) => (answers[entry.orderNo] || []).length > 0).length,
    [answers, items],
  );

  function choose(key: string) {
    if (!item) return;
    const previous = answersRef.current[item.orderNo] || [];
    let nextSelected: string[];
    if (item.type === "SINGLE") {
      nextSelected = [key];
    } else {
      nextSelected = previous.includes(key)
        ? previous.filter((value) => value !== key)
        : [...previous, key];
    }
    const next: Record<number, string[]> = {
      ...answersRef.current,
      [item.orderNo]: nextSelected,
    };
    answersRef.current = next;
    setAnswers(next);
    localStorage.setItem(draftKey, JSON.stringify(next));
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      persist(next);
      timerRef.current = null;
    }, 800);
  }

  if (loading) {
    return (
      <main className="page">
        <div className="card">正在加载试卷...</div>
      </main>
    );
  }

  if (error || !data || !item) {
    return (
      <main className="page">
        <div className="card">
          <h2>无法加载试卷</h2>
          <p className="muted">{error || "试卷数据异常"}</p>
          <Link className="btn btn-primary" href="/">
            返回首页
          </Link>
        </div>
      </main>
    );
  }

  const selected = answers[item.orderNo] || [];
  const warn = remaining <= 5 * 60;

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">Mock Exam · In Progress</div>
          <h1>FDE 模拟考试</h1>
          <p>
            共 {data.attempt.questionCount} 题 · 已作答 {answeredCount} 题 · 满分{" "}
            {data.attempt.totalScore} 分
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className={`badge ${warn ? "badge-red" : "badge-blue"}`}>
            剩余 {formatTime(remaining)}
          </div>
          <div className="save-status" style={{ marginTop: 6 }}>
            {saveState === "saving"
              ? "正在保存..."
              : saveState === "saved"
                ? "已自动保存"
                : saveState === "error"
                  ? "保存失败，请检查网络"
                  : ""}
          </div>
        </div>
      </div>

      {submitError ? <div className="alert alert-error">{submitError}</div> : null}

      <div className="exam-layout">
        <section>
          <div className="question-card">
            <div className="question-meta">
              <span className="badge badge-blue">
                第 {item.orderNo} / {data.attempt.questionCount} 题
              </span>
              <span className="badge badge-gray">{typeLabel(item.type)}</span>
              <span className="badge badge-gray">{item.maxScore} 分</span>
              {item.chapterTitle ? (
                <span className="badge badge-gray">{item.chapterTitle}</span>
              ) : null}
            </div>
            <h2 className="question-stem">{item.stem}</h2>
            <div className="option-list">
              {item.options.map((option) => {
                const active = selected.includes(option.key);
                return (
                  <button
                    type="button"
                    key={option.key}
                    className={`option ${active ? "selected" : ""}`}
                    onClick={() => choose(option.key)}
                    aria-pressed={active}
                  >
                    <span className="option-key">{option.key}</span>
                    <span className="option-text">{option.content}</span>
                  </button>
                );
              })}
            </div>
            {item.type === "MULTIPLE" ? (
              <div className="tiny muted" style={{ marginTop: 10 }}>
                多选题：可选择多个选项，全部选对才得分。
              </div>
            ) : null}
            <div className="exam-actions">
              <div className="exam-actions-right">
                <button
                  className="btn btn-outline"
                  disabled={current === 0}
                  onClick={() => setCurrent((value) => Math.max(0, value - 1))}
                >
                  上一题
                </button>
                <button
                  className="btn btn-primary"
                  disabled={current >= items.length - 1}
                  onClick={() =>
                    setCurrent((value) => Math.min(items.length - 1, value + 1))
                  }
                >
                  下一题
                </button>
              </div>
              <button
                className="btn btn-outline"
                onClick={() => submit(false)}
                disabled={submitting}
              >
                {submitting ? "交卷中..." : "交卷"}
              </button>
            </div>
          </div>
        </section>

        <aside className="exam-side">
          <div className="card">
            <div className="timer">
              <div>
                <div className="stat-label">剩余时间</div>
                <div className={`timer-value ${warn ? "warn" : ""}`}>
                  {formatTime(remaining)}
                </div>
              </div>
              {warn ? <span className="badge badge-red">请注意</span> : null}
            </div>
            <div className="tiny muted" style={{ marginTop: 6 }}>
              已作答 {answeredCount} / {items.length} 题
            </div>
          </div>

          <div className="card">
            <div className="card-head" style={{ marginBottom: 10 }}>
              <h3>答题卡</h3>
            </div>
            <div className="qnav-grid">
              {items.map((entry, index) => {
                const isAnswered = (answers[entry.orderNo] || []).length > 0;
                const classes = [
                  "qnav-item",
                  isAnswered ? "answered" : "",
                  index === current ? "current" : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <button
                    key={entry.orderNo}
                    className={classes}
                    onClick={() => setCurrent(index)}
                    title={`第 ${entry.orderNo} 题`}
                  >
                    {entry.orderNo}
                  </button>
                );
              })}
            </div>
            <button
              className="btn btn-primary btn-block"
              style={{ marginTop: 16 }}
              onClick={() => submit(false)}
              disabled={submitting}
            >
              {submitting ? "交卷中..." : "交卷并查看成绩"}
            </button>
            <div className="tiny muted" style={{ marginTop: 8 }}>
              交卷后不可修改答案；超时会自动交卷。
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
