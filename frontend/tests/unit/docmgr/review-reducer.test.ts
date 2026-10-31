import { describe, expect, test } from "@rstest/core";

import { type DocAIFinding } from "@/extensions/api";
import {
  type DocAIReviewAction,
  type DocAIReviewState,
  initialReviewState,
  reviewReducer,
} from "@/extensions/docmgr/DocAIReviewArea";

// reducer 返回 DocAIReviewState | null（reset 路径）；流式测试路径恒非空——helper 收窄。
const run = (
  s: DocAIReviewState | null,
  action: DocAIReviewAction,
): DocAIReviewState => {
  const next = reviewReducer(s, action);
  if (!next) throw new Error("unexpected null state");
  return next;
};

const s0 = () => initialReviewState("consistency");

const mkFinding = (
  id: string,
  severity: "error" | "warn" | "info" = "warn",
  withFix = false,
): DocAIFinding => ({
  id,
  severity,
  anchor: "概述",
  excerpt: "蒸发损失系数",
  problem: "同词异形",
  suggestion: "统一为同一写法",
  ...(withFix
    ? { fix_op: { op: "replace_section", anchor: "概述", content: "修正后" } }
    : {}),
});

describe("reviewReducer（审查任务区状态机）", () => {
  test("start → running + 全量清空（含 total/summary/message）", () => {
    let s: DocAIReviewState | null = s0();
    s = run(s, {
      type: "section_start",
      index: 0,
      total: 3,
      title: "一",
    });
    s = run(s, {
      type: "finding",
      index: 0,
      finding: mkFinding("f1"),
    });
    s = run(s, {
      type: "done",
      total: 3,
      failed: [],
      skipped: [],
      summary: { error: 1, warn: 0, info: 0 },
    });
    // restart 场景模拟：再次 start 必须清空上一场审查的累计
    s = run(s, { type: "start", reviewType: "numbering" });
    expect(s.running).toBe(true);
    expect(s.reviewType).toBe("numbering");
    expect(s.entries).toEqual([]);
    expect(s.audited).toEqual([]);
    expect(s.failed).toEqual([]);
    expect(s.skipped).toEqual([]);
    expect(s.dismissedIds).toEqual([]);
    expect(s.total).toBeUndefined();
    expect(s.summary).toBeUndefined();
    expect(s.message).toBeUndefined();
  });

  test("section_start → 记已审节 + total 取 max（分母不缩水）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 5,
      title: "一",
    });
    expect(s.audited).toEqual([0]);
    expect(s.total).toBe(5);
    // 后端重跑/重试只报小 total → 分母保持旧值
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二" });
    expect(s.total).toBe(5);
    expect(s.audited).toEqual([0, 1]);
    // 同节重复 section_start（事件重放）→ 去重
    s = run(s, { type: "section_start", index: 0, total: 5, title: "一" });
    expect(s.audited).toEqual([0, 1]);
  });

  test("skipped 节（structured）→ 记 skipped 且不置 current", () => {
    const s = run(s0(), {
      type: "section_start",
      index: 1,
      total: 3,
      title: "表格节",
      skipped: true,
    });
    expect(s.skipped).toEqual([1]);
    expect(s.current).toBeUndefined();
    const s2 = run(s, {
      type: "section_start",
      index: 2,
      total: 3,
      title: "三",
    });
    expect(s2.current).toEqual({ index: 2, title: "三" });
  });

  test("finding → 按事件序追加（节桶由 sectionIndex 承载）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    s = run(s, {
      type: "section_start",
      index: 1,
      total: 2,
      title: "二",
    });
    // 节序与事件序交错的 findings：入桶保 event 序
    s = run(s, { type: "finding", index: 1, finding: mkFinding("b1") });
    s = run(s, { type: "finding", index: 0, finding: mkFinding("a1") });
    s = run(s, { type: "finding", index: 1, finding: mkFinding("b2") });
    expect(s.entries.map((e) => e.finding.id)).toEqual(["b1", "a1", "b2"]);
    expect(s.entries.map((e) => e.sectionIndex)).toEqual([1, 0, 1]);
  });

  test("finding 同 id 重放 → upsert 不重复追加", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, { type: "finding", index: 0, finding: mkFinding("f1") });
    s = run(s, { type: "finding", index: 0, finding: mkFinding("f1") });
    expect(s.entries.length).toBe(1);
  });

  test("section_error → 入 failed（去重）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    s = run(s, { type: "section_error", index: 0, message: "失败" });
    expect(s.failed).toEqual([0]);
    s = run(s, { type: "section_error", index: 0, message: "重试又失败" });
    expect(s.failed).toEqual([0]);
  });

  test("done → 收官 + failed/skipped 覆写 + total 取 max", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 4,
      title: "一",
    });
    s = run(s, {
      type: "section_start",
      index: 1,
      total: 4,
      title: "二",
      skipped: true,
    });
    s = run(s, { type: "section_error", index: 2, message: "失败" });
    s = run(s, {
      type: "done",
      total: 4,
      failed: [2],
      skipped: [1],
      summary: { error: 1, warn: 2, info: 0 },
    });
    expect(s.running).toBe(false);
    expect(s.total).toBe(4);
    expect(s.failed).toEqual([2]);
    expect(s.skipped).toEqual([1]);
    expect(s.summary).toEqual({ error: 1, warn: 2, info: 0 });
  });

  test("done 空表短路路径（无 summary 键）→ 计数全 0 不炸（Chunk 1 移交提示）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    // 后端 numbering/consistency 空表短路：done 无 summary 键
    s = run(s, {
      type: "done",
      total: 0,
      failed: [],
      skipped: [],
      message: "未发现术语变体",
    });
    expect(s.running).toBe(false);
    expect(s.summary).toEqual({ error: 0, warn: 0, info: 0 });
    expect(s.message).toBe("未发现术语变体");
    // total:0 不得缩水已见分母
    expect(s.total).toBe(2);
  });

  test("dismiss + restore：忽略可撤销，重复 dismiss 去重", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, { type: "finding", index: 0, finding: mkFinding("f1") });
    s = run(s, { type: "dismiss", id: "f1" });
    expect(s.dismissedIds).toEqual(["f1"]);
    s = run(s, { type: "dismiss", id: "f1" });
    expect(s.dismissedIds).toEqual(["f1"]);
    s = run(s, { type: "restore", id: "f1" });
    expect(s.dismissedIds).toEqual([]);
  });

  test("fail：流异常中断收官——failed/entries/total 保留，message 落位（不走 done 权威替换）", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    s = run(s, { type: "finding", index: 0, finding: mkFinding("f1") });
    s = run(s, { type: "section_error", index: 1, message: "超时" });
    s = run(s, { type: "fail", message: "连接中断" });
    expect(s.running).toBe(false);
    expect(s.message).toBe("连接中断");
    expect(s.current).toBeUndefined();
    // 已入册的失败节与 findings 原样保留——错误路径不得合成空权威清单
    expect(s.failed).toEqual([1]);
    expect(s.entries.map((e) => e.finding.id)).toEqual(["f1"]);
    expect(s.total).toBe(2);
  });

  test("total 不缩水（restart 用例）：restart 重开事件闸门且保留累计", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 3,
      title: "一",
    });
    s = run(s, { type: "finding", index: 0, finding: mkFinding("f1") });
    s = run(s, { type: "done", total: 3, failed: [], skipped: [] });
    expect(s.running).toBe(false);
    // 重开：running 复活、累计不丢
    s = run(s, { type: "restart" });
    expect(s.running).toBe(true);
    expect(s.total).toBe(3);
    expect(s.entries.length).toBe(1);
    // 闸门已重开：后续流事件（小 total）不再缩水分母
    s = run(s, { type: "section_start", index: 1, total: 1, title: "二" });
    expect(s.total).toBe(3);
    expect(s.audited).toEqual([0, 1]);
  });

  test("running 闸门：done/finish 后拒收在途流事件", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 2,
      title: "一",
    });
    s = run(s, { type: "done", total: 2, failed: [], skipped: [] });
    const frozen = s;
    s = run(s, { type: "section_start", index: 1, total: 2, title: "二" });
    expect(s).toBe(frozen);
    s = run(s, { type: "finding", index: 1, finding: mkFinding("late") });
    expect(s.entries.length).toBe(0);
    s = run(s, { type: "section_error", index: 1, message: "迟到" });
    expect(s.failed).toEqual([]);
  });

  test("fix_applied / fixes_reverted：单条翻已修复、整批撤销回退", () => {
    let s = run(s0(), {
      type: "section_start",
      index: 0,
      total: 1,
      title: "一",
    });
    s = run(s, {
      type: "finding",
      index: 0,
      finding: mkFinding("f1", "warn", true),
    });
    s = run(s, {
      type: "finding",
      index: 0,
      finding: mkFinding("f2", "info", true),
    });
    s = run(s, { type: "fix_applied", id: "f1" });
    expect(s.entries[0]!.fixed).toBe(true);
    expect(s.entries[1]!.fixed).toBe(false);
    s = run(s, { type: "fixes_reverted" });
    expect(s.entries.every((e) => !e.fixed)).toBe(true);
  });

  test("reset → null（任务区卸载）", () => {
    expect(reviewReducer(s0(), { type: "reset" })).toBeNull();
    // 空态 reset 幂等
    expect(reviewReducer(null, { type: "reset" })).toBeNull();
  });
});
