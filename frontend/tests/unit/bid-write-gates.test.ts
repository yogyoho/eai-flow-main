import { describe, expect, it } from "@rstest/core";

import { gatesFromData } from "@/extensions/bid-write/helpers";

describe("bid-write delivery gates", () => {
  it("renders four passing cards when every source has no blocking state", () => {
    const gates = gatesFromData({
      matrixBlocked: 0,
      assertionsBlocked: false,
      noMaterialCount: 0,
      revisionApproved: true,
    });

    expect(gates.map((gate) => gate.key)).toEqual([
      "matrix",
      "assertions",
      "materials",
      "revision",
    ]);
    expect(gates.map((gate) => gate.label)).toEqual([
      "矩阵记录已全部核对",
      "预审查检查通过",
      "素材缺口已处理",
      "正式正文文件审批",
    ]);
    expect(gates.map((gate) => gate.state)).toEqual([
      "pass",
      "pass",
      "pass",
      "pass",
    ]);
    expect(gates.map((gate) => gate.detail)).toEqual([
      "响应矩阵无阻断行",
      "检查通过",
      "素材全部有佐证",
      "正文已批准",
    ]);
  });

  it("marks blocking counts and approval states as failures", () => {
    const gates = gatesFromData({
      matrixBlocked: 3,
      assertionsBlocked: true,
      noMaterialCount: 2,
      revisionApproved: false,
    });

    expect(gates.map((gate) => gate.state)).toEqual([
      "fail",
      "fail",
      "fail",
      "fail",
    ]);
    expect(gates.map((gate) => gate.detail)).toEqual([
      "3 行待人工核对",
      "存在阻止导出的检查失败",
      "2 条要求无对应素材",
      "正文待审批",
    ]);
  });

  it("keeps loading data honest as unknown", () => {
    const gates = gatesFromData({
      matrixBlocked: null,
      assertionsBlocked: null,
      noMaterialCount: null,
      revisionApproved: null,
    });

    expect(gates.map((gate) => gate.state)).toEqual([
      "unknown",
      "unknown",
      "unknown",
      "unknown",
    ]);
    expect(
      gates.every((gate) => gate.detail === "暂无数据"),
    ).toBe(true);
  });

  it("renders a mixed checklist without turning absent data into failure", () => {
    const gates = gatesFromData({
      matrixBlocked: 1,
      assertionsBlocked: null,
      noMaterialCount: 0,
      revisionApproved: false,
    });

    expect(gates.map((gate) => [gate.key, gate.state])).toEqual([
      ["matrix", "fail"],
      ["assertions", "unknown"],
      ["materials", "pass"],
      ["revision", "fail"],
    ]);
  });
});
