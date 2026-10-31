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

// Plan6 (spec §4.3) /parsing 归拢专屏回归门:解析信息四源归拢——页头四元组+
// 待基准确认 pill、六步步骤条+引擎进度行(TaskStepper 共享件)、解析质量表
// (原型 s3 扁平 5 列:文件/页数/识别置信度/状态/说明+OCR 兜底行;B3 页级置信
// 未落地=置信格「—」诚实降级)、基准字段抽取扁平表(裁定 15,2026-10-31 用户
// 纠正:原型 s3 优先,不用基准确认页的字段族 tabs/字段卡形态——5 列 字段路径/
// 锚点/抽取值/形态/状态+hd-right 三 pill+冲突不嵌裁定只给「去基准确认」链接)。
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
      candidates: {
        "bid.total_price": [
          { value: 1000000, doc_id: "b.pdf", page: 5, quote: "报价汇总表" },
        ],
      },
      provenance: {
        "tender.max_price": {
          doc_id: "b.pdf",
          page: 3,
          quote: "最高限价壹佰万元",
        },
      },
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

  it("解析质量:原型 s3 扁平 5 列表+OCR 兜底行(B3 前置信格「—」诚实降级)", async () => {
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
    // card-hd:h3 + hd-sub「N 个文件 · M 页」
    expect(bodyHas("2 个文件 · 12 页")).toBe(true);
    // 原型 5 列:文件/页数/识别置信度/状态/说明
    const quality = document.querySelectorAll(".card")[0]!;
    const headers = [...quality.querySelectorAll("thead th")].map((th) =>
      th.textContent?.trim(),
    );
    expect(headers).toEqual(["文件", "页数", "识别置信度", "状态", "说明"]);
    // 2 文档行 + 1 OCR 兜底行(b.pdf assets=3)
    const rows = [...quality.querySelectorAll("tbody tr")];
    expect(rows.length).toBe(3);
    const txtCells = rows[0]!.querySelectorAll("td");
    expect(txtCells[0]?.textContent).toBe("t.txt");
    expect(txtCells[1]?.textContent?.trim()).toBe("—"); // text 无页
    expect(txtCells[2]?.textContent?.trim()).toBe("—"); // B3 未落地,不冒充置信
    expect(txtCells[3]?.textContent?.trim()).toBe("完成");
    const pdfCells = rows[1]!.querySelectorAll("td");
    expect(pdfCells[1]?.textContent?.trim()).toBe("12");
    // OCR 兜底:warn 底色整行 pill+说明,不伪造页码区间/置信数字
    expect(
      rows[2]!.getAttribute("colspan") ??
        rows[2]!.querySelector("td")?.getAttribute("colspan"),
    ).toBe("5");
    expect(rows[2]!.textContent).toContain("OCR 兜底");
    expect(rows[2]!.textContent).toContain("b.pdf");
    expect(rows[2]!.textContent).toContain("3 个扫描页/内嵌图片");
  });

  it("基准字段抽取:原型 s3 扁平 5 列表+hd-right 三 pill+冲突行候选 pill(裁定 15:无字段族 tabs)", async () => {
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK);
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASELINES);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    await waitFor(() => {
      expect(bodyHas("tender.max_price")).toBe(true);
    });
    // card-hd:hd-right 三 pill(已抽取/冲突/缺失),快照哈希入 hd-sub
    expect(bodyHas("已抽取 2")).toBe(true);
    expect(bodyHas("冲突 1")).toBe(true);
    expect(bodyHas("缺失 1")).toBe(true);
    expect(bodyHas("abcdef123456")).toBe(true);
    // 原型 5 列:字段路径/锚点/抽取值/形态/状态
    const fields = document.querySelectorAll(".card")[1]!;
    const headers = [...fields.querySelectorAll("thead th")].map((th) =>
      th.textContent?.trim(),
    );
    expect(headers).toEqual(["字段路径", "锚点", "抽取值", "形态", "状态"]);
    const rows = [...fields.querySelectorAll("tbody tr")];
    expect(rows.length).toBe(3);
    // fieldRows 按路径字典序:bid.total_price / tender.duration / tender.max_price
    // tender.max_price:mono 路径 + 锚点 code.k(doc·p.X)+查看原文 + num 值 + number 形态 + 已抽取
    const mx = rows[2]!.querySelectorAll("td");
    expect(mx[0]?.textContent?.trim()).toBe("tender.max_price");
    expect(mx[0]?.className).toContain("mono");
    expect(mx[1]?.textContent).toContain("b.pdf · p.3");
    expect(mx[1]?.querySelector("code.k")).not.toBeNull();
    expect(
      [...mx[1]!.querySelectorAll("button")].some((b) =>
        b.textContent?.includes("查看原文"),
      ),
    ).toBe(true);
    expect(mx[2]?.textContent).toContain("1,000,000");
    expect(mx[3]?.textContent?.trim()).toBe("number");
    expect(mx[4]?.textContent?.trim()).toBe("已抽取");
    // tender.duration:null → 值格「未在正文定位到」、形态「—」、缺失 pill-gray
    const dur = rows[1]!.querySelectorAll("td");
    expect(dur[0]?.textContent?.trim()).toBe("tender.duration");
    expect(dur[2]?.textContent?.trim()).toBe("未在正文定位到");
    expect(dur[3]?.textContent?.trim()).toBe("—");
    expect(dur[4]?.querySelector(".pill-gray")?.textContent?.trim()).toBe(
      "缺失",
    );
    // bid.total_price:冲突行=状态 pill-warn 冲突+值内嵌候选 pill(汇总表 1,000,000)
    const tp = rows[0]!.querySelectorAll("td");
    expect(tp[0]?.textContent?.trim()).toBe("bid.total_price");
    expect(tp[4]?.querySelector(".pill-warn")?.textContent?.trim()).toBe(
      "冲突",
    );
    expect(tp[2]?.textContent).toContain("候选 1,000,000");
    // tbl-foot:on_missing_input 原型句式(三值语义防误读)
    expect(bodyHas("on_missing_input: need_human")).toBe(true);
    expect(bodyHas("不计为通过")).toBe(true);
    // 冲突不嵌裁定:去基准确认链接,无 radio
    const link = screen.getByRole("link", { name: "去基准确认 →" });
    expect(link.getAttribute("href")).toBe("/bid-review/baseline?task_id=t1");
    expect(document.querySelector('input[type="radio"]')).toBeNull();
    // 裁定 15:无字段族 tabs/搜索(基准确认页交互形态不上本屏)
    expect(document.querySelectorAll(".fam-item").length).toBe(0);
    expect(screen.queryByLabelText("按字段路径过滤")).toBeNull();
  });

  it("长表分页:两表各自每页 10 行,上一页/下一页独立翻页(共 N 计数,2026-10-31 用户要求)", async () => {
    const manyDocs = Array.from({ length: 12 }, (_, i) => ({
      doc_id: `d${i + 1}.pdf`,
      role: "bid",
      kind: "pdf",
      chars: 100,
      status: "parsed",
      pages: 1,
      assets: 0,
    }));
    const TASK12 = { ...TASK, engine_meta: { docs: manyDocs } };
    const manyFields: Record<string, unknown> = {};
    for (let i = 0; i < 12; i++) manyFields[`tender.f${i}`] = i;
    const BASE12 = {
      items: [
        {
          ...BASELINES.items[0]!,
          fields: manyFields,
          provenance: {},
          conflicts: [],
          candidates: {},
        },
      ],
      labels: {},
      adjudications: {},
    };
    responder = (path) => {
      if (path.endsWith("/tasks/t1")) return jsonRes(TASK12);
      if (path.endsWith("/tasks/t1/baselines")) return jsonRes(BASE12);
      return jsonRes({}, 404);
    };
    renderParsing();
    await screen.findByText("解析与字段抽取");
    await waitFor(() => {
      expect(bodyHas("d1.pdf")).toBe(true);
    });
    // 质量表:12 docs → 首页 10 行;hd-sub 仍显总数 12
    const quality = document.querySelectorAll(".card")[0]!;
    expect(quality.querySelectorAll("tbody tr").length).toBe(10);
    expect(bodyHas("12 个文件 · 12 页")).toBe(true);
    expect(quality.querySelector(".tbl-foot")?.textContent).toContain(
      "共 12 个文件",
    );
    expect(quality.querySelector(".tbl-foot")?.textContent).toContain(
      "第 1 / 2 页",
    );
    // 字段表:12 fields → 首页 10 行,pager 独立
    const fields = document.querySelectorAll(".card")[1]!;
    expect(fields.querySelectorAll("tbody tr").length).toBe(10);
    // 质量表下一页 → 第二页 2 行(OCR 行无,12-10=2)
    fireEvent.click(screen.getAllByRole("button", { name: "下一页" })[0]!);
    expect(quality.querySelectorAll("tbody tr").length).toBe(2);
    // 字段表下一页 → 第二页 2 行(两表页状态互不影响)
    fireEvent.click(screen.getAllByRole("button", { name: "下一页" })[1]!);
    expect(fields.querySelectorAll("tbody tr").length).toBe(2);
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
