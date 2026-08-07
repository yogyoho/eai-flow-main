import type { Cover, CoverElement, CoverMaster, CoverTemplate } from "./types";

/** Neutral cover-template seed: every boolean explicitly false + centered logo.
 * NOT the old COVER_DEFAULT (all-true): a partial patch merged over this base
 * keeps each toggle independent, and the explicit `false` survives backend
 * `model_dump()` defaults on create (CoverTemplateSchema defaults booleans to
 * true — see service.py::create_template). */
export const COVER_EMPTY: CoverTemplate = {
  showLogo: false,
  showTitle: false,
  showClient: false,
  showDate: false,
  showProjectNumber: false,
  logoPosition: "center",
};

/** Merge a partial patch over the current cover-template state, ALWAYS seeding
 * from COVER_EMPTY (all five booleans explicitly false). A non-null partial
 * `current` (e.g. a template reloaded from the update path, which persists only
 * the set fields) must not leak missing booleans — they'd be defaulted to true
 * by the backend CoverTemplateSchema on the next create/update. */
export function patchCoverState(
  current: CoverTemplate | null,
  patch: Partial<CoverTemplate>,
): CoverTemplate {
  return { ...COVER_EMPTY, ...(current ?? {}), ...patch };
}

/** A cover-template whose five content booleans are all false carries no cover
 * content — collapse it to null so it is not persisted as a configured cover
 * (api.ts forwards any non-null cover_template) and does not flip backend
 * has_cover, which would render a spurious blank cover page. */
export function normalizeCoverTemplate(
  ct: CoverTemplate | null,
): CoverTemplate | null {
  if (!ct) return null;
  if (
    ct.showLogo ||
    ct.showTitle ||
    ct.showClient ||
    ct.showDate ||
    ct.showProjectNumber
  ) {
    return ct;
  }
  return null;
}

/** A cover with no pages — the neutral seed for a brand-new element-based cover
 * (mode `elements`, one empty page). */
export const COVER_EMPTY_ELEMENTS: Cover = { mode: "elements", pages: [{ elements: [] }] };

/** Variable-bound slot options for a cover element, in display order. The
 * `value` set mirrors the backend generator.py `COVER_SLOT_VALUE_KEYS`
 * (7 keys, incl. `design_unit` — resolvable from frontmatter via
 * `_resolve_cover_fields`). */
export const COVER_SLOT_OPTIONS: { value: string; label: string }[] = [
  { value: "title", label: "报告标题" },
  { value: "client", label: "建设单位" },
  { value: "project_number", label: "项目编号" },
  { value: "date", label: "日期" },
  { value: "project_name", label: "项目名" },
  { value: "stage", label: "设计阶段" },
  { value: "design_unit", label: "设计单位" },
];

/** Patch the elements of a single cover page (immutable). `pageIndex` out of
 * range leaves the cover untouched; `null` cover passes through as null. */
export function patchCoverElementsPage(
  cover: Cover | null,
  pageIndex: number,
  updater: (elements: CoverElement[]) => CoverElement[],
): Cover | null {
  if (!cover) return cover;
  return {
    ...cover,
    pages: cover.pages.map((p, i) => (i === pageIndex ? { ...p, elements: updater(p.elements) } : p)),
  };
}

/** Slot ids the generator can resolve a replacement value for — synced with the
 * backend generator.py `COVER_SLOT_VALUE_KEYS` (7 keys, incl. design_unit from
 * frontmatter via `_resolve_cover_fields`). Any other slot
 * (archive_no / version / certificate_no) has no value source at generation:
 * toggling it to "variable" is a silent no-op, so the UI must lock it to
 * literal. */
export const COVER_RESOLVABLE_SLOT_IDS = [
  "title",
  "client",
  "project_number",
  "date",
  "project_name",
  "stage",
  "design_unit",
] as const;

export function isCoverSlotResolvable(id: string): boolean {
  return (COVER_RESOLVABLE_SLOT_IDS as readonly string[]).includes(id);
}

/** Effective slot kind for DISPLAY: unresolvable slots are always literal,
 * regardless of the stored `kind` (archive_no/version/certificate_no are
 * extracted as "variable" but can never be filled at generation). */
export function coverSlotEffectiveKind(slot: {
  id: string;
  kind: string;
}): "variable" | "literal" {
  return isCoverSlotResolvable(slot.id) && slot.kind === "variable"
    ? "variable"
    : "literal";
}

/** Human label for a slot's value-source hint. `defaultFrom` is the declared
 * extraction source (layout_import._prefill_cover_slots); when it is null the
 * generator STILL fills resolvable slots at generation (project_number from
 * api/frontmatter, project_name/stage from frontmatter) — so "无自动来源" must
 * only appear for genuinely unresolvable ids (archive_no/version/
 * certificate_no), never for a resolvable slot that auto-fills. */
const COVER_DEFAULT_FROM_LABELS: Record<string, string> = {
  doc_title: "来自文档标题",
  today: "来自当前日期",
  "frontmatter:client": "来自报告元数据·建设单位",
};

const COVER_ID_SOURCE_LABELS: Record<string, string> = {
  project_number: "来自接口参数/报告元数据",
  project_name: "来自报告元数据·项目名",
  stage: "来自报告元数据·设计阶段",
  design_unit: "来自报告元数据·设计单位",
  title: "生成时填入报告标题",
  client: "生成时填入建设单位",
  date: "生成时填入日期",
};

export function coverSlotSourceLabel(
  id: string,
  defaultFrom: string | null | undefined,
): string {
  if (defaultFrom)
    return COVER_DEFAULT_FROM_LABELS[defaultFrom] ?? "无自动来源";
  if (isCoverSlotResolvable(id))
    return COVER_ID_SOURCE_LABELS[id] ?? "生成时填入";
  return "无自动来源";
}

/** Keep a slot's find-anchor (`target`) consistent when its sampleValue is
 * edited. Colon slots carry a label-inclusive target ("项目编号：XX") that the
 * generator locates; the edit must rewrite the value part inside the target so
 * generation still finds it. Non-colon slots return null → generator falls back
 * to the (edited) sampleValue. */
export function syncSlotTarget(
  slot: { target?: string | null; sampleValue: string },
  newValue: string,
): string | null {
  const t = slot.target;
  if (t && t !== slot.sampleValue) {
    return slot.sampleValue ? t.replace(slot.sampleValue, newValue) : newValue;
  }
  return null;
}

/** Display logo position, defaulting to "center" for null/old templates. */
export function coverLogoPosition(
  ct: CoverTemplate | null,
): CoverTemplate["logoPosition"] {
  return ct?.logoPosition ?? "center";
}

export interface CoverImportResult {
  coverMaster: CoverMaster | null;
  /** `undefined` = keep the current toggle fallback (a master supersedes it but
   * removing the master later falls back to it). */
  coverTemplate: CoverTemplate | null | undefined;
}

/** Derive cover state from an import payload.
 *
 * - master present → adopt it; leave the toggle fallback dormant.
 * - no master → ALWAYS reset any stale master (re-importing a cover-less sample
 *   must not keep showing the old cover).
 * - toggle template present + `cover_detected` → adopt it; else clear it.
 * - ignores every non-cover key (cover-only imports must not touch other sections). */
export function resolveCoverFromImport(
  data: Record<string, unknown>,
): CoverImportResult {
  const cm = data.cover_master as CoverMaster | null | undefined;
  if (cm?.mode === "master") {
    return { coverMaster: cm, coverTemplate: undefined };
  }
  const ct = data.cover_template as CoverTemplate | null | undefined;
  if (
    data.cover_detected === true &&
    ct &&
    (ct.showLogo ||
      ct.showTitle ||
      ct.showClient ||
      ct.showDate ||
      ct.showProjectNumber)
  ) {
    return { coverMaster: null, coverTemplate: ct };
  }
  return { coverMaster: null, coverTemplate: null };
}
