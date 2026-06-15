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
 * 强调色 → 图标容器样式映射。
 * 完整字面量类名，确保 Tailwind v4 能静态扫描到并生成。
 */
export const ACCENT_STYLES: Record<
  AccentColor,
  { container: string; icon: string }
> = {
  blue: {
    container:
      "bg-gradient-to-br from-blue-500/15 to-blue-500/5 ring-blue-500/20",
    icon: "text-blue-600 dark:text-blue-400",
  },
  violet: {
    container:
      "bg-gradient-to-br from-violet-500/15 to-violet-500/5 ring-violet-500/20",
    icon: "text-violet-600 dark:text-violet-400",
  },
  cyan: {
    container:
      "bg-gradient-to-br from-cyan-500/15 to-cyan-500/5 ring-cyan-500/20",
    icon: "text-cyan-600 dark:text-cyan-400",
  },
  amber: {
    container:
      "bg-gradient-to-br from-amber-500/15 to-amber-500/5 ring-amber-500/20",
    icon: "text-amber-600 dark:text-amber-400",
  },
  emerald: {
    container:
      "bg-gradient-to-br from-emerald-500/15 to-emerald-500/5 ring-emerald-500/20",
    icon: "text-emerald-600 dark:text-emerald-400",
  },
  slate: {
    container:
      "bg-gradient-to-br from-slate-500/15 to-slate-500/5 ring-slate-500/20",
    icon: "text-slate-600 dark:text-slate-300",
  },
};
