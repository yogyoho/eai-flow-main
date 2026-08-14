import { describe, expect, it } from "vitest";

import { buildWhere, esc, sqlFor } from "@/extensions/bid-quote/api";
import {
  EMPTY_FILTERS,
  type ChartFilter,
  type FilterState,
  matchesSelfAttribute,
} from "@/extensions/bid-quote/types";

describe("matchesSelfAttribute", () => {
  it("all/undefined → 全过", () => {
    expect(matchesSelfAttribute(null, "all")).toBe(true);
    expect(matchesSelfAttribute(null, undefined)).toBe(true);
  });
  it("self_dominant: ≥50;outsource_dominant: <50", () => {
    expect(matchesSelfAttribute("60.0", "self_dominant")).toBe(true);
    expect(matchesSelfAttribute("49.9", "self_dominant")).toBe(false);
    expect(matchesSelfAttribute("30.0", "outsource_dominant")).toBe(true);
    expect(matchesSelfAttribute("50.0", "outsource_dominant")).toBe(false);
  });
  it("pct 为 null(我方无数据)不匹配任何属性分支", () => {
    expect(matchesSelfAttribute(null, "self_dominant")).toBe(false);
    expect(matchesSelfAttribute(null, "outsource_dominant")).toBe(false);
  });
});

describe("esc", () => {
  it("转义单引号", () => {
    expect(esc("O'Brien")).toBe("O''Brien");
    expect(esc("正常")).toBe("正常");
  });
});

describe("buildWhere", () => {
  it("空过滤返回 1=1", () => {
    expect(buildWhere(EMPTY_FILTERS, "mock_bid.project_name")).toBe("1=1");
  });
  it("projects → IN(乱序输入也按拼音序输出,保证 queryKey 规范化)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["乙", "甲"] };
    expect(buildWhere(g, "mock_bid.project_name")).toBe(
      "1=1 AND project_name IN ('甲','乙')",
    );
  });
  it("competitors → 统一 EXISTS 语义(筛“有选中友商参与的项目”,保留我方行)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    const w = buildWhere(g, "mock_bid.project_name");
    expect(w).toContain(
      "EXISTS (SELECT 1 FROM mock_bid c2 WHERE c2.project_name = mock_bid.project_name",
    );
    expect(w).toContain("c2.bidder_name IN ('友A')");
    // 不再产出裸 bidder_name IN(会把仅我方查询清成空集,C1)
    expect(w).not.toContain(" bidder_name IN");
  });
  it("competitors + 别名外层(b.project_name)→ 关联列跟随别名", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    const w = buildWhere(g, "b.project_name");
    expect(w).toContain("c2.project_name = b.project_name");
    expect(w).not.toContain("mock_bid.project_name");
  });
  it("日期范围", () => {
    const g: FilterState = {
      ...EMPTY_FILTERS,
      dateFrom: "2025-01-01",
      dateTo: "2025-12-31",
    };
    expect(buildWhere(g, "mock_bid.project_name")).toBe(
      "1=1 AND bid_date >= '2025-01-01' AND bid_date <= '2025-12-31'",
    );
  });
  it("chart.amountSegment", () => {
    const chart: ChartFilter = { amountSegment: "100to500w" };
    expect(
      buildWhere(EMPTY_FILTERS, "mock_bid.project_name", chart),
    ).toContain("winning_price >= 1000000 AND winning_price < 5000000");
  });
  it("chart.goodsName", () => {
    const chart: ChartFilter = { goodsName: ["塔器"] };
    expect(buildWhere(EMPTY_FILTERS, "mock_bid.project_name", chart)).toBe(
      "1=1 AND goods_name IN ('塔器')",
    );
  });
  it("单引号转义进 SQL", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["O'Brien厂"] };
    expect(buildWhere(g, "mock_bid.project_name")).toBe(
      "1=1 AND project_name IN ('O''Brien厂')",
    );
  });
  it("全局 + 每图 AND 叠加", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲"] };
    const chart: ChartFilter = { amountSegment: "lt100w" };
    const w = buildWhere(g, "mock_bid.project_name", chart);
    expect(w).toBe(
      "1=1 AND project_name IN ('甲') AND winning_price < 1000000",
    );
  });
});

describe("sqlFor 组装", () => {
  it("selfRate:WHERE ours + AND 过滤 + GROUP BY 尾部齐全", () => {
    const g: FilterState = { ...EMPTY_FILTERS, projects: ["甲"] };
    const sql = sqlFor("selfRate", g);
    expect(sql).toContain(
      "WHERE b.bidder_role='ours' AND 1=1 AND project_name IN ('甲')",
    );
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
  it("selfRate + competitors → EXISTS 关联 b.project_name(非恒真、不清空我方行)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A", "友C"] };
    const sql = sqlFor("selfRate", g);
    expect(sql).toContain(
      "EXISTS (SELECT 1 FROM mock_bid c2 WHERE c2.project_name = b.project_name",
    );
    expect(sql).toContain("c2.bidder_name IN ('友A','友C')");
    expect(sql).toContain("WHERE b.bidder_role='ours' AND 1=1 AND EXISTS");
  });
  it("composition + competitors → EXISTS 关联 b.project_name(我方聚合不被 IN 清空)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    const sql = sqlFor("composition", g);
    expect(sql).toContain("c2.project_name = b.project_name");
    expect(sql).not.toContain(" bidder_name IN");
  });
  it("summary/showdown + competitors → EXISTS 关联 mock_bid.project_name(未别名外层)", () => {
    const g: FilterState = { ...EMPTY_FILTERS, competitors: ["友A"] };
    expect(sqlFor("summary", g)).toContain(
      "c2.project_name = mock_bid.project_name",
    );
    expect(sqlFor("showdown", g)).toContain(
      "c2.project_name = mock_bid.project_name",
    );
  });
});
