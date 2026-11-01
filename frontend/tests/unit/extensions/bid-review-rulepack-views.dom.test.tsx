import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";

// EAI-CUSTOM (2026-10-30) 回归门:规则库按 2026-10-30 原型重整(#s9)+ 规则效果看板新页
// (#s10,/bid-review/metrics)。锁定六类行为:
// ① 规则包头卡(name/version/stage-chip rule_count/enabled pill)与只读 Switch(disabled);
// ② 规则表 .tbl:高误报(hit>0 且 fp/hit≥0.2)id 旁 pill-warn「误报 NN%」,stats 缺失显示
//    「—」不显示 0(伪零纪律);③ .seg 层级过滤(M5 §4.7:全部/L1 实质性/L3 一致性/高误报);
// ④ 看板四格 metric-strip = Σrule_count/Σfp/Σhit/Σadopted(跨规则包求和);⑤ 逐规则表按
//    fp 降序 + 高误报 FAIL 名单(.pill-err,仅收入高误报规则);⑥ 零回流诚实态(FAIL 名单
//    提示尚无数据,不伪造 PASS)与 note-bar 诚实说明(独立评测端点未接入)。
// M5(Plan10 §4.7/§4.8):判定算子列+规则五块抽屉(B5)+?rule= 深链;看板周趋势 6 柱 +
// FAIL 归因 foot(B6)+ FAIL 行 → 规则库深链(互跳②)。
const calls: Array<{ path: string }> = [];
let packPayload: unknown;
let responder: (path: string) => Response;
let mockParams = new URLSearchParams();

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, _init?: RequestInit) => {
    calls.push({ path });
    return responder(path);
  },
}));

rs.mock("next/navigation", () => ({
  useParams: () => ({}),
  usePathname: () => "/bid-review/rules",
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  useSearchParams: () => mockParams,
}));

// Radix Switch 在 happy-dom 下不稳定,且这里只断言 disabled/checked 契约,替身为 span
rs.mock("@/components/ui/switch", () => ({
  Switch: (props: { checked?: boolean; disabled?: boolean }) => (
    <span
      data-testid="pack-switch"
      data-checked={String(props.checked ?? false)}
      data-disabled={String(props.disabled ?? false)}
    />
  ),
}));

import { MetricsView } from "@/extensions/bid-review/components/MetricsView";
import { RulesView } from "@/extensions/bid-review/components/RulesView";

const PACK = {
  name: "bid-review-core",
  version: "1.0.0",
  rule_count: 3,
  rules: [
    {
      id: "R-001",
      name: "总价上限",
      layer: "L1",
      severity: "fatal",
      type: "deterministic",
      op: "lte",
    },
    {
      id: "R-002",
      name: "算术一致",
      layer: "L1",
      severity: "major",
      type: "hybrid",
      op: "steps",
    },
    {
      id: "R-003",
      name: "主体一致",
      layer: "L3",
      severity: "minor",
      type: "semantic",
      op: "gte",
    },
  ],
  stats: {
    "R-001": { hit: 10, fp: 3, adopted: 5 },
    "R-002": { hit: 10, fp: 1, adopted: 8 },
  },
  enabled: true,
};

/** B5 五块明细夹具(GET /rulepacks/bid-review-core/rules;形状照 RuleExprOut)。 */
const EXPRS = {
  pack: { name: "bid-review-core", version: "1.0.0" },
  items: [
    {
      id: "R-001",
      name: "总价上限",
      layer: "L1",
      severity: "fatal",
      type: "deterministic",
      op: "lte",
      precondition: "bid.total_price is not None",
      expr_lines: ["bid.total_price lte tender.max_price"],
      on_missing_input: "need_human",
      message_tpl: "投标总价 {bid.total_price} 超过最高限价 {tender.max_price}",
      fix_tpl: "调整报价不高于最高限价",
      evidence: [],
    },
    {
      id: "R-002",
      name: "算术一致",
      layer: "L1",
      severity: "major",
      type: "hybrid",
      op: "steps",
      precondition: null,
      expr_lines: ["sum(bid.detail_rows[*].amount) == bid.subtotal", "bid.subtotal == bid.total_price"],
      on_missing_input: "need_human",
      message_tpl: "报价加总不一致",
      fix_tpl: "以明细表为准重算",
      evidence: [],
    },
  ],
};

/** B6 归因夹具(GET /metrics/fail_attribution)。 */
const ATTR = {
  items: [{ rule_id: "R-001", total: 4, reasons: [{ reason: "规则误判", count: 3 }, { reason: "证据错位", count: 1 }] }],
};

function week(start: string, fp: number, confirmed: number) {
  return { week_start: start, fp, confirmed, rate: fp + confirmed > 0 ? Math.round((fp / (fp + confirmed)) * 1000) / 10 : null };
}

/** B6 趋势夹具:近 6 周,2 周有值。 */
const TRENDS = {
  weeks: [
    week("2026-09-28", 0, 0),
    week("2026-10-05", 2, 3),
    week("2026-10-12", 1, 4),
    week("2026-10-19", 0, 0),
    week("2026-10-26", 0, 2),
    week("2026-11-02", 0, 0),
  ],
};

/** 全空周(伪零纪律:rate 全 null)。 */
const TREND_EMPTY = {
  weeks: Array.from({ length: 6 }, (_, i) => week(`2026-09-28`, 0, 0)).map((w, i) => ({
    ...w,
    week_start: `2026-09-${21 + i}`,
  })),
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** 默认响应器:/rulepacks → 包清单;/rulepacks/{name}/rules → 五块;/metrics/* → B6。 */
function defaultResponder(path: string): Response {
  if (path.includes("/metrics/fail_attribution")) return jsonRes(ATTR);
  if (path.includes("/metrics/trends")) return jsonRes(TRENDS);
  if (path.endsWith("/rules")) return jsonRes(EXPRS);
  return jsonRes(packPayload);
}

function renderView(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(ui, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

/** metric-strip 值段(label .m-lb 的相邻 .m-v 段)。 */
function metricValue(label: string): string {
  return screen.getByText(label).nextElementSibling?.textContent?.trim() ?? "";
}

describe("bid-review RulesView 原型重整(2026-10-30 #s9)", () => {
  beforeEach(() => {
    calls.length = 0;
    packPayload = { items: [PACK] };
    responder = defaultResponder;
    mockParams = new URLSearchParams();
  });
  afterEach(cleanup);

  it("包头卡 + 只读 Switch + 高误报 pill-warn + 缺 stats 显示「—」+ 启停 note-bar", async () => {
    renderView(<RulesView />);
    await screen.findByText("bid-review-core");
    expect(screen.getByText("v1.0.0")).not.toBeNull();
    await waitFor(() => expect(screen.getByText("R-001")).not.toBeNull());
    // 只读 Switch:disabled 恒真,checked 跟随包 enabled
    const sw = screen.getByTestId("pack-switch");
    expect(sw.getAttribute("data-disabled")).toBe("true");
    expect(sw.getAttribute("data-checked")).toBe("true");
    // R-001 fp/hit = 3/10 = 30% ≥ 20% → 「误报 30%」
    expect(screen.getByText("误报 30%")).not.toBeNull();
    // R-003 无回流:三列计数显示 —(禁伪零)
    const row = screen.getByText("R-003").closest("tr");
    expect(row?.textContent).toContain("—");
    // 启停诚实说明
    expect(screen.getByText(/规则启停走规则包版本发布/)).not.toBeNull();
  });

  it("M5 §4.7:判定算子列 + 点规则 id 开五块抽屉(B5)+ 修订走版本发布 foot", async () => {
    renderView(<RulesView />);
    await screen.findByText("bid-review-core");
    await waitFor(() => expect(screen.getByText("判定")).not.toBeNull());
    // 判定列:mono 算子(steps 链归一);规则 id 可点
    expect(screen.getByText("steps")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "R-001" }));
    // 抽屉五块 + EXPR 头带算子 + 版本发布 foot
    expect(await screen.findByText("PRECONDITION")).not.toBeNull();
    expect(screen.getByText("EXPR · lte")).not.toBeNull();
    expect(screen.getByText("ON_MISSING_INPUT")).not.toBeNull();
    expect(screen.getByText("MESSAGE_TPL")).not.toBeNull();
    expect(screen.getByText("FIX_TPL")).not.toBeNull();
    expect(screen.getByText(/修订须走规则包版本发布/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    await waitFor(() => expect(screen.queryByText("MESSAGE_TPL")).toBeNull());
  });

  it("M5 §4.7:?rule= 深链直达抽屉(s10 FAIL 行互跳②反向)", async () => {
    mockParams = new URLSearchParams("rule=R-002");
    renderView(<RulesView />);
    expect(await screen.findByText("规则定义 · R-002")).not.toBeNull();
    // 包加载后五块明细落定(抽屉先开、数据后至)
    await waitFor(() => expect(screen.getByText("EXPR · steps")).not.toBeNull());
    expect(screen.getByText("MESSAGE_TPL")).not.toBeNull();
  });

  it(".seg 层级过滤(M5):L1 实质性只剩 L1 规则;高误报段只剩高误报并出互跳链接", async () => {
    renderView(<RulesView />);
    await screen.findByText("bid-review-core");
    await waitFor(() => expect(screen.getByText("R-001")).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "L1 实质性 2" }));
    await waitFor(() => expect(screen.queryByText("R-003")).toBeNull());
    expect(screen.getByText("R-001")).not.toBeNull();
    expect(screen.getByText("R-002")).not.toBeNull();
    // 高误报段:仅 R-001(30%);互跳①→ 看板 FAIL 名单锚点
    fireEvent.click(screen.getByRole("button", { name: "高误报 1" }));
    await waitFor(() => expect(screen.queryByText("R-002")).toBeNull());
    const link = screen.getByText("查看 FAIL 名单").closest("a");
    expect(link?.getAttribute("href")).toBe("/bid-review/metrics#fail-list");
  });
});

describe("bid-review MetricsView 规则效果看板(2026-10-30 #s10)", () => {
  beforeEach(() => {
    calls.length = 0;
    packPayload = { items: [PACK] };
    responder = defaultResponder;
    mockParams = new URLSearchParams();
  });
  afterEach(cleanup);

  it("四格 metric-strip = Σrule_count/Σfp/Σhit/Σadopted", async () => {
    renderView(<MetricsView />);
    await screen.findByText("规则效果看板");
    // R-001 出现在逐规则表 + FAIL 名单两处,用 findAllByText 探数据落定
    await screen.findAllByText("R-001");
    expect(metricValue("规则总数")).toBe("3条");
    expect(metricValue("回流误报")).toBe("4次");
    expect(metricValue("命中总数")).toBe("20次");
    expect(metricValue("复核采纳")).toBe("13次");
  });

  it("逐规则表按 fp 降序,FAIL 名单只收高误报规则(.pill-err)", async () => {
    renderView(<MetricsView />);
    await screen.findByText("规则效果看板");
    await screen.findAllByText("R-001");
    // fp 降序:3 → 1 → 无
    const statsCard = screen.getByText("逐规则回流统计").closest(".card");
    const firstCol = Array.from(
      statsCard?.querySelectorAll("tbody tr td:first-child") ?? [],
    ).map((td) => td.textContent);
    expect(firstCol[0]?.startsWith("R-001")).toBe(true);
    expect(firstCol[1]?.startsWith("R-002")).toBe(true);
    expect(firstCol[2]?.startsWith("R-003")).toBe(true);
    // FAIL 名单:仅 R-001(30%);R-002(10%)不入榜
    const failCard = screen.getByText("高误报 FAIL 名单").closest(".card");
    expect(failCard?.textContent).toContain("R-001");
    expect(failCard?.textContent).not.toContain("R-002");
    expect(failCard?.textContent).toContain("30%");
    expect(screen.getByText("FAIL")).not.toBeNull();
    // 诚实说明
    expect(screen.getByText(/独立评测端点未接入/)).not.toBeNull();
  });

  it("零回流:FAIL 名单提示尚无数据,逐规则计数显示「—」", async () => {
    packPayload = { items: [{ ...PACK, stats: {} }] };
    renderView(<MetricsView />);
    await screen.findByText("规则效果看板");
    await waitFor(() =>
      expect(screen.getByText(/尚无回流数据/)).not.toBeNull(),
    );
    const row = screen.getByText("R-001").closest("tr");
    expect(row?.textContent).toContain("—");
    expect(screen.queryByText("FAIL")).toBeNull();
  });

  it("M5 §4.8:周趋势 6 柱 + 回流闭环注 + FAIL 归因 foot + FAIL 行深链规则库(互跳②)", async () => {
    renderView(<MetricsView />);
    await screen.findByText("规则效果看板");
    // 周趋势卡:6 柱 + 回流闭环 note
    expect(await screen.findByText("周趋势")).not.toBeNull();
    await waitFor(() => expect(document.querySelectorAll(".t-col").length).toBe(6));
    expect(screen.getByText(/回流闭环生效/)).not.toBeNull();
    // FAIL 名单卡锚点(s9 高误报段互跳①落点)
    const failCard = screen.getByText("高误报 FAIL 名单").closest(".card");
    expect(failCard?.id).toBe("fail-list");
    // 归因 foot:note 首段聚合句式(原型 s10);FAIL 行 → 规则库深链
    expect(screen.getByText(/R-001 集中在「规则误判」\(3\/4\)/)).not.toBeNull();
    // R-001 同时在逐规则统计表渲染,深链断言只在 FAIL 名单卡内找 <a>
    const failLink = failCard?.querySelector("a.k");
    expect(failLink?.getAttribute("href")).toBe("/bid-review/rules?rule=R-001");
  });

  it("M5 §4.8:无回流时趋势空态不画 0%(伪零纪律)", async () => {
    packPayload = { items: [{ ...PACK, stats: {} }] };
    responder = (path) => {
      if (path.includes("/metrics/fail_attribution")) return jsonRes({ items: [] });
      if (path.includes("/metrics/trends")) return jsonRes(TREND_EMPTY);
      return jsonRes(packPayload);
    };
    renderView(<MetricsView />);
    expect(await screen.findByText(/尚无回流数据——周趋势随人工复核产生/)).not.toBeNull();
    expect(document.querySelectorAll(".t-col").length).toBe(0);
  });
});
