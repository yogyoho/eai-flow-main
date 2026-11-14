/**
 * bid-write 纯展示工具：状态词表、矩阵摘要、CSV 导出。
 *
 * 词表与后端 contracts.py / models.py 对齐；未知值原样展示，不猜测含义。
 */

import type { GenerateKnobs, GapItem, MatrixRowOut, WriteTaskOut } from "./types";

export const TASK_STATUS_LABELS: Record<string, string> = {
  created: "已创建",
  parsing: "解析中",
  extracting: "要素抽取中",
  matrix_ready: "矩阵就绪",
  failed: "已失败",
};

export const TASK_STATUS_TONES: Record<
  string,
  "ok" | "warn" | "bad" | "gray" | "info"
> = {
  created: "gray",
  parsing: "info",
  extracting: "info",
  matrix_ready: "ok",
  failed: "bad",
};

export const MATRIX_STRATEGY_LABELS: Record<string, string> = {
  pending: "待定",
  full: "完全响应",
  positive: "正偏离",
  negative: "负偏离",
};

export const MATRIX_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  confirmed: "已确认",
  blocked: "低置信待确认",
};

export const MATRIX_KIND_LABELS: Record<string, string> = {
  attachment: "附件要求",
  clause: "承诺条款",
  aggregate: "聚合要素",
};

export const SOURCE_PATH_LABELS: Record<string, string> = {
  "tender.attachment_requirements": "附件要求",
  "tender.required_declarations": "承诺条款",
  "tender.required_signatures": "签章要求",
  "tender.deposit_required": "投标保证金",
  "tender.bid_deadline": "投标截止",
  "tender.bid_scope": "招标范围",
  "tender.required_sections": "必需章节",
  "tender.required_tables": "必需表格",
  "tender.required_fields": "必需字段",
  "tender.volume_specs": "分册与份数",
  "tender.required_qual_level": "资质等级门槛",
  "tender.min_performance_amount": "业绩金额门槛",
  "tender.performance_window_months": "业绩年限窗口",
  "tender.min_warranty_period": "最低质保期",
  "tender.max_duration": "最长交货期",
  "tender.consortium_allowed": "联合体",
  "tender.allowed_submit_methods": "递交方式",
  "tender.electronic_files": "电子标书要求",
};

export const ASSERTION_STATUS_LABELS: Record<string, string> = {
  PASS: "通过",
  FAIL: "失败",
  ERROR: "错误",
  SKIPPED: "已跳过",
};

export function sourcePathLabel(path: string): string {
  return SOURCE_PATH_LABELS[path] ?? path;
}

export function matrixStrategyLabel(value: string): string {
  return MATRIX_STRATEGY_LABELS[value] ?? value;
}

export function matrixStatusLabel(value: string): string {
  return MATRIX_STATUS_LABELS[value] ?? value;
}

export function matrixStatusTone(
  row: Pick<MatrixRowOut, "status">,
): "ok" | "warn" | "bad" | "gray" {
  if (row.status === "confirmed") return "ok";
  if (row.status === "blocked") return "bad";
  return "gray";
}

export function taskStatusView(task: WriteTaskOut): {
  label: string;
  tone: "ok" | "warn" | "bad" | "gray" | "info";
  pct: number;
  message: string;
} {
  const progress = task.progress ?? {};
  const pctRaw = progress.pct;
  const pct =
    typeof pctRaw === "number" && Number.isFinite(pctRaw)
      ? Math.max(0, Math.min(100, pctRaw))
      : 0;
  const msg = typeof progress.msg === "string" ? progress.msg : "";
  return {
    label: TASK_STATUS_LABELS[task.status] ?? task.status,
    tone: TASK_STATUS_TONES[task.status] ?? "gray",
    pct,
    message: msg,
  };
}

export interface MatrixSummary {
  total: number;
  star: number;
  blocked: number;
  confirmed: number;
  strategyPending: number;
  lowConfidence: number;
}

export function matrixSummary(rows: MatrixRowOut[]): MatrixSummary {
  return {
    total: rows.length,
    star: rows.filter((row) => row.star).length,
    blocked: rows.filter((row) => row.status === "blocked").length,
    confirmed: rows.filter((row) => row.status === "confirmed").length,
    strategyPending: rows.filter((row) => row.strategy === "pending").length,
    lowConfidence: rows.filter(
      (row) => typeof row.conf === "number" && row.conf < 0.6,
    ).length,
  };
}

export function canLeaveIntake(summary: MatrixSummary): boolean {
  return summary.total > 0 && summary.blocked === 0;
}

export function sectionNames(rows: MatrixRowOut[]): string[] {
  const names = new Set<string>();
  for (const row of rows) {
    const name = row.target_section.trim();
    if (name) names.add(name);
  }
  return [...names];
}

export function gapStatusTone(item: GapItem): "ok" | "warn" | "bad" | "gray" {
  if (item.status === "confirmed") return "ok";
  if (item.status === "blocked") return "bad";
  if (item.material_state === "无对应素材") return "bad";
  return "warn";
}

export function assertionWatermark(
  assertions: { blocked: boolean; pending: unknown[] } | null,
): "blocked" | "clean" | "unrun" {
  if (!assertions) return "unrun";
  if (assertions.blocked) return "blocked";
  return "clean";
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function projectTitle(task: WriteTaskOut): string {
  const name = task.project_name?.trim();
  if (name) return name;
  return "未命名写作项目";
}

export function projectSubtitle(task: WriteTaskOut): string {
  const parts = [task.lot_name?.trim(), task.tender_no?.trim()].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "商务部分写作";
}

type CsvValue = string | number | boolean | null | undefined;

function csvCell(value: CsvValue): string {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

export function downloadCsv(
  filename: string,
  headers: string[],
  rows: Array<Array<CsvValue>>,
): void {
  const content = [headers, ...rows]
    .map((row) => row.map(csvCell).join(","))
    .join("\r\n");
  const blob = new Blob(["\uFEFF", content], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

// \u2500\u2500 \u6279\u5EFF\u4E94 P1-\u03B4:\u751F\u6210\u65CB\u94AE\u88C5\u914D+\u7D20\u6750\u7C7B\u578B\u8BCD\u8868 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

export const MATERIAL_ENTITY_LABELS: Record<string, string> = {
  qualification: "\u8D44\u8D28",
  performance: "\u540C\u7C7B\u4E1A\u7EE9",
  personnel: "\u4EBA\u5458",
  capacity: "\u4EA7\u80FD",
  network: "\u7F51\u70B9",
  history_bid: "\u5386\u53F2\u6807\u4E66",
};

export function materialEntityLabel(entityType: string): string {
  return MATERIAL_ENTITY_LABELS[entityType] ?? entityType;
}

export interface GenerateKnobsDraft {
  warrantyMonths: string;
  spareYears: string;
  responseHours: string;
  penaltyCap: string;
  signDate: string;
  priceNote: string;
  unitPrices: Record<string, string>; // boq item id \u2192 \u5355\u4EF7(\u7A7A\u4E32=\u672A\u51FA\u4EF7\u5254\u9664)
}

/**
 * \u65CB\u94AE\u8349\u7A3F \u2192 POST /generate body(\u6279\u5EFF\u4E94 P1-\u03B4)\u3002\u7A7A\u503C\u952E\u6574\u4F53\u7F3A\u5E2D(None \u952E\u4E0D
 * \u8986\u76D6 meta.knobs \u5DF2\u5B58\u503C,\u540E\u7AEF\u5408\u5E76\u8BED\u4E49);\u8D28\u4FDD\u7EAF\u6570\u5B57\u8865\u300C\u4E2A\u6708\u300D\u5355\u4F4D;
 * \u5907\u4EF6/\u54CD\u5E94\u65F6\u9650/\u8FDD\u7EA6\u91D1\u58F0\u660E\u4E3A\u901A\u7528\u627F\u8BFA(\u8FDB BL \u627F\u8BFA\u6E05\u5355+L4-003 \u5BA1\u67E5\u9762)\u3002
 */
export function assembleGenerateKnobs(draft: GenerateKnobsDraft): GenerateKnobs {
  const knobs: GenerateKnobs = {};
  const warranty = draft.warrantyMonths.trim();
  if (warranty) {
    knobs.warranty_period = /^\d+$/.test(warranty)
      ? `${warranty}\u4E2A\u6708`
      : warranty;
  }
  const commitments = [
    draft.spareYears.trim() &&
      `\u5907\u4EF6\u4F9B\u5E94\u5E74\u9650:${draft.spareYears.trim()}\u5E74`,
    draft.responseHours.trim() &&
      `\u6545\u969C\u54CD\u5E94\u65F6\u9650:${draft.responseHours.trim()}\u5C0F\u65F6`,
    draft.penaltyCap.trim() && `\u8FDD\u7EA6\u91D1\u4E0A\u9650:${draft.penaltyCap.trim()}%`,
  ].filter(Boolean);
  if (commitments.length > 0) {
    knobs.general_commitments = commitments.map((text) => ({
      text,
      clause_id: "",
    }));
  }
  const prices = Object.fromEntries(
    Object.entries(draft.unitPrices).filter(
      ([, value]) => value.trim() !== "",
    ),
  );
  if (Object.keys(prices).length > 0) knobs.unit_prices = prices;
  const signDate = draft.signDate.trim();
  if (signDate) knobs.sign_date = signDate;
  const priceNote = draft.priceNote.trim();
  if (priceNote) knobs.price_note = priceNote;
  return knobs;
}
