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

// EAI-CUSTOM 2026-10-30 分期建议一期(s3/s4,ui-gaps spec §二):
// ① 解析质量表 = engine_meta.docs 清单 —— Plan6(2026-10-31)已迁 /parsing 归拢
//    专屏,断言随迁 bid-review-parsing.dom.test.tsx;
// ② 字段对照卡 = GET /tasks/{id}/baselines 行级快照 → 已抽取/缺失 pill +
//    「查看原文」→ content 端点定位弹层(与工作台证据 chip 同源);
// ③ 确认门 gating:仅 awaiting_confirm 可确认,按钮带未确认行数,POST /confirm。
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

import { BaselineView } from "@/extensions/bid-review/components/BaselineView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TASK = (status: string) => ({
  id: "t1",
  owner_id: "u1",
  status,
  mode: "deep",
  progress: { pct: status === "awaiting_confirm" ? 30 : 100 },
  error: null,
  engine_meta: {
    materials_hash: "abcdef1234567890",
    docs: [
      {
        doc_id: "招标文件.pdf",
        role: "tender",
        kind: "pdf",
        pages: 12,
        chars: 3400,
        assets: 1,
        status: "parsed",
      },
      {
        doc_id: "投标文件.docx",
        role: "bid",
        kind: "docx",
        pages: 0,
        chars: 2200,
        assets: 0,
        status: "parsed",
      },
    ],
  },
  prev_task_id: null,
  created_at: "2026-10-30T00:00:00Z",
});

const BASELINES = [
  {
    kind: "tender",
    doc_id: "招标文件.pdf",
    confirmed: false,
    created_at: "2026-10-30T00:00:00Z",
    fields: { "tender.max_price": 8000000, "tender.boq_items": null },
    provenance: {
      "tender.max_price": {
        doc_id: "招标文件.pdf",
        page: 3,
        quote: "最高限价捌佰万元整",
      },
    },
    materials_hash: "abcdef1234567890",
  },
  {
    kind: "bid",
    doc_id: "投标文件.docx",
    confirmed: false,
    created_at: "2026-10-30T00:00:00Z",
    fields: { "bid.total_price": 9000000 },
    provenance: {},
    materials_hash: "abcdef1234567890",
  },
];

const CONTENT = {
  doc: {
    doc_id: "招标文件.pdf",
    role: "tender",
    kind: "pdf",
    pages: 12,
    chars: 3400,
    assets: 1,
    status: "parsed",
  },
  page: 3,
  seq: 2,
  segments: [
    {
      seq: 2,
      page: 3,
      kind: "text",
      text: "投标最高限价:人民币捌佰万元整",
      asset_id: null,
    },
  ],
};

function renderBaseline() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<BaselineView taskId="t1" />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-review BaselineView 分期建议一期(EAI-CUSTOM 2026-10-30)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("字段卡对照渲染;查看原文 → content 定位弹层", async () => {
    responder = (path) => {
      if (path.endsWith("/baselines")) return jsonRes({ items: BASELINES });
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes(CONTENT);
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("done"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    // Plan6:解析质量表已迁 /parsing 归拢专屏(bid-review-parsing.dom.test.tsx 接管),
    // 本页只留字段对照+确认门。

    // 字段对照:族按钮 + 字段卡(已抽取/缺失 pill 与值);findByRole 兼数据加载门
    // 字段族主题(Plan8 §4.4):报价基准(默认选中)/清单基准按钮可见
    expect(
      await screen.findByRole("button", { name: /报价基准/ }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /清单基准/ })).toBeTruthy();
    // 已抽取字段默认折叠(Plan8 §4.4):折叠注可见,max_price 卡不可见
    expect(screen.getByText(/已由引擎交叉校验通过/)).toBeTruthy();
    expect(screen.queryByText("tender.max_price")).toBeNull();

    // 点折叠注展开 → 字段卡出现
    fireEvent.click(screen.getByText(/已由引擎交叉校验通过/));
    expect(await screen.findByText("tender.max_price")).toBeTruthy();
    expect(screen.getByText("8,000,000")).toBeTruthy();

    // 查看原文 → content?page=3(pdf 真页码直取)→ 定位弹层渲染命中段
    // (max_price 卡属默认族,先做定位流程再切族)
    fireEvent.click(screen.getByRole("button", { name: "查看原文" }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path.startsWith("/api/extensions/bid-review/tasks/t1/docs/") &&
            c.path.endsWith("/content?page=3"),
        ),
      ).toBe(true),
    );
    expect(
      await screen.findByRole("dialog", { name: "定位原文" }),
    ).toBeTruthy();
    expect(screen.getByText(/最高限价:人民币捌佰万元整/)).toBeTruthy();

    // Plan8 §4.4:boq_items 归「清单基准」主题,切族可见(缺失 pill)
    fireEvent.click(screen.getByRole("button", { name: /清单基准/ }));
    expect(await screen.findByText("tender.boq_items")).toBeTruthy();
    expect(screen.getAllByText("缺失").length).toBeGreaterThan(0);
  });

  it("确认门 gating:仅 awaiting_confirm 可确认,按钮带未确认行数并 POST /confirm", async () => {
    responder = (path, init) => {
      if (path.endsWith("/baselines")) return jsonRes({ items: BASELINES });
      if (path.endsWith("/tasks/t1/confirm") && init?.method === "POST")
        return jsonRes(TASK("running"));
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("awaiting_confirm"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    const btn = await screen.findByRole("button", {
      name: /确认基准包并开始审查/,
    });
    // 基线行到达后按钮才带未确认行数(行数随 baselines 查询异步填充)
    await waitFor(() => expect(btn.textContent).toContain("待确认 2 行"));
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path === "/api/extensions/bid-review/tasks/t1/confirm" &&
            c.init?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("页头待确认 pill + 渐进门 meter(Plan8 §4.4):pill=未确认行+未裁冲突,meter 渐进,proto-banner 清除", async () => {
    // 双行夹具一行已确认:无交互即得渐进 50%(1/2)
    const HALF = [
      { ...BASELINES[0]!, confirmed: true },
      { ...BASELINES[1]!, confirmed: false },
    ];
    responder = (path) => {
      if (path.endsWith("/baselines")) return jsonRes({ items: HALF });
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("awaiting_confirm"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    // 页头 warn pill = 未确认行 1 + 未裁冲突 0 = 1 项
    expect(await screen.findByText(/待确认 1 项/)).toBeTruthy();
    // proto-banner 已清除(Plan8 T1)
    expect(screen.queryByText(/P0-2b/)).toBeNull();

    // 渐进 meter:已确认行 1 / 分母(2 行 + 0 冲突) = 50%
    const gateBtn = screen.getByRole("button", {
      name: /确认基准包并开始审查/,
    });
    await waitFor(() => expect(gateBtn.textContent).toContain("待确认 1 行"));
    expect(screen.getByText(/50%/)).toBeTruthy();
  });
});

// ── 二期(EAI-CUSTOM 2026-10-31 spec §1.5/§二/§四):冲突裁定 / 置信 pill / 中文 label ──

/** 二期投影:labels 中文名 + candidates 冲突 + fields_conf + adjudications。 */
const BASELINES_P2 = () => ({
  items: [
    {
      kind: "bid",
      doc_id: "投标文件.docx",
      confirmed: false,
      created_at: "2026-10-31T00:00:00Z",
      fields: { "bid.total_price": 9000000, "bid.subtotal": null },
      effective_fields: { "bid.total_price": 9000000, "bid.subtotal": null },
      provenance: {},
      candidates: {
        "bid.total_price": [
          { value: 8000000, doc_id: "投标文件.docx", page: 1, quote: "捌佰万" },
          { value: 9000000, doc_id: "投标文件.docx", page: 2, quote: "玖佰万" },
        ],
      },
      fields_conf: { "bid.total_price": { conf: 0.6, verified: true } },
      conflicts: ["bid.total_price"],
      materials_hash: "abcdef1234567890",
    },
  ],
  labels: {
    "bid.total_price": "投标总价",
    "bid.subtotal": "投标明细合计",
  },
  adjudications: {},
});

describe("bid-review BaselineView 二期冲突裁定(EAI-CUSTOM 2026-10-31)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("冲突卡:多候选 radio + 中文 label + 置信 pill;采纳 → POST adjudicate → 已裁定", async () => {
    responder = (path, init) => {
      if (path.endsWith("/baselines")) return jsonRes(BASELINES_P2());
      if (path.endsWith("/baselines/adjudicate") && init?.method === "POST") {
        const body = JSON.parse(init.body as string) as {
          path: string;
          value: unknown;
        };
        expect(body.path).toBe("bid.total_price");
        expect(body.value).toBe(9000000);
        const out = BASELINES_P2();
        out.adjudications = {
          "bid.total_price": { value: 9000000, at: "2026-10-31T01:00:00Z" },
        };
        return jsonRes(out);
      }
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("awaiting_confirm"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    // 中文 label 卡(路径降为 code 小字)+ 冲突待裁定区
    // Plan8 §4.4 后字段卡同屏可见(报价基准族),裁定卡+字段卡各一份 → findAll
    expect((await screen.findAllByText("投标总价")).length).toBeGreaterThan(0);
    expect(screen.getByText(/冲突待裁定/)).toBeTruthy();
    expect(screen.getByText("待裁定")).toBeTruthy();

    // 采纳按钮初始禁用(未选候选);gate 按钮带未裁定冲突数
    const adopt = screen.getByRole("button", { name: "采纳为基准值" });
    expect((adopt as HTMLButtonElement).disabled).toBe(true);
    const gateBtn = screen.getByRole("button", {
      name: /确认基准包并开始审查/,
    });
    await waitFor(() =>
      expect(gateBtn.textContent).toContain("未裁定冲突 1 处"),
    );

    // 选候选 9000000 → 采纳 → POST adjudicate;响应整包回填 → 已裁定 pill
    const radios = screen
      .getAllByRole("radio")
      .filter((r) => (r as HTMLInputElement).name === "cand-bid.total_price");
    expect(radios.length).toBe(2);
    fireEvent.click(radios[1]!);
    // 核对勾 gate(Plan8 §4.4):仅选候选不够,须勾「我已核对两处原文」
    await waitFor(() =>
      expect((adopt as HTMLButtonElement).disabled).toBe(true),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /我已核对两处原文/ }));
    await waitFor(() =>
      expect((adopt as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(adopt);
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path ===
            "/api/extensions/bid-review/tasks/t1/baselines/adjudicate",
        ),
      ).toBe(true),
    );
    expect(await screen.findByText("已裁定")).toBeTruthy();
    expect(screen.getByText(/当前基准 9,000,000/)).toBeTruthy();

    // 裁定后 gate 按钮不再带未裁定冲突数;渐进 meter 0%→50%(1 冲突已裁/分母 2)
    await waitFor(() =>
      expect(gateBtn.textContent).not.toContain("未裁定冲突"),
    );
    await waitFor(() => expect(screen.getByText(/50%/)).toBeTruthy());
    // 页头 pill 收敛:未裁冲突清零,剩未确认行 1 → 待确认 1 项
    await waitFor(() => expect(screen.getByText(/待确认 1 项/)).toBeTruthy());
  });

  it("已裁定快照直达:adjudications 非空时冲突卡直接呈已裁定态,门不带冲突计数", async () => {
    const snapshot = BASELINES_P2();
    snapshot.adjudications = {
      "bid.total_price": { value: 8000000, at: "2026-10-31T01:00:00Z" },
    };
    responder = (path) => {
      if (path.endsWith("/baselines")) return jsonRes(snapshot);
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK("awaiting_confirm"));
      return jsonRes({}, 404);
    };
    renderBaseline();

    expect(await screen.findByText("已裁定")).toBeTruthy();
    // 基准值=裁定覆盖后 effective(此处字段值仍 9000000,裁定 8000000 在
    // effective_fields 由后端合并——夹具以 fields 直陈,呈 9,000,000)
    await waitFor(() => {
      const gateBtn = screen.getByRole("button", {
        name: /确认基准包并开始审查/,
      });
      expect(gateBtn.textContent).not.toContain("未裁定冲突");
    });
  });
});
