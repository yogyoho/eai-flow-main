import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { PropsWithChildren } from "react";

// 待人工核对行的确认必须带核对依据：空备注不得发 PATCH，填写后只提交
// status=confirmed + note；行级 422 由调用方 toast 展示。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (path: string, init?: RequestInit) => Response;

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/bid-write/intake",
  useSearchParams: () => new URLSearchParams("task_id=t1"),
}));

import { IntakeView } from "@/extensions/bid-write/components/IntakeView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const TASK = {
  id: "t1",
  biz_no: "BW-0001",
  status: "matrix_ready",
  progress: { pct: 100 },
  error: null,
  project_name: "数据中心一期",
  lot_name: "标段一",
  tender_no: "T-2026-1",
  created_at: "2026-11-13T08:00:00Z",
  engine_meta: {
    matrix_counts: { total: 1, star: 0, blocked: 1 },
    provenance: {
      "tender.required_declarations": {
        doc_id: "t.txt",
        page: null,
        quote: "投标有效期不少于 90 日历天",
      },
    },
  },
};

const BLOCKED_ROW = {
  clause_id: "clause:2",
  kind: "clause",
  source_path: "tender.required_declarations",
  requirement: "投标有效期不少于 90 日历天",
  star: false,
  strategy: "positive",
  target_section: "二、商务响应",
  evidence_refs: [],
  status: "blocked",
  conf: 0.42,
  verified: false,
  note: "",
};

const MATRIX = {
  schema_version: "1.0.0",
  vocab: {
    strategies: ["pending", "full", "positive", "negative"],
    statuses: ["draft", "confirmed", "blocked"],
    kinds: ["attachment", "clause", "aggregate"],
  },
  items: [BLOCKED_ROW],
};

const EXTRA_ROW = {
  ...BLOCKED_ROW,
  clause_id: "att:1",
  kind: "attachment",
  source_path: "tender.attachment_requirements",
  requirement: "营业执照复印件一式两份",
};

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<IntakeView />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-write IntakeView 阻断行确认", () => {
  beforeEach(() => {
    calls.length = 0;
    rs.spyOn(HTMLElement.prototype, "scrollIntoView").mockImplementation(
      () => undefined,
    );
    responder = (path, init) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/matrix") && init?.method === "PATCH") {
        return jsonRes({
          ...BLOCKED_ROW,
          status: "confirmed",
          note: "已对照招标文件 p.18 原文",
        });
      }
      if (path.endsWith("/matrix")) return jsonRes(MATRIX);
      if (path.includes("/docs/t.txt/content")) {
        const url = new URL(path, "http://t");
        const quote = (url.searchParams.get("quote") ?? "").replace(/\s+/g, "");
        if (quote.includes("投标有效期")) {
          return jsonRes({
            doc: { doc_id: "t.txt", role: "tender", kind: "text", pages: 3, chars: 120, assets: 0, status: "parsed" },
            page: null,
            seq: 2,
            segments: [
              { seq: 2, page: null, kind: "text", text: "投标有效期不少于 90 日历天，自开标之日起算。", asset_id: null },
            ],
          });
        }
        return jsonRes({ detail: "未定位到原文" }, 404);
      }
      return jsonRes({ detail: { message: "not found" } }, 404);
    };
  });

  afterEach(() => {
    cleanup();
    rs.restoreAllMocks();
  });

  it("空备注不发 PATCH，填写依据后才确认", async () => {
    renderView();

    fireEvent.click(await screen.findByRole("button", { name: "确认" }));
    expect(screen.getByText("人工核对确认")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "核对无误，确认" }));
    expect(calls.some((call) => call.init?.method === "PATCH")).toBe(false);

    fireEvent.change(screen.getByPlaceholderText(/已对照招标文件 p.18 原文/), {
      target: { value: "已对照招标文件 p.18 原文，确认投标有效期为 90 天" },
    });
    fireEvent.click(screen.getByRole("button", { name: "核对无误，确认" }));

    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.init?.method === "PATCH" &&
            call.path ===
              "/api/extensions/bid-write/tasks/t1/matrix/clause%3A2",
        ),
      ).toBe(true),
    );
    const patch = calls.find((call) => call.init?.method === "PATCH");
    const body = patch?.init?.body;
    if (typeof body !== "string") throw new Error("PATCH body 不是字符串");
    expect(JSON.parse(body)).toEqual({
      status: "confirmed",
      note: "已对照招标文件 p.18 原文，确认投标有效期为 90 天",
    });
  });

  it("uses a non-native strategy dropdown and PATCHes the selection", async () => {
    renderView();

    await screen.findAllByText("条款 2");
    expect(document.querySelector("select")).toBeNull();

    const trigger = screen.getByRole("combobox", {
      name: "条款 2 响应策略",
    });
    expect(trigger.textContent).toContain("正偏离");

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "负偏离" }));

    await waitFor(() => {
      const patch = calls.find((call) => call.init?.method === "PATCH");
      const body = patch?.init?.body;
      if (typeof body !== "string") throw new Error("PATCH body 不是字符串");
      expect(JSON.parse(body)).toEqual({ strategy: "negative" });
    });
  });

  it("筛选面板不重复摘录：来源单选叠加状态多选过滤矩阵，可一键清除", async () => {
    responder = (path, _init) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/matrix")) {
        return jsonRes({ ...MATRIX, items: [BLOCKED_ROW, EXTRA_ROW] });
      }
      return jsonRes({ detail: { message: "not found" } }, 404);
    };
    renderView();

    await screen.findByText("营业执照复印件一式两份");
    const filter = document.querySelector(".bw-filter");
    if (!filter) throw new Error("filter panel not ready");
    const filterScope = filter as HTMLElement;

    // 面板只承载筛选选项，不重复摘录全文
    expect(within(filterScope).getByText("承诺条款")).toBeTruthy();
    expect(
      within(filterScope).queryByText("投标有效期不少于 90 日历天"),
    ).toBeNull();

    // 来源单选：选中承诺条款 → 矩阵只剩该来源
    fireEvent.click(within(filterScope).getByRole("radio", { name: /承诺条款/ }));
    expect(screen.getByText(/显示 1 \/ 2/)).toBeTruthy();
    expect(screen.getByText(/筛选 1\/2 · 清除/)).toBeTruthy();

    // 叠加状态多选（已确认）→ 无匹配 → 空态引导清除筛选
    fireEvent.click(within(filterScope).getByRole("checkbox", { name: /已确认/ }));
    expect(screen.getByText("当前筛选没有匹配的矩阵行")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(screen.getByText("营业执照复印件一式两份")).toBeTruthy();
    expect(
      within(filterScope)
        .getByRole("radio", { name: /全部来源/ })
        .getAttribute("aria-checked"),
    ).toBe("true");
    expect(screen.getByText("全部 2")).toBeTruthy();

    // ★ 必答开关：无必答行时过滤为空，chip 可单独移除
    fireEvent.click(
      within(filterScope).getByRole("checkbox", { name: /仅看必答条款/ }),
    );
    expect(screen.getByText("当前筛选没有匹配的矩阵行")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /★ 仅看必答/ }));
    expect(screen.getByText("营业执照复印件一式两份")).toBeTruthy();
  });

  it("搜索框定位具体条款：命中后选中矩阵行", async () => {
    responder = (path, _init) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/matrix")) {
        return jsonRes({ ...MATRIX, items: [BLOCKED_ROW, EXTRA_ROW] });
      }
      return jsonRes({ detail: { message: "not found" } }, 404);
    };
    renderView();

    await screen.findByText("营业执照复印件一式两份");
    fireEvent.change(screen.getByPlaceholderText("搜索条款定位，如「附件 1」"), {
      target: { value: "附件 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "定位" }));

    await waitFor(() => {
      const row = document.querySelector(".bw-matrix-table tbody tr.on");
      expect(row).toBeTruthy();
    });
    expect(
      document
        .querySelector(".bw-matrix-table tbody tr.on")
        ?.getAttribute("id"),
    ).toBe("matrix-att:1");
  });

  it("shows the page guide with Chinese business terminology", async () => {
    renderView();

    await screen.findAllByText("条款 2");
    expect(screen.queryByText("det / sem")).toBeNull();
    expect(screen.getByText("点选即筛选")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "本页说明" }));

    const dialog = await screen.findByRole("dialog", { name: "本页说明" });
    expect(within(dialog).getByText("要求来源从哪里来")).toBeTruthy();
    expect(within(dialog).getByText("响应矩阵有什么用")).toBeTruthy();
    expect(within(dialog).getByText(/行编号是系统生成/)).toBeTruthy();

    const copy = dialog.textContent ?? "";
    for (const token of [
      "source_path",
      "target_section",
      "canLeaveIntake",
      "tender.*",
      "draft",
      "confirmed",
      "blocked",
      "pending",
      "positive",
      "negative",
    ]) {
      expect(copy).not.toContain(token);
    }
  });

  it("要求摘录不截断：矩阵表摘录格去掉单行省略，完整文本可换行", async () => {
    renderView();

    await screen.findAllByText("条款 2");

    const cell = document.querySelector(".bw-matrix-table td .excerpt");
    if (!cell) throw new Error("excerpt cell not ready");
    expect(cell.className).toBe("excerpt"); // 无 ellipsis：不再单行截断
    expect(cell.textContent).toContain("投标有效期不少于 90 日历天");
    expect(cell.getAttribute("title")).toContain("投标有效期不少于 90 日历天");
  });

  it("溯源按钮打开定位原文弹窗，命中显示原文窗口；无出处置灰", async () => {
    renderView();
    await screen.findAllByText("条款 2");

    // 有出处行 → 点击溯源,弹窗渲染原文窗口(命中段)
    fireEvent.click(screen.getByRole("button", { name: /溯源/ }));
    const dialog = await screen.findByRole("dialog", { name: "定位原文" });
    expect(
      await within(dialog).findByText(/投标有效期不少于 90 日历天/),
    ).toBeTruthy();

    fireEvent.click(within(dialog).getByText("关闭")); // 底部按钮(右上角 X 是 aria-label,无文本)
    expect(screen.queryByRole("dialog", { name: "定位原文" })).toBeNull();

    // 无出处来源 → 溯源按钮置灰(不造假定位入口)
    responder = (path, _init) => {
      if (path.endsWith("/tasks")) return jsonRes({ items: [TASK] });
      if (path.endsWith("/matrix")) {
        return jsonRes({ ...MATRIX, items: [BLOCKED_ROW, EXTRA_ROW] });
      }
      return jsonRes({ detail: { message: "not found" } }, 404);
    };
    renderView();
    const attRow = await screen.findByText("营业执照复印件一式两份");
    const cell = attRow.closest("td");
    const row = cell?.parentElement;
    if (!row) throw new Error("row not ready");
    const locateBtn = within(row).getByRole("button", {
      name: /溯源/,
    });
    expect((locateBtn as HTMLButtonElement).disabled).toBe(true);
  });
});
