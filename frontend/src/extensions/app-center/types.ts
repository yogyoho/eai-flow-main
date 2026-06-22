import type { LucideIcon } from "lucide-react";

/** 业务域标识（动态扩展） */
export type BusinessDomainKey = string;

/** 功能阶段标签 */
export type StageTag =
  | "overview"     // 概览
  | "collect"      // 采集
  | "process"      // 加工
  | "collaborate"  // 协作
  | "output"       // 输出
  | "retrieve"     // 检索
  | "manage";      // 管理

/** 排序模式 */
export type SortMode = "default" | "alphabetical" | "favorites-first";

/** 图标容器强调色 */
export type AccentColor =
  | "blue"
  | "violet"
  | "cyan"
  | "amber"
  | "emerald"
  | "rose"
  | "indigo"
  | "teal"
  | "orange"
  | "sky"
  | "slate";

/** 单个应用的定义 */
export interface AppDefinition {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  /** 所属业务域 */
  businessDomain: BusinessDomainKey;
  /** 功能阶段标签（可选） */
  stageTag?: StageTag;
  path: string;
  licenseModule: string | null;
  adminOnly?: boolean;
  sortOrder: number;
  sortKey: string;
  isBuiltin: boolean;
}

/** 领域筛选值（含 "all"） */
export type DomainFilter = BusinessDomainKey | "all";
