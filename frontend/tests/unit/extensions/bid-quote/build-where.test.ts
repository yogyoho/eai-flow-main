import { describe, expect, it } from "vitest";

import { buildWhere, esc, sqlFor } from "@/extensions/bid-quote/api";
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
  it("projects → IN(乱序输入也按拼音序输出,保证 queryKey 规范化)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["乙", "甲"] };
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

describe("sqlFor 组装", () => {
  it("selfRate:WHERE ours + AND 过滤 + GROUP BY 尾部齐全", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲"] };
    const sql = sqlFor("selfRate", g);
    expect(sql).toContain("WHERE b.bidder_role='ours' AND 1=1 AND project_name IN ('甲')");
    expect(sql).toContain("GROUP BY b.project_name");
    expect(sql).toContain("ORDER BY self_rate DESC");
  });
  it("segment:base 已含 WHERE,过滤用 AND 接续不产生双 WHERE", () => {
    const sql = sqlFor("segment", EMPTY_FILTERS);
    expect(sql).toContain("WHERE bidder_role='ours' AND 1=1");
    expect(sql).not.toMatch(/WHERE.*WHERE/);
    expect(sql).toContain("GROUP BY 1");
  });
  it("summary:WHERE 直接拼接", () => {
    const sql = sqlFor("summary", EMPTY_FILTERS);
    expect(sql).toContain("FROM mock_bid WHERE 1=1");
  });
});
