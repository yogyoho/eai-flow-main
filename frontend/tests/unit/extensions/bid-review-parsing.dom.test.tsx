import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// Plan6 (spec §4.3) /parsing 归拢专屏回归门:解析信息四源归拢——页头四元组+
// 待基准确认 pill、六步步骤条+引擎进度行(TaskStepper 共享件)、解析质量表
// (engine_meta.docs;B3 前无页级置信列=文档级 OCR 注记诚实降级)、基准字段
// 对照只读区(汇总行+族 tabs+字段卡;冲突不嵌裁定——「去基准确认」链接,
// 裁定交互仍留基准确认页)。
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

import { ParsingView } from "@/extensions/bid-review/components/ParsingView";

const TASK = {
  id: "t1",
  owner_id: "u1",
  status: "awaiting_confirm",
  mode: "deep",
  progress: { stage: "confirm_gate", pct: 40, msg: "基线已生成,等待人工确认" },
  error: null,
  engine_meta: {
    docs: [
      {
        doc_id: "t.txt",
        role: "tender",
        kind: "text",
        chars: 1200,
        status: "parsed",
        pages: 0,
        assets: 0,
      },
      {
        doc_id: "b.pdf",
        role: "bid",
        kind: "pdf",
        chars: 800,
        status: "parsed",
        pages: 12,
        assets: 3,
      },
    ],
  },
  prev_task_id: null,
  created_at: "2026-10-31T00:00:00Z",
  fatal_unhandled: 0,
  need_human_count: 0,
  biz_no: "TBR-20261031-0001",
  project_name: "XX数据中心一期采购项目",
  lot_name: "标段一",
  tender_no: null,
  updated_at: null,
  done_at: null,
  main_unhandled: 0,
  created_by_name: null,
};

const BASELINES = {
  items: [
    {
      doc_id: "b.pdf",
      materials_hash: "abcdef1234567890",
      fields: {
        "tender.max_price": 1000000,
        "tender.duration": null,
        "bid.total_price": 1002300,
      },
      effective_fields: null,
      conflicts: ["bid.total_price"],
      candidates: {},
      provenance: {},
      fields_conf: {},
    },
  ],
  labels: { "tender.max_price": "招标最高限价" },
  adjudications: {},
};

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** body 全文包含(字段卡文本嵌套 span,精确 getByText 脆)。 */
function bodyHas(s: string): boolean {
  return document.body.textContent?.includes(s) ?? false;
}

function renderParsing(taskId: string | null = "t1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<ParsingView taskId={taskId} />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-review ParsingView /parsing 归拢专屏(Plan6 spec §4.3)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("页头四元组+待基准确认 pill", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASELINES);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    // 任务详情异步后到:h2 同步渲染,先等数据落位再断言
    await waitFor(() => {
      expect(bodyHas("TBR-20261031-0001")).toBe(true);
    });
    // 业务号(TaskTitleTag)· 项目/标段(ph-sub)· 模式
    expect(bodyHas("XX数据中心一期采购项目 / 标段一")).toBe(true);
    expect(bodyHas("深度评审")).toBe(true);
    // ph-actions 待基准确认 pill(awaiting_confirm 状态驱动)
    expect(screen.getByText("待基准确认")).not.toBeNull();
  });

  it("stepper 六步+引擎进度行(confirm_gate → 第 4 步 on)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASELINES);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    await waitFor(() => {
      expect(bodyHas("基线已生成,等待人工确认")).toBe(true);
    });
    const steps = document.querySelectorAll(".stepper .step");
    expect(steps.length).toBe(6);
    expect(steps[3]?.className).toContain("on");
    expect(steps[3]?.textContent).toContain("基准确认");
    // 引擎进度行:「引擎:{msg} · {pct}%」
    expect(bodyHas("引擎:基线已生成,等待人工确认")).toBe(true);
    expect(bodyHas("40%")).toBe(true);
  });

  it("解析质量表:docs 清单+OCR 文档级注记(B3 前诚实降级)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASELINES);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    await waitFor(() => {
      expect(bodyHas("b.pdf")).toBe(true);
    });
    expect(bodyHas("解析质量")).toBe(true);
    expect(bodyHas("t.txt")).toBe(true);
    expect(bodyHas("1,200")).toBe(true);
    // 文档级 OCR 注记(assets>0 计数),无页级「识别置信度」列
    expect(bodyHas("1 份文档含扫描页")).toBe(true);
    expect(bodyHas("识别置信度")).toBe(false);
  });

  it("基准字段只读区:汇总行+族 tab+字段卡+冲突去基准确认链接", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASELINES);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    await waitFor(() => {
      expect(bodyHas("共 3 字段")).toBe(true);
    });
    // 汇总行:共/已抽取/缺失/冲突(未裁)+快照哈希前 12 位
    expect(bodyHas("已抽取 2")).toBe(true);
    expect(bodyHas("缺失 1")).toBe(true);
    expect(bodyHas("冲突 1(未裁 1)")).toBe(true);
    expect(bodyHas("abcdef123456")).toBe(true);
    // 族 tab(招标基准 1/2 抽取、投标响应 1/1)
    expect(
      screen.getByRole("button", { name: /招标基准/ }).textContent,
    ).toContain("1/2");
    expect(
      screen.getByRole("button", { name: /投标响应/ }).textContent,
    ).toContain("1/1");
    // 字段卡:中文名+值+缺失 pill+废标风险文案(无 provenance 诚实降级)
    expect(bodyHas("招标最高限价")).toBe(true);
    expect(bodyHas("1,000,000")).toBe(true);
    expect(screen.getByText("缺失")).not.toBeNull();
    expect(bodyHas("废标风险")).toBe(true);
    // 冲突不嵌裁定:给「去基准确认」链接,不给 radio
    const link = screen.getByRole("link", { name: "去基准确认 →" });
    expect(link.getAttribute("href")).toBe(
      "/bid-review/baseline?task_id=t1",
    );
    expect(document.querySelector('input[type="radio"]')).toBeNull();
    // 底部注:缺失不阻断不计通过(spec §4.3 三值语义防误读)
    expect(bodyHas("不计为通过")).toBe(true);
  });

  it("failed:引擎错误 errbar", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1"))
        return jsonRes({
          ...TASK,
          status: "failed",
          error: "引擎连接超时",
          progress: { stage: "parsing", pct: 15, msg: "解析中" },
        });
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASELINES);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    await waitFor(() => {
      expect(bodyHas("审查失败:引擎连接超时")).toBe(true);
    });
    expect(bodyHas("审查失败:引擎连接超时")).toBe(true);
  });

  it("taskId=null:未指定任务降级", async () => {
    renderParsing(null);
    await screen.findByText("解析与字段抽取");
    expect(bodyHas("未指定任务")).toBe(true);
    expect(calls.length).toBe(0);
  });
});
