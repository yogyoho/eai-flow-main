import { describe, expect, test } from "vitest";

import {
  COVER_EMPTY_ELEMENTS,
  COVER_SLOT_OPTIONS,
  isCoverSlotResolvable,
  patchCoverElementsPage,
} from "@/extensions/output/cover-state";
import { transformTemplate } from "@/extensions/output/transforms";
import type { Cover } from "@/extensions/output/types";

describe("transformTemplate cover_elements", () => {
  test("maps cover_elements → coverElements", () => {
    const tpl = transformTemplate({
      id: "1", name: "T", report_type: "g", is_builtin: false,
      page_settings: {}, body_styles: {}, heading_styles: [], reference_style: "gb7714",
      created_at: "", updated_at: "",
      cover_elements: { mode: "elements", pages: [{ elements: [{ id: "e1", type: "text", text: "报告标题" }] }], sourceFile: "x.docx" },
    });
    expect(tpl.coverElements?.pages[0]?.elements[0]?.text).toBe("报告标题");
  });

  test("defaults coverElements to null when absent", () => {
    const tpl = transformTemplate({ id: "1", name: "T", report_type: "g", is_builtin: false, page_settings: {}, body_styles: {}, heading_styles: [], reference_style: "gb7714", created_at: "", updated_at: "" });
    expect(tpl.coverElements).toBeNull();
  });
});

describe("cover element helpers", () => {
  test("COVER_SLOT_OPTIONS 含全部绑定变量 (含 design_unit)", () => {
    const ids = COVER_SLOT_OPTIONS.map((o) => o.value);
    expect(ids).toEqual(["title", "client", "project_number", "date", "project_name", "stage", "design_unit"]);
  });

  test("design_unit 已纳入可解析集 (后端 COVER_SLOT_VALUE_KEYS 已含)", () => {
    expect(isCoverSlotResolvable("design_unit")).toBe(true);
  });

  test("patchCoverElementsPage 更新指定页元素", () => {
    const cover: Cover = {
      mode: "elements",
      pages: [{ elements: [{ id: "e1", type: "text", text: "A" }] }, { elements: [] }],
    };
    const next = patchCoverElementsPage(cover, 0, (els) =>
      els.map((e) => (e.id === "e1" ? { ...e, text: "B" } : e)),
    );
    expect(next).not.toBeNull();
    expect(next!.pages[0]?.elements[0]?.text).toBe("B");
    expect(next!.pages[1]).toEqual(cover.pages[1]);
  });

  test("COVER_EMPTY_ELEMENTS 是空封面", () => {
    expect(COVER_EMPTY_ELEMENTS.mode).toBe("elements");
    expect(COVER_EMPTY_ELEMENTS.pages).toEqual([{ elements: [] }]);
  });
});
