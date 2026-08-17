import { describe, expect, it } from "@rstest/core";

import {
  esc,
  sqlCompetitorGoods,
  sqlCompetitorProfile,
  sqlHead2Head,
  sqlKpiByYear,
  sqlPremiumCurve,
  sqlPriceBand,
  sqlShareStack,
  sqlTrend,
} from "@/extensions/bid-quote/api";
import { EMPTY_FILTERS, type FilterState } from "@/extensions/bid-quote/types";

// 带全部过滤维度的状态:验证 EXISTS 外引用与注入转义
const f: FilterState = {
  projects: ["甲项目"],
  competitors: ["北方重工"],
  dateFrom: "2023-01-01",
  dateTo: "2025-12-31",
};

describe("三问框架新图 SQL 形状(2026-08-15)", () => {
  it("sqlTrend: 按季度 date_trunc + 我方/友商双率", () => {
    const sql = sqlTrend(f);
    expect(sql).toContain("date_trunc('quarter'");
    // 季度标签在 SQL 侧 to_char 出 "23Q1":timestamptz 序列化为 UTC 串,前端 new Date 取 UTC 会整体错一季
    expect(sql).toContain(`to_char(qtr, 'YY"Q"Q')`);
    expect(sql).toContain("bidder_role='ours'");
    expect(sql).toContain("bidder_role='competitor'");
  });

  it("sqlPremiumCurve: 固定 6 桶边界 + 我方行过滤 + EXISTS 正确外引用", () => {
    const sql = sqlPremiumCurve(f);
    // CASE 桶边界(前端 BUCKETS 标签与之一一对应,改边界必须两处同步)
    expect(sql).toContain("prem <= -0.05"); // 首桶是闭边界
    for (const edge of ["0.03", "0.06", "0.10"]) {
      expect(sql).toContain(`prem < ${edge}`);
    }
    // 只统计我方报价的行(不是全部投标)
    expect(sql).toContain("WHERE b.bidder_role='ours'");
    // 口径锁:溢价相对【友商最低价】(相对中标价会退化——胜场溢价恒 0)
    expect(sql).toContain("MIN(winning_price) AS cmin_price");
    expect(sql).not.toContain("w.won");
    // 友商过滤为行级语义(2026-08-17),前缀引用 base 的 FROM 表(未别名 mock_bid)
    expect(sql).toContain(
      "(mock_bid.bidder_name IN ('北方重工') OR mock_bid.bidder_role='ours')",
    );
  });

  it("sqlPriceBand: 三分位数 + 成本底线走 mock_bid_item", () => {
    const sql = sqlPriceBand(f);
    expect(sql).toContain("percentile_cont(0.25)");
    expect(sql).toContain("percentile_cont(0.50)");
    expect(sql).toContain("percentile_cont(0.75)");
    expect(sql).toContain("JOIN mock_bid_item i ON i.bid_id = b.bid_id");
    // 成本只算我方行,且按项目聚合再取段内均值(直接 SUM 全段会把十几个项目的成本叠成天文数字)
    expect(sql).toContain("b.bidder_role='ours'");
    expect(sql).toContain("AVG(pc.cost) AS cost_floor");
  });

  it("sqlCompetitorProfile: 平均溢价 = 相对同项目中标价", () => {
    const sql = sqlCompetitorProfile(f);
    expect(sql).toContain("AVG((b.winning_price - w.win_price) / w.win_price)");
    expect(sql).toContain("b.bidder_role='competitor'");
  });

  it("sqlCompetitorGoods: 仅中标行 + 外层别名 b 的 EXISTS 外引用", () => {
    const sql = sqlCompetitorGoods(f);
    expect(sql).toContain("b.won");
    // 行级语义(2026-08-17):外层别名是 b
    expect(sql).toContain(
      "(b.bidder_name IN ('北方重工') OR b.bidder_role='ours')",
    );
  });

  it("sqlHead2Head: 竞争对手名单引号转义 + 双方同场判定", () => {
    const sql = sqlHead2Head(f, "东方'宏业");
    expect(sql).toContain("东方''宏业"); // esc 转义,防注入/防语法错误
    expect(sql).toContain("HAVING BOOL_OR(bidder_role='ours')");
    expect(sql).toContain("EXTRACT(YEAR");
    // CTE 不能叫 both——PG 保留字(TRIM(BOTH…)),运行期 PostgresSyntaxError(bug-1211)
    expect(sql).toContain("both_in AS (");
  });

  it("sqlShareStack: 只统计中标金额,按年", () => {
    const sql = sqlShareStack(f);
    expect(sql).toContain("FROM mock_bid WHERE won");
    expect(sql).toContain("EXTRACT(YEAR");
  });

  it("sqlKpiByYear: 空过滤 = 全量(无 EXISTS 片段),带过滤 = 注入安全", () => {
    expect(sqlKpiByYear(EMPTY_FILTERS)).not.toContain("EXISTS");
    const evil: FilterState = { ...EMPTY_FILTERS, projects: ["x' OR '1'='1"] };
    expect(sqlKpiByYear(evil)).toContain("x'' OR ''1''=''1"); // esc 已转义
  });

  it("esc: 单引号单源转义", () => {
    expect(esc("a'b")).toBe("a''b");
  });
});
