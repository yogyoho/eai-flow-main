/**
 * geo-samples 共享主题常量 — forked from bid-quote/components/chartTheme.ts
 * (EAI-CUSTOM: geo-sample-bank Phase 1 沿用 bid-quote 原语体系,复制模式而非跨模块 import,
 * 与 bid-quote→contract-price 的 table.tsx 复制惯例一致)。
 * token 与 bid-quote 严格同值:暖白底/白卡细边 14px 圆角/单主色蓝/克制配色/tabular 数字。
 * 保持与 bid-quote 同名同值,换肤时对齐复制即可。
 */

export const PAGE_BG = "#fbfafa"; // 页面暖白底
export const CARD = "#ffffff"; // 卡片纯白
export const CARD_BORDER = "rgba(0,0,0,0.06)"; // 卡片细边
export const GRID = "#f0f0ef"; // 网格线(替代原 cyber 半透明网格)
export const AXIS_FILL = "#9c9da0"; // 弱文字色兼轴标签
export const AXIS = { fontSize: 11, fill: AXIS_FILL };
export const CURSOR = { fill: "rgba(0,0,0,0.04)" }; // 悬停列高亮(极轻)

export const BLUE = "#4D6BFE"; // 主蓝(主系列/进行中)
export const COMPETITOR = "#c6cdf6"; // 友商弱化色
export const ACCENT_SOFT = "#eef1ff"; // 主蓝极浅底(badge/待审标记行)
export const AMBER = "#f0a122"; // 待审/运行中琥珀
export const GREEN = "#20b26c"; // 胜/正向/完成
export const RED = "#e5484d"; // 负/警示/失败
export const RED_55 = "#e5484dbf"; // 弱化红
export const THRESHOLD_RED = RED; // 门槛参考线(与警示同源)

export const INK = "#1b1c1d"; // 主文字
export const INK_2 = "#6b6c6e"; // 次级文字
export const INK_3 = "#9c9da0"; // 弱文字

/**
 * X 轴长名称截断:优先按 市/省 断点截断,无断点退化为纯长度截断。
 * (随 chartTheme 一并复制,geo-samples 暂无图表,供后续扩展。)
 */
export function truncateLabel(label: string | null | undefined): string {
  // 兜底:label 来自 GROUP BY 列,null 组会让 .replace 抛错整卡崩掉
  return (label ?? "")
    .replace(/.{6,}?[市省]/, (m) => m.slice(0, 4) + "…")
    .replace(/^(.{4}).{5,}$/, "$1…");
}
