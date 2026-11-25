"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const isLogin = mode === "login";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`/api/auth/${isLogin ? "login" : "register"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          isLogin ? { username, password } : { username, password, nickname },
        ),
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        setError(json?.error?.message || "操作失败");
        return;
      }
      router.push("/");
      router.refresh();
    } catch {
      setError("网络错误，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-card">
      <h2>{isLogin ? "登录" : "创建账号"}</h2>
      <p>
        {isLogin
          ? "登录后开始 FDE 模拟考试，系统会自动保存你的作答。"
          : "注册后即可参加模拟考试，并保存每一次做题记录。"}
      </p>
      <form className="form" onSubmit={submit}>
        {!isLogin ? (
          <div className="field">
            <label htmlFor="nickname">昵称（可选）</label>
            <input
              id="nickname"
              className="input"
              value={nickname}
              onChange={(event) => setNickname(event.target.value)}
              placeholder="例如：小明"
              maxLength={32}
            />
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="username">用户名</label>
          <input
            id="username"
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="3～32 个字符"
            autoComplete="username"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">密码</label>
          <input
            id="password"
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={isLogin ? "请输入密码" : "至少 8 位"}
            autoComplete={isLogin ? "current-password" : "new-password"}
            required
          />
        </div>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <button className="btn btn-primary btn-block" disabled={loading}>
          {loading ? "请稍候..." : isLogin ? "登录" : "注册并登录"}
        </button>
      </form>
      <div className="auth-switch">
        {isLogin ? (
          <>
            还没有账号？<Link href="/register">立即注册</Link>
          </>
        ) : (
          <>
            已有账号？<Link href="/login">直接登录</Link>
          </>
        )}
      </div>
      {isLogin ? (
        <div className="demo-hint">
          演示账号：普通用户 <strong>demo / demo123456</strong>
          <br />
          管理员 <strong>admin / admin123456</strong>
        </div>
      ) : null}
    </div>
  );
}
