import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

// EAI-CUSTOM 2026-10-30 证据管线(spec 2026-10-30-bid-review-evidence-pipeline-design):
// ① 真证据 chip 可点 → GET /tasks/{id}/docs/{doc}/content?page=(pdf 真页码直取页),
//    弹层渲染片段窗口 + 命中高亮;
// ② content 404 → 「未定位到原文」如实呈现(不造假原文);
// ③ 「待人工」按钮 → POST /issues/{id}/feedback {action:"need_human"}(spec D9)。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (
  path: string,
  init?: RequestInit,
) => Response | Promise<Response>;

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

import { ResultsView } from "@/extensions/bid-review/components/ResultsView";

const TASK = {
  id: "t1",
  owner_id: "u1",
  status: "done",
  mode: "quick",
  progress: { pct: 100 },
  error: null,
  engine_meta: {},
  prev_task_id: null,
  created_at: "2026-10-29T00:00:00Z",
  done_at: "2026-10-29T00:11:32Z",
};

const ISSUE = {
  id: "i1",
  task_id: "t1",
  rule_id: "L1-009",
  layer: "L1",
  severity: "fatal",
  verdict: "FAIL",
  clause_id: null,
  message: "投标总价超出招标控制价",
  fix: "下调总价至控制价以内",
  evidence: [
    {
      doc_id: "bid.pdf",
      page: 3,
      section_path: "bid.total_price",
      text: "投标总价:¥9,000,000",
    },
  ],
  dedup_key: "L1-009|-|k",
  need_human: false,
  confidence: 1.0,
  created_at: "2026-10-29T00:00:00Z",
};

const CONTENT = {
  doc: {
    doc_id: "bid.pdf",
    role: "bid",
    kind: "pdf",
    pages: 12,
    chars: 5000,
    assets: 0,
    status: "parsed",
  },
  page: 3,
  seq: 2,
  segments: [
    {
      seq: 2,
      page: 3,
      kind: "text",
      text: "投标总价:¥9,000,000",
      asset_id: null,
    },
    { seq: 3, page: 3, kind: "table", text: "| 项目 | 金额 |", asset_id: null },
  ],
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
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

describe("bid-review ResultsView 证据管线(EAI-CUSTOM 2026-10-30)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("页头五元组+常驻按钮:审查结果/用时 11m 32s/发起复核→review/刷新(Plan7 spec §4.5)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    // h2 = 审查结果(裁定8 工作台退役)
    expect(screen.getByRole("heading", { level: 2 })?.textContent).toContain(
      "审查结果",
    );
    // 用时 = done_at − created_at 客户端算(11m 32s)
    expect(screen.getByText(/用时/)?.textContent).toContain("11m 32s");
    // 常驻按钮:发起复核 → /bid-review/review?task_id=t1(status=done 可用)
    const review = screen.getByRole("link", { name: "发起复核" });
    expect(review.getAttribute("href")).toBe("/bid-review/review?task_id=t1");
    // 常驻按钮:刷新
    expect(screen.getByRole("button", { name: "刷新" })).toBeTruthy();
    // 资料完备性卡已删(裁定 16,2026-10-31 用户:与 /parsing 缺失列+待确认组重复)
    expect(screen.queryByText("资料完备性")).toBeNull();
  });

  it("证据 chip 点击 → content?page= 定位弹层渲染命中窗口", async () => {
    responder = (path) => {
      if (path.includes("/docs/bid.pdf/content")) return jsonRes(CONTENT);
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    fireEvent.click(screen.getByRole("button", { name: /bid\.pdf/ }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path ===
            "/api/extensions/bid-review/tasks/t1/docs/bid.pdf/content?page=3",
        ),
      ).toBe(true),
    );
    expect(
      await screen.findByRole("dialog", { name: "定位原文" }),
    ).toBeTruthy();
    expect(screen.getAllByText("投标总价:¥9,000,000").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/第\s*3\s*页/)).toBeTruthy();
  });

  it("content 404 → 未定位到原文如实呈现", async () => {
    responder = (path) => {
      if (path.includes("/docs/bid.pdf/content"))
        return jsonRes({ detail: "未定位到原文" }, 404);
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    fireEvent.click(screen.getByRole("button", { name: /bid\.pdf/ }));
    expect(await screen.findByText(/未定位到原文/)).toBeTruthy();
  });

  it("待人工按钮 → POST feedback action=need_human", async () => {
    responder = (path) => {
      if (path.endsWith("/feedback"))
        return jsonRes({ ...ISSUE, verdict: "UNKNOWN", need_human: true });
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    fireEvent.click(screen.getByRole("button", { name: "待人工" }));
    await waitFor(() => {
      const fb = calls.find((c) => c.path.endsWith("/issues/i1/feedback"));
      expect(fb).toBeTruthy();
      const body = fb?.init?.body;
      if (typeof body !== "string") throw new Error("feedback body missing");
      expect(JSON.parse(body)).toEqual({
        action: "need_human",
        note: "",
      });
    });
  });

  it("复核进度读服务端 review_state(B2,spec §4.5):刷新不丢,行级标签随投影出现", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/issues"))
        return jsonRes({
          items: [
            { ...ISSUE, id: "i1", review_state: "maintained" },
            {
              ...ISSUE,
              id: "i2",
              rule_id: "L1-010",
              review_state: "false_positive",
            },
            {
              ...ISSUE,
              id: "i3",
              rule_id: "L1-011",
              review_state: "unresolved",
            },
          ],
        });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findAllByText("投标总价超出招标控制价");
    // 复核进度卡:已复核 2/3 · 维持 1 · 误报 1(全来自服务端投影,无本地动作)
    const card = screen.getByText("复核进度").closest(".card");
    expect(card?.textContent).toMatch(/已复核\s*2\s*\/\s*3/);
    expect(card?.textContent).toMatch(/维持\s*1/);
    expect(card?.textContent).toMatch(/误报\s*1/);
    // 行级标签:三条同 fixture,按渲染序断言——i1 维持违规、i2 误报、i3 无标签
    const labels = screen.getAllByText(/已复核 · /).map((el) => el.textContent);
    expect(labels).toEqual(["已复核 · 维持违规", "已复核 · 误报"]);
  });

  it("B7 版本对比:prev_task_id 显按钮,点开拉 diff 卡——三态计数+新增问题列表(spec §4.5)", async () => {
    const TASK_PREV = { ...TASK, prev_task_id: "t0" };
    responder = (path) => {
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK_PREV);
      if (path.includes("/tasks/t1/diff"))
        return jsonRes({
          added: [
            {
              id: "a1",
              rule_id: "L3-005",
              layer: "L3",
              severity: "major",
              message: "工期表述不一致",
              need_human: false,
            },
          ],
          removed: [
            { rule_id: "L1-009", severity: "fatal", message: "旧版总价超限价" },
          ],
          unchanged_count: 2,
        });
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findByText("审查结果");
    // 任务详情异步落位(prev_task_id 驱动按钮,先等 task 数据)
    await screen.findByText(/用时 11m 32s/);
    // 按钮常驻(prev_task_id 才渲染),未点开不发 diff 请求
    const btn = screen.getByRole("button", { name: "对比上一版本" });
    expect(calls.filter((c) => c.path.includes("/diff")).length).toBe(0);
    fireEvent.click(btn);
    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.path.includes("/tasks/t1/diff") && c.path.includes("prev=t0"),
        ),
      ).toBe(true);
    });
    // 三态计数 + 新增问题列表(rule_id+severity pill+message)
    await waitFor(() => {
      expect(document.body.textContent).toContain("工期表述不一致");
    });
    expect(document.body.textContent).toContain("新增 1");
    expect(document.body.textContent).toContain("消失 1");
    expect(document.body.textContent).toContain("未变 2");
    const diffCard = screen.getByText("版本对比").closest(".card");
    expect(diffCard?.textContent).toContain("L3-005");
    // 行内 sev pill(major→pill-orange 主要);hd-right 首个 pill-warn=新增计数
    expect(diffCard?.querySelector("tbody .pill-orange")?.textContent).toBe(
      "主要",
    );
    expect(diffCard?.querySelector(".pill-warn")?.textContent).toContain(
      "新增",
    );
    // tbl-foot:消失问题详情在上一版任务
    expect(diffCard?.textContent).toContain("上一版本任务");
    // B10 版本链入口(spec 2026-11-01 §2):卡头「查看整屏」→ /diff 整屏(双参数)
    const fullLink = screen.getByRole("link", { name: "查看整屏" });
    expect(fullLink.getAttribute("href")).toBe(
      "/bid-review/diff?task_id=t1&prev=t0",
    );
    // 页头「换版重审」→ /bid-review?prev= 深链(TasksView 自动开对话框预选基准)
    expect(
      screen.getByRole("link", { name: "换版重审" }).getAttribute("href"),
    ).toBe("/bid-review?prev=t1");
  });

  it("无 prev_task_id:不渲染对比按钮,不发 diff 请求", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findByText("审查结果");
    expect(screen.queryByRole("button", { name: "对比上一版本" })).toBeNull();
    expect(calls.filter((c) => c.path.includes("/diff")).length).toBe(0);
  });

  it("B4 评分覆盖:数据在 → 规则执行卡 meter 升级「评分覆盖度」(total/covered 直出)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/rulepacks"))
        return jsonRes({
          items: [
            {
              name: "bid-review-core",
              version: "1.0.0",
              rule_count: 2,
              enabled: true,
              stats: {},
              rules: [
                {
                  id: "L1-009",
                  name: "总价不超限价",
                  layer: "L1",
                  severity: "fatal",
                  type: "deterministic",
                },
                {
                  id: "L3-005",
                  name: "工期三处一致",
                  layer: "L3",
                  severity: "major",
                  type: "semantic",
                },
              ],
            },
          ],
        });
      if (path.endsWith("/tasks/t1/score_coverage"))
        return jsonRes({
          total: 4,
          covered: 3,
          items: [
            { name: "价格分", max_score: 50, covered_by_rules: ["L1-009"] },
            { name: "方案分", max_score: 30, covered_by_rules: [] },
          ],
        });
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findByText("审查结果");
    // 规则执行卡:评分覆盖度行替换规则命中行(spec §4.5 line 117),75% + 已覆盖注
    expect(await screen.findByText("评分覆盖度")).toBeTruthy();
    expect(screen.queryByText("规则命中")).toBeNull();
    expect(document.body.textContent).toContain("评分办法 4 项已覆盖 3");
    expect(document.body.textContent).toContain("75%");
    // 口径注:未覆盖 ≠ 审错
    expect(document.body.textContent).toContain("未覆盖不代表审错");
  });

  it("B4 评分覆盖:旧任务 total=0 → 回落「规则命中」meter 现状口径", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/rulepacks"))
        return jsonRes({
          items: [
            {
              name: "bid-review-core",
              version: "1.0.0",
              rule_count: 2,
              enabled: true,
              stats: {},
              rules: [
                {
                  id: "L1-009",
                  name: "总价不超限价",
                  layer: "L1",
                  severity: "fatal",
                  type: "deterministic",
                },
                {
                  id: "L3-005",
                  name: "工期三处一致",
                  layer: "L3",
                  severity: "major",
                  type: "semantic",
                },
              ],
            },
          ],
        });
      if (path.endsWith("/tasks/t1/score_coverage"))
        return jsonRes({ total: 0, covered: 0, items: [] });
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await screen.findByText("审查结果");
    // 回落:ISSUE 命中 L1-009 → 1/2 = 50%
    expect(await screen.findByText("规则命中")).toBeTruthy();
    expect(screen.queryByText("评分覆盖度")).toBeNull();
    expect(document.body.textContent).toContain("命中 1 / 2 条");
  });
});

// ── L2 P1 附件核对表卡(EAI-CUSTOM 2026-11-02 spec §5)──

const CHECKLIST = {
  counts: { required: 3, matched: 1, partial: 1, missing: 1, extra: 1 },
  items: [
    {
      no: "ATT-E-008",
      name: "类似业绩证明",
      mandatory: "★",
      min_count: 3,
      found: 2,
      status: "PARTIAL",
      clause: "第三章3.4",
      refs: [{ doc_id: "bid.pdf", page: 118 }],
    },
    {
      no: "ATT-G-002",
      name: "安全生产许可证",
      mandatory: "★",
      min_count: null,
      found: 0,
      status: "MISSING",
      clause: null,
      refs: [],
    },
    {
      no: "ATT-F-001",
      name: "投标函",
      mandatory: "★",
      min_count: null,
      found: 1,
      status: "MATCHED",
      clause: null,
      refs: [{ doc_id: "bid.pdf", page: 2 }],
    },
  ],
  extra_items: [{ name: "企业宣传册", doc_id: "bid.pdf", page: 310 }],
};

describe("bid-review ResultsView L2 P1 附件核对表(EAI-CUSTOM 2026-11-02)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("附件核对表卡:六格/排序 MISSING 前/pill 映射/EXTRA 灰行/页码 chip", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/attachment_checklist"))
        return jsonRes(CHECKLIST);
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await waitFor(() => expect(screen.getByText("附件核对表")).toBeTruthy());
    // pill 映射(卡内作用域断言——metric-strip m-lb 与 pill 同文案,裸 getByText 会撞):
    // MISSING→pill-err 缺失;PARTIAL→pill-warn 份数不足
    const card = screen.getByText("附件核对表").closest(".card");
    expect(card?.querySelector(".pill-err")?.textContent).toBe("缺失");
    expect(card?.querySelector(".pill-warn")?.textContent).toBe("份数不足");
    // MISSING 行排最前(MISSING<PARTIAL<MATCHED);份数 cell found/min_count
    const missRow = screen
      .getByText("安全生产许可证")
      .closest("tr") as HTMLElement;
    const partRow = screen
      .getByText("类似业绩证明")
      .closest("tr") as HTMLElement;
    const rows = Array.from(partRow.parentElement?.children ?? []);
    expect(rows.indexOf(missRow)).toBeLessThan(rows.indexOf(partRow));
    expect(missRow.querySelectorAll(".pill-err").length).toBeGreaterThan(0);
    expect(partRow.textContent).toContain("2/3");
    // EXTRA 灰行不产 issue:多余 pill + 页码 chip(bid 首文档页码)
    expect(screen.getByText("企业宣传册").closest("tr")?.textContent).toContain(
      "p.310",
    );
    expect(screen.getByText("多余")).toBeTruthy();
    // 六格 counts 直出(L2 P2 增需人工格;旧夹具无 unknown → ?? 0 兜底仍为六格)
    expect(card?.querySelectorAll(".metric-cell").length).toBe(6);
  });

  it("零投影:counts.required=0 → 诚实空态引导", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1/attachment_checklist"))
        return jsonRes({
          counts: { required: 0, matched: 0, partial: 0, missing: 0, extra: 0 },
          items: [],
          extra_items: [],
        });
      if (path.endsWith("/tasks/t1/issues")) return jsonRes({ items: [ISSUE] });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      return jsonRes({}, 404);
    };
    renderWorkbench();
    await waitFor(() =>
      expect(screen.getByText(/本任务抽取时未包含附件要求维度/)).toBeTruthy(),
    );
  });
});

// ── L2 P2 附件子件分组 + 跨层去重(EAI-CUSTOM 2026-11-02 spec §7)──

const P2_CHECKLIST = {
  counts: {
    required: 2,
    matched: 1,
    partial: 0,
    missing: 0,
    unknown: 1,
    extra: 0,
  },
  items: [
    {
      no: "3",
      name: "资格审查文件",
      mandatory: "★",
      min_count: null,
      found: 1,
      status: "UNKNOWN",
      clause: "第三章3.1",
      refs: [],
      sub_results: [
        { no: "3.1", name: "营业执照", found: 1, status: "MATCHED" },
        { no: "3.2", name: "资质证书", found: 0, status: "MISSING" },
      ],
    },
    {
      no: "A-1",
      name: "投标函",
      mandatory: "★",
      min_count: null,
      found: 1,
      status: "MATCHED",
      clause: null,
      refs: [],
      sub_results: [],
    },
  ],
  extra_items: [],
};

const P2_ISSUES = [
  {
    id: "i1",
    task_id: "t1",
    rule_id: "L2-020",
    layer: "L2",
    severity: "fatal",
    verdict: "FAIL",
    clause_id: null,
    message: "缺少附件 A-2",
    fix: "",
    evidence: [],
    dedup_key: "k1",
    need_human: false,
    confidence: 1,
    review_state: "unresolved",
    created_at: "2026-11-02T00:00:00Z",
    entity_keys: ["attachment:A-2"],
    grouped_into: null,
    related_issues: [
      {
        id: "i2",
        rule_id: "L3-005",
        layer: "L3",
        severity: "minor",
        message: "业绩证明表述不一致",
      },
    ],
  },
  {
    id: "i2",
    task_id: "t1",
    rule_id: "L3-005",
    layer: "L3",
    severity: "minor",
    verdict: "FAIL",
    clause_id: null,
    message: "业绩证明表述不一致",
    fix: "",
    evidence: [],
    dedup_key: "k2",
    need_human: false,
    confidence: 1,
    review_state: "unresolved",
    created_at: "2026-11-02T00:01:00Z",
    entity_keys: ["attachment:A-2"],
    grouped_into: "i1",
    related_issues: [],
  },
];

describe("bid-review ResultsView L2 P2 子件分组+跨层去重(EAI-CUSTOM 2026-11-02)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("附件核对表:UNKNOWN→需人工 pill+第六格 counts+子件明细行", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/issues")) return jsonRes({ items: [] });
      if (path.endsWith("/rulepacks")) return jsonRes({ items: [] });
      if (path.includes("/attachment_checklist")) return jsonRes(P2_CHECKLIST);
      if (path.includes("/score_coverage"))
        return jsonRes({ total: 0, covered: 0, items: [] });
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes({ segments: [] });
      return jsonRes({}, 404);
    };
    renderWorkbench();

    // 需人工文本恰两处:UNKNOWN 行 pill(pill-gray)+ metric-strip 第六格
    // 标签 → getAllByText 消歧,断言其一为 pill-gray(不弱化为裸 truthy)
    const human = await screen.findAllByText("需人工");
    expect(human.length).toBe(2);
    expect(
      human.filter((el) => el.className.includes("pill-gray")).length,
    ).toBe(1);
    // 子件明细行(✓/✗ 随 sub_results.found," · " 连接)
    expect(
      screen.getByText(/子件:3.1 营业执照 ✓ · 3.2 资质证书 ✗/),
    ).toBeTruthy();
    // UNKNOWN 提供情况如实呈现「无法自动分组」
    expect(screen.getByText("无法自动分组")).toBeTruthy();
    // 第六格:卡内 metric-strip 需人工值 = counts.unknown(按标签定位取值,
    // 裸 querySelector(".metric-cell .m-v") 只会命中第一格)
    const card = screen.getByText("附件核对表").closest(".card");
    const cells = Array.from(card?.querySelectorAll(".metric-cell") ?? []);
    expect(cells.length).toBe(6);
    const unknownCell = cells.find(
      (c) => c.querySelector(".m-lb")?.textContent === "需人工",
    );
    expect(unknownCell?.querySelector(".m-v")?.textContent).toBe("1");
  });

  it("问题清单:grouped 行隐藏,keep 卡渲染关联问题 chip", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/issues"))
        return jsonRes({ items: P2_ISSUES, summary: {} });
      if (path.endsWith("/rulepacks")) return jsonRes({ items: [] });
      if (path.includes("/attachment_checklist"))
        return jsonRes({
          counts: {
            required: 0,
            matched: 0,
            partial: 0,
            missing: 0,
            unknown: 0,
            extra: 0,
          },
          items: [],
          extra_items: [],
        });
      if (path.includes("/score_coverage"))
        return jsonRes({ total: 0, covered: 0, items: [] });
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes({ segments: [] });
      return jsonRes({}, 404);
    };
    renderWorkbench();

    // keep 卡(L2-020)可见并带关联 chip(次要 = sevPillBrx minor 中文标签);
    // grouped 行(L3-005 独立卡)由展示层隐藏——独立 message 全文不出现
    expect(await screen.findByText(/关联问题 1/)).toBeTruthy();
    expect(screen.getByText(/L3-005 次要\] 业绩证明表述不一致/)).toBeTruthy();
    expect(screen.queryByText(/^业绩证明表述不一致$/)).toBeNull();
  });
});
