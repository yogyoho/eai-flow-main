// 批卅二 T3:②素材核对页瘦身断言——实体库区块移除、缺口关键词映射(经 helpers 纯函数面)。
import { describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { MaterialsView } from "@/extensions/bid-write/components/MaterialsView";
import { gapLibraryType } from "@/extensions/bid-write/helpers";

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/bid-write/materials",
  useSearchParams: () => new URLSearchParams("task_id=t1"),
}));

describe("②素材核对页 瘦身(批卅二)", () => {
  it("实体库区块不再渲染(素材实体库标题不存在)", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(<MaterialsView />, {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    expect(screen.queryByText("素材实体库")).toBeNull();
  });

  it("缺口关键词映射到六类或 all(gapLibraryType)", () => {
    expect(gapLibraryType("ISO9001 质量管理体系认证证书")).toBe("qualification");
    expect(gapLibraryType("同类合同业绩案例")).toBe("performance");
    expect(gapLibraryType("无关键词的要求")).toBe("all");
  });
});
