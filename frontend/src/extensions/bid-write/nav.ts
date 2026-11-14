/**
 * bid-write 侧栏导航纯工具。
 *
 * 任务链页互跳统一走 `taskHref`（保留 `task_id`，与 bid-review 同款），
 * 治理页（注册表）保持裸路径。徽标只使用后端 `engine_meta.matrix_counts`
 * 的真实计数；未加载/未统计时不渲染（禁伪零）。
 */

import type { WriteTaskOut } from "./types";

export type WritePage =
  | "projects"
  | "intake"
  | "materials"
  | "generate"
  | "workbench"
  | "review"
  | "export"
  | "registry";

export const WRITE_PAGE_PATHS: Record<WritePage, string> = {
  projects: "/bid-write",
  intake: "/bid-write/intake",
  materials: "/bid-write/materials",
  generate: "/bid-write/generate",
  workbench: "/bid-write/workbench",
  review: "/bid-write/review",
  export: "/bid-write/export",
  registry: "/bid-write/registry",
};

export function writeTaskHref(page: WritePage, taskId: string): string {
  return `${WRITE_PAGE_PATHS[page]}?task_id=${encodeURIComponent(taskId)}`;
}

export interface WriteNavBadges {
  active: number;
  blocked: number;
}

export function writeNavBadges(
  tasks: WriteTaskOut[],
  effectiveTaskId: string | null,
): WriteNavBadges {
  const active = tasks.filter((task) =>
    ["created", "parsing", "extracting"].includes(task.status),
  ).length;
  const task =
    tasks.find((item) => item.id === effectiveTaskId) ?? tasks[0] ?? null;
  const blocked = task?.engine_meta?.matrix_counts?.blocked;
  return {
    active,
    blocked: typeof blocked === "number" ? blocked : 0,
  };
}

export function effectiveWriteTaskId(
  tasks: WriteTaskOut[],
  requestedId: string | null,
): string | null {
  if (requestedId && tasks.some((task) => task.id === requestedId)) {
    return requestedId;
  }
  return tasks[0]?.id ?? null;
}
