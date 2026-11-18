import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { cleanup, screen } from "@testing-library/react";

import { EnumCellView } from "@/extensions/bid-write/editor/constraints";

afterEach(cleanup);

function enumNode() {
  return {
    type: { name: "enum_cell" },
    attrs: {
      enum_values: ["完全响应", "正偏离", "负偏离"],
      current: "完全响应",
      col_span: 1,
      row_span: 1,
    },
    content: { size: 0 },
  };
}

describe("bid-write EnumCellView", () => {
  it("响应策略使用 shadcn Select，页面不再出现原生 select", async () => {
    const dispatch = rs.fn();
    const view = new EnumCellView(
      enumNode() as never,
      { state: {} as never, dispatch },
      () => 0,
    );
    document.body.append(view.dom);

    const trigger = await screen.findByRole("combobox", { name: "响应策略" });
    expect(trigger.getAttribute("data-slot")).toBe("select-trigger");
    expect(document.querySelector("select")).toBeNull();

    view.destroy();
    view.dom.remove();
  });
});
