"use client";

import {
  BarChart3,
  Check,
  ChevronDown,
  FileText,
  FileUp,
  Heading1,
  Image as ImageIcon,
  ListOrdered,
  Loader2,
  type LucideIcon,
  PanelTop,
  Paperclip,
  Plus,
  Settings2,
  Table2,
  Trash2,
  Type,
} from "lucide-react";
import React, { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import {
  COVER_EMPTY_ELEMENTS,
  coverLogoPosition,
  coverSlotEffectiveKind,
  coverSlotSourceLabel,
  isCoverSlotResolvable,
  normalizeCoverElements,
  normalizeCoverTemplate,
  patchCoverState,
  resolveCoverFromImport,
  syncSlotTarget,
} from "@/extensions/output/cover-state";
import type {
  AppendixRules,
  BodyStyles,
  Cover,
  CoverMaster,
  CoverSlot,
  CoverTemplate,
  FigureStyles,
  HeaderFooter,
  HeadingStyle,
  LayoutTemplate,
  PageSettings,
  TableStyles,
  TocSettings,
} from "@/extensions/output/types";
import { cn } from "@/lib/utils";

import { CoverElementsEditor } from "./CoverElementsEditor";

// ─────────────────────────────────────────────────────────────────────────────
// Primitives
// ─────────────────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/50 hover:border-primary/40 focus:border-primary focus:ring-2 focus:ring-primary/20";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label className="text-muted-foreground text-[11px] font-medium">
          {label}
        </label>
        {hint && (
          <span className="text-muted-foreground/60 shrink-0 text-[10px] font-normal">
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

/** Color picker rendered as a swatch + monospace hex label (not a bare native box). */
function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label} hint={value.toUpperCase()}>
      <div className="border-input bg-background hover:border-primary/40 focus-within:border-primary focus-within:ring-primary/20 flex h-9 items-center gap-2 rounded-lg border pr-2.5 transition-all focus-within:ring-2">
        <div className="relative h-full w-10 shrink-0 overflow-hidden rounded-l-lg ring-1 ring-black/5 ring-inset">
          <input
            type="color"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          />
          <div className="h-full w-full" style={{ backgroundColor: value }} />
        </div>
        <span className="text-muted-foreground font-mono text-xs uppercase">
          {value}
        </span>
      </div>
    </Field>
  );
}

/** Card-style toggle replacing bare checkboxes — tints primary when active. */
function Toggle({
  checked,
  onChange,
  label,
  icon: Icon,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  icon?: LucideIcon;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-all",
        checked
          ? "border-primary/30 bg-primary/5 text-foreground"
          : "border-border bg-background text-muted-foreground hover:border-input hover:bg-muted/40",
      )}
    >
      <span
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border transition-all",
          checked
            ? "border-primary bg-primary text-primary-foreground"
            : "border-input bg-background",
        )}
      >
        {checked && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
      {Icon && (
        <Icon
          className={cn(
            "h-3.5 w-3.5",
            checked ? "text-primary" : "text-muted-foreground/70",
          )}
        />
      )}
      <span className="flex-1">{label}</span>
    </button>
  );
}

function Section({
  icon: Icon,
  title,
  defaultOpen = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      className={cn(
        "border-border bg-card overflow-hidden rounded-xl border transition-shadow",
        open && "shadow-sm",
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="hover:bg-muted/50 flex w-full items-center gap-3 px-4 py-3 text-left transition-colors"
      >
        <span className="bg-primary/10 text-primary ring-primary/15 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset">
          <Icon className="h-4 w-4" />
        </span>
        <span className="text-foreground flex-1 text-sm font-semibold">
          {title}
        </span>
        <ChevronDown
          className={cn(
            "text-muted-foreground h-4 w-4 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="animate-in fade-in-0 border-border bg-muted/40 border-t px-4 py-4 duration-200">
          {children}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Live previews (WYSIWYG) — the core upgrade
// ─────────────────────────────────────────────────────────────────────────────

function PagePreview({ settings }: { settings: PageSettings }) {
  const landscape = settings.orientation === "landscape";
  const W = 21;
  const H = 29.7;
  const dims = landscape ? { w: H, h: W } : { w: W, h: H };
  const top = (settings.marginTop / dims.h) * 100;
  const bottom = (settings.marginBottom / dims.h) * 100;
  const left = (settings.marginLeft / dims.w) * 100;
  const right = (settings.marginRight / dims.w) * 100;
  return (
    <div className="bg-muted/40 flex flex-col items-center justify-center gap-2 rounded-lg p-4">
      <div
        className="bg-background ring-border relative rounded-sm shadow-md ring-1"
        style={{
          width: landscape ? 116 : 86,
          aspectRatio: landscape ? "29.7 / 21" : "21 / 29.7",
        }}
      >
        {/* margin zone tint */}
        <div
          className="bg-primary/12 absolute rounded-[1px]"
          style={{
            top: `${top}%`,
            bottom: `${bottom}%`,
            left: `${left}%`,
            right: `${right}%`,
          }}
        >
          <div className="flex h-full flex-col justify-center gap-[3px] px-1.5">
            <div className="bg-muted-foreground/30 h-[2px] w-3/4 rounded-full" />
            <div className="bg-muted-foreground/20 h-[2px] w-full rounded-full" />
            <div className="bg-muted-foreground/20 h-[2px] w-5/6 rounded-full" />
            <div className="bg-muted-foreground/20 h-[2px] w-full rounded-full" />
            <div className="bg-muted-foreground/20 h-[2px] w-2/3 rounded-full" />
          </div>
        </div>
      </div>
      <span className="text-muted-foreground text-[10px] font-medium">
        {settings.paperSize} · {landscape ? "横向" : "纵向"}
      </span>
    </div>
  );
}

function BodyPreview({ styles }: { styles: BodyStyles }) {
  const pStyle: React.CSSProperties = {
    fontFamily: styles.fontFamily,
    fontSize: `${styles.fontSize}pt`,
    lineHeight: styles.lineHeight,
    marginBottom: `${styles.paragraphSpacing}pt`,
    textIndent: `${styles.firstLineIndent}em`,
    color: "var(--foreground)",
  };
  return (
    <div className="bg-muted/30 rounded-lg p-4">
      <p style={pStyle}>
        本项目位于某工业园区，厂区总平面布置符合防火间距要求。
      </p>
      <p style={pStyle}>
        设计依据国家现行消防技术标准，总建筑面积及防火分区均满足规范。
      </p>
    </div>
  );
}

function HeadingPreview({ h }: { h: HeadingStyle }) {
  return (
    <div
      className="flex-1 truncate"
      style={{
        fontFamily: h.fontFamily,
        fontSize: `${h.fontSize}pt`,
        fontWeight: h.fontWeight,
        color: h.color,
        lineHeight: 1.3,
      }}
    >
      {h.level === 1 ? "第一章" : h.level === 2 ? "1.1" : `${h.level}.1`} 概述
    </div>
  );
}

function TablePreview({ styles }: { styles: TableStyles }) {
  const rows = [0, 1, 2];
  return (
    <div
      className="overflow-hidden rounded-lg ring-1"
      style={{ "--tw-ring-color": styles.borderColor } as React.CSSProperties}
    >
      <table className="w-full text-xs">
        <thead>
          <tr
            style={{
              backgroundColor: styles.headerBg,
              color: styles.headerColor,
            }}
          >
            <th className="px-3 py-1.5 text-left font-medium">项目</th>
            <th className="px-3 py-1.5 text-right font-medium">数值</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((i) => (
            <tr
              key={i}
              style={
                styles.stripeRows && i % 2 === 1
                  ? {
                      backgroundColor:
                        "color-mix(in oklch, var(--foreground) 4%, transparent)",
                    }
                  : undefined
              }
            >
              <td
                className="text-muted-foreground border-t px-3 py-1.5"
                style={{ borderColor: styles.borderColor }}
              >
                数据行 {i + 1}
              </td>
              <td
                className="text-muted-foreground border-t px-3 py-1.5 text-right"
                style={{ borderColor: styles.borderColor }}
              >
                100
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HeaderFooterPreview({ hf }: { hf: HeaderFooter }) {
  return (
    <div className="bg-muted/40 rounded-lg p-3">
      <div
        className="bg-background ring-border space-y-2 rounded p-2.5 shadow-sm ring-1"
        style={{ minHeight: 92 }}
      >
        <div className="border-border flex items-center justify-between gap-2 border-b border-dashed pb-1.5">
          {hf.showLogo ? (
            <span className="text-muted-foreground flex items-center gap-1 text-[9px] font-medium">
              <ImageIcon className="h-3 w-3" /> LOGO
            </span>
          ) : (
            <span />
          )}
          <span className="text-muted-foreground max-w-[70%] truncate text-[9px]">
            {hf.headerText || "页眉文本"}
          </span>
        </div>
        <div className="space-y-1 py-0.5">
          <div className="bg-muted-foreground/20 h-1 w-full rounded-full" />
          <div className="bg-muted-foreground/20 h-1 w-5/6 rounded-full" />
          <div className="bg-muted-foreground/20 h-1 w-3/4 rounded-full" />
        </div>
        <div className="border-border flex items-center justify-between gap-2 border-t border-dashed pt-1.5">
          <span className="text-muted-foreground max-w-[60%] truncate text-[9px]">
            {hf.footerText || "页脚文本"}
          </span>
          {hf.showPageNumber && (
            <span className="text-muted-foreground text-[9px]">第 1 页</span>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Options
// ─────────────────────────────────────────────────────────────────────────────

const PAPER_OPTIONS = [
  { value: "A4", label: "A4" },
  { value: "A3", label: "A3" },
  { value: "B5", label: "B5" },
  { value: "letter", label: "Letter" },
];
const ORIENTATION_OPTIONS = [
  { value: "portrait", label: "纵向" },
  { value: "landscape", label: "横向" },
];
const REFERENCE_OPTIONS = [
  { value: "gb7714", label: "GB/T 7714" },
  { value: "apa", label: "APA" },
  { value: "mla", label: "MLA" },
  { value: "chicago", label: "Chicago" },
];
const APPENDIX_NUMBERING_OPTIONS = [
  { value: "A-B-C", label: "A-B-C" },
  { value: "I-II-III", label: "I-II-III" },
  { value: "1-2-3", label: "1-2-3" },
];
const HEADING_NUMBERING_OPTIONS = [
  { value: "decimal", label: "1, 2, 3" },
  { value: "chinese", label: "一, 二, 三" },
  { value: "none", label: "无编号" },
];
const CAPTION_POSITION_OPTIONS = [
  { value: "above", label: "图上方" },
  { value: "below", label: "图下方" },
];
const FIGURE_NUMBERING_OPTIONS = [
  { value: "chapter", label: "按章节" },
  { value: "continuous", label: "连续编号" },
];
const REPORT_TYPE_OPTIONS = [
  { value: "environmental_assessment", label: "环评报告" },
  { value: "feasibility_study", label: "可行性研究报告" },
  { value: "technical_consulting", label: "技术咨询报告" },
  { value: "general", label: "通用报告" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Defaults & helpers
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULT_PAGE_SETTINGS: PageSettings = {
  paperSize: "A4",
  orientation: "portrait",
  marginTop: 2.54,
  marginBottom: 2.54,
  marginLeft: 3.17,
  marginRight: 3.17,
};
const DEFAULT_BODY_STYLES: BodyStyles = {
  fontFamily: "宋体",
  fontSize: 12,
  lineHeight: 1.5,
  paragraphSpacing: 0,
  firstLineIndent: 2,
};
const DEFAULT_HEADING_STYLES: HeadingStyle[] = [
  {
    level: 1,
    fontFamily: "黑体",
    fontSize: 16,
    fontWeight: 700,
    color: "#000000",
    numbering: "decimal",
  },
  {
    level: 2,
    fontFamily: "黑体",
    fontSize: 14,
    fontWeight: 700,
    color: "#000000",
    numbering: "decimal",
  },
];

const TABLE_DEFAULT: TableStyles = {
  headerBg: "#2B579A",
  headerColor: "#FFFFFF",
  borderColor: "#CCCCCC",
  stripeRows: true,
};
const FIGURE_DEFAULT: FigureStyles = {
  captionPosition: "below",
  numbering: "chapter",
  showSource: true,
};
const HF_DEFAULT: HeaderFooter = {
  headerText: "",
  footerText: "",
  showPageNumber: true,
  showLogo: false,
};
const APPENDIX_DEFAULT: AppendixRules = {
  numbering: "A-B-C",
  separateToc: false,
};
const TOC_DEFAULT: TocSettings = {
  maxDepth: 3,
  showPageNumbers: true,
  leaderDots: true,
};

const headingInputCls =
  "w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs text-foreground outline-none transition-all hover:border-primary/40 focus:border-primary focus:ring-2 focus:ring-primary/20";

// ─────────────────────────────────────────────────────────────────────────────
// Editor
// ─────────────────────────────────────────────────────────────────────────────

interface LayoutTemplateEditorProps {
  template: LayoutTemplate | null;
  onSave: (
    data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">,
  ) => Promise<void>;
  onCancel: () => void;
}

export function LayoutTemplateEditor({
  template,
  onSave,
  onCancel,
}: LayoutTemplateEditorProps) {
  const isEdit = template !== null;

  const [name, setName] = useState(template?.name ?? "");
  const [reportType, setReportType] = useState(
    template?.reportType ?? "general",
  );
  const [pageSettings, setPageSettings] = useState<PageSettings>(
    template?.pageSettings ?? DEFAULT_PAGE_SETTINGS,
  );
  const [coverTemplate, setCoverTemplate] = useState<CoverTemplate | null>(
    template?.coverTemplate ?? null,
  );
  const [coverMaster, setCoverMaster] = useState<CoverMaster | null>(
    template?.coverMaster ?? null,
  );
  const [coverElements, setCoverElements] = useState<Cover | null>(
    template?.coverElements ?? null,
  );
  const [tocSettings, setTocSettings] = useState<TocSettings | null>(
    template?.tocSettings ?? null,
  );
  const [bodyStyles, setBodyStyles] = useState<BodyStyles>(
    template?.bodyStyles ?? DEFAULT_BODY_STYLES,
  );
  const [headingStyles, setHeadingStyles] = useState<HeadingStyle[]>(
    template?.headingStyles ?? DEFAULT_HEADING_STYLES,
  );
  const [tableStyles, setTableStyles] = useState<TableStyles | null>(
    template?.tableStyles ?? null,
  );
  const [figureStyles, setFigureStyles] = useState<FigureStyles | null>(
    template?.figureStyles ?? null,
  );
  const [headerFooter, setHeaderFooter] = useState<HeaderFooter | null>(
    template?.headerFooter ?? null,
  );
  const [referenceStyle, setReferenceStyle] = useState(
    template?.referenceStyle ?? "gb7714",
  );
  const [appendixRules, setAppendixRules] = useState<AppendixRules | null>(
    template?.appendixRules ?? null,
  );

  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Which import did the last button-click ask for? The three buttons share one
  // hidden input + one onChange; the scope set before click routes to the right
  // applier (full layout vs cover-only).
  const pendingScopeRef = useRef<"full" | "cover">("full");

  // patch helpers — collapse the repeated `{ ...(x ?? DEFAULT), patch }` boilerplate
  const patchCover = useCallback(
    (p: Partial<CoverTemplate>) =>
      setCoverTemplate((c) => patchCoverState(c, p)),
    [],
  );
  const patchSlot = useCallback(
    (index: number, p: Partial<CoverSlot>) =>
      setCoverMaster((m) =>
        m
          ? {
              ...m,
              slots: m.slots.map((s, i) => (i === index ? { ...s, ...p } : s)),
            }
          : m,
      ),
    [],
  );
  const patchTable = useCallback(
    (p: Partial<TableStyles>) =>
      setTableStyles((t) => ({ ...(t ?? TABLE_DEFAULT), ...p })),
    [],
  );
  const patchFigure = useCallback(
    (p: Partial<FigureStyles>) =>
      setFigureStyles((f) => ({ ...(f ?? FIGURE_DEFAULT), ...p })),
    [],
  );
  const patchHF = useCallback(
    (p: Partial<HeaderFooter>) =>
      setHeaderFooter((h) => ({ ...(h ?? HF_DEFAULT), ...p })),
    [],
  );
  const patchAppendix = useCallback(
    (p: Partial<AppendixRules>) =>
      setAppendixRules((a) => ({ ...(a ?? APPENDIX_DEFAULT), ...p })),
    [],
  );
  const patchToc = useCallback(
    (p: Partial<TocSettings>) =>
      setTocSettings((t) => ({ ...(t ?? TOC_DEFAULT), ...p })),
    [],
  );

  const handleSave = useCallback(async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      // 全 false 的 coverTemplate 视为无封面，保存为 null（否则会触发空白封面页）
      const normalizedCoverTemplate = normalizeCoverTemplate(coverTemplate);
      await onSave({
        name: name.trim(),
        reportType,
        pageSettings,
        coverTemplate: normalizedCoverTemplate,
        coverMaster,
        // 全空封面（只有空行/空文本）归一化为 null，避免持久化触发空白封面页
        coverElements: normalizeCoverElements(coverElements),
        tocSettings,
        bodyStyles,
        headingStyles,
        tableStyles,
        figureStyles,
        headerFooter,
        referenceStyle,
        appendixRules,
      });
    } finally {
      setSaving(false);
    }
  }, [
    name,
    reportType,
    pageSettings,
    coverTemplate,
    coverMaster,
    coverElements,
    tocSettings,
    bodyStyles,
    headingStyles,
    tableStyles,
    figureStyles,
    headerFooter,
    referenceStyle,
    appendixRules,
    onSave,
  ]);

  // 共享封面复位语义（H2 stale 防护）：元素/母版存在则采纳；不存在则总把旧的清掉。
  // cover_elements 是新一代结构化封面（优先于 cover_master 的旧数据兜底）。
  const applyCoverImport = useCallback((data: Record<string, unknown>) => {
    const { coverMaster, coverTemplate } = resolveCoverFromImport(data);
    const ce = data.cover_elements as Cover | null | undefined;
    setCoverElements(ce?.mode === "elements" ? ce : null);
    setCoverMaster(coverMaster);
    if (coverTemplate !== undefined) setCoverTemplate(coverTemplate);
  }, []);

  // 全量导入：逐 section 覆盖；封面走共享复位（从基本信息区导入也防 stale master）
  const applyImportedLayout = useCallback(
    (data: Record<string, unknown>) => {
      const ps = data.page_settings as PageSettings | undefined;
      if (ps) setPageSettings(ps);
      const bs = data.body_styles as BodyStyles | undefined;
      if (bs) setBodyStyles(bs);
      const hs = data.heading_styles as HeadingStyle[] | undefined;
      if (hs?.length) setHeadingStyles(hs.map((h) => ({ ...h })));
      const ts = data.table_styles as TableStyles | null | undefined;
      if (ts) setTableStyles(ts);
      const ff = data.figure_styles as FigureStyles | null | undefined;
      if (ff) setFigureStyles(ff);
      const hf = data.header_footer as HeaderFooter | null | undefined;
      if (hf) setHeaderFooter(hf);
      // 封面（含 cover_elements stale 防护）统一走 applyCoverImport，单点负责
      applyCoverImport(data);
    },
    [applyCoverImport],
  );

  const handleImportedFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      // 选文件时刻即定格 scope（不得在 await 之后再读，避免任何潜在误路由）；
      // 立刻复位 ref，取消文件对话框（提前 return）也不会留下 stale scope。
      const scope = pendingScopeRef.current;
      pendingScopeRef.current = "full";
      setImporting(true);
      try {
        const { outputApi } = await import("@/extensions/output/api");
        const data = await outputApi.importLayout(file);
        if (scope === "cover") {
          // H1：封面专用导入只动封面 state，其它 section 不受影响
          applyCoverImport(data);
          toast.success("已从样例导入封面");
        } else {
          applyImportedLayout(data);
          toast.success("已从样例文档提取排版");
        }
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "无法从该文件提取排版信息",
        );
      } finally {
        setImporting(false);
        pendingScopeRef.current = "full";
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [applyCoverImport, applyImportedLayout],
  );

  const updateHeading = (
    index: number,
    field: keyof HeadingStyle,
    value: string | number,
  ) =>
    setHeadingStyles((prev) =>
      prev.map((h, i) => (i === index ? { ...h, [field]: value } : h)),
    );
  const addHeadingLevel = () => {
    const lastLevel = headingStyles[headingStyles.length - 1]?.level ?? 0;
    setHeadingStyles((prev) => [
      ...prev,
      {
        level: lastLevel + 1,
        fontFamily: "黑体",
        fontSize: 12,
        fontWeight: 700,
        color: "#000000",
        numbering: "decimal",
      },
    ]);
  };
  const removeHeadingLevel = (index: number) =>
    setHeadingStyles((prev) => prev.filter((_, i) => i !== index));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="bg-background ring-border flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl shadow-2xl ring-1">
        {/* Header */}
        <div className="border-border from-muted/40 to-background flex shrink-0 items-center justify-between border-b bg-gradient-to-b px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="bg-primary/10 text-primary ring-primary/15 flex h-9 w-9 items-center justify-center rounded-xl ring-1 ring-inset">
              <FileText className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-foreground text-base font-semibold">
                {isEdit ? "编辑排版模板" : "新建排版模板"}
              </h2>
              <p className="text-muted-foreground text-xs">
                配置报告导出的页面、字体与版式参数
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="text-muted-foreground hover:bg-muted hover:text-foreground flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
          {/* 基本信息 */}
          <Section icon={Settings2} title="基本信息" defaultOpen>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label="模板名称">
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="例如：环评报告（国标）"
                    className={inputCls}
                  />
                </Field>
                <Field label="报告类型">
                  <AdminSelect
                    value={reportType}
                    onChange={setReportType}
                    options={REPORT_TYPE_OPTIONS}
                    className="w-full"
                  />
                </Field>
              </div>
              <div className="border-primary/30 bg-primary/5 flex flex-wrap items-center gap-3 rounded-lg border border-dashed p-3">
                <button
                  type="button"
                  onClick={() => {
                    pendingScopeRef.current = "full";
                    fileInputRef.current?.click();
                  }}
                  disabled={importing}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium shadow-sm transition-all disabled:opacity-50"
                >
                  {importing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <FileUp className="h-4 w-4" />
                  )}
                  {importing ? "提取中..." : "从样例导入排版"}
                </button>
                <span className="text-muted-foreground text-xs">
                  上传 .docx 样例，自动识别并填充以下各项参数
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx"
                  onChange={handleImportedFile}
                  className="hidden"
                />
              </div>
            </div>
          </Section>

          {/* 页面设置 */}
          <Section icon={FileText} title="页面设置" defaultOpen>
            <div className="grid grid-cols-[1fr_auto] gap-5">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="纸张尺寸">
                    <AdminSelect
                      value={pageSettings.paperSize}
                      onChange={(v) =>
                        setPageSettings({
                          ...pageSettings,
                          paperSize: v as PageSettings["paperSize"],
                        })
                      }
                      options={PAPER_OPTIONS}
                      className="w-full"
                    />
                  </Field>
                  <Field label="方向">
                    <AdminSelect
                      value={pageSettings.orientation}
                      onChange={(v) =>
                        setPageSettings({
                          ...pageSettings,
                          orientation: v as PageSettings["orientation"],
                        })
                      }
                      options={ORIENTATION_OPTIONS}
                      className="w-full"
                    />
                  </Field>
                </div>
                <Field label="页边距" hint="cm">
                  <div className="grid grid-cols-4 gap-2">
                    {(
                      [
                        ["上", "marginTop", pageSettings.marginTop],
                        ["下", "marginBottom", pageSettings.marginBottom],
                        ["左", "marginLeft", pageSettings.marginLeft],
                        ["右", "marginRight", pageSettings.marginRight],
                      ] as const
                    ).map(([lbl, key, val]) => (
                      <div key={key} className="space-y-1 text-center">
                        <span className="text-muted-foreground text-[10px]">
                          {lbl}
                        </span>
                        <input
                          type="number"
                          step="0.01"
                          value={val}
                          onChange={(e) =>
                            setPageSettings({
                              ...pageSettings,
                              [key]: parseFloat(e.target.value) || 0,
                            })
                          }
                          className={cn(inputCls, "px-1 text-center")}
                        />
                      </div>
                    ))}
                  </div>
                </Field>
              </div>
              <PagePreview settings={pageSettings} />
            </div>
          </Section>

          {/* 正文样式 */}
          <Section icon={Type} title="正文样式" defaultOpen>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                <Field label="字体">
                  <input
                    type="text"
                    value={bodyStyles.fontFamily}
                    onChange={(e) =>
                      setBodyStyles({
                        ...bodyStyles,
                        fontFamily: e.target.value,
                      })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="字号" hint="pt">
                  <input
                    type="number"
                    value={bodyStyles.fontSize}
                    onChange={(e) =>
                      setBodyStyles({
                        ...bodyStyles,
                        fontSize: parseInt(e.target.value) || 12,
                      })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="行高" hint="倍">
                  <input
                    type="number"
                    step="0.1"
                    value={bodyStyles.lineHeight}
                    onChange={(e) =>
                      setBodyStyles({
                        ...bodyStyles,
                        lineHeight: parseFloat(e.target.value) || 1.5,
                      })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="段后距" hint="pt">
                  <input
                    type="number"
                    value={bodyStyles.paragraphSpacing}
                    onChange={(e) =>
                      setBodyStyles({
                        ...bodyStyles,
                        paragraphSpacing: parseInt(e.target.value) || 0,
                      })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="首行缩进" hint="字符">
                  <input
                    type="number"
                    value={bodyStyles.firstLineIndent}
                    onChange={(e) =>
                      setBodyStyles({
                        ...bodyStyles,
                        firstLineIndent: parseInt(e.target.value) || 0,
                      })
                    }
                    className={inputCls}
                  />
                </Field>
              </div>
              <BodyPreview styles={bodyStyles} />
            </div>
          </Section>

          {/* 标题样式 */}
          <Section icon={Heading1} title="标题样式">
            <div className="space-y-2.5">
              {headingStyles.map((h, i) => (
                <div
                  key={i}
                  className="border-border bg-muted/20 rounded-lg border p-3"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="bg-primary/10 text-primary flex h-6 items-center rounded-md px-2 text-[11px] font-semibold">
                      H{h.level}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeHeadingLevel(i)}
                      className="text-muted-foreground hover:text-destructive flex items-center gap-1 text-[11px] transition-colors"
                    >
                      <Trash2 className="h-3 w-3" /> 删除
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                    <input
                      type="text"
                      value={h.fontFamily}
                      onChange={(e) =>
                        updateHeading(i, "fontFamily", e.target.value)
                      }
                      placeholder="字体"
                      className={headingInputCls}
                    />
                    <input
                      type="number"
                      value={h.fontSize}
                      onChange={(e) =>
                        updateHeading(
                          i,
                          "fontSize",
                          parseInt(e.target.value) || 12,
                        )
                      }
                      placeholder="字号"
                      className={headingInputCls}
                    />
                    <input
                      type="number"
                      value={h.fontWeight}
                      onChange={(e) =>
                        updateHeading(
                          i,
                          "fontWeight",
                          parseInt(e.target.value) || 400,
                        )
                      }
                      placeholder="粗细"
                      className={headingInputCls}
                    />
                    <div className="border-input bg-background flex h-[34px] items-center gap-2 rounded-md border px-2">
                      <input
                        type="color"
                        value={h.color}
                        onChange={(e) =>
                          updateHeading(i, "color", e.target.value)
                        }
                        className="h-5 w-5 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
                      />
                      <span className="text-muted-foreground font-mono text-[10px] uppercase">
                        {h.color}
                      </span>
                    </div>
                    <AdminSelect
                      value={h.numbering}
                      onChange={(v) => updateHeading(i, "numbering", v)}
                      options={HEADING_NUMBERING_OPTIONS}
                      className="w-full"
                    />
                  </div>
                  <div className="bg-background ring-border mt-2.5 rounded-md px-3 py-2 ring-1">
                    <HeadingPreview h={h} />
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={addHeadingLevel}
                className="border-border text-muted-foreground hover:border-primary/40 hover:text-primary flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed py-2 text-sm transition-colors"
              >
                <Plus className="h-4 w-4" /> 添加标题级别
              </button>
            </div>
          </Section>

          {/* 表格样式 */}
          <Section icon={Table2} title="表格样式">
            <div className="grid grid-cols-[1fr_auto] gap-5">
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <ColorField
                    label="表头背景"
                    value={tableStyles?.headerBg ?? TABLE_DEFAULT.headerBg}
                    onChange={(v) => patchTable({ headerBg: v })}
                  />
                  <ColorField
                    label="表头字色"
                    value={
                      tableStyles?.headerColor ?? TABLE_DEFAULT.headerColor
                    }
                    onChange={(v) => patchTable({ headerColor: v })}
                  />
                  <ColorField
                    label="边框色"
                    value={
                      tableStyles?.borderColor ?? TABLE_DEFAULT.borderColor
                    }
                    onChange={(v) => patchTable({ borderColor: v })}
                  />
                </div>
                <Toggle
                  checked={tableStyles?.stripeRows ?? TABLE_DEFAULT.stripeRows}
                  onChange={(v) => patchTable({ stripeRows: v })}
                  label="斑马纹（隔行底纹）"
                  icon={Table2}
                />
              </div>
              <TablePreview styles={tableStyles ?? TABLE_DEFAULT} />
            </div>
          </Section>

          {/* 图表样式 */}
          <Section icon={BarChart3} title="图表样式">
            <div className="grid grid-cols-2 gap-3">
              <Field label="标题位置">
                <AdminSelect
                  value={
                    figureStyles?.captionPosition ??
                    FIGURE_DEFAULT.captionPosition
                  }
                  onChange={(v) =>
                    patchFigure({ captionPosition: v as "above" | "below" })
                  }
                  options={CAPTION_POSITION_OPTIONS}
                  className="w-full"
                />
              </Field>
              <Field label="编号方式">
                <AdminSelect
                  value={figureStyles?.numbering ?? FIGURE_DEFAULT.numbering}
                  onChange={(v) =>
                    patchFigure({ numbering: v as "chapter" | "continuous" })
                  }
                  options={FIGURE_NUMBERING_OPTIONS}
                  className="w-full"
                />
              </Field>
            </div>
            <div className="mt-3">
              <Toggle
                checked={figureStyles?.showSource ?? FIGURE_DEFAULT.showSource}
                onChange={(v) => patchFigure({ showSource: v })}
                label="显示数据来源"
                icon={BarChart3}
              />
            </div>
          </Section>

          {/* 页眉页脚 */}
          <Section icon={PanelTop} title="页眉页脚">
            <div className="grid grid-cols-[1fr_auto] gap-5">
              <div className="space-y-3">
                <Field label="页眉文本">
                  <input
                    type="text"
                    value={headerFooter?.headerText ?? ""}
                    onChange={(e) => patchHF({ headerText: e.target.value })}
                    placeholder="如：项目消防设计专篇"
                    className={inputCls}
                  />
                </Field>
                <Field label="页脚文本">
                  <input
                    type="text"
                    value={headerFooter?.footerText ?? ""}
                    onChange={(e) => patchHF({ footerText: e.target.value })}
                    placeholder="如：设计院名称"
                    className={inputCls}
                  />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Toggle
                    checked={
                      headerFooter?.showPageNumber ?? HF_DEFAULT.showPageNumber
                    }
                    onChange={(v) => patchHF({ showPageNumber: v })}
                    label="显示页码"
                  />
                  <Toggle
                    checked={headerFooter?.showLogo ?? HF_DEFAULT.showLogo}
                    onChange={(v) => patchHF({ showLogo: v })}
                    label="显示 Logo"
                  />
                </div>
              </div>
              <HeaderFooterPreview hf={headerFooter ?? HF_DEFAULT} />
            </div>
          </Section>

          {/* 封面配置 */}
          <Section icon={ImageIcon} title="封面配置">
            {coverElements ? (
              <div className="space-y-3">
                <div className="bg-muted/40 flex items-center gap-2 rounded-lg px-3 py-2 text-xs">
                  <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                  <span className="text-muted-foreground truncate">
                    来自样例：{coverElements.sourceFile ?? "（未命名）"}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setCoverElements(null);
                      setCoverMaster(null);
                      setCoverTemplate(null);
                    }}
                    className="border-border text-destructive hover:bg-destructive/10 ml-auto shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium"
                  >
                    移除封面
                  </button>
                </div>
                <CoverElementsEditor
                  cover={coverElements}
                  onChange={setCoverElements}
                />
              </div>
            ) : coverMaster ? (
              <div className="space-y-3">
                <div className="bg-muted/40 flex items-center gap-2 rounded-lg px-3 py-2 text-xs">
                  <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                  <span className="text-muted-foreground truncate">
                    来自样例：
                    <span className="text-foreground font-medium">
                      {coverMaster.sourceFile || "（未命名）"}
                    </span>
                  </span>
                  <span className="bg-primary/10 text-primary ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium">
                    {coverMaster.boundary === "before_toc"
                      ? "目录前"
                      : "首标题前"}
                  </span>
                </div>
                <div className="space-y-1.5">
                  <p className="text-muted-foreground text-[11px] font-medium">{`槽位（生成时替换"变量"，保留"字面"）`}</p>
                  <p className="text-muted-foreground/70 text-[10px]">
                    原文靶文本：生成时按此文本（带标签字段按「标签+原文」整体）定位并替换；须与封面原文匹配才生效。
                  </p>
                  {coverMaster.slots.map((slot, i) => {
                    const resolvable = isCoverSlotResolvable(slot.id);
                    const kind = coverSlotEffectiveKind(slot);
                    return (
                      <div
                        key={slot.id}
                        className="border-border flex items-center gap-2 rounded-lg border px-2 py-1.5"
                      >
                        <span className="text-muted-foreground flex w-32 shrink-0 flex-col">
                          <span className="text-[11px] font-medium">
                            {slot.label}
                          </span>
                          <span
                            className="text-muted-foreground/60 truncate text-[9px]"
                            title={coverSlotSourceLabel(
                              slot.id,
                              slot.defaultFrom,
                            )}
                          >
                            {coverSlotSourceLabel(slot.id, slot.defaultFrom)}
                          </span>
                        </span>
                        {kind === "literal" ? (
                          <span className="border-border text-muted-foreground bg-background flex h-7 flex-1 items-center rounded-md border px-2 text-xs">
                            {slot.sampleValue}
                          </span>
                        ) : (
                          <input
                            className="border-border bg-background h-7 flex-1 rounded-md border px-2 text-xs"
                            value={slot.sampleValue}
                            onChange={(e) =>
                              patchSlot(i, {
                                sampleValue: e.target.value,
                                target: syncSlotTarget(slot, e.target.value),
                              })
                            }
                            placeholder="原文靶文本"
                            title="原文靶文本——生成时按此文本定位并替换；带标签字段以「标签+原文」定位，须与封面原文匹配才生效"
                          />
                        )}
                        <button
                          type="button"
                          disabled={!resolvable}
                          onClick={() =>
                            patchSlot(i, {
                              kind:
                                slot.kind === "variable"
                                  ? "literal"
                                  : "variable",
                            })
                          }
                          className={`ring-border shrink-0 rounded-md px-2 py-1 text-[10px] font-medium ring-1 transition-colors ring-inset ${kind === "variable" ? "text-primary" : "text-muted-foreground"} ${resolvable ? "hover:bg-muted" : "cursor-not-allowed opacity-50"}`}
                          title={
                            resolvable
                              ? kind === "variable"
                                ? "点击切为字面（原样保留不替换）"
                                : "点击切为变量（生成时替换）"
                              : "该槽位生成时无取值来源，仅保留原文"
                          }
                        >
                          {kind === "variable" ? "变量" : "字面"}
                        </button>
                      </div>
                    );
                  })}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      pendingScopeRef.current = "cover";
                      fileInputRef.current?.click();
                    }}
                    disabled={importing}
                    className="border-border text-muted-foreground hover:bg-muted flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50"
                  >
                    <FileUp className="h-3.5 w-3.5" />
                    {importing ? "提取中…" : "重新从样例导入封面"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setCoverMaster(null)}
                    className="border-border text-destructive hover:bg-destructive/10 flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> 移除母版
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <Toggle
                    checked={coverTemplate?.showLogo ?? false}
                    onChange={(v) => patchCover({ showLogo: v })}
                    label="显示 Logo"
                    icon={ImageIcon}
                  />
                  <Toggle
                    checked={coverTemplate?.showTitle ?? false}
                    onChange={(v) => patchCover({ showTitle: v })}
                    label="显示标题"
                    icon={Type}
                  />
                  <Toggle
                    checked={coverTemplate?.showClient ?? false}
                    onChange={(v) => patchCover({ showClient: v })}
                    label="显示建设单位"
                  />
                  <Toggle
                    checked={coverTemplate?.showDate ?? false}
                    onChange={(v) => patchCover({ showDate: v })}
                    label="显示日期"
                  />
                  <Toggle
                    checked={coverTemplate?.showProjectNumber ?? false}
                    onChange={(v) => patchCover({ showProjectNumber: v })}
                    label="显示项目编号"
                  />
                </div>
                {coverTemplate?.showLogo && (
                  <Field label="Logo 位置">
                    <AdminSelect
                      value={coverLogoPosition(coverTemplate)}
                      onChange={(v) =>
                        patchCover({
                          logoPosition: v as CoverTemplate["logoPosition"],
                        })
                      }
                      options={[
                        { value: "left", label: "左" },
                        { value: "center", label: "中" },
                        { value: "right", label: "右" },
                      ]}
                      className="w-full"
                    />
                  </Field>
                )}
                {((coverTemplate?.showLogo ?? false) ||
                  (coverTemplate?.showTitle ?? false) ||
                  (coverTemplate?.showClient ?? false) ||
                  (coverTemplate?.showDate ?? false) ||
                  (coverTemplate?.showProjectNumber ?? false)) && (
                  <div className="bg-muted/30 rounded-lg p-5">
                    <p className="text-muted-foreground mb-3 text-[10px] font-semibold tracking-wide uppercase">
                      预览
                    </p>
                    <div className="mx-auto max-w-[240px] space-y-2.5 text-center">
                      {coverTemplate?.showLogo && (
                        <div
                          className={cn(
                            "flex w-full",
                            coverTemplate.logoPosition === "left"
                              ? "justify-start"
                              : coverTemplate.logoPosition === "right"
                                ? "justify-end"
                                : "justify-center",
                          )}
                        >
                          <div className="bg-primary/10 text-primary ring-primary/15 flex h-12 w-20 items-center justify-center rounded-md text-[10px] font-medium ring-1 ring-inset">
                            LOGO
                          </div>
                        </div>
                      )}
                      {coverTemplate?.showTitle && (
                        <div className="text-foreground text-lg font-bold">
                          报告标题
                        </div>
                      )}
                      <div className="text-muted-foreground space-y-1.5 pt-1 text-xs">
                        {coverTemplate?.showClient && <div>建设单位：XXXX</div>}
                        {coverTemplate?.showDate && <div>日期：2026-08</div>}
                        {coverTemplate?.showProjectNumber && (
                          <div>项目编号：XXXX</div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setCoverElements(COVER_EMPTY_ELEMENTS)}
                    className="border-border text-muted-foreground hover:bg-muted flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-medium transition-colors"
                  >
                    <Type className="h-3.5 w-3.5" />
                    用元素编辑器
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      pendingScopeRef.current = "cover";
                      fileInputRef.current?.click();
                    }}
                    disabled={importing}
                    className="border-border text-primary hover:bg-primary/5 flex flex-1 items-center justify-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50"
                  >
                    <FileUp className="h-3.5 w-3.5" />
                    {importing ? "提取中…" : "从样例 .docx 导入真实封面"}
                  </button>
                  {coverTemplate && (
                    <button
                      type="button"
                      onClick={() => {
                        setCoverMaster(null);
                        setCoverTemplate(null);
                      }}
                      className="border-border text-destructive hover:bg-destructive/10 flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
                    >
                      <Trash2 className="h-3.5 w-3.5" /> 移除封面
                    </button>
                  )}
                </div>
              </div>
            )}
          </Section>

          {/* 目录设置 */}
          <Section icon={ListOrdered} title="目录设置">
            <div className="space-y-3">
              <Toggle
                checked={tocSettings !== null}
                onChange={(v) => setTocSettings(v ? TOC_DEFAULT : null)}
                label="包含目录"
                icon={ListOrdered}
              />
              {tocSettings && (
                <div className="space-y-3 pl-1">
                  <Field label="收录级别">
                    <AdminSelect
                      value={String(tocSettings.maxDepth)}
                      onChange={(v) => patchToc({ maxDepth: Number(v) })}
                      options={[1, 2, 3, 4].map((n) => ({
                        value: String(n),
                        label: `${n} 级`,
                      }))}
                      className="w-full"
                    />
                  </Field>
                  <div className="grid grid-cols-2 gap-2">
                    <Toggle
                      checked={tocSettings.showPageNumbers}
                      onChange={(v) => patchToc({ showPageNumbers: v })}
                      label="显示页码"
                    />
                    <Toggle
                      checked={tocSettings.leaderDots}
                      onChange={(v) => patchToc({ leaderDots: v })}
                      label="目录点线"
                    />
                  </div>
                </div>
              )}
            </div>
          </Section>

          {/* 参考文献与附录 */}
          <Section icon={Paperclip} title="参考文献与附录">
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="参考文献格式">
                  <AdminSelect
                    value={referenceStyle}
                    onChange={setReferenceStyle}
                    options={REFERENCE_OPTIONS}
                    className="w-full"
                  />
                </Field>
                <Field label="附录编号">
                  <AdminSelect
                    value={
                      appendixRules?.numbering ?? APPENDIX_DEFAULT.numbering
                    }
                    onChange={(v) =>
                      patchAppendix({
                        numbering: v as "A-B-C" | "I-II-III" | "1-2-3",
                      })
                    }
                    options={APPENDIX_NUMBERING_OPTIONS}
                    className="w-full"
                  />
                </Field>
              </div>
              <Toggle
                checked={appendixRules?.separateToc ?? false}
                onChange={(v) => patchAppendix({ separateToc: v })}
                label="附录独立目录"
                icon={Paperclip}
              />
            </div>
          </Section>
        </div>

        {/* Footer */}
        <div className="border-border bg-muted/30 flex shrink-0 items-center justify-end gap-3 border-t px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="border-border bg-background text-foreground hover:bg-muted rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!name.trim() || saving}
            className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-medium shadow-sm transition-all disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> 保存中...
              </>
            ) : (
              "保存模板"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
