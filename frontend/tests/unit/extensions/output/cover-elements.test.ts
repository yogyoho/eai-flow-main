import { describe, expect, test } from "vitest";

import { transformTemplate } from "@/extensions/output/transforms";

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
