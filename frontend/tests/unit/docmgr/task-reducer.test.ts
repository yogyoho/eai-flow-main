import { describe, expect, test } from "@rstest/core";

import {
  type DocAITaskAction,
  type DocAITaskState,
  initialTaskState,
  taskReducer,
} from "@/extensions/docmgr/DocAITaskArea";

const s0 = () => initialTaskState("polish");

// reducer 返回 DocAITaskState | null；流式测试路径恒非空——helper 收窄，免去逐处 !
const run = (s: DocAITaskState | null, action: DocAITaskAction): DocAITaskState => {
  const next = taskReducer(s, action);
  if (!next) throw new Error("unexpected null state");
  return next;
};

describe("taskReducer（任务区状态机）", () => {
  test("section_start → streaming 卡片；skipped → skipped", () => {
    let s = run(s0(), { type: "section_start", index: 0, total: 2, title: "一" });
    expect(s.sections[0]).toMatchObject({ index: 0, status: "streaming", title: "一" });
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二", skipped: true });
    expect(s.sections[1]).toMatchObject({ index: 1, status: "skipped" });
    expect(s.skipped).toEqual([1]);
  });

  test("ops 非空 → ready；空 → unchanged", () => {
    let s = run(s0(), { type: "section_start", index: 0, total: 1, title: "一" });
    s = run(s, { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] });
    expect(s.sections[0]).toMatchObject({ status: "ready" });
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二" });
    s = run(s, { type: "ops", index: 1, ops: [] });
    expect(s.sections[1]).toMatchObject({ status: "unchanged" });
  });

  test("section_error → failed 且后续节继续", () => {
    let s = run(s0(), { type: "section_start", index: 0, total: 2, title: "一" });
    s = run(s, { type: "section_error", index: 0, message: "失败" });
    expect(s.sections[0]).toMatchObject({ status: "failed", error: "失败" });
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二" });
    expect(s.sections[1]).toMatchObject({ status: "streaming" });
    expect(s.failed).toEqual([0]);
  });

  test("applySection → applied；reverted 批量回 applied", () => {
    let s = run(s0(), { type: "section_start", index: 0, total: 1, title: "一" });
    s = run(s, { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] });
    s = run(s, { type: "apply_section", index: 0 });
    expect(s.sections[0]?.status).toBe("applied");
    s = run(s, { type: "reverted" });
    expect(s.sections[0]?.status).toBe("ready");
  });

  test("summary 事件与 done 收口", () => {
    let s = run(s0(), { type: "summary", content: "摘要" });
    expect(s.summary).toBe("摘要");
    s = run(s, { type: "done", total: 0, failed: [], skipped: [], message: "提示" });
    expect(s).toMatchObject({ running: false, message: "提示" });
  });

  test("cancel 丢弃未确认（streaming/ready/failed 清除,applied/unchanged/skipped 保留）", () => {
    let s = run(s0(), { type: "section_start", index: 0, total: 3, title: "一" });
    s = run(s, { type: "ops", index: 0, ops: [{ op: "replace_section", anchor: "一", content: "x" }] });
    s = run(s, { type: "apply_section", index: 0 });
    s = run(s, { type: "section_start", index: 1, total: 3, title: "二" });
    s = run(s, { type: "section_start", index: 2, total: 3, title: "三", skipped: true });
    s = run(s, { type: "cancel" });
    expect(s.sections.map((x) => x.status)).toEqual(["applied", "skipped"]);
    expect(s.running).toBe(false);
    expect(s.message).toContain("已取消");
  });

  test("dismiss 清空任务", () => {
    expect(taskReducer(s0(), { type: "dismiss" })).toBeNull();
  });
});
