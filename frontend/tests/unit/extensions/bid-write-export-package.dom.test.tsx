// 批三十三：交付包卡片（批准门控 / 生成动作 / 审计历史）
import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { DeliveryPackageCard } from "@/extensions/bid-write/components/DeliveryPackageCard";
import type { ApprovalRevision, ExportRecord } from "@/extensions/bid-write/types";

const HASH = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890";

function revision(status: string): ApprovalRevision {
  return {
    id: "rev-1",
    revision_no: 2,
    status,
    doc_hash: HASH,
    schema_version: "0.1.0",
    assertion_snapshot: { status: "ok", blocked: false },
    approval_instance_id: "inst-1",
    hash_ok: true,
    created_at: "2026-11-14T10:00:00Z",
    submitted_at: "2026-11-14T10:00:00Z",
    decided_at: status === "approved" ? "2026-11-14T11:00:00Z" : null,
  };
}

const HISTORY: ExportRecord[] = [
  {
    id: "exp-1",
    revision_id: "rev-12345678",
    doc_hash: HASH,
    bundle_sha256: HASH,
    file_count: 3,
    total_bytes: 2048,
    watermark: "商务风险未确认",
    created_at: "2026-11-15T00:10:00Z",
  },
];

afterEach(cleanup);

function renderCard(overrides: Partial<Parameters<typeof DeliveryPackageCard>[0]> = {}) {
  const onExport = rs.fn();
  render(
    <DeliveryPackageCard
      revision={revision("submitted")}
      history={[]}
      exporting={false}
      result={null}
      error={null}
      onExport={onExport}
      {...overrides}
    />,
  );
  return onExport;
}

describe("DeliveryPackageCard", () => {
  it("未批准时禁用导出并说明原因", () => {
    const onExport = renderCard();
    const button = screen.getByRole("button", { name: /生成 DOCX 交付包/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/需正文审批通过后才能生成交付包/)).toBeTruthy();
    expect(onExport).not.toHaveBeenCalled();
  });

  it("已批准时点击生成交付包", () => {
    const onExport = renderCard({ revision: revision("approved") });
    const button = screen.getByRole("button", { name: /生成 DOCX 交付包/ });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("展示导出结果与审计历史", () => {
    renderCard({
      revision: revision("approved"),
      history: HISTORY,
      result: {
        blob: new Blob(["zip"]),
        filename: "项目-交付包.zip",
        exportId: "exp-1",
        sha256: HASH,
        fileCount: 3,
        totalBytes: 2048,
        watermarked: true,
      },
    });
    expect(screen.getByTestId("export-result").textContent).toContain("3 个 DOCX 分册");
    expect(screen.getByTestId("export-result").textContent).toContain("商务风险未确认");
    expect(screen.getByText(/3 个文件/)).toBeTruthy();
  });
});
