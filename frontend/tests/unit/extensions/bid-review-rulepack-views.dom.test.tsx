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
//    「—」不显示 0(伪零纪律);③ .seg 类型过滤(替换 FilterPills);④ 看板四格 metric-strip
//    = Σrule_count/Σfp/Σhit/Σadopted(跨规则包求和);⑤ 逐规则表按 fp 降序 + 高误报 FAIL
//    名单(.pill-err,仅收入高误报规则);⑥ 零回流诚实态(FAIL 名单提示尚无数据,不伪造
//    PASS)与 note-bar 诚实说明(独立评测端点未接入)。
const calls: Array<{ path: string }> = [];
let packPayload: unknown;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, _init?: RequestInit) => {
    calls.push({ path });
    return new Response(JSON.stringify(packPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  },
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
    },
    {
      id: "R-002",
      name: "算术一致",
      layer: "L1",
      severity: "major",
      type: "hybrid",
    },
    {
      id: "R-003",
      name: "主体一致",
      layer: "L3",
      severity: "minor",
      type: "semantic",
    },
  ],
  stats: {
    "R-001": { hit: 10, fp: 3, adopted: 5 },
    "R-002": { hit: 10, fp: 1, adopted: 8 },
  },
  enabled: true,
};

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

  it(".seg 类型过滤:点 sem 只剩该类型规则", async () => {
    renderView(<RulesView />);
    await screen.findByText("bid-review-core");
    await waitFor(() => expect(screen.getByText("R-001")).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "sem 1" }));
    await waitFor(() => expect(screen.queryByText("R-001")).toBeNull());
    expect(screen.queryByText("R-002")).toBeNull();
    expect(screen.getByText("R-003")).not.toBeNull();
  });
});

describe("bid-review MetricsView 规则效果看板(2026-10-30 #s10)", () => {
  beforeEach(() => {
    calls.length = 0;
    packPayload = { items: [PACK] };
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
});
