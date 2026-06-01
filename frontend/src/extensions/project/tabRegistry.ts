"use client";

import {
  CheckCircle,
  FileText,
  GitBranch,
  History,
  LayoutDashboard,
  Link,
  Settings,
  type LucideIcon,
} from "lucide-react";

import type { ProjectPermissions } from "./types";

// ── Project Identity ──

/** Derived identity context for tab visibility decisions. */
export interface ProjectIdentity {
  /** User's role in this project */
  projectRole: string | null;
  /** Effective permissions from Role.permissions + phase duty bonuses */
  permissions: string[];
  /** Phase duties from project_members.phase_duties */
  phaseDuties: Record<string, { duty: string; role?: string }> | null;
  /** Whether user is system admin */
  isAdmin: boolean;
  /** Check if user has ANY of the given duties */
  hasAnyDuty: (duties: string[]) => boolean;
  /** Check if user has ANY of the given permissions */
  hasAnyPermission: (perms: string[]) => boolean;
}

// ── Tab Definition ──

export interface TabDefinition {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Component key — resolved by ProjectWorkspace to lazy-load components */
  componentKey: string;
  /** Visibility predicate based on user's project identity */
  visibleWhen: (ctx: ProjectIdentity) => boolean;
  /** Sort order (lower = first) */
  order: number;
}

// ── Registry ──

export const TAB_REGISTRY: TabDefinition[] = [
  {
    id: "overview",
    label: "项目概览",
    icon: LayoutDashboard,
    componentKey: "overview",
    visibleWhen: () => true,
    order: 1,
  },
  {
    id: "workflow",
    label: "流程看板",
    icon: GitBranch,
    componentKey: "workflow",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission(["project:edit", "outline:edit", "ai:start_writing", "member:add"]),
    order: 2,
  },
  {
    id: "editor",
    label: "文档编辑",
    icon: FileText,
    componentKey: "editor",
    visibleWhen: (ctx) =>
      ctx.hasAnyDuty(["write", "edit", "review", "approve"]) ||
      ctx.hasAnyPermission([
        "chapter:write_any",
        "chapter:write_own",
        "chapter:review",
        "approval:review",
        "approval:approve",
        "source:view",
      ]),
    order: 3,
  },
  {
    id: "review",
    label: "审核工作台",
    icon: CheckCircle,
    componentKey: "review",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission(["approval:review", "approval:approve", "approval:submit"]),
    order: 4,
  },
  {
    id: "traceability",
    label: "溯源",
    icon: Link,
    componentKey: "traceability",
    visibleWhen: () => true,
    order: 5,
  },
  {
    id: "history",
    label: "版本历史",
    icon: History,
    componentKey: "history",
    visibleWhen: () => true,
    order: 6,
  },
  {
    id: "settings",
    label: "项目设置",
    icon: Settings,
    componentKey: "settings",
    visibleWhen: (ctx) =>
      ctx.hasAnyPermission(["settings:edit", "project:edit", "project:delete", "member:add", "member:remove"]),
    order: 99,
  },
];

// ── Helpers ──

/** Get visible tabs for a given project identity, sorted by order. */
export function getVisibleTabs(ctx: ProjectIdentity): TabDefinition[] {
  return TAB_REGISTRY
    .filter((tab) => tab.visibleWhen(ctx))
    .sort((a, b) => a.order - b.order);
}

/** Create a ProjectIdentity from the API response data. */
export function createProjectIdentity(data: ProjectPermissions): ProjectIdentity {
  return {
    projectRole: data.role,
    permissions: data.permissions ?? [],
    phaseDuties: data.phaseDuties ?? null,
    isAdmin: data.isAdmin ?? false,
    hasAnyDuty: (duties: string[]) => {
      if (!data.phaseDuties) return false;
      return Object.values(data.phaseDuties).some((d) => duties.includes(d.duty));
    },
    hasAnyPermission: (perms: string[]) => {
      if (data.isAdmin) return true;
      if (!data.permissions?.length) return false;
      return perms.some((p) => data.permissions.includes(p));
    },
  };
}
