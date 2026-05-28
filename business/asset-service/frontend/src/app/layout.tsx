import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "资产管理",
  description: "EAIFlow 企业资产管理微服务",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
