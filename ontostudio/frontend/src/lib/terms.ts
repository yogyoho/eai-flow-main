/**
 * 术语中文别名表（EAI-CUSTOM 2026-10-01 B1 文案包，设计 docs/designs/2026-10-01-ontostudio-ux-governance.md §B1.5）。
 * 轻量常量 + 帮助函数，非 i18n 框架——eng-review 前提①：问题是「开发者词汇渗入」，不是「UI 未翻译」。
 * 新增别名只改这张表，勿在页面散落硬编码。
 */

export const DOMAIN_ALIASES: Record<string, string> = {
  eia: "环评",
  core_graph: "图谱底座",
  bid_quote: "投标报价",
};

/** 域 key → 中文别名（未知 key 原样返回，null/空返回 null 便于调用方回退）。 */
export function domainAlias(key: string | null | undefined): string | null {
  if (!key) return null;
  return DOMAIN_ALIASES[key] ?? null;
}

/** 通用 UI 术语映射（列头/按钮等的英文残留统一在此收口）。 */
export const TERM_ALIASES: Record<string, string> = {
  "NAMED GRAPH": "派生图",
  Registry: "注册表",
  fingerprint: "指纹",
};
