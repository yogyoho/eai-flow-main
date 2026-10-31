/**
 * 基线字段/解析质量共享词汇(Plan6 自 BaselineView 上移;裁定交互仍留
 * BaselineView)。EAI-CUSTOM 2026-10-31。消费方:BaselineView(裁定卡+字段卡)
 * 与 ParsingView(/parsing 归拢专屏,只读展示)。
 */
import { type BidBaselineRow } from "@/extensions/bid-review/api";
import { type PillTone } from "@/extensions/contract-price/components/ui/bits";

export interface DocMeta {
  doc_id?: string;
  role?: string;
  kind?: string;
  pages?: number;
  chars?: number;
  assets?: number;
  status?: string;
  /** v1 旧任务(上传即解码纯文本直存)遗留字段,仅用于字符数回退估算。 */
  text?: string;
}

export const KIND_LABEL: Record<string, string> = {
  docx: "Word",
  pdf: "PDF",
  text: "文本",
};

export function roleLabel(role: string | undefined): string {
  if (role === "tender") return "招标";
  if (role === "bid") return "投标";
  return role ?? "未知";
}

/** role → 原型 pill 档(招标=主色/投标=橙警示/未知=灰)。 */
export function rolePillClass(role: string | undefined): string {
  if (role === "tender") return "pill-main";
  if (role === "bid") return "pill-orange";
  return "pill-gray";
}

/** taskStatusPill 的 PillTone → 原型 .pill-* 档(info 无专属档,归主色)。 */
export const STATUS_PILL_CLASS: Record<PillTone, string> = {
  primary: "pill-main",
  success: "pill-ok",
  warn: "pill-warn",
  error: "pill-err",
  gray: "pill-gray",
  info: "pill-main",
};

/** 字段族:路径首段(tender/bid);一期限引擎语义,主题级中文分组待标签映射。 */
export const FAMILIES: { key: string; label: string }[] = [
  { key: "tender", label: "招标基准" },
  { key: "bid", label: "投标响应" },
];

export function familyOf(path: string): string {
  return path.split(".", 1)[0] ?? path;
}

export function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString();
  if (typeof v === "boolean") return v ? "是" : "否";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

// 字段路径段 → 中文(2026-10-31 用户要求 /parsing 说明列;未收录段原样透传)。
// 覆盖字段字典常见段;新字段类型出现时随 labels 维护同款扩表。
const SEG_ZH: Record<string, string> = {
  tender: "招标",
  bid: "投标",
  project_identity: "项目主体",
  name: "名称",
  code: "编号",
  max_price: "最高限价",
  total_price: "总价",
  total_price_words: "总价大写",
  subtotal: "小计",
  detail_rows: "明细行数",
  boq_items: "工程量清单",
  price_includes_tax: "含税报价",
  duration: "工期",
  warranty_months: "质保期(月)",
};

/** 说明列:labels 中文名优先(服务端权威),无 label 走段翻译(如 bid.total_price→投标.总价)。 */
export function pathZh(path: string, label?: string): string {
  if (label && label !== path) return label;
  return path
    .split(".")
    .map((s) => SEG_ZH[s] ?? s)
    .join(".");
}

/** 置信 pill(二期 spec §二):quote 服务端核验为真信号——未核验=灰;
 * 核验且 conf<0.8=低置信 warn;核验且 conf≥0.8(或模型未自报)=高置信 ok。 */
export function confPill(
  c: { conf: number | null; verified: boolean } | null,
): {
  cls: string;
  text: string;
} {
  if (!c?.verified) return { cls: "pill-gray", text: "未核验" };
  if (c.conf != null && c.conf < 0.8)
    return { cls: "pill-warn", text: "低置信" };
  return { cls: "pill-ok", text: "高置信" };
}

/** 单行基线快照 → 字段卡列表数据(行间快照同源,取首行即可)。
 * 二期:effective_fields(裁定覆盖后值)+ labels 中文名 + fields_conf 置信。 */
export function fieldRows(
  row: BidBaselineRow | undefined,
  labels: Record<string, string>,
) {
  const fields = row?.effective_fields ?? row?.fields ?? {};
  const prov = row?.provenance ?? {};
  const conf = row?.fields_conf ?? {};
  const conflictSet = new Set(row?.conflicts ?? []);
  return Object.keys(fields)
    .sort()
    .map((p) => {
      const value = fields[p];
      const src = prov[p];
      return {
        path: p,
        label: labels[p] ?? p,
        value,
        missing: value === null || value === undefined,
        src,
        conf: conf[p] ?? null,
        conflicted: conflictSet.has(p),
      };
    });
}

// 稳定空对象:labels/adjudications 缺省时避免每渲染换引用破坏 useMemo 依赖
export const NO_LABELS: Record<string, string> = {};
