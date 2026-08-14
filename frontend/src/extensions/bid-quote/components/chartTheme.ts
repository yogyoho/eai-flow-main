/**
 * bid-quote 图表共享主题常量。原先在 DashboardView / SelfRateDistChart 各持一份,
 * 图B(SelfVsOutsourceChart)落地前收敛到此,三处图表共用,避免三份漂移。
 */

// EAI-CUSTOM: 项目 chart/success/destructive CSS 变量为完整颜色(非 HSL 通道),故图表用字面 hex
export const GRID = "rgba(100,116,139,0.22)";
export const AXIS_FILL = "#94a3b8";
export const AXIS = { fontSize: 11, fill: AXIS_FILL };
export const CURSOR = { fill: "rgba(148,163,184,0.15)" };
export const BLUE = "#3b82f6";
export const AMBER = "#f6bd16";
export const GREEN = "#10b981"; // 自产率达标(≥ 门槛)
export const RED_55 = "#f43f5e8c"; // destructive @ ~55%
export const THRESHOLD_RED = "#f43f5e"; // 门槛参考线

/**
 * X 轴长名称截断:优先按 市/省 断点截断,无断点(当前 seed 全部如此)退化为纯长度截断。
 * 与图C(自产率分布)保持同一链路,长项目/货物名不会挤爆 X 轴。
 */
export function truncateLabel(label: string | null | undefined): string {
  // 兜底:label 来自 GROUP BY 列,null 组会让 .replace 抛错整卡崩掉
  return (label ?? "")
    .replace(/.{6,}?[市省]/, (m) => m.slice(0, 4) + "…")
    .replace(/^(.{4}).{5,}$/, "$1…");
}
