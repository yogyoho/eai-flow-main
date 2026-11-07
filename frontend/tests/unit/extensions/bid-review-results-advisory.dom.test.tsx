import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// P1-β批二续 T5(A-续-⑥,2026-11-07):L4 激活 advisory 面。锁定四行为:
// ① advisory 分节:「竞争力建议(L4,advisory)」收 advisory.items,行只读;
// ② N1 FP 过滤:advisory.items 里 verdict=="false_positive" 的行(API 面不过滤)
//    不得当建议呈现——verdict/review_state/会话内三通道全滤(advisoryVisibleItems);
// ③ 正式视图排 L4:L4 fatal FAIL 不入正式清单与客户端 summary →
//    verdict-band 仍「建议提交」(advisory 不影响提交判定);
// ④ 空 advisory(旧网关缺键/滤空)→ 整节不渲染。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (path: string, init?: RequestInit) => Response;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

rs.mock("next/navigation", () => ({
  useParams: () => ({}),
  usePathname: () => "/bid-review",
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
}));

import {
  advisoryVisibleItems,
  ResultsView,
} from "@/extensions/bid-review/components/ResultsView";
import type { IssueOut } from "@/extensions/bid-review/types";

const TASK = {
  id: "t1",
  owner_id: "u1",
  status: "done",
  mode: "quick",
  progress: { pct: 100 },
  error: null,
  engine_meta: {},
  prev_task_id: null,
  created_at: "2026-11-07T00:00:00Z",
  done_at: "2026-11-07T00:05:00Z",
};

const FORMAL: IssueOut = {
  id: "i1",
  task_id: "t1",
  rule_id: "L1-009",
  layer: "L1",
  severity: "major",
  verdict: "FAIL",
  clause_id: null,
  message: "投标总价超出招标控制价",
  fix: "下调总价至控制价以内",
  evidence: [],
  dedup_key: "k1",
  need_human: false,
  confidence: 1,
  review_state: "unresolved",
  created_at: "2026-11-07T00:00:00Z",
};

// L4 fatal FAIL:若漏入正式清单/客户端 summary,verdict-band 会误翻红——本测钉死
const L4_OK: IssueOut = {
  ...FORMAL,
  id: "i2",
  rule_id: "L4-001",
  layer: "L4",
  severity: "fatal",
  verdict: "FAIL",
  message: "施工组织设计可增加BIM协同亮点",
  fix: "补充BIM协同章节提升技术分",
  dedup_key: "k2",
};

// 已判误报的 L4 行:API 面不过滤(N1),前端必须自滤
const L4_FP: IssueOut = {
  ...FORMAL,
  id: "i3",
  rule_id: "L4-002",
  layer: "L4",
  severity: "major",
  verdict: "false_positive",
  message: "已判误报的建议条目",
  fix: "",
  dedup_key: "k3",
};

const PACKS = {
  items: [
    {
      name: "bid-review-core",
      version: "1.0.0",
      rule_count: 1,
      enabled: true,
      stats: {},
      rules: [
        {
          id: "L1-009",
          name: "总价不超限价",
          layer: "L1",
          severity: "major",
          type: "deterministic",
        },
      ],
    },
    {
      name: "bid-review-l4",
      version: "1.0.0",
      rule_count: 2,
      enabled: true,
      stats: {},
      rules: [
        {
          id: "L4-001",
          name: "BIM协同亮点",
          layer: "L4",
          severity: "info",
          type: "semantic",
        },
        {
          id: "L4-002",
          name: "冗余建议",
          layer: "L4",
          severity: "info",
          type: "semantic",
        },
      ],
    },
  ],
};

const ZERO_COVERAGE = { total: 0, covered: 0, items: [] };
const ZERO_CHECKLIST = {
  counts: { required: 0, matched: 0, partial: 0, missing: 0, extra: 0 },
  items: [],
  extra_items: [],
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function issuesPayload() {
  return {
    items: [FORMAL, L4_OK, L4_FP],
    summary: {
      fatal: 0,
      major: 1,
      minor: 0,
      info: 0,
      need_human: 0,
      advisory: { total: 2, by_severity: { fatal: 1, major: 1 } },
    },
    advisory: {
      items: [L4_OK, L4_FP],
      total: 2,
      by_severity: { fatal: 1, major: 1, minor: 0, info: 0 },
    },
  };
}

function renderWorkbench() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<ResultsView taskId="t1" />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

function baseResponder(issues: unknown) {
  return (path: string) => {
    if (path.endsWith("/tasks/t1/issues")) return jsonRes(issues);
    if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
    if (path.endsWith("/rulepacks")) return jsonRes(PACKS);
    if (path.includes("/score_coverage")) return jsonRes(ZERO_COVERAGE);
    if (path.includes("/attachment_checklist")) return jsonRes(ZERO_CHECKLIST);
    return jsonRes({}, 404);
  };
}

describe("bid-review ResultsView L4 advisory 分节(P1-β批二续 T5)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("advisory 节渲染 + 正式清单排 L4 + N1:已判误报行不当建议呈现", async () => {
    responder = baseResponder(issuesPayload());
    renderWorkbench();
    // 正式问题(L1 major)可见
    await screen.findByText("投标总价超出招标控制价");
    // advisory 节头:标题口径 + 「不影响提交判定」标注
    expect(
      screen.getByRole("heading", { name: "竞争力建议(L4,advisory)" }),
    ).not.toBeNull();
    expect(screen.getByText("竞争力建议 · 不影响提交判定")).not.toBeNull();
    // L4 建议行恰一次(在 advisory 节;正式清单已排 L4,不双呈现)
    expect(
      screen.getAllByText("施工组织设计可增加BIM协同亮点"),
    ).toHaveLength(1);
    // N1:verdict=false_positive 的 L4 行不渲染(误报不当建议)
    expect(screen.queryByText("已判误报的建议条目")).toBeNull();
    // verdict-band:L4 fatal FAIL 不入正式计数 → 仍「建议提交」
    expect(screen.getByText("建议提交")).not.toBeNull();
    expect(screen.queryByText("不建议提交")).toBeNull();
    // 折叠交互:收起后建议行隐藏,节头仍在
    fireEvent.click(screen.getByRole("button", { name: "收起" }));
    await waitForAbsent("施工组织设计可增加BIM协同亮点");
    expect(
      screen.getByRole("heading", { name: "竞争力建议(L4,advisory)" }),
    ).not.toBeNull();
  });

  it("空 advisory(旧网关缺键)→ 整节不渲染", async () => {
    responder = baseResponder({ items: [FORMAL] });
    renderWorkbench();
    await screen.findByText("投标总价超出招标控制价");
    expect(
      screen.queryByRole("heading", { name: "竞争力建议(L4,advisory)" }),
    ).toBeNull();
  });

  it("advisory 全误报滤空 → 整节不渲染(不只看 total)", async () => {
    responder = baseResponder({
      items: [FORMAL, L4_FP],
      advisory: {
        items: [L4_FP],
        total: 1,
        by_severity: { fatal: 0, major: 1, minor: 0, info: 0 },
      },
    });
    renderWorkbench();
    await screen.findByText("投标总价超出招标控制价");
    expect(
      screen.queryByRole("heading", { name: "竞争力建议(L4,advisory)" }),
    ).toBeNull();
    expect(screen.queryByText("已判误报的建议条目")).toBeNull();
  });
});

/** 轮询等元素从文档消失(收起/隐藏断言用)。 */
async function waitForAbsent(text: string) {
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline) {
    if (screen.queryByText(text) === null) return;
    await new Promise((r) => setTimeout(r, 25));
  }
  throw new Error(`element still present: ${text}`);
}

describe("advisoryVisibleItems FP 过滤(N1 钉死)", () => {
  it("verdict / review_state / 会话内三通道误报全滤,其余保留", () => {
    const items: IssueOut[] = [
      L4_OK,
      { ...L4_OK, id: "a", verdict: "false_positive" },
      { ...L4_OK, id: "b", review_state: "false_positive" },
      { ...L4_OK, id: "c" },
    ];
    expect(advisoryVisibleItems(items).map((i) => i.id)).toEqual(["i2", "c"]);
    // 会话内刚标误报(服务端投影未落定前也要即时隐藏)
    expect(
      advisoryVisibleItems(items, { c: "false_positive" }).map((i) => i.id),
    ).toEqual(["i2"]);
  });

  it("全误报 → 空数组(整节不渲染的前提)", () => {
    expect(
      advisoryVisibleItems([{ ...L4_OK, verdict: "false_positive" }]),
    ).toEqual([]);
    expect(advisoryVisibleItems([])).toEqual([]);
  });
});
