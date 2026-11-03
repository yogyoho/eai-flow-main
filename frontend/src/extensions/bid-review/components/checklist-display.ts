/**
 * 附件核对表卡纯展示函数(L2 P3.3 spec 2026-11-03 §2;EAI-CUSTOM):
 * P3 平件负证据 + P3.2 复合子行 near-miss 门的前端消费面。
 * 全部纯函数,无 React 依赖,rstest node 环境直测。
 */

import type { BidNegativeEvidence } from "@/extensions/bid-review/api";

/** 子件状态 marker(P3.3 §2 裁决2):UNKNOWN(=P3.2 near_miss 门产物)→「?」,命中「✓」,否则「✗」。
 * 命中以 status 为准(FOUND 数受 min_count 影响,PARTIAL 可 found>0 但非全命中);found>0 仅作 MATCHED 的防御性复核。 */
export function subItemMarker(s: { status: string; found: number }): string {
  if (s.status === "UNKNOWN") return "?";
  return s.status === "MATCHED" && s.found > 0 ? "✓" : "✗";
}

/** near-miss hint 行(P3.3 §2;ev null/undefined=旧网关 → 零渲染):
 * closest[0] 在场 → 「未精确命中 · 近似候选「{no} {name}」相似度 {sim%}（待人工核对）」;
 * closest 空 → 「未精确命中 · 无近似候选记录（待人工核对）」。 */
export function nearMissHintLines(
  ev: BidNegativeEvidence | null | undefined,
): string[] {
  const c0 = ev?.closest?.[0];
  if (!ev) return [];
  if (!c0) return ["未精确命中 · 无近似候选记录（待人工核对）"];
  const label =
    `${c0.no ? `${c0.no} ` : ""}${c0.name}`.trim() || "无近似候选记录";
  return [
    `未精确命中 · 近似候选「${label}」相似度 ${(c0.sim * 100).toFixed(0)}%（待人工核对）`,
  ];
}
