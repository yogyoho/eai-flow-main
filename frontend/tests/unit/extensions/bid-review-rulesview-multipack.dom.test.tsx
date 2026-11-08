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

// P1-β批二续 T5(A-续-⑥,2026-11-07):/rulepacks 升双包(bid-review-core 生产包 +
// bid-review-l4 advisory 包,后端序 core 在前)。锁定三行为:
// ① 多包聚合:双包 rules 拼接全可见(RulesView 不再 data[0] 单包取用),包头卡逐包
//    渲染且 l4 包带 advisory pill,seg「全部 3」= 双包聚合计数;
// ② L4 过滤档:「L4 竞争力」筛后只剩 L4 规则,core 规则隐藏(与既有 layer 筛选同交互);
// ③ 五块抽屉按规则所属包路由:?rule=L4-001 深链 → GET /rulepacks/bid-review-l4/rules。
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

import { RulesView } from "@/extensions/bid-review/components/RulesView";

const CORE_PACK = {
  name: "bid-review-core",
  version: "1.0.0",
  rule_count: 2,
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
      layer: "L3",
      severity: "major",
      type: "semantic",
      op: "gte",
    },
  ],
  stats: { "R-001": { hit: 10, fp: 3, adopted: 5 } },
  enabled: true,
};

const L4_PACK = {
  name: "bid-review-l4",
  version: "1.0.0",
  rule_count: 1,
  rules: [
    {
      id: "L4-001",
      name: "方案亮点提炼",
      layer: "L4",
      severity: "info",
      type: "semantic",
      op: "steps",
    },
  ],
  stats: {},
  enabled: true,
};

/** 五块明细夹具:core/l4 两包各回各的(GET /rulepacks/{name}/rules)。 */
const CORE_EXPRS = {
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
      message_tpl: "投标总价超过最高限价",
      fix_tpl: "调整报价不高于最高限价",
      evidence: [],
    },
  ],
};

const L4_EXPRS = {
  items: [
    {
      id: "L4-001",
      name: "方案亮点提炼",
      layer: "L4",
      severity: "info",
      type: "semantic",
      op: "steps",
      precondition: null,
      expr_lines: ["sem(bid.full_text, '提炼方案竞争力亮点')"],
      on_missing_input: "skip",
      message_tpl: "竞争力建议:可提炼方案亮点",
      fix_tpl: "补充方案亮点章节",
      evidence: [],
    },
  ],
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** 默认响应器:/rulepacks → 双包清单;/rulepacks/bid-review-l4/rules → l4 五块;
 * 其余 /rules → core 五块。 */
function defaultResponder(path: string): Response {
  if (path.includes("/rulepacks/bid-review-l4/rules")) return jsonRes(L4_EXPRS);
  if (path.endsWith("/rules")) return jsonRes(CORE_EXPRS);
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

describe("bid-review RulesView 多包聚合(P1-β批二续 T5,A-续-⑥)", () => {
  beforeEach(() => {
    calls.length = 0;
    packPayload = { items: [CORE_PACK, L4_PACK] };
    responder = defaultResponder;
    mockParams = new URLSearchParams();
  });
  afterEach(cleanup);

  it("双包聚合:rules 拼接全可见 + 包头卡逐包(l4 带 advisory pill)+ 全部 3", async () => {
    renderView(<RulesView />);
    // 双包名各出现两处(包头卡 h3 + 表组小节头)→ findAllByText;核心是都在
    expect(
      await screen.findAllByText("bid-review-core").then((els) => els.length),
    ).toBeGreaterThan(0);
    expect(
      await screen.findAllByText("bid-review-l4").then((els) => els.length),
    ).toBeGreaterThan(0);
    // 三条规则(2 core + 1 l4)全可见——多包聚合不再 data[0] 丢包
    await waitFor(() => expect(screen.getByText("L4-001")).not.toBeNull());
    expect(screen.getByText("R-001")).not.toBeNull();
    expect(screen.getByText("R-002")).not.toBeNull();
    // seg 聚合计数:全部 3 / L4 竞争力 1
    expect(screen.getByRole("button", { name: "全部 3" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "L4 竞争力 1" })).not.toBeNull();
    // l4 包头卡带 advisory pill(卡内作用域断言)
    const l4Card = (await screen.findAllByText("bid-review-l4"))[0]!.closest(
      ".card",
    );
    expect(l4Card?.querySelector(".pill-gray")?.textContent).toBe("advisory");
    const coreCard = (
      await screen.findAllByText("bid-review-core")
    )[0]!.closest(".card");
    expect(coreCard?.querySelector(".pill-gray")).toBeNull();
    // 双包各一只只读 Switch
    const switches = screen.getAllByTestId("pack-switch");
    expect(switches).toHaveLength(2);
    for (const sw of switches) {
      expect(sw.getAttribute("data-disabled")).toBe("true");
    }
  });

  it("L4 过滤档:L4 竞争力 1 筛后只剩 L4 规则,core 规则隐藏", async () => {
    renderView(<RulesView />);
    await waitFor(() => expect(screen.getByText("L4-001")).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "L4 竞争力 1" }));
    await waitFor(() => expect(screen.queryByText("R-001")).toBeNull());
    expect(screen.queryByText("R-002")).toBeNull();
    expect(screen.getByText("L4-001")).not.toBeNull();
    // 高误报段互不干扰:R-001 30% 高误报仍只入高误报档
    fireEvent.click(screen.getByRole("button", { name: "高误报 1" }));
    await waitFor(() => expect(screen.queryByText("L4-001")).toBeNull());
    expect(screen.getByText("R-001")).not.toBeNull();
  });

  it("五块抽屉按规则所属包路由:?rule=L4-001 深链 → /rulepacks/bid-review-l4/rules", async () => {
    mockParams = new URLSearchParams("rule=L4-001");
    renderView(<RulesView />);
    expect(await screen.findByText("规则定义 · L4-001")).not.toBeNull();
    await waitFor(() =>
      expect(screen.getByText("EXPR · steps")).not.toBeNull(),
    );
    expect(
      calls.some(
        (c) =>
          c.path === "/api/extensions/bid-review/rulepacks/bid-review-l4/rules",
      ),
    ).toBe(true);
    expect(screen.getByText(/提炼方案竞争力亮点/)).not.toBeNull();
  });
});
