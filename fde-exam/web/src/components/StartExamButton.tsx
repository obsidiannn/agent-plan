"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function StartExamButton({
  className = "btn btn-light",
  label = "开始模拟考试",
}: {
  className?: string;
  label?: string;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function start() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/exams/start", { method: "POST" });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        setError(json?.error?.message || "开始考试失败");
        return;
      }
      router.push(`/exam/${json.data.attemptId}`);
    } catch {
      setError("网络错误，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button className={className} onClick={start} disabled={loading}>
        {loading ? "正在组卷..." : label}
      </button>
      {error ? (
        <div className="alert alert-error" style={{ marginTop: 10 }}>
          {error}
        </div>
      ) : null}
    </div>
  );
}
