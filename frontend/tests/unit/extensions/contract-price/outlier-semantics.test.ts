/**
 * EAI-CUSTOM F3a 离群语义分层 — 整文档成片判定纯函数单测。
 * 对应源: src/extensions/contract-price/outlier-semantics.ts
 */

import { describe, expect, test } from "@rstest/core";

import {
  OUTLIER_DOC_DEVIATION_THRESHOLD,
  OUTLIER_DOC_MIN_OUTLIERS,
  OUTLIER_DOC_RATIO_THRESHOLD,
  baselineShiftDocIds,
  buildBaselineTooltips,
  docOutlierProfile,
  medianOf,
  rowDeviationPct,
  rowOutlierTier,
  type OutlierStatRow,
} from "@/extensions/contract-price/outlier-semantics";

function row(partial: Partial<OutlierStatRow> & { id: string; documentId: string }): OutlierStatRow {
  return {
    isOutlier: false,
    unitPrice: null,
    clusterMedian: null,
    ...partial,
  };
}

describe("medianOf", () => {
  test("empty input → null", () => {
    expect(medianOf([])).toBeNull();
  });

  test("odd length picks the middle", () => {
    expect(medianOf([3, 1, 2])).toBe(2);
  });

  test("even length averages the middle two", () => {
    expect(medianOf([4, 1, 3, 2])).toBe(2.5);
  });
});

describe("rowDeviationPct", () => {
  test("prefers the backend-provided deviation", () => {
    expect(rowDeviationPct(row({ id: "1", documentId: "d", deviationPct: 0.5, unitPrice: 1, clusterMedian: 100 }))).toBe(0.5);
  });

  test("computes from unitPrice/clusterMedian as fallback", () => {
    expect(rowDeviationPct(row({ id: "1", documentId: "d", unitPrice: 110, clusterMedian: 100 }))).toBeCloseTo(0.1);
    expect(rowDeviationPct(row({ id: "1", documentId: "d", unitPrice: 90, clusterMedian: 100 }))).toBeCloseTo(-0.1);
  });

  test("null when price/median unavailable or median is zero", () => {
    expect(rowDeviationPct(row({ id: "1", documentId: "d", unitPrice: null, clusterMedian: 100 }))).toBeNull();
    expect(rowDeviationPct(row({ id: "1", documentId: "d", unitPrice: 10, clusterMedian: null }))).toBeNull();
    expect(rowDeviationPct(row({ id: "1", documentId: "d", unitPrice: 10, clusterMedian: 0 }))).toBeNull();
  });
});

describe("docOutlierProfile", () => {
  test("no outlier rows → never a baseline shift", () => {
    const p = docOutlierProfile([
      row({ id: "1", documentId: "d", unitPrice: 100, clusterMedian: 100 }),
    ]);
    expect(p.isBaselineShift).toBe(false);
    expect(p.outlierCount).toBe(0);
  });

  test("single outlier row is a scattered outlier, NOT a baseline shift (min-outliers guard)", () => {
    // 单行文档整行离群(占比 1.0)且偏离 40% —— 但散点异常必须保持红色
    const p = docOutlierProfile([
      row({ id: "1", documentId: "d", isOutlier: true, unitPrice: 140, clusterMedian: 100 }),
    ]);
    expect(p.outlierRatio).toBeGreaterThanOrEqual(OUTLIER_DOC_RATIO_THRESHOLD);
    expect(p.isBaselineShift).toBe(false);
  });

  test("ratio rule fires: outlier share >= 0.60 with enough support", () => {
    const rows = [
      row({ id: "1", documentId: "d", isOutlier: true, unitPrice: 105, clusterMedian: 100 }),
      row({ id: "2", documentId: "d", isOutlier: true, unitPrice: 104, clusterMedian: 100 }),
      row({ id: "3", documentId: "d", unitPrice: 100, clusterMedian: 100 }),
      row({ id: "4", documentId: "d", unitPrice: 101, clusterMedian: 100 }),
    ];
    // 偏离仅 4-5% (< 10%),只靠占比 2/4=0.5... 0.5 < 0.6 → false
    expect(docOutlierProfile(rows).isBaselineShift).toBe(false);

    const rows3 = rows.slice(0, 3); // 2/3 = 0.667 >= 0.6 → ratio 触发
    const p = docOutlierProfile(rows3);
    expect(p.outlierRatio).toBeGreaterThanOrEqual(OUTLIER_DOC_RATIO_THRESHOLD);
    expect(p.outlierCount).toBeGreaterThanOrEqual(OUTLIER_DOC_MIN_OUTLIERS);
    expect(p.isBaselineShift).toBe(true);
  });

  test("deviation rule fires even when the ratio is small", () => {
    const rows = [
      row({ id: "1", documentId: "d", isOutlier: true, unitPrice: 112, clusterMedian: 100 }),
      row({ id: "2", documentId: "d", isOutlier: true, unitPrice: 115, clusterMedian: 100 }),
      ...Array.from({ length: 8 }, (_, i) => row({ id: `n${i}`, documentId: "d", unitPrice: 100, clusterMedian: 100 })),
    ];
    const p = docOutlierProfile(rows);
    expect(p.outlierRatio).toBeLessThan(OUTLIER_DOC_RATIO_THRESHOLD); // 0.2
    expect(p.deviationMedian).toBeCloseTo(0.135); // median(0.12, 0.15)
    expect(p.isBaselineShift).toBe(true);
  });

  test("small deviations below threshold do not fire", () => {
    const rows = [
      row({ id: "1", documentId: "d", isOutlier: true, unitPrice: 103, clusterMedian: 100 }),
      row({ id: "2", documentId: "d", isOutlier: true, unitPrice: 102, clusterMedian: 100 }),
      ...Array.from({ length: 8 }, (_, i) => row({ id: `n${i}`, documentId: "d", unitPrice: 100, clusterMedian: 100 })),
    ];
    const p = docOutlierProfile(rows);
    expect(Math.abs(p.deviationMedian as number)).toBeLessThan(OUTLIER_DOC_DEVIATION_THRESHOLD);
    expect(p.isBaselineShift).toBe(false);
  });

  test("mixed-direction outliers cancel out (median 0) → not a baseline shift", () => {
    const rows = [
      row({ id: "1", documentId: "d", isOutlier: true, unitPrice: 130, clusterMedian: 100 }),
      row({ id: "2", documentId: "d", isOutlier: true, unitPrice: 70, clusterMedian: 100 }),
      row({ id: "3", documentId: "d", unitPrice: 100, clusterMedian: 100 }),
      row({ id: "4", documentId: "d", unitPrice: 101, clusterMedian: 100 }),
    ];
    const p = docOutlierProfile(rows);
    // 占比 2/4=0.5 < 0.6;偏离中位 0 → 两条规则都不触发
    expect(p.deviationMedian).toBe(0);
    expect(p.isBaselineShift).toBe(false);
  });
});

describe("baselineShiftDocIds + rowOutlierTier", () => {
  const rows: OutlierStatRow[] = [
    // doc A: 整文档成片(3 行里 2 行离群,占比 0.667)
    row({ id: "a1", documentId: "A", isOutlier: true, unitPrice: 120, clusterMedian: 100 }),
    row({ id: "a2", documentId: "A", isOutlier: true, unitPrice: 118, clusterMedian: 100 }),
    row({ id: "a3", documentId: "A", unitPrice: 100, clusterMedian: 100 }),
    // doc B: 单行散点离群,保持红色
    row({ id: "b1", documentId: "B", isOutlier: true, unitPrice: 140, clusterMedian: 100 }),
    row({ id: "b2", documentId: "B", unitPrice: 100, clusterMedian: 100 }),
    row({ id: "b3", documentId: "B", unitPrice: 100, clusterMedian: 100 }),
  ];

  test("only shifted docs land in the set", () => {
    const ids = baselineShiftDocIds(rows);
    expect(ids.has("A")).toBe(true);
    expect(ids.has("B")).toBe(false);
  });

  test("tier: outlier rows of shifted docs downgrade; scattered outliers stay red", () => {
    expect(rowOutlierTier(rows[0]!, baselineShiftDocIds(rows))).toBe("baseline-shift");
    expect(rowOutlierTier(rows[2]!, baselineShiftDocIds(rows))).toBe("normal");
    expect(rowOutlierTier(rows[3]!, baselineShiftDocIds(rows))).toBe("outlier");
  });
});

describe("buildBaselineTooltips", () => {
  test("tooltip carries direction, X%, N docs and the per-doc baseline overview", () => {
    const rows: OutlierStatRow[] = [
      row({ id: "a1", documentId: "A", isOutlier: true, unitPrice: 120, clusterMedian: 100, clusterId: "c1", contractNo: "C-A", clusterDocCount: 2 }),
      row({ id: "a2", documentId: "A", isOutlier: true, unitPrice: 118, clusterMedian: 100, clusterId: "c1", contractNo: "C-A", clusterDocCount: 2 }),
      row({ id: "a3", documentId: "A", unitPrice: 100, clusterMedian: 100, clusterId: "c1", contractNo: "C-A" }),
      row({ id: "b1", documentId: "B", unitPrice: 100, clusterMedian: 100, clusterId: "c1", contractNo: "C-B" }),
      row({ id: "b2", documentId: "B", unitPrice: 102, clusterMedian: 100, clusterId: "c1", contractNo: "C-B" }),
    ];
    const tips = buildBaselineTooltips(rows);
    // 只有成片文档的离群行拿得到 tooltip
    expect(tips.has("a1")).toBe(true);
    expect(tips.has("a2")).toBe(true);
    expect(tips.has("a3")).toBe(false);
    expect(tips.has("b1")).toBe(false);

    const tip = tips.get("a1") as string;
    expect(tip).toContain("跨合同基线差异");
    expect(tip).toContain("高于");
    expect(tip).toContain("19.0%"); // outlier 行偏离中位 median(0.20, 0.18)
    expect(tip).toContain("簇内含 2 份合同");
    // 各文档基线概览: C-A 全行偏离中位 median(0.20,0.18,0)=0.18;C-B median(0,0.02)=0.01
    expect(tip).toContain("C-A +18.0%");
    expect(tip).toContain("C-B +1.0%");
  });

  test("negative baseline renders 低于 and a minus percentage", () => {
    const rows: OutlierStatRow[] = [
      row({ id: "a1", documentId: "A", isOutlier: true, unitPrice: 85, clusterMedian: 100, clusterId: "c1", contractNo: "C-A", clusterDocCount: 1 }),
      row({ id: "a2", documentId: "A", isOutlier: true, unitPrice: 88, clusterMedian: 100, clusterId: "c1", contractNo: "C-A", clusterDocCount: 1 }),
      row({ id: "b1", documentId: "B", unitPrice: 100, clusterMedian: 100, clusterId: "c1", contractNo: "C-B" }),
      row({ id: "b2", documentId: "B", unitPrice: 101, clusterMedian: 100, clusterId: "c1", contractNo: "C-B" }),
      row({ id: "b3", documentId: "B", unitPrice: 99, clusterMedian: 100, clusterId: "c1", contractNo: "C-B" }),
    ];
    const tips = buildBaselineTooltips(rows);
    const tip = tips.get("a1") as string;
    expect(tip).toContain("低于");
    expect(tip).toContain("13.5%"); // median(-0.15, -0.12)
    expect(tip).toContain("簇内含 1 份合同");
  });

  test("clusterDocCount missing falls back to the in-view doc count of the cluster", () => {
    const rows: OutlierStatRow[] = [
      row({ id: "a1", documentId: "A", isOutlier: true, unitPrice: 120, clusterMedian: 100, clusterId: "c1", contractNo: "C-A" }),
      row({ id: "a2", documentId: "A", isOutlier: true, unitPrice: 118, clusterMedian: 100, clusterId: "c1", contractNo: "C-A" }),
      row({ id: "b1", documentId: "B", unitPrice: 100, clusterMedian: 100, clusterId: "c1", contractNo: "C-B" }),
    ];
    const tip = buildBaselineTooltips(rows).get("a1") as string;
    expect(tip).toContain("簇内含 2 份合同"); // 视图内同簇文档数 A+B
  });

  test("scattered outliers (non-shifted docs) get no tooltip", () => {
    const rows: OutlierStatRow[] = [
      row({ id: "s1", documentId: "S", isOutlier: true, unitPrice: 140, clusterMedian: 100, clusterId: "c1" }),
      row({ id: "s2", documentId: "S", unitPrice: 100, clusterMedian: 100, clusterId: "c1" }),
    ];
    expect(buildBaselineTooltips(rows).size).toBe(0);
  });
});
