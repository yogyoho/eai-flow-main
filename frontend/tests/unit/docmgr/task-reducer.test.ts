import { describe, expect, test } from "@rstest/core";

import {
  type DocAITaskAction,
  type DocAITaskState,
  initialTaskState,
  taskReducer,
} from "@/extensions/docmgr/DocAITaskArea";

const s0 = () => initialTaskState("polish");

// reducer 返回 DocAITaskState | null；流式测试路径恒非空——helper 收窄，免去逐处 !
const run = (
  s: DocAITaskState | null,
  action: DocAITaskAction,
): DocAITaskState => {
  const next = taskReducer(s, action);
  if (!next) throw new Error("unexpected null state");
  return next;
};

describe("taskReducer（任务区状态机）", () => {
  test("section_start → streaming 卡片；skipped → skipped", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    expect(s.sections[0]).toMatchObject({
      index: 0,
      status: "streaming",
      title: "一",
    });
    s = run(s, {
      type: "section_start",
      index: 1,
      total: 2,
      title: "二",
      skipped: true,
    });
    expect(s.sections[1]).toMatchObject({ index: 1, status: "skipped" });
    expect(s.skipped).toEqual([1]);
  });

  test("ops 非空 → ready；空 → unchanged", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, {
      type: "ops",
      index: 0,
      ops: [{ op: "replace_section", anchor: "一", content: "x" }],
    });
    expect(s.sections[0]).toMatchObject({ status: "ready" });
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二" });
    s = run(s, { type: "ops", index: 1, ops: [] });
    expect(s.sections[1]).toMatchObject({ status: "unchanged" });
  });

  test("section_error → failed 且后续节继续", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    s = run(s, { type: "section_error", index: 0, message: "失败" });
    expect(s.sections[0]).toMatchObject({ status: "failed", error: "失败" });
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二" });
    expect(s.sections[1]).toMatchObject({ status: "streaming" });
    expect(s.failed).toEqual([0]);
  });

  test("applySection → applied；reverted 批量回 applied", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, {
      type: "ops",
      index: 0,
      ops: [{ op: "replace_section", anchor: "一", content: "x" }],
    });
    s = run(s, { type: "apply_section", index: 0 });
    expect(s.sections[0]?.status).toBe("applied");
    s = run(s, { type: "reverted" });
    expect(s.sections[0]?.status).toBe("ready");
  });

  test("summary 事件与 done 收口", () => {
    let s = run(s0(), { type: "summary", content: "摘要" });
    expect(s.summary).toBe("摘要");
    s = run(s, {
      type: "done",
      total: 0,
      failed: [],
      skipped: [],
      message: "提示",
    });
    expect(s).toMatchObject({ running: false, message: "提示" });
  });

  test("cancel 丢弃未确认（streaming/ready/failed 清除,applied/unchanged/skipped 保留）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 3,
      title: "一",
    });
    s = run(s, {
      type: "ops",
      index: 0,
      ops: [{ op: "replace_section", anchor: "一", content: "x" }],
    });
    s = run(s, { type: "apply_section", index: 0 });
    s = run(s, { type: "section_start", index: 1, total: 3, title: "二" });
    s = run(s, {
      type: "section_start",
      index: 2,
      total: 3,
      title: "三",
      skipped: true,
    });
    s = run(s, { type: "cancel" });
    expect(s.sections.map((x) => x.status)).toEqual(["applied", "skipped"]);
    expect(s.running).toBe(false);
    expect(s.message).toContain("已取消");
  });

  test("cancel 后拒收在途流事件（终审 I-2a）", () => {
    const s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 3,
      title: "一",
    });
    const cancelled = taskReducer(s, { type: "cancel" });
    if (!cancelled) throw new Error("unexpected null state");
    // guard 用例须直呼 taskReducer 断言引用不变——run helper 收窄了返回值，看不出拒收
    const afterStart = taskReducer(cancelled, {
      type: "section_start",
      index: 1,
      total: 3,
      title: "二",
    });
    const afterOps = taskReducer(afterStart, {
      type: "ops",
      index: 1,
      ops: [{ op: "replace_section", anchor: "二", content: "x" }],
    });
    const afterErr = taskReducer(afterOps, {
      type: "section_error",
      index: 2,
      message: "迟到失败",
    });
    expect(afterErr).toBe(cancelled);
    expect(cancelled.sections).toEqual([]);
    expect(cancelled.running).toBe(false);
  });

  test("restart 重开事件闸门（护 retry 路径, 终审 I-2a）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, { type: "done", total: 1, failed: [], skipped: [] });
    expect(s.running).toBe(false);
    s = run(s, { type: "restart", operation: "polish" });
    expect(s.running).toBe(true);
    expect(s.message).toBeUndefined();
    s = run(s, { type: "section_start", index: 0, total: 1, title: "一" });
    expect(s.sections[0]).toMatchObject({ index: 0, status: "streaming" });
  });

  test("dismiss 清空任务", () => {
    expect(taskReducer(s0(), { type: "dismiss" })).toBeNull();
  });

  // ── 全文操作 v2: 拒绝 / 恢复建议 ──────────────────────────────────

  test("reject_section → rejected，ops 保留、不入 failed、仍在列表（v2）", () => {
    const ops = [{ op: "replace_section", anchor: "一", content: "x" }];
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, { type: "ops", index: 0, ops });
    s = run(s, { type: "reject_section", index: 0 });
    expect(s.sections[0]).toMatchObject({ index: 0, status: "rejected" });
    expect(s.sections[0]?.ops).toEqual(ops);
    expect(s.failed).toEqual([]);
  });

  test("restore_section → rejected 反悔回 ready（ops 仍在）；非 rejected 不动（v2）", () => {
    const ops = [{ op: "replace_section", anchor: "一", content: "x" }];
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, { type: "ops", index: 0, ops });
    s = run(s, { type: "reject_section", index: 0 });
    s = run(s, { type: "restore_section", index: 0 });
    expect(s.sections[0]).toMatchObject({ status: "ready" });
    expect(s.sections[0]?.ops).toEqual(ops);
    // 非 rejected（如 applied）收到 restore 不变化
    const applied = run(
      {
        ...s,
        sections: s.sections.map((x) => ({ ...x, status: "applied" as const })),
      },
      { type: "restore_section", index: 0 },
    );
    expect(applied.sections[0]?.status).toBe("applied");
  });

  test("section_start 记录 total 供进度分母；部分重试 total 不缩水（复审#2）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 3,
      title: "一",
    });
    expect(s.total).toBe(3);
    // 部分重试 run 只报 total=1（旧卡仍在 state）——分母取 max 不得缩水回落
    s = run(s, { type: "restart", operation: "polish" });
    s = run(s, { type: "section_start", index: 0, total: 1, title: "一" });
    expect(s.total).toBe(3);
  });

  test("done 记录 total 供进度条；错误路径 total:0 不覆盖（v2）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 3,
      title: "一",
    });
    s = run(s, { type: "done", total: 3, failed: [], skipped: [] });
    expect(s.total).toBe(3);
    // apply 失败等错误路径复用 done 携带 message（total:0）——不得把进度分母清零
    s = run(s, {
      type: "done",
      total: 0,
      failed: [],
      skipped: [],
      message: "应用失败：x",
    });
    expect(s.total).toBe(3);
    // 分节重试 run（重审镜像断言）：section_start/done 都只带 total=1（后端
    // chosen=[i]）——max 守卫下分母不得从 3 缩回 1，否则重试完成时进度虚满
    s = run(s, { type: "restart", operation: "polish" });
    s = run(s, { type: "section_start", index: 1, total: 1, title: "二" });
    expect(s.total).toBe(3);
    s = run(s, { type: "done", total: 1, failed: [], skipped: [] });
    expect(s.total).toBe(3);
  });

  test("cancel 丢弃 rejected（v2 决策：取消仅保留 applied/unchanged/skipped）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 4,
      title: "一",
    });
    s = run(s, {
      type: "ops",
      index: 0,
      ops: [{ op: "replace_section", anchor: "一", content: "x" }],
    });
    s = run(s, { type: "apply_section", index: 0 });
    s = run(s, { type: "section_start", index: 1, total: 4, title: "二" });
    s = run(s, {
      type: "ops",
      index: 1,
      ops: [{ op: "replace_section", anchor: "二", content: "y" }],
    });
    s = run(s, { type: "reject_section", index: 1 });
    s = run(s, {
      type: "section_start",
      index: 3,
      total: 4,
      title: "四",
      skipped: true,
    });
    s = run(s, { type: "cancel" });
    // rejected 与 ready 同属未确认 → 取消即丢弃；仅 applied/skipped 幸存
    expect(s.sections.map((x) => [x.index, x.status])).toEqual([
      [0, "applied"],
      [3, "skipped"],
    ]);
  });
});
