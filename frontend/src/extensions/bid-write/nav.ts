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
  | "materials_library"
  | "generate"
  | "workbench"
  | "review"
  | "export"
  | "registry";

export const WRITE_PAGE_PATHS: Record<WritePage, string> = {
  projects: "/bid-write",
  intake: "/bid-write/intake",
  materials: "/bid-write/materials",
  materials_library: "/bid-write/materials-library",
  generate: "/bid-write/generate",
  workbench: "/bid-write/workbench",
  review: "/bid-write/review",
  export: "/bid-write/export",
  registry: "/bid-write/registry",
};

const LAST_TASK_STORAGE_KEY = "bw-last-task";

function writeTaskPageStorageKey(taskId: string): string {
  return `bw-task-page:${taskId}`;
}

function isWritePage(value: string): value is WritePage {
  return Object.hasOwn(WRITE_PAGE_PATHS, value);
}

export function writeTaskHref(page: WritePage, taskId: string): string {
  return `${WRITE_PAGE_PATHS[page]}?task_id=${encodeURIComponent(taskId)}`;
}

export function rememberTaskPage(taskId: string, page: WritePage): void {
  try {
    const storage = globalThis.localStorage;
    const pageKey = writeTaskPageStorageKey(taskId);
    if (
      storage?.getItem(LAST_TASK_STORAGE_KEY) === taskId &&
      storage.getItem(pageKey) === page
    ) {
      return;
    }
    storage.setItem(pageKey, page);
    storage.setItem(LAST_TASK_STORAGE_KEY, taskId);
  } catch {
    // SSR 与浏览器隐私模式都可能没有可写 storage；导航记忆必须静默降级。
  }
}

export function lastVisitedPage(taskId: string): WritePage | null {
  try {
    const page = globalThis.localStorage?.getItem(
      writeTaskPageStorageKey(taskId),
    );
    return page && isWritePage(page) ? page : null;
  } catch {
    return null;
  }
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

  let rememberedTaskId: string | null = null;
  try {
    rememberedTaskId = globalThis.localStorage?.getItem(
      LAST_TASK_STORAGE_KEY,
    ) ?? null;
  } catch {
    rememberedTaskId = null;
  }
  if (
    rememberedTaskId &&
    tasks.some((task) => task.id === rememberedTaskId)
  ) {
    return rememberedTaskId;
  }

  return tasks[0]?.id ?? null;
}
