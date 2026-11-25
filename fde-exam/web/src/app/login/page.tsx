import { redirect } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { AuthForm } from "@/components/AuthForm";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const user = await getSessionUser();
  if (user) redirect("/");
  return (
    <div className="auth-shell">
      <section className="auth-art">
        <div>
          <div className="eyebrow">Tencent Cloud · FDE</div>
          <h1>
            把课程学到的，
            <br />
            变成能答出来的。
          </h1>
          <p>
            基于 FDE 课程 12 章内容整理的模拟题库，覆盖角色认知、产品矩阵、AI
            工程、交付、沉淀与安全治理。
          </p>
          <div className="auth-features">
            <div className="auth-feature">
              <div>
                <strong>60 题标准模拟卷</strong>
                <span>40 道单选 + 20 道多选，满分 100 分，70 分及格。</span>
              </div>
            </div>
            <div className="auth-feature">
              <div>
                <strong>随时续答</strong>
                <span>作答自动保存，同一时间只保留一份进行中的试卷。</span>
              </div>
            </div>
            <div className="auth-feature">
              <div>
                <strong>逐题复盘</strong>
                <span>查看得分、正确答案、解析与原文页码。</span>
              </div>
            </div>
          </div>
        </div>
        <div className="tiny" style={{ color: "#93c5fd" }}>
          课程内容仅供内部学习使用
        </div>
      </section>
      <section className="auth-panel">
        <AuthForm mode="login" />
      </section>
    </div>
  );
}
