import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FDE 模拟考试",
  description: "腾讯云 FDE 课程模拟考试与题库系统",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
