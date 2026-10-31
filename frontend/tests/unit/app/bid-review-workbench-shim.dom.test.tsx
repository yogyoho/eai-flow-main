import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, render, waitFor } from "@testing-library/react";

// Plan7 T3:/workbench 退役重定向 shim(裁定8)——旧深链保活,内容归 /results。
const replace = rs.fn();
let params: Record<string, string> = {};

rs.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: rs.fn(), refresh: rs.fn() }),
  useSearchParams: () => ({
    get: (k: string) => params[k] ?? null,
  }),
  usePathname: () => "/bid-review/workbench",
}));

import WorkbenchRedirectPage from "@/app/bid-review/workbench/page";

function renderShim() {
  return render(<WorkbenchRedirectPage />);
}

describe("bid-review /workbench 重定向 shim(Plan7)", () => {
  afterEach(() => {
    cleanup();
    params = {};
    replace.mockClear();
  });

  it("带 task_id → /bid-review/results?task_id=(编码透传)", async () => {
    params = { task_id: "t9" };
    renderShim();
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/bid-review/results?task_id=t9"),
    );
  });

  it("不带 task_id → /bid-review/results", async () => {
    renderShim();
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/bid-review/results"),
    );
  });
});
