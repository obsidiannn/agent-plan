import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { AuthForm } from "@/components/AuthForm";

export const dynamic = "force-dynamic";

export default async function RegisterPage() {
  const user = await getSessionUser();
  if (user) redirect("/");
  return (
    <div className="auth-shell">
      <section className="auth-art">
        <div>
          <div className="eyebrow">Tencent Cloud · FDE</div>
          <h1>
            每一次作答，
            <br />
            都是一次复盘。
          </h1>
          <p>
            注册后即可开始模拟考试。系统会记录你的每一次成绩、用时和逐题作答情况。
          </p>
        </div>
        <div className="tiny" style={{ color: "#93c5fd" }}>
          课程内容仅供内部学习使用
        </div>
      </section>
      <section className="auth-panel">
        <AuthForm mode="register" />
      </section>
    </div>
  );
}
