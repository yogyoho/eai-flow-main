import { describe, expect, test } from "@rstest/core";

import {
  nearMissHintLines,
  subItemMarker,
} from "@/extensions/bid-review/components/checklist-display";

describe("subItemMarker", () => {
  test("UNKNOWN → ?(P3.2 子行门)", () => {
    expect(subItemMarker({ status: "UNKNOWN", found: 0 })).toBe("?");
  });
  test("命中 → ✓", () => {
    expect(subItemMarker({ status: "MATCHED", found: 1 })).toBe("✓");
  });
  test("PARTIAL → ✗", () => {
    expect(subItemMarker({ status: "PARTIAL", found: 1 })).toBe("✗");
  });
  test("MISSING → ✗", () => {
    expect(subItemMarker({ status: "MISSING", found: 0 })).toBe("✗");
  });
  test("MATCHED 且 found=0 → ✗(防御性复核钉,审查 Minor-1)", () => {
    expect(subItemMarker({ status: "MATCHED", found: 0 })).toBe("✗");
  });
});

describe("nearMissHintLines", () => {
  test("closest 在场(no+name)→ 含候选与百分比", () => {
    expect(
      nearMissHintLines({
        channels: ["name"],
        pool: 1,
        closest: [{ no: "3-2", name: "中标通知书回执", sim: 0.8333 }],
      }),
    ).toEqual([
      "未精确命中 · 近似候选「3-2 中标通知书回执」相似度 83%（待人工核对）",
    ]);
  });
  test("closest[0] 无 no → 只显 name", () => {
    expect(
      nearMissHintLines({
        channels: ["name"],
        pool: 1,
        closest: [{ no: "", name: "中标通知书回执", sim: 0.8 }],
      }),
    ).toEqual([
      "未精确命中 · 近似候选「中标通知书回执」相似度 80%（待人工核对）",
    ]);
  });
  test("sim 0.856 → 86%(就近舍入钉,审查 Minor-2)", () => {
    expect(
      nearMissHintLines({
        channels: [],
        pool: 1,
        closest: [{ no: "", name: "回执", sim: 0.856 }],
      }),
    ).toEqual(["未精确命中 · 近似候选「回执」相似度 86%（待人工核对）"]);
  });
  test("no 有值 name 空串 → label 只含 no(审查附加)", () => {
    expect(
      nearMissHintLines({
        channels: [],
        pool: 1,
        closest: [{ no: "3-2", name: "", sim: 0.8 }],
      }),
    ).toEqual(["未精确命中 · 近似候选「3-2」相似度 80%（待人工核对）"]);
  });
  test("closest 空 → 无近似候选记录", () => {
    expect(nearMissHintLines({ channels: [], pool: 0, closest: [] })).toEqual([
      "未精确命中 · 无近似候选记录（待人工核对）",
    ]);
  });
  test("null/undefined(旧网关)→ 零渲染", () => {
    expect(nearMissHintLines(null)).toEqual([]);
    expect(nearMissHintLines(undefined)).toEqual([]);
  });
});
