import { afterEach, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";

import { ExportView } from "@/extensions/bid-write/components/ExportView";
import { LibraryView } from "@/extensions/bid-write/components/LibraryView";
import { EXPORT_COPY, LIBRARY_COPY } from "@/extensions/bid-write/copy";

rs.mock("@/extensions/bid-write/hooks", () => ({
  useBidWriteGaps: () => ({
    data: {
      items: [],
      summary: { total: 0, material_ready: 0 },
      assertions: null,
    },
    error: null,
    isLoading: false,
    refetch: async () => undefined,
  }),
  useExportPrecheck: () => ({
    data: null,
    error: null,
    isPending: false,
    mutateAsync: async () => null,
  }),
  useExportRevision: () => ({
    data: null,
    error: null,
    isPending: false,
    mutateAsync: async () => null,
  }),
  useSelectedWriteTask: () => ({
    taskId: "t1",
    task: {
      id: "t1",
      biz_no: "BIZ-1",
      status: "submitted",
      progress: {},
      error: null,
      project_name: "测试项目",
      lot_name: null,
      tender_no: null,
      created_at: null,
      engine_meta: {},
    },
    tasks: [],
    isLoading: false,
    error: null,
  }),
  useTaskApproval: () => ({
    data: {
      revision: {
        id: "rev-1",
        revision_no: 1,
        status: "submitted",
        doc_hash: "hash",
        schema_version: "v1",
        assertion_snapshot: {},
        approval_instance_id: null,
        hash_ok: true,
        created_at: null,
        submitted_at: null,
        decided_at: null,
      },
      approval: null,
      revisions: [],
      is_owner: true,
    },
    error: null,
    isLoading: false,
  }),
  useTaskExports: () => ({
    data: { items: [] },
    error: null,
    isLoading: false,
  }),
  useCreateMaterial: () => ({
    isPending: false,
    mutateAsync: async () => null,
  }),
  useDeleteMaterial: () => ({
    isPending: false,
    mutateAsync: async () => null,
  }),
  useMaterials: () => ({
    data: { items: [] },
    error: null,
    isLoading: false,
    refetch: async () => undefined,
  }),
  usePatchMaterial: () => ({
    isPending: false,
    mutateAsync: async () => null,
  }),
}));

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/bid-write",
  useSearchParams: () => new URLSearchParams(),
}));

function renderView(view: "export" | "library"): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      {view === "export" ? <ExportView /> : <LibraryView />}
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  rs.restoreAllMocks();
});

it("导出页副标题、交付说明与修订状态为业务词", () => {
  renderView("export");

  expect(
    screen.getByText(`测试项目 · ${EXPORT_COPY.subtitle}`),
  ).toBeTruthy();
  expect(screen.getByText(/修订 1 · 已提交审批/)).toBeTruthy();
  expect(
    screen.getAllByText("需正文审批通过后才能生成交付包").length,
  ).toBeGreaterThan(0);
  expect(screen.queryByText(/前置校验只读重算，零落库/)).toBeNull();
  expect(screen.queryByText(/已批准修订可生成 DOCX 分册交付包/)).toBeNull();
});

it("素材库副标题、空状态与底部注释为业务词", () => {
  renderView("library");

  expect(screen.getByText(LIBRARY_COPY.subtitle)).toBeTruthy();
  expect(screen.getByText(LIBRARY_COPY.empty)).toBeTruthy();
  expect(screen.getByText(LIBRARY_COPY.footerNote)).toBeTruthy();
  expect(screen.queryByText(/owner 级资产/)).toBeNull();
  expect(screen.queryByText(/verifiable/)).toBeNull();
  expect(screen.queryByText(/D0 门禁/)).toBeNull();
});
