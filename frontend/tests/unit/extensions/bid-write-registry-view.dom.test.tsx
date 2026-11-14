import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";

// 断言注册表是新增只读端点：旧 Gateway 未重启时会返回 404。页面必须
// 诚实说明“接口尚未启用”，不得渲染 0 条断言或伪造等级行为表。
const calls: string[] = [];

rs.mock("@/core/api/fetcher", () => ({
  fetch: async (path: string) => {
    calls.push(path);
    return new Response(JSON.stringify({ detail: "Not Found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  },
}));

import { RegistryView } from "@/extensions/bid-write/components/RegistryView";

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<RegistryView />, {
    wrapper: ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe("bid-write RegistryView", () => {
  beforeEach(() => {
    calls.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  it("注册表端点 404 时提示接口未启用并可重试", async () => {
    renderView();

    expect(await screen.findByText("断言注册表接口尚未启用")).toBeTruthy();
    expect(screen.queryByText("断言总数")).toBeNull();
    expect(calls.filter((path) => path.endsWith("/registry")).length).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "重新检查" }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(
      calls.filter((path) => path.endsWith("/registry")).length,
    ).toBeGreaterThan(1);
  });
});
