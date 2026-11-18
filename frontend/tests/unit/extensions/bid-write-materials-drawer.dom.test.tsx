import { afterEach, describe, expect, it, rs } from "@rstest/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

rs.mock("@/extensions/bid-write/hooks", () => {
  const idle = () => ({ mutateAsync: async () => undefined, isPending: false });
  return {
    useSelectedWriteTask: () => ({
      taskId: "t1",
      task: { id: "t1", status: "matrix_ready" },
      isLoading: false,
      error: null,
    }),
    useBidWriteGaps: () => ({
      data: {
        items: [
          {
            clause_id: "att:1",
            kind: "attachment",
            requirement: "营业执照副本",
            star: true,
            status: "confirmed",
            material_state: "无对应素材",
            evidence_refs: [],
          },
          {
            clause_id: "decl:1",
            kind: "clause",
            requirement: "投标有效期不少于 90 日历天",
            star: false,
            status: "blocked",
            material_state: "无对应素材",
            evidence_refs: [],
          },
          {
            clause_id: "att:2",
            kind: "attachment",
            requirement:
              "name=营业执照; clause=第一章4.1; mandatory=★必需; year_span=1; min_count=2",
            star: true,
            status: "draft",
            material_state: "有但缺佐证",
            evidence_refs: [],
          },
        ],
        summary: { total: 2, material_ready: 0 },
        assertions: null,
      },
      isLoading: false,
      error: null,
      refetch: rs.fn(),
    }),
    useMaterials: () => ({
      data: { items: [] },
      isLoading: false,
      error: null,
      refetch: rs.fn(),
    }),
    useCreateMaterial: idle,
    useDeleteMaterial: idle,
    useMaterialProfile: () => ({ data: { profile: {} }, isLoading: false }),
    usePutMaterialProfile: idle,
    usePolicy: () => ({ data: { policy: undefined }, isLoading: false }),
    usePutPolicy: idle,
  };
});

import { MaterialsView } from "@/extensions/bid-write/components/MaterialsView";

afterEach(cleanup);

describe("bid-write MaterialsView 缺口详情抽屉", () => {
  it("缺口清单横向充满，点击行后在右侧抽屉展示详情", async () => {
    render(<MaterialsView />);

    await screen.findByRole("heading", { name: "缺口清单" });
    expect(document.querySelector(".bw-materials-split")).toBeNull();
    expect(document.querySelector(".bw-detail-card")).toBeNull();
    expect(screen.queryByRole("dialog", { name: "缺口详情" })).toBeNull();
    expect(screen.getByText("附件 1")).toBeTruthy();
    expect(screen.getByText("承诺 1")).toBeTruthy();

    const row = screen.getByText("营业执照副本").closest("tr");
    if (!row) throw new Error("缺口行未渲染");
    fireEvent.click(row);

    const drawer = await screen.findByRole("dialog", { name: "缺口详情" });
    expect(drawer.className).toContain("drawer");
    expect(within(drawer).getByText("营业执照副本")).toBeTruthy();
    expect(within(drawer).getByText("附件要求")).toBeTruthy();
    expect(within(drawer).getByText("强制条款")).toBeTruthy();

    fireEvent.click(within(drawer).getByRole("button", { name: "关闭详情" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "缺口详情" })).toBeNull(),
    );
  });

  it("要求列与详情抽屉中的英文关键字显示为中文", async () => {
    render(<MaterialsView />);

    const translated =
      "名称：营业执照；条款：第一章4.1；要求：★必需；年限：1；份数：2";
    const cell = await screen.findByText(translated);
    expect(screen.queryByText(/name=/)).toBeNull();

    const row = cell.closest("tr");
    if (!row) throw new Error("缺口行未渲染");
    fireEvent.click(row);

    const drawer = await screen.findByRole("dialog", { name: "缺口详情" });
    expect(within(drawer).getByText(translated)).toBeTruthy();
  });
});
