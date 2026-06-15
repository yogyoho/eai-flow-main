import type { LucideIcon } from "lucide-react";

/** 业务分类标识 */
export type CategoryKey =
  | "writing"
  | "project"
  | "document"
  | "knowledge"
  | "report"
  | "admin";

/** 排序模式 */
export type SortMode = "default" | "alphabetical" | "favorites-first";

/** 图标容器强调色（每类一个色调） */
export type AccentColor =
  | "blue"
  | "violet"
  | "cyan"
  | "amber"
  | "emerald"
  | "slate";

/** 单个应用的定义 */
export interface AppDefinition {
  /** 唯一标识 */
  id: string;
  /** 应用名称 */
  name: string;
  /** 一句话描述（1-2 行） */
  description: string;
  /** Lucide 图标组件 */
  icon: LucideIcon;
  /** 所属分类 */
  category: CategoryKey;
  /** 路由路径（点击跳转） */
  path: string;
  /**
   * License 模块 key（对应 useLicense.hasModule 的入参）。
   * 为 null 表示无需 license，始终可见。
   */
  licenseModule: string | null;
  /** 仅管理员可见（role_name === "Super Admin"） */
  adminOnly?: boolean;
  /** 默认排序权重（越小越靠前） */
  sortOrder: number;
  /** 拼音排序键（用于按字母 A-Z 排序，无需引入 pinyin 依赖） */
  sortKey: string;
  /** 内置应用（不可删除） */
  isBuiltin: boolean;
}

/** 分类定义 */
export interface CategoryDef {
  key: CategoryKey;
  /** 中文标签 */
  label: string;
  /** 强调色 */
  accent: AccentColor;
}

/** 分类筛选值（含 "all"） */
export type CategoryFilter = CategoryKey | "all";
