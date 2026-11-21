import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { HelpDrawer } from "@/extensions/bid-write/components/HelpDrawer";

describe("bid-write HelpDrawer", () => {
  afterEach(() => {
    cleanup();
  });

  it("打开时渲染标题与内容", () => {
    const onClose = rs.fn();
    render(
      <HelpDrawer open title="流程说明" onClose={onClose}>
        <p>本页说明内容</p>
      </HelpDrawer>,
    );

    const dialog = screen.getByRole("dialog", { name: "流程说明" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByText("本页说明内容")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("知道了按钮触发 onClose", () => {
    const onClose = rs.fn();
    render(
      <HelpDrawer open title="本页说明" onClose={onClose}>
        <p>帮助内容</p>
      </HelpDrawer>,
    );

    fireEvent.click(screen.getByRole("button", { name: "知道了" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("关闭时不渲染", () => {
    const onClose = rs.fn();
    render(
      <HelpDrawer open={false} title="流程说明" onClose={onClose}>
        <p>本页说明内容</p>
      </HelpDrawer>,
    );

    expect(screen.queryByRole("dialog", { name: "流程说明" })).toBeNull();
    expect(screen.queryByText("本页说明内容")).toBeNull();
    expect(onClose).not.toHaveBeenCalled();
  });
});
