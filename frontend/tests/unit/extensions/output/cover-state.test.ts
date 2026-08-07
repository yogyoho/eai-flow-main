import { describe, expect, test } from "vitest";

import {
  COVER_EMPTY,
  coverLogoPosition,
  coverSlotEffectiveKind,
  coverSlotSourceLabel,
  isCoverSlotResolvable,
  normalizeCoverTemplate,
  patchCoverState,
  resolveCoverFromImport,
  syncSlotTarget,
} from "@/extensions/output/cover-state";
import type { CoverMaster, CoverTemplate } from "@/extensions/output/types";

const MASTER: CoverMaster = {
  mode: "master",
  xml: "<w:p/>",
  images: [],
  slots: [
    {
      id: "client",
      label: "建设单位",
      kind: "variable",
      sampleValue: "甲公司",
      defaultFrom: "frontmatter:client",
    },
  ],
  sourceFile: "a.docx",
  boundary: "before_toc",
};

const CT = {
  showLogo: true,
  logoPosition: "center" as const,
  showTitle: false,
  showClient: false,
  showDate: false,
  showProjectNumber: false,
};

describe("COVER_EMPTY", () => {
  test("is a full CoverTemplate with every boolean explicitly false", () => {
    expect(COVER_EMPTY).toEqual({
      showLogo: false,
      showTitle: false,
      showClient: false,
      showDate: false,
      showProjectNumber: false,
      logoPosition: "center",
    });
    // M1 往返回归：全 5 布尔显式 present，载荷不被后端 CoverTemplateSchema 缺省值补成 true
    expect(Object.keys(COVER_EMPTY).sort()).toEqual([
      "logoPosition",
      "showClient",
      "showDate",
      "showLogo",
      "showProjectNumber",
      "showTitle",
    ]);
  });
});

describe("patchCoverState (M1)", () => {
  test("from null, toggling one switch turns on exactly that field", () => {
    const s = patchCoverState(null, { showLogo: true });
    expect(s.showLogo).toBe(true);
    expect(s.showTitle).toBe(false);
    expect(s.showClient).toBe(false);
    expect(s.showDate).toBe(false);
    expect(s.showProjectNumber).toBe(false);
  });

  test("later toggles preserve prior selections and stay independent", () => {
    const once = patchCoverState(null, { showLogo: true });
    const twice = patchCoverState(once, { showDate: true });
    expect(twice).toEqual({ ...COVER_EMPTY, showLogo: true, showDate: true });
  });

  test("non-null PARTIAL current still yields a complete explicit-false object", () => {
    // update path persists only set fields (service exclude_unset) → reload gives partial
    const partial = { logoPosition: "center" as const };
    const s = patchCoverState(partial as CoverTemplate, { showLogo: true });
    expect(s).toEqual({ ...COVER_EMPTY, showLogo: true });
    expect(s.showTitle).toBe(false);
  });
});

describe("normalizeCoverTemplate", () => {
  test("all-false cover collapses to null (no spurious blank cover page)", () => {
    expect(normalizeCoverTemplate({ ...COVER_EMPTY })).toBeNull();
    expect(normalizeCoverTemplate(null)).toBeNull();
  });

  test("any content boolean true → passthrough", () => {
    const ct = { ...COVER_EMPTY, showLogo: true };
    expect(normalizeCoverTemplate(ct)).toEqual(ct);
  });
});

describe("resolveCoverFromImport", () => {
  test("master present → adopt it, leave toggle fallback dormant (H2)", () => {
    const r = resolveCoverFromImport({
      cover_master: MASTER,
      cover_detected: true,
    });
    expect(r.coverMaster).toEqual(MASTER);
    expect(r.coverTemplate).toBeUndefined();
  });

  test("no master + cover detected + toggles → reset stale master, adopt toggles (H2)", () => {
    const r = resolveCoverFromImport({
      cover_template: CT,
      cover_detected: true,
    });
    expect(r.coverMaster).toBeNull();
    expect(r.coverTemplate).toEqual(CT);
  });

  test("no cover at all → reset both (H2 stale master cleared)", () => {
    const r = resolveCoverFromImport({});
    expect(r.coverMaster).toBeNull();
    expect(r.coverTemplate).toBeNull();
  });

  test("cover_detected false → stale toggle payload is cleared too (H2)", () => {
    const r = resolveCoverFromImport({
      cover_template: CT,
      cover_detected: false,
    });
    expect(r.coverMaster).toBeNull();
    expect(r.coverTemplate).toBeNull();
  });

  test("all-false toggle payload is treated as no cover", () => {
    const allFalse = { ...COVER_EMPTY };
    const r = resolveCoverFromImport({
      cover_template: allFalse,
      cover_detected: true,
    });
    expect(r.coverMaster).toBeNull();
    expect(r.coverTemplate).toBeNull();
  });

  test("non-master cover_master is treated as absent, not adopted", () => {
    const r = resolveCoverFromImport({
      cover_master: { ...MASTER, mode: "toggle" },
      cover_detected: true,
    });
    expect(r.coverMaster).toBeNull();
    expect(r.coverTemplate).toBeNull();
  });

  test("master + toggle both present → master wins, toggle stays dormant", () => {
    const r = resolveCoverFromImport({
      cover_master: MASTER,
      cover_template: CT,
      cover_detected: true,
    });
    expect(r.coverMaster).toEqual(MASTER);
    expect(r.coverTemplate).toBeUndefined();
  });

  test("toggle present but cover_detected absent → cleared", () => {
    const r = resolveCoverFromImport({ cover_template: CT });
    expect(r.coverMaster).toBeNull();
    expect(r.coverTemplate).toBeNull();
  });

  test("returns only cover keys — non-cover sections untouched by cover-only import (H1)", () => {
    const r = resolveCoverFromImport({
      page_settings: { paperSize: "A3" },
      cover_master: MASTER,
      cover_detected: true,
    });
    expect(r.coverMaster).toEqual(MASTER);
    expect(Object.keys(r).sort()).toEqual(["coverMaster", "coverTemplate"]);
  });
});

describe("M6 resolvable-slot lock", () => {
  test("generator-resolvable ids are resolvable", () => {
    expect(
      [
        "title",
        "client",
        "project_number",
        "date",
        "project_name",
        "stage",
        "design_unit",
      ].every(isCoverSlotResolvable),
    ).toBe(true);
  });

  test("unresolvable ids are not resolvable", () => {
    expect(isCoverSlotResolvable("archive_no")).toBe(false);
    expect(isCoverSlotResolvable("version")).toBe(false);
    expect(isCoverSlotResolvable("certificate_no")).toBe(false);
  });

  test("unresolvable slot forces literal display regardless of stored kind", () => {
    expect(coverSlotEffectiveKind({ id: "archive_no", kind: "variable" })).toBe(
      "literal",
    );
    expect(coverSlotEffectiveKind({ id: "design_unit", kind: "literal" })).toBe(
      "literal",
    );
  });

  test("resolvable slot respects stored kind", () => {
    expect(coverSlotEffectiveKind({ id: "client", kind: "variable" })).toBe(
      "variable",
    );
    expect(coverSlotEffectiveKind({ id: "client", kind: "literal" })).toBe(
      "literal",
    );
  });
});

describe("M4 source labels", () => {
  test("maps known defaultFrom values", () => {
    expect(coverSlotSourceLabel("title", "doc_title")).toBe("来自文档标题");
    expect(coverSlotSourceLabel("date", "today")).toBe("来自当前日期");
    expect(coverSlotSourceLabel("client", "frontmatter:client")).toBe(
      "来自报告元数据·建设单位",
    );
  });

  test("resolvable slot with null defaultFrom still auto-fills at generation — shows its actual source", () => {
    expect(coverSlotSourceLabel("project_number", null)).toBe(
      "来自接口参数/报告元数据",
    );
    expect(coverSlotSourceLabel("project_name", null)).toBe(
      "来自报告元数据·项目名",
    );
    expect(coverSlotSourceLabel("stage", null)).toBe("来自报告元数据·设计阶段");
    expect(coverSlotSourceLabel("design_unit", null)).toBe(
      "来自报告元数据·设计单位",
    );
  });

  test("genuinely unresolvable slot → 无自动来源", () => {
    expect(coverSlotSourceLabel("archive_no", null)).toBe("无自动来源");
    expect(coverSlotSourceLabel("archive_no", undefined)).toBe("无自动来源");
  });

  test("unknown defaultFrom on a resolvable slot → 无自动来源", () => {
    expect(coverSlotSourceLabel("title", "frontmatter:stage")).toBe(
      "无自动来源",
    );
  });
});

describe("M3 syncSlotTarget", () => {
  test("colon slot: rewrites the value inside the label-inclusive target", () => {
    expect(
      syncSlotTarget({ target: "项目编号：XX", sampleValue: "XX" }, "P001"),
    ).toBe("项目编号：P001");
  });

  test("non-colon slot (target absent) → null, generator falls back to sampleValue", () => {
    expect(
      syncSlotTarget({ target: null, sampleValue: "旧标题" }, "新标题"),
    ).toBeNull();
  });

  test("target equal to sampleValue → null (falls back to edited sampleValue)", () => {
    expect(
      syncSlotTarget({ target: "XX", sampleValue: "XX" }, "P002"),
    ).toBeNull();
  });
});

describe("M2 coverLogoPosition", () => {
  test("null template → center", () => {
    expect(coverLogoPosition(null)).toBe("center");
  });

  test("missing logoPosition on old template → center", () => {
    expect(coverLogoPosition({ showLogo: true } as CoverTemplate)).toBe(
      "center",
    );
  });

  test("respects explicit value", () => {
    expect(coverLogoPosition({ ...COVER_EMPTY, logoPosition: "right" })).toBe(
      "right",
    );
  });
});
