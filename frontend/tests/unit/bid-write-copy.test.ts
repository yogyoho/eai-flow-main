import { describe, expect, it } from "@rstest/core";

import {
  ASSERTION_PRE_LABELS,
  ASSERTION_RENDER_LABELS,
  ASSERTION_RETRY_LABELS,
  EXPORT_COPY,
  GENERATE_COPY,
  LIBRARY_COPY,
  MATERIALS_COPY,
  PROJECTS_COPY,
  REGISTRY_COPY,
  REVIEW_COPY,
  WORKBENCH_COPY,
} from "@/extensions/bid-write/copy";
import {
  assertionMessageLabel,
  safeProjectTitle,
} from "@/extensions/bid-write/helpers";

const BANNED =
  /批廿|批卅|M6|旋钮|knobs|boq_items|unit_prices|hash|no_signal|verifiable|owner 级|零落库|p0\.yaml|TODO_BLOCK|MARK_YELLOW|BOARD_ONLY|self_refine|advisory-only|埋点|真执行器|D0 |D1 |D2 |D3 |SK-[A-Z]+-\d+/;

function allStrings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (typeof value === "function") return [];
  if (value && typeof value === "object") {
    return Object.values(value).flatMap(allStrings);
  }
  return [];
}

const COPY_MODULES = {
  GENERATE_COPY,
  WORKBENCH_COPY,
  REVIEW_COPY,
  EXPORT_COPY,
  LIBRARY_COPY,
  PROJECTS_COPY,
  MATERIALS_COPY,
  REGISTRY_COPY,
};

describe("bid-write copy 文案中心", () => {
  it("所有静态文案不含禁用术语", () => {
    for (const [name, module] of Object.entries(COPY_MODULES)) {
      for (const text of allStrings(module)) {
        expect(BANNED.test(text), `${name} 含术语: ${text}`).toBe(false);
      }
    }
  });

  it("断言渲染/预审/重试词表覆盖已知常量且值为业务词", () => {
    expect(ASSERTION_RENDER_LABELS.TODO_BLOCK).toBe("标红并列入待补清单");
    expect(ASSERTION_RENDER_LABELS.MARK_YELLOW).toBe("标黄提醒");
    expect(ASSERTION_RENDER_LABELS.BOARD_ONLY).toBe("仅面板展示");
    expect(ASSERTION_RENDER_LABELS.NONE).toBe("不显示");
    expect(ASSERTION_PRE_LABELS.MISSING).toBe("显示缺失");
    expect(ASSERTION_PRE_LABELS.UNKNOWN).toBe("显示未知");
    expect(ASSERTION_RETRY_LABELS.self_refine_max_2).toBe("自动重试最多 2 次");
    expect(ASSERTION_RETRY_LABELS.self_refine_max_1).toBe("自动重试最多 1 次");
    expect(ASSERTION_RETRY_LABELS.none).toBe("不重试");
  });

  it("assertionMessageLabel 将内部断言码转为业务句", () => {
    expect(assertionMessageLabel("E-CTX-MISSING: tender.bid_deadline")).toBe(
      "缺少「投标截止」",
    );
    expect(
      assertionMessageLabel("E-CTX-MISSING: tender.bid_deadline 需补充签署日期"),
    ).toBe("缺少「投标截止」（需补充签署日期）");
    // 非内部码格式原样保留
    expect(assertionMessageLabel("承诺缺溯源 3 条")).toBe("承诺缺溯源 3 条");
  });

  it("safeProjectTitle 对乱码标题兜底，对正常标题原样返回", () => {
    expect(safeProjectTitle("环评报告智能写作平台")).toBe(
      "环评报告智能写作平台",
    );
    expect(safeProjectTitle("M0 ù¾¼Æ·ÃÉèÏîÄ¿")).toBe(
      PROJECTS_COPY.untitledProject,
    );
    expect(safeProjectTitle("")).toBe("");
  });
});
