/**
 * bid-quote 图表共享主题常量 — DeepSeek usage 页风格(2026-08-15 仪表盘重构定稿)。
 * token 来源:三区块已确认原型(.superpowers/brainstorm 下 19219 会话 content 目录的 block1~3 三份 html),
 * 严格对齐:暖白底/白卡细边 14px 圆角/单主色蓝/克制网格/tabular 数字。
 * EAI-CUSTOM: 仪表盘按原型为浅色单主题实现,不随暗色主题切换(原型即验收标准);
 * 存量导出名(BLUE/GRID/AXIS...)保持不变,4 张既有图改这里即自动换肤。
 */

export const PAGE_BG = "#fbfafa"; // 页面暖白底
export const CARD = "#ffffff"; // 卡片纯白
export const CARD_BORDER = "rgba(0,0,0,0.06)"; // 卡片细边
export const GRID = "#f0f0ef"; // 网格线(替代原 cyber 半透明网格)
export const AXIS_FILL = "#9c9da0"; // 弱文字色兼轴标签
export const AXIS = { fontSize: 11, fill: AXIS_FILL };
export const CURSOR = { fill: "rgba(0,0,0,0.04)" }; // 悬停列高亮(极轻)

export const BLUE = "#4D6BFE"; // DeepSeek 主蓝(我方/主系列)
export const COMPETITOR = "#c6cdf6"; // 友商弱化色
export const ACCENT_SOFT = "#eef1ff"; // 主蓝极浅底(badge/insight 条)
export const AMBER = "#f0a122"; // 友商对比琥珀
export const GREEN = "#20b26c"; // 胜/正向
export const RED = "#e5484d"; // 负/警示
export const RED_55 = "#e5484dbf"; // 我方落标(原型 0.75 透明度红)
export const THRESHOLD_RED = RED; // 门槛参考线(与警示同源)

export const INK = "#1b1c1d"; // 主文字
export const INK_2 = "#6b6c6e"; // 次级文字
export const INK_3 = "#9c9da0"; // 弱文字

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
