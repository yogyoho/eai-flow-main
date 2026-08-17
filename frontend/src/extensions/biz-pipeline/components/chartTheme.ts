/**
 * biz-pipeline 图表共享主题常量 —— 克隆自 bid-quote/chartTheme.ts(DeepSeek usage 页风格,
 * 2026-08-15 定稿),2026-08-17 仪表盘重构随原型 docs/superpowers/specs/2026-08-17-biz-pipeline-dashboard-prototype.html 落地。
 * 模块自包含惯例(与 ① 同构克隆,不做跨 extension import);① 若再调 token,两处需同步。
 * EAI-CUSTOM: 仪表盘按原型为浅色单主题实现,不随暗色主题切换(原型即验收标准)。
 */

export const PAGE_BG = "#fbfafa"; // 页面暖白底
export const CARD = "#ffffff"; // 卡片纯白
export const CARD_BORDER = "rgba(0,0,0,0.06)"; // 卡片细边
export const GRID = "#f0f0ef"; // 网格线(实线,dataviz:虚线网格是反模式)
export const AXIS_FILL = "#9c9da0"; // 弱文字色兼轴标签
export const AXIS = { fontSize: 11, fill: AXIS_FILL };
export const CURSOR = { fill: "rgba(0,0,0,0.04)" }; // 悬停列高亮(极轻)

export const BLUE = "#4D6BFE"; // 主蓝(投标/已开票/漏斗单系列)
export const GREEN = "#20b26c"; // 胜/正向(中标)
export const RED = "#e5484d"; // 负/警示(待开票文字)
export const RED_55 = "#e5484dbf"; // 待开票段(原型 0.75 透明度红)
export const ACCENT_SOFT = "#eef1ff"; // 主蓝极浅底(badge)

export const INK = "#1b1c1d"; // 主文字
export const INK_2 = "#6b6c6e"; // 次级文字
export const INK_3 = "#9c9da0"; // 弱文字
