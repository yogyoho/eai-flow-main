import { describe, expect, it } from "@rstest/core";

import {
  fillItemLabel,
  workbenchSubtitle,
} from "@/extensions/bid-write/components/WorkbenchView";
import { WORKBENCH_COPY } from "@/extensions/bid-write/copy";

describe("workbench 文案组装", () => {
  it("副标题 = 项目名 + 业务描述，无任务时也返回业务描述", () => {
    expect(workbenchSubtitle("测试项目")).toBe(
      `测试项目 · ${WORKBENCH_COPY.subtitle}`,
    );
    expect(workbenchSubtitle(null)).toBe(WORKBENCH_COPY.subtitle);
  });

  it("空白占位 label 兜底为「未命名占位符」，短 label 不猜测", () => {
    expect(fillItemLabel("%")).toBe("%");
    expect(fillItemLabel("与")).toBe("与");
    expect(fillItemLabel("   ")).toBe(WORKBENCH_COPY.unnamedPlaceholder);
  });
});
