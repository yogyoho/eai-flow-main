import type { AccentColor, BusinessDomainKey, StageTag } from "../types";

/**
 * 通用分类 —— 固定白名单，不属于任何业务域。
 * 数组顺序即 toolbar pill 中通用分类的展示顺序。
 */
export const UNIVERSAL_DOMAINS: BusinessDomainKey[] = [
  "universal",
  "admin",
];

export const UNIVERSAL_DOMAIN_SET: Set<BusinessDomainKey> = new Set(UNIVERSAL_DOMAINS);

/** 通用分类 label + accent（硬编码）。业务域按需自动分配。 */
export const DOMAIN_CONFIG: Record<string, { label: string; accent: AccentColor }> = {
  universal: { label: "通用工具", accent: "blue" },
  admin:     { label: "系统管理", accent: "slate" },
};

/** accent 调色板（通用分类占用后，业务域按首次出现顺序轮转） */
export const ACCENT_PALETTE: AccentColor[] = [
  "violet", "cyan", "amber", "emerald",
  "rose", "indigo", "teal", "orange", "sky", "blue",
];

/** 功能阶段标签中文映射 */
export const STAGE_LABELS: Record<StageTag, string> = {
  overview:    "概览",
  collect:     "采集",
  process:     "加工",
  collaborate: "协作",
  output:      "输出",
  retrieve:    "检索",
  manage:      "管理",
};

/**
 * 强调色 → 样式映射。
 * 完整字面量类名，确保 Tailwind v4 能静态扫描到并生成。
 */
export const ACCENT_STYLES: Record<
  AccentColor,
  { container: string; icon: string; tag: string }
> = {
  blue: {
    container: "bg-gradient-to-br from-blue-500/20 to-blue-500/10 ring-blue-500/25",
    icon: "text-blue-600 dark:text-blue-400",
    tag: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  },
  violet: {
    container: "bg-gradient-to-br from-violet-500/20 to-violet-500/10 ring-violet-500/25",
    icon: "text-violet-600 dark:text-violet-400",
    tag: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
  cyan: {
    container: "bg-gradient-to-br from-cyan-500/20 to-cyan-500/10 ring-cyan-500/25",
    icon: "text-cyan-600 dark:text-cyan-400",
    tag: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300",
  },
  amber: {
    container: "bg-gradient-to-br from-amber-500/20 to-amber-500/10 ring-amber-500/25",
    icon: "text-amber-600 dark:text-amber-400",
    tag: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  emerald: {
    container: "bg-gradient-to-br from-emerald-500/20 to-emerald-500/10 ring-emerald-500/25",
    icon: "text-emerald-600 dark:text-emerald-400",
    tag: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  rose: {
    container: "bg-gradient-to-br from-rose-500/20 to-rose-500/10 ring-rose-500/25",
    icon: "text-rose-600 dark:text-rose-400",
    tag: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  },
  indigo: {
    container: "bg-gradient-to-br from-indigo-500/20 to-indigo-500/10 ring-indigo-500/25",
    icon: "text-indigo-600 dark:text-indigo-400",
    tag: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  },
  teal: {
    container: "bg-gradient-to-br from-teal-500/20 to-teal-500/10 ring-teal-500/25",
    icon: "text-teal-600 dark:text-teal-400",
    tag: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
  },
  orange: {
    container: "bg-gradient-to-br from-orange-500/20 to-orange-500/10 ring-orange-500/25",
    icon: "text-orange-600 dark:text-orange-400",
    tag: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
  },
  sky: {
    container: "bg-gradient-to-br from-sky-500/20 to-sky-500/10 ring-sky-500/25",
    icon: "text-sky-600 dark:text-sky-400",
    tag: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  slate: {
    container: "bg-gradient-to-br from-slate-500/20 to-slate-500/10 ring-slate-500/25",
    icon: "text-slate-600 dark:text-slate-300",
    tag: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
  },
};

/**
 * 获取业务域的中文标签。
 * 优先查 DOMAIN_CONFIG（通用分类），否则将 key 本身作为 label（业务域的 key 即中文名）。
 */
export function getDomainLabel(key: BusinessDomainKey): string {
  return DOMAIN_CONFIG[key]?.label ?? key;
}

/**
 * 获取业务域的 accent 颜色。
 * 通用分类使用预定义 accent；业务域从调色板轮转分配（按首次出现顺序确定性映射）。
 */
export function getDomainAccent(
  key: BusinessDomainKey,
  domainOrder: BusinessDomainKey[],
): AccentColor {
  if (DOMAIN_CONFIG[key]) return DOMAIN_CONFIG[key].accent;

  const idx = domainOrder.indexOf(key);
  if (idx === -1) return "blue"; // fallback
  return ACCENT_PALETTE[idx % ACCENT_PALETTE.length];
}
