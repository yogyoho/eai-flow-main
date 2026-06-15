import type { AccentColor, CategoryDef, CategoryKey } from "../types";

/**
 * 分类定义 —— 顺序即默认展示顺序。
 * 每个分类绑定一个强调色，用于应用卡片图标容器的色调。
 */
export const CATEGORIES: CategoryDef[] = [
  { key: "writing", label: "创作中心", accent: "blue" },
  { key: "project", label: "项目协作", accent: "violet" },
  { key: "document", label: "文档协作", accent: "cyan" },
  { key: "knowledge", label: "知识管理", accent: "amber" },
  { key: "report", label: "成果输出", accent: "emerald" },
  { key: "admin", label: "系统管理", accent: "slate" },
];

export const CATEGORY_MAP: Record<CategoryKey, CategoryDef> = Object.fromEntries(
  CATEGORIES.map((c) => [c.key, c]),
) as Record<CategoryKey, CategoryDef>;

/**
 * 强调色 → 样式映射。
 * 完整字面量类名，确保 Tailwind v4 能静态扫描到并生成。
 * - container: 图标容器渐变底 + ring 颜色（透明度足以在白底上清晰可辨）
 * - icon: 图标文字色
 * - tag: 分类角标底色 + 文字色（呼应图标容器，形成统一色彩系统）
 */
export const ACCENT_STYLES: Record<
  AccentColor,
  { container: string; icon: string; tag: string }
> = {
  blue: {
    container:
      "bg-gradient-to-br from-blue-500/20 to-blue-500/10 ring-blue-500/25",
    icon: "text-blue-600 dark:text-blue-400",
    tag: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  },
  violet: {
    container:
      "bg-gradient-to-br from-violet-500/20 to-violet-500/10 ring-violet-500/25",
    icon: "text-violet-600 dark:text-violet-400",
    tag: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
  cyan: {
    container:
      "bg-gradient-to-br from-cyan-500/20 to-cyan-500/10 ring-cyan-500/25",
    icon: "text-cyan-600 dark:text-cyan-400",
    tag: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  },
  amber: {
    container:
      "bg-gradient-to-br from-amber-500/20 to-amber-500/10 ring-amber-500/25",
    icon: "text-amber-600 dark:text-amber-400",
    tag: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  emerald: {
    container:
      "bg-gradient-to-br from-emerald-500/20 to-emerald-500/10 ring-emerald-500/25",
    icon: "text-emerald-600 dark:text-emerald-400",
    tag: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  slate: {
    container:
      "bg-gradient-to-br from-slate-500/20 to-slate-500/10 ring-slate-500/25",
    icon: "text-slate-600 dark:text-slate-300",
    tag: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  },
};
