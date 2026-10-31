import { describe, expect, it } from "@rstest/core";

import {
  firstTaskIdFor,
  sidebarBadges,
  taskHref,
  taskStatusLabel,
} from "@/extensions/bid-review/nav";
import type { TaskOut } from "@/extensions/bid-review/types";

// UX 重构 Plan 1 T1:侧栏流程化纯工具——taskHref 统一任务链页互跳;
// 状态词表与 TasksView 列表 pill 同词汇;徽标计数(进行中/待基准确认/复核待办)
// 与「徽标点击直达」的 firstTaskIdFor 共用一套口径(layout 与页面都从这里取)。
function task(partial: Partial<TaskOut>): TaskOut {
  return {
    id: "t0",
    owner_id: "o",
    status: "created",
    mode: "deep",
    progress: {},
    error: null,
    engine_meta: {},
    prev_task_id: null,
    created_at: "2026-10-31T00:00:00Z",
    fatal_unhandled: null,
    need_human_count: null,
    ...partial,
  };
}

describe("taskHref", () => {
  it("任务链页拼 task_id 并编码", () => {
    expect(taskHref("workbench", "abc")).toBe(
      "/bid-review/workbench?task_id=abc",
    );
    expect(taskHref("review", "a b")).toBe("/bid-review/review?task_id=a%20b");
    expect(taskHref("baseline", "x")).toBe("/bid-review/baseline?task_id=x");
    expect(taskHref("tasks", "x")).toBe("/bid-review?task_id=x");
  });
});

describe("taskStatusLabel", () => {
  it("与 TasksView 列表 pill 同词汇,未知状态原样回落", () => {
    expect(taskStatusLabel("awaiting_confirm")).toBe("待基准确认");
    expect(taskStatusLabel("extracting")).toBe("基准提取中");
    expect(taskStatusLabel("failed")).toBe("失败");
    expect(taskStatusLabel("mystery")).toBe("mystery");
  });
});

describe("sidebarBadges", () => {
  it("进行中含三在途态;复核待办是 need_human_count 求和(null=0 禁伪零)", () => {
    const tasks = [
      task({ id: "a", status: "parsing" }),
      task({ id: "b", status: "running" }),
      task({ id: "c", status: "awaiting_confirm" }),
      task({ id: "d", status: "awaiting_confirm" }),
      task({ id: "e", status: "done", need_human_count: 3 }),
      task({ id: "f", status: "done", need_human_count: 2 }),
      task({ id: "g", status: "done", need_human_count: null }),
    ];
    expect(sidebarBadges(tasks)).toEqual({
      running: 2,
      awaitingConfirm: 2,
      reviewTodo: 5,
    });
  });
  it("空列表全零", () => {
    expect(sidebarBadges([])).toEqual({
      running: 0,
      awaitingConfirm: 0,
      reviewTodo: 0,
    });
  });
});

describe("firstTaskIdFor", () => {
  const tasks = [
    task({ id: "run1", status: "extracting" }),
    task({ id: "await1", status: "awaiting_confirm" }),
    task({ id: "todo1", status: "done", need_human_count: 4 }),
  ];
  it("按徽标返回第一个命中任务 id", () => {
    expect(firstTaskIdFor(tasks, "running")).toBe("run1");
    expect(firstTaskIdFor(tasks, "awaitingConfirm")).toBe("await1");
    expect(firstTaskIdFor(tasks, "reviewTodo")).toBe("todo1");
  });
  it("无命中返回 null(徽标隐藏时不会调用,防御)", () => {
    expect(firstTaskIdFor([], "running")).toBeNull();
    expect(
      firstTaskIdFor([task({ id: "d", status: "done" })], "awaitingConfirm"),
    ).toBeNull();
  });
});
