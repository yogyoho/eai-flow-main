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

// EAI-CUSTOM 2026-10-31 二期 spec §五(s6):人工复核工作台队列视图——
// ① need_human 队列 N/M 进度 + 处置表单(确认/误报四因/严重度调整);
// ② 提交 → POST /issues/{id}/feedback,handled 本地推进(当前 1/1);
// ③ 左栏原文对照 = 当前项首条证据 → content?quote= 定位(与弹层同源 DocLocateBody)。
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
  usePathname: () => "/bid-review/review",
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
}));

import { ReviewQueueView } from "@/extensions/bid-review/components/ReviewQueueView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const issue = (id: string, over: Partial<Record<string, unknown>> = {}) => ({
  id,
  task_id: "t1",
  rule_id: `R-${id}`,
  layer: "semantic",
  severity: "major",
  verdict: "UNKNOWN",
  clause_id: null,
  message: `字段缺失无法判定:bid.duration_main_text(on_missing_input=need_human)`,
  fix: "补齐工期表述后重跑",
  evidence:
    id === "i1"
      ? [
          {
            doc_id: "投标文件.docx",
            page: null,
            section_path: "",
            text: "工期540日历天",
          },
        ]
      : [],
  dedup_key: `k-${id}`,
  need_human: true,
  confidence: 0,
  created_at: "2026-10-31T00:00:00Z",
  ...over,
});

const ISSUES = {
  items: [issue("i1"), issue("i2")],
};

const CONTENT = {
  doc: {
    doc_id: "投标文件.docx",
    role: "bid",
    kind: "docx",
    pages: 0,
    chars: 2200,
    assets: 0,
    status: "parsed",
  },
  page: null,
  seq: 4,
  segments: [
    {
      seq: 4,
      page: null,
      kind: "text",
      text: "工期:540日历天",
      asset_id: null,
    },
  ],
};

function renderReview() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<ReviewQueueView taskId="t1" />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-review ReviewQueueView 复核工作台(EAI-CUSTOM 2026-10-31)", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = () => jsonRes({});
  });

  afterEach(() => {
    cleanup();
  });

  it("need_human 队列渲染 + 原文对照(证据 quote 定位);确认问题 → POST feedback → 队列推进", async () => {
    responder = (path) => {
      if (path.endsWith("/issues")) return jsonRes(ISSUES);
      if (path.includes("/feedback")) return jsonRes({});
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes(CONTENT);
      return jsonRes({}, 404);
    };
    renderReview();

    // 队列进度 1/2 + 左栏取当前项证据(docx 无页码 → quote 窗口)
    expect(await screen.findByText("待复核队列")).toBeTruthy();
    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.path.includes("/docs/") &&
            c.path.includes("/content") &&
            c.path.includes("quote="),
        ),
      ).toBe(true),
    );
    expect(screen.getByText(/工期:540日历天/)).toBeTruthy();

    // 默认动作=确认问题 → 提交 → POST feedback(action=confirm)
    fireEvent.click(screen.getByRole("button", { name: "提交并下一条" }));
    await waitFor(() => {
      const fb = calls.find(
        (c) => c.path === "/api/extensions/bid-review/issues/i1/feedback",
      );
      expect(fb).toBeTruthy();
      const body = JSON.parse(fb!.init!.body as string) as { action: string };
      expect(body.action).toBe("confirm");
    });
    // handled 推进:issue i2 滑入
    await waitFor(() => {
      expect(screen.getByText(/R-i2/)).toBeTruthy();
    });
  });

  it("误报必选原因折进 note;无证据项左栏如实呈无证据提示", async () => {
    responder = (path) => {
      if (path.endsWith("/issues")) return jsonRes(ISSUES);
      if (path.includes("/feedback")) return jsonRes({});
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes(CONTENT);
      return jsonRes({}, 404);
    };
    renderReview();

    await screen.findByText("待复核队列");
    // 选误报(第 2 个 radio)+ 原因「证据错位」→ 提交 → note 折因
    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[1]!);
    fireEvent.change(screen.getByLabelText("误报原因"), {
      target: { value: "证据错位" },
    });
    fireEvent.click(screen.getByRole("button", { name: "标误报并下一条" }));
    await waitFor(() => {
      const fb = calls.find(
        (c) => c.path === "/api/extensions/bid-review/issues/i1/feedback",
      );
      expect(fb).toBeTruthy();
      const body = JSON.parse(fb!.init!.body as string) as {
        action: string;
        note: string;
      };
      expect(body.action).toBe("false_positive");
      expect(body.note).toContain("误报原因:证据错位");
    });
  });

  it("M4 §4.6:全量未复核队列+seg筛选(默认待人工)+stage-chip+页脚进度;转待人工→need_human", async () => {
    const MIX = {
      items: [
        // 致命违规:不在默认段,「全部」段可达
        issue("i1", {
          severity: "fatal",
          verdict: "FAIL",
          need_human: false,
        }),
        // need_human:默认段唯一入队项
        issue("i2"),
        // 已复核维持:全量口径下也不入队
        issue("i3", { review_state: "maintained", need_human: false }),
      ],
    };
    responder = (path) => {
      if (path.endsWith("/issues")) return jsonRes(MIX);
      if (path.includes("/feedback")) return jsonRes({});
      if (path.includes("/docs/") && path.includes("/content"))
        return jsonRes(CONTENT);
      return jsonRes({}, 404);
    };
    renderReview();

    // 默认段=待人工:仅 i2;stage-chip 复核中 1/1
    expect(await screen.findByText(/复核中 1\/1/)).toBeTruthy();
    expect(screen.getByText(/R-i2/)).toBeTruthy();
    expect(screen.queryByText(/R-i1/)).toBeNull();

    // hd-sub 进度注 + 页脚:已复核 1(维持 1)/ 待复核 2
    expect(screen.getByText(/已复核 1/)).toBeTruthy();
    expect(screen.getByText(/本任务复核进度 1 \/ 3/)).toBeTruthy();

    // 切「全部」→ i1 滑入(i3 maintained 仍排除)
    fireEvent.click(screen.getByRole("button", { name: /全部/ }));
    expect(await screen.findByText(/R-i1/)).toBeTruthy();
    expect(screen.getByText(/复核中 1\/2/)).toBeTruthy();

    // 第四处置项:转待人工 → POST action=need_human
    fireEvent.click(screen.getByRole("radio", { name: /转待人工/ }));
    fireEvent.click(screen.getByRole("button", { name: "转待人工并下一条" }));
    await waitFor(() => {
      const fb = calls.find(
        (c) => c.path === "/api/extensions/bid-review/issues/i1/feedback",
      );
      expect(fb).toBeTruthy();
      const body = JSON.parse(fb!.init!.body as string) as { action: string };
      expect(body.action).toBe("need_human");
    });
    // 本地 handled 推进(裁决 7):页脚待复核收敛 2→1
    await waitFor(() => expect(screen.getByText(/待复核 1/)).toBeTruthy());
  });
});
