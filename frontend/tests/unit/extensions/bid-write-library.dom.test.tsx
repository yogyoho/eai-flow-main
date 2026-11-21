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

// 资质素材库:概览/类型 rail/佐证过滤 + 编辑抽屉(字段模板、佐证行)/删除确认。
// 词汇契约:entity_type 必须是后端六类(past_bid 而非 history_bid,回归批卅二 bug)。
const calls: Array<{ path: string; init?: RequestInit }> = [];
let responder: (path: string, init?: RequestInit) => Response;

/** 请求体断言辅助:显式 narrow 掉 BodyInit 的非字符串分支。 */
function jsonBody(init?: RequestInit): Record<string, unknown> {
  const body = init?.body;
  if (typeof body !== "string") throw new Error("请求体不是字符串");
  return JSON.parse(body) as Record<string, unknown>;
}

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string, init?: RequestInit) => {
    calls.push({ path, init });
    return responder(path, init);
  },
}));

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/bid-write/materials-library",
  useSearchParams: () => new URLSearchParams(""),
}));

import { LibraryView } from "@/extensions/bid-write/components/LibraryView";

function jsonRes(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const MATS = {
  items: [
    {
      id: "m1",
      entity_type: "qualification",
      name: "ISO9001 质量管理体系认证",
      fields: {
        证书编号: "CN2024-0881",
        发证机关: "CQC",
        有效期至: "2027-06-30",
        内部档案: { nested: true },
      },
      evidence_refs: ["doc:1", "doc:2"],
      verifiable: true,
      created_at: "2026-11-02T08:00:00Z",
    },
    {
      id: "m2",
      entity_type: "performance",
      name: "XX 污水处理厂提标改造 EPC",
      fields: {},
      evidence_refs: [],
      verifiable: false,
      created_at: "2026-11-10T08:00:00Z",
    },
    {
      id: "m3",
      entity_type: "past_bid",
      name: "2025 某集团废水治理投标文件(脱敏)",
      fields: {
        来源项目: "某集团 2025-04",
        中标时间: "2025-05",
        复用章节: "技术方案 §3",
        脱敏状态: "已脱敏",
      },
      evidence_refs: ["doc:5"],
      verifiable: true,
      created_at: "2026-08-30T08:00:00Z",
    },
  ],
};

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<LibraryView />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-write 资质素材库", () => {
  beforeEach(() => {
    calls.length = 0;
    responder = (path, init) => {
      if (path.endsWith("/materials") && init?.method === "POST") {
        const body = jsonBody(init);
        return jsonRes({
          id: "m-new",
          evidence_refs: body.evidence_refs ?? [],
          created_at: "2026-11-18T08:00:00Z",
          verifiable: Array.isArray(body.evidence_refs)
            ? body.evidence_refs.length > 0
            : false,
          ...body,
        });
      }
      if (path.includes("/materials/") && init?.method === "PATCH") {
        return jsonRes({ ...MATS.items[0], ...jsonBody(init) });
      }
      if (path.includes("/materials/") && init?.method === "DELETE") {
        return jsonRes({ ok: true });
      }
      if (path.endsWith("/materials")) return jsonRes(MATS);
      return jsonRes({ detail: { message: "not found" } }, 404);
    };
  });

  afterEach(() => {
    cleanup();
    rs.restoreAllMocks();
  });

  it("概览与类型 rail 渲染计数,实体行展示字段键值预览(跳过非基本类型)", async () => {
    renderView();

    await screen.findByText("ISO9001 质量管理体系认证");
    expect(screen.getByText("实体总数")).toBeTruthy();
    expect(screen.getByText("无引用(导出将被拦)")).toBeTruthy();

    // rail:全部类型 + 六类逐项计数
    const rail = document.querySelector(".bw-lib-rail");
    if (!rail) throw new Error("rail not ready");
    expect(within(rail as HTMLElement).getByText("全部类型")).toBeTruthy();
    expect(within(rail as HTMLElement).getByText("资质")).toBeTruthy();
    expect(within(rail as HTMLElement).getByText("历史标书")).toBeTruthy();

    // 字段预览:基本类型键值上墙,对象值(内部档案)不展示也不显示 [object Object]
    expect(screen.getByText("CN2024-0881")).toBeTruthy();
    expect(screen.queryByText(/object Object/)).toBeNull();
    expect(screen.getByText("暂无字段,编辑抽屉内按模板补齐")).toBeTruthy();

    // 佐证外框徽标:有引用带数量 / 无引用警示(按行作用域断言,避免与过滤 chip 撞名)
    expect(screen.getByText("有引用 2")).toBeTruthy();
    const perfRow = screen
      .getByText("XX 污水处理厂提标改造 EPC")
      .closest("tr");
    if (!perfRow) throw new Error("row not ready");
    expect(within(perfRow as HTMLElement).getByText("无引用")).toBeTruthy();

    // 字段完整度:3 实体中 past_bid 覆盖模板 4 键,其余缺键 → 33%
    const strip = document.querySelector(".metric-strip");
    if (!strip) throw new Error("metric strip not ready");
    expect(within(strip as HTMLElement).getByText("字段完整度")).toBeTruthy();
    expect(within(strip as HTMLElement).getByText("按类型模板 1/3")).toBeTruthy();
  });

  it("佐证过滤 chips 与类型 rail 叠加过滤矩阵", async () => {
    renderView();

    await screen.findByText("ISO9001 质量管理体系认证");

    // 无引用过滤 → 只剩业绩行
    fireEvent.click(screen.getByRole("button", { name: /无引用 1/ }));
    expect(
      screen.getByText("XX 污水处理厂提标改造 EPC"),
    ).toBeTruthy();
    expect(
      screen.queryByText("ISO9001 质量管理体系认证"),
    ).toBeNull();

    // 叠加类型过滤:资质 + 无引用 → 空态
    const rail = document.querySelector(".bw-lib-rail");
    if (!rail) throw new Error("rail not ready");
    fireEvent.click(within(rail as HTMLElement).getByRole("button", { name: /资质/ }));
    expect(screen.getByText("当前过滤没有匹配实体")).toBeTruthy();

    // 回到全部
    fireEvent.click(within(rail as HTMLElement).getByRole("button", { name: /全部类型/ }));
    fireEvent.click(screen.getByRole("button", { name: /全部 3/ }));
    expect(screen.getByText("ISO9001 质量管理体系认证")).toBeTruthy();
  });

  it("搜索:名称与字段值均可命中,无命中给空态", async () => {
    renderView();

    await screen.findByText("ISO9001 质量管理体系认证");

    // 字段值命中(证书编号)
    fireEvent.change(screen.getByLabelText("搜索素材"), {
      target: { value: "CN2024-0881" },
    });
    expect(screen.getByText("ISO9001 质量管理体系认证")).toBeTruthy();
    expect(screen.queryByText("XX 污水处理厂提标改造 EPC")).toBeNull();

    // 名称命中
    fireEvent.change(screen.getByLabelText("搜索素材"), {
      target: { value: "提标改造" },
    });
    expect(screen.getByText("XX 污水处理厂提标改造 EPC")).toBeTruthy();
    expect(
      screen.queryByText("ISO9001 质量管理体系认证"),
    ).toBeNull();

    // 无命中 → 空态
    fireEvent.change(screen.getByLabelText("搜索素材"), {
      target: { value: "不存在的关键字" },
    });
    expect(screen.getByText("当前过滤没有匹配实体")).toBeTruthy();
  });

  it("历史标书复用入口:复制实体引用 ent:{id},非历史标书行不显示", async () => {
    const writeText = rs.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    renderView();

    await screen.findByText("2025 某集团废水治理投标文件(脱敏)");

    // 历史标书行有复用按钮
    const copyBtn = screen.getByRole("button", {
      name: "复制实体引用 ent:m3",
    });
    fireEvent.click(copyBtn);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("ent:m3"));

    // 其他类型行没有复用按钮
    const isoRow = screen
      .getByText("ISO9001 质量管理体系认证")
      .closest("tr");
    if (!isoRow) throw new Error("row not ready");
    expect(
      within(isoRow as HTMLElement).queryByRole("button", {
        name: /复制实体引用/,
      }),
    ).toBeNull();
  });

  it("编辑抽屉:字段按值回填,佐证行可改,PATCH 提交 name/fields/evidence_refs", async () => {
    renderView();

    fireEvent.click(
      await screen.findByRole("button", { name: "编辑 ISO9001 质量管理体系认证" }),
    );

    const dialog = await screen.findByRole("dialog");
    // 类型锁定:radio 禁用且资质选中
    const qual = within(dialog).getByRole("radio", { name: /资质/ });
    expect(qual.getAttribute("aria-checked")).toBe("true");
    expect(qual.hasAttribute("disabled")).toBe(true);

    // 字段按值回填
    expect(
      document.querySelector<HTMLInputElement>('[aria-label="字段名 1"]')
        ?.value,
    ).toBe("证书编号");
    expect(
      document.querySelector<HTMLInputElement>('[aria-label="字段值 1"]')
        ?.value,
    ).toBe("CN2024-0881");

    // 改第 2 条佐证引用 doc:2 → doc:9,保存发 PATCH
    fireEvent.change(screen.getByLabelText("佐证引用 2"), {
      target: { value: "doc:9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存实体" }));

    await waitFor(() => {
      const patch = calls.find(
        (call) => call.init?.method === "PATCH" && call.path.includes("/materials/"),
      );
      if (!patch) throw new Error("PATCH not sent");
      expect(patch.path).toBe("/api/extensions/bid-write/materials/m1");
      const body = jsonBody(patch.init);
      expect(body.name).toBe("ISO9001 质量管理体系认证");
      expect((body.fields as Record<string, string>)["证书编号"]).toBe(
        "CN2024-0881",
      );
      expect(body.evidence_refs).toEqual(["doc:1", "doc:9"]);
    });
  });

  it("新建抽屉:切换类型重载模板,POST 携带 fields 与佐证引用(past_bid 词汇回归)", async () => {
    renderView();

    fireEvent.click(
      await screen.findByRole("button", { name: /新建实体/ }),
    );

    const dialog = await screen.findByRole("dialog");
    // 默认资质模板预填 4 行
    expect(
      document.querySelector<HTMLInputElement>('[aria-label="字段名 4"]')
        ?.value,
    ).toBe("覆盖范围");

    // 切到历史标书:模板换为 past_bid 四行(词汇契约回归:不再是 history_bid)
    fireEvent.click(within(dialog).getByRole("radio", { name: /历史标书/ }));
    expect(
      document.querySelector<HTMLInputElement>('[aria-label="字段名 1"]')
        ?.value,
    ).toBe("来源项目");

    fireEvent.change(screen.getByLabelText("实体名称"), {
      target: { value: "2025 某集团废水治理投标文件(脱敏)" },
    });
    fireEvent.change(screen.getByLabelText("字段值 1"), {
      target: { value: "某集团 2025-04" },
    });
    fireEvent.click(screen.getByRole("button", { name: /添加佐证引用/ }));
    fireEvent.change(screen.getByLabelText("佐证引用 1"), {
      target: { value: "doc:7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建实体" }));

    await waitFor(() => {
      const post = calls.find(
        (call) => call.init?.method === "POST" && call.path.endsWith("/materials"),
      );
      if (!post) throw new Error("POST not sent");
      const body = jsonBody(post.init);
      expect(body.entity_type).toBe("past_bid");
      expect(body.name).toBe("2025 某集团废水治理投标文件(脱敏)");
      expect((body.fields as Record<string, string>)["来源项目"]).toBe(
        "某集团 2025-04",
      );
      expect(body.evidence_refs).toEqual(["doc:7"]);
    });
  });

  it("删除需确认:取消不发请求,确认后发 DELETE", async () => {
    renderView();

    fireEvent.click(
      await screen.findByRole("button", { name: "删除 XX 污水处理厂提标改造 EPC" }),
    );

    const dialog = await screen.findByRole("dialog", { name: "删除实体" });
    expect(within(dialog).getByText(/已引用该实体的任务/)).toBeTruthy();

    // 取消不发 DELETE
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(
      calls.some((call) => call.init?.method === "DELETE"),
    ).toBe(false);

    // 再次进入并确认 → DELETE
    fireEvent.click(
      screen.getByRole("button", { name: "删除 XX 污水处理厂提标改造 EPC" }),
    );
    fireEvent.click(
      within(await screen.findByRole("dialog", { name: "删除实体" })).getByRole(
        "button",
        { name: "确认删除" },
      ),
    );
    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.init?.method === "DELETE" &&
            call.path === "/api/extensions/bid-write/materials/m2",
        ),
      ).toBe(true);
    });
  });
});
