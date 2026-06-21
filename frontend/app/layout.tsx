import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "给不想发朋友圈的人，一个安心表达的地方",
  description: "VibeChat 是一个给不想发朋友圈的人安心表达情绪的匿名空间。"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
