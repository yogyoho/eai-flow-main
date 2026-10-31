/**
 * 侧栏流程化纯工具(UX 重构 Plan 1 / spec §3)。
 * 任务链页互跳统一走 taskHref(后续逐步替代组件私有 workbenchHref);徽标计数
 * 与「最近命中任务」定位在此,layout 与页面共用同一口径。状态词表与 TasksView
 * 列表 pill 保持同词汇(改一处须同步另一处)。
 */
import type { TaskOut } from "./types";

export type TaskPage =
  | "tasks"
  | "parsing"
  | "workbench"
  | "baseline"
  | "review";

const PAGE_PATHS: Record<TaskPage, string> = {
  tasks: "/bid-review",
  // Plan6 (spec §4.3):解析与字段抽取归拢专屏
  parsing: "/bid-review/parsing",
  workbench: "/bid-review/workbench",
  baseline: "/bid-review/baseline",
  review: "/bid-review/review",
};

export function taskHref(page: TaskPage, taskId: string): string {
  return `${PAGE_PATHS[page]}?task_id=${encodeURIComponent(taskId)}`;
}

/** 状态词表(与 TasksView statusPill 同词汇;后端终态无 completed)。 */
export const TASK_STATUS_LABELS: Record<string, string> = {
  created: "已创建",
  parsing: "解析中",
  extracting: "基准提取中",
  awaiting_confirm: "待基准确认",
  running: "进行中",
  done: "已完成",
  failed: "失败",
};

export function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABELS[status] ?? status;
}

/** 在途态(「进行中」徽标口径,同 TasksView seg active)。 */
const ACTIVE_STATUSES = new Set(["parsing", "extracting", "running"]);

export interface SidebarBadges {
  running: number;
  awaitingConfirm: number;
  reviewTodo: number;
}

export function sidebarBadges(tasks: TaskOut[]): SidebarBadges {
  return {
    running: tasks.filter((t) => ACTIVE_STATUSES.has(t.status)).length,
    awaitingConfirm: tasks.filter((t) => t.status === "awaiting_confirm")
      .length,
    reviewTodo: tasks.reduce((sum, t) => sum + (t.need_human_count ?? 0), 0),
  };
}

/** 徽标点击直达用:第一个命中任务 id(列表为 owner 内返回序)。 */
export function firstTaskIdFor(
  tasks: TaskOut[],
  badge: keyof SidebarBadges,
): string | null {
  if (badge === "running") {
    return tasks.find((t) => ACTIVE_STATUSES.has(t.status))?.id ?? null;
  }
  if (badge === "awaitingConfirm") {
    return tasks.find((t) => t.status === "awaiting_confirm")?.id ?? null;
  }
  return tasks.find((t) => (t.need_human_count ?? 0) > 0)?.id ?? null;
}
