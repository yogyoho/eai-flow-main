// EAI-CUSTOM: 新版 landing 页（landing-v2）路由挂载。/ 仍指向 landing-new，
// 本页（/landing-v2）供新版设计预览与切换评估，互不影响。
// 设计文档：docs/designs/2026-09-26-landing-v2-optimization.md（方案 B，2026-09-26 拍板）
import type { Metadata } from "next";

import LandingV2 from "@/components/landing-v2";

export const metadata: Metadata = {
  title: "中交三公局智能体平台 · 中交三公局",
  description:
    "矿山与煤炭工程领域企业级智能应用平台：统一编排智能体、知识库、技能与 MCP 工具链，工程报告生成、知识加工与文档协作从需求直达交付。",
};

export default function LandingV2Page() {
  return <LandingV2 />;
}
