import { expect, test, describe } from "vitest";

import type { LayoutTemplate } from "@/extensions/output/types";
import { transformTemplate } from "@/extensions/output/transforms";

describe("transformTemplate", () => {
  test("converts snake_case fields to camelCase", () => {
    const result = transformTemplate({
      id: "t1",
      name: "Test Template",
      report_type: "environmental_impact",
      reference_style: "gb7714",
      body_styles: { fontFamily: "SimSun", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 6, firstLineIndent: 24 },
      heading_styles: [],
      page_settings: {
        paper_size: "A4",
        orientation: "portrait",
        margin_top: 25,
        margin_bottom: 25,
        margin_left: 30,
        margin_right: 20,
      },
      created_at: "2024-01-01",
      updated_at: "2024-01-02",
    });
    expect(result.id).toBe("t1");
    expect(result.name).toBe("Test Template");
    expect(result.reportType).toBe("environmental_impact");
    expect(result.referenceStyle).toBe("gb7714");
    expect(result.bodyStyles.fontFamily).toBe("SimSun");
    expect(result.headingStyles).toEqual([]);
  });

  test("defaults referenceStyle to gb7714 when missing", () => {
    const result = transformTemplate({
      id: "t2",
      name: "No Ref Style",
      report_type: "other",
      body_styles: { fontFamily: "Arial", fontSize: 14, lineHeight: 1.6, paragraphSpacing: 8, firstLineIndent: 28 },
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
    });
    expect(result.referenceStyle).toBe("gb7714");
  });

  test("defaults headingStyles to empty array when missing", () => {
    const result = transformTemplate({
      id: "t3",
      name: "No Heading Styles",
      report_type: "safety",
      body_styles: { fontFamily: "SimHei", fontSize: 16, lineHeight: 1.8, paragraphSpacing: 10, firstLineIndent: 32 },
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
    });
    expect(result.headingStyles).toEqual([]);
  });

  test("defaults optional fields to null when missing", () => {
    const result = transformTemplate({
      id: "t4",
      name: "Minimal Template",
      report_type: "social_impact",
      body_styles: { fontFamily: "FangSong", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 6, firstLineIndent: 24 },
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
    });
    expect(result.coverTemplate).toBeNull();
    expect(result.tocSettings).toBeNull();
    expect(result.tableStyles).toBeNull();
    expect(result.figureStyles).toBeNull();
    expect(result.headerFooter).toBeNull();
    expect(result.appendixRules).toBeNull();
  });

  test("preserves all provided optional fields", () => {
    const coverTemplate = { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: false, showDate: true, showProjectNumber: true };
    const tocSettings = { maxDepth: 3, showPageNumbers: true, leaderDots: true };
    const result = transformTemplate({
      id: "t5",
      name: "Full Template",
      report_type: "environmental_impact",
      cover_template: coverTemplate,
      toc_settings: tocSettings,
      body_styles: { fontFamily: "SimSun", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 6, firstLineIndent: 24 },
      heading_styles: [{ level: 1, fontFamily: "SimHei", fontSize: 22, fontWeight: 700, color: "#000", numbering: "chinese" }],
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
    });
    expect(result.coverTemplate).toEqual(coverTemplate);
    expect(result.tocSettings).toEqual(tocSettings);
    expect(result.headingStyles).toHaveLength(1);
  });

  test("returns correct type matching LayoutTemplate interface", () => {
    const result: LayoutTemplate = transformTemplate({
      id: "t6",
      name: "Type Check",
      report_type: "test",
      body_styles: { fontFamily: "A", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 0, firstLineIndent: 0 },
      page_settings: { paper_size: "A4", orientation: "portrait", margin_top: 25, margin_bottom: 25, margin_left: 30, margin_right: 20 },
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
    });
    expect(result).toHaveProperty("id");
    expect(result).toHaveProperty("name");
    expect(result).toHaveProperty("reportType");
    expect(result).toHaveProperty("pageSettings");
    expect(result).toHaveProperty("bodyStyles");
    expect(result).toHaveProperty("createdAt");
    expect(result).toHaveProperty("updatedAt");
  });
});
