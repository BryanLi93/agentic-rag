import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgenticRAG — 全栈知识助手",
  description: "支持引用溯源、Agent 工具轨迹与 SSE 流式回答的 AI 知识助手",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
