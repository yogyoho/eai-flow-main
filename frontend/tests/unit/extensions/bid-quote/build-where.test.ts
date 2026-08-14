import { describe, expect, it } from "vitest";

import { buildWhere, esc } from "@/extensions/bid-quote/api";
import { EMPTY_FILTERS, type ChartFilter, type FilterState } from "@/extensions/bid-quote/types";

describe("esc", () => {
  it("转义单引号", () => {
    expect(esc("O'Brien")).toBe("O''Brien");
    expect(esc("正常")).toBe("正常");
  });
});

describe("buildWhere", () => {
  it("空过滤返回 1=1", () => {
    expect(buildWhere(EMPTY_FILTERS)).toBe("1=1");
  });
  it("projects → IN", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲", "乙"] };
    expect(buildWhere(g)).toBe("1=1 AND project_name IN ('甲','乙')");
  });
  it("competitors → bidder_name IN(普通模式)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    expect(buildWhere(g)).toBe("1=1 AND bidder_name IN ('友A')");
  });
  it("competitors + useCompetitorExists → EXISTS(仅我方查询)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    const w = buildWhere(g, undefined, true);
    expect(w).toContain("EXISTS");
    expect(w).toContain("c2.bidder_name IN ('友A')");
  });
  it("日期范围", () => {
    const g: FilterState = { ...EMPTY_FILTERS, dateFrom: "2025-01-01", dateTo: "2025-12-31" };
    expect(buildWhere(g)).toBe("1=1 AND bid_date >= '2025-01-01' AND bid_date <= '2025-12-31'");
  });
  it("chart.amountSegment", () => {
    const chart: ChartFilter = { amountSegment: "100to500w" };
    expect(buildWhere(EMPTY_FILTERS, chart)).toContain("winning_price >= 1000000 AND winning_price < 5000000");
  });
  it("chart.goodsName", () => {
    const chart: ChartFilter = { goodsName: ["塔器"] };
    expect(buildWhere(EMPTY_FILTERS, chart)).toBe("1=1 AND goods_name IN ('塔器')");
  });
  it("单引号转义进 SQL", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["O'Brien厂"] };
    expect(buildWhere(g)).toBe("1=1 AND project_name IN ('O''Brien厂')");
  });
  it("全局 + 每图 AND 叠加", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲"] };
    const chart: ChartFilter = { amountSegment: "lt100w" };
    const w = buildWhere(g, chart);
    expect(w).toBe("1=1 AND project_name IN ('甲') AND winning_price < 1000000");
  });
});
