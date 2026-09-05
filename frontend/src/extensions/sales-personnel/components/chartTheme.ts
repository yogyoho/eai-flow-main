/**
 * sales-personnel 图表共享主题常量 —— 克隆自 biz-pipeline/chartTheme.ts(DeepSeek usage 页风格),
 * 2026-08-18 仪表盘重构随原型 docs/superpowers/specs/2026-08-18-sales-personnel-dashboard-prototype.html 落地。
 * 模块自包含惯例(与 ①③ 同构克隆,不做跨 extension import);token 若调整,各模块需同步。
 * EAI-CUSTOM: 仪表盘按原型为浅色单主题实现,不随暗色主题切换(原型即验收标准)。
 */

export const PAGE_BG = "#fbfafa"; // 页面暖白底
export const CARD = "#ffffff"; // 卡片纯白
export const CARD_BORDER = "rgba(0,0,0,0.06)"; // 卡片细边
export const GRID = "#f0f0ef"; // 网格线(实线,dataviz:虚线网格是反模式)
export const AXIS_FILL = "#9c9da0"; // 弱文字色兼轴标签
export const AXIS = { fontSize: 11, fill: AXIS_FILL };
export const CURSOR = { fill: "rgba(0,0,0,0.04)" }; // 悬停列高亮(极轻)

export const BLUE = "#4D6BFE"; // 主蓝(出勤/差旅单系列)
export const GREEN = "#20b26c"; // 正向(达标)
export const RED = "#e5484d"; // 负/警示(缺勤/驳回/低于目标)
export const ORANGE = "#eb6834"; // 出差(考勤堆叠 slot2)
export const LEAVE = "#8b98ad"; // 请假(语义中性,故意低彩度;靠图例+tooltip+数据表兜底)
export const AMBER = "#eda100"; // 待审批(橙+红对 CVD 不可分,故用琥珀非橙)
export const ACCENT_SOFT = "#eef1ff"; // 主蓝极浅底(badge/选中 chip)

export const INK = "#1b1c1d"; // 主文字
export const INK_2 = "#6b6c6e"; // 次级文字
export const INK_3 = "#9c9da0"; // 弱文字
