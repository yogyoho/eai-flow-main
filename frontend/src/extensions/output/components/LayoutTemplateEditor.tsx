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
import type {
  AppendixRules,
  BodyStyles,
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

// ─────────────────────────────────────────────────────────────────────────────
// Primitives
// ─────────────────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground/50 hover:border-primary/40 focus:border-primary focus:ring-2 focus:ring-primary/20";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
        {hint && <span className="shrink-0 text-[10px] font-normal text-muted-foreground/60">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

/** Color picker rendered as a swatch + monospace hex label (not a bare native box). */
function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <Field label={label} hint={value.toUpperCase()}>
      <div className="flex h-9 items-center gap-2 rounded-lg border border-input bg-background pr-2.5 transition-all hover:border-primary/40 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20">
        <div className="relative h-full w-10 shrink-0 overflow-hidden rounded-l-lg ring-1 ring-inset ring-black/5">
          <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 h-full w-full cursor-pointer opacity-0" />
          <div className="h-full w-full" style={{ backgroundColor: value }} />
        </div>
        <span className="font-mono text-xs uppercase text-muted-foreground">{value}</span>
      </div>
    </Field>
  );
}

/** Card-style toggle replacing bare checkboxes — tints primary when active. */
function Toggle({ checked, onChange, label, icon: Icon }: { checked: boolean; onChange: (v: boolean) => void; label: string; icon?: LucideIcon }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-all",
        checked ? "border-primary/30 bg-primary/5 text-foreground" : "border-border bg-background text-muted-foreground hover:border-input hover:bg-muted/40",
      )}
    >
      <span
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border transition-all",
          checked ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background",
        )}
      >
        {checked && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
      {Icon && <Icon className={cn("h-3.5 w-3.5", checked ? "text-primary" : "text-muted-foreground/70")} />}
      <span className="flex-1">{label}</span>
    </button>
  );
}

function Section({ icon: Icon, title, defaultOpen = false, children }: { icon: LucideIcon; title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={cn("overflow-hidden rounded-xl border border-border bg-card transition-shadow", open && "shadow-sm")}>
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary ring-1 ring-inset ring-primary/15">
          <Icon className="h-4 w-4" />
        </span>
        <span className="flex-1 text-sm font-semibold text-foreground">{title}</span>
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && <div className="animate-in fade-in-0 border-t border-border bg-muted/40 px-4 py-4 duration-200">{children}</div>}
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
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg bg-muted/40 p-4">
      <div
        className="relative rounded-sm bg-background shadow-md ring-1 ring-border"
        style={{ width: landscape ? 116 : 86, aspectRatio: landscape ? "29.7 / 21" : "21 / 29.7" }}
      >
        {/* margin zone tint */}
        <div className="absolute rounded-[1px] bg-primary/12" style={{ top: `${top}%`, bottom: `${bottom}%`, left: `${left}%`, right: `${right}%` }}>
          <div className="flex h-full flex-col justify-center gap-[3px] px-1.5">
            <div className="h-[2px] w-3/4 rounded-full bg-muted-foreground/30" />
            <div className="h-[2px] w-full rounded-full bg-muted-foreground/20" />
            <div className="h-[2px] w-5/6 rounded-full bg-muted-foreground/20" />
            <div className="h-[2px] w-full rounded-full bg-muted-foreground/20" />
            <div className="h-[2px] w-2/3 rounded-full bg-muted-foreground/20" />
          </div>
        </div>
      </div>
      <span className="text-[10px] font-medium text-muted-foreground">
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
    <div className="rounded-lg bg-muted/30 p-4">
      <p style={pStyle}>本项目位于某工业园区，厂区总平面布置符合防火间距要求。</p>
      <p style={pStyle}>设计依据国家现行消防技术标准，总建筑面积及防火分区均满足规范。</p>
    </div>
  );
}

function HeadingPreview({ h }: { h: HeadingStyle }) {
  return (
    <div className="flex-1 truncate" style={{ fontFamily: h.fontFamily, fontSize: `${h.fontSize}pt`, fontWeight: h.fontWeight, color: h.color, lineHeight: 1.3 }}>
      {h.level === 1 ? "第一章" : h.level === 2 ? "1.1" : `${h.level}.1`} 概述
    </div>
  );
}

function TablePreview({ styles }: { styles: TableStyles }) {
  const rows = [0, 1, 2];
  return (
    <div className="overflow-hidden rounded-lg ring-1" style={{ "--tw-ring-color": styles.borderColor } as React.CSSProperties}>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ backgroundColor: styles.headerBg, color: styles.headerColor }}>
            <th className="px-3 py-1.5 text-left font-medium">项目</th>
            <th className="px-3 py-1.5 text-right font-medium">数值</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i} style={styles.stripeRows && i % 2 === 1 ? { backgroundColor: "color-mix(in oklch, var(--foreground) 4%, transparent)" } : undefined}>
              <td className="border-t px-3 py-1.5 text-muted-foreground" style={{ borderColor: styles.borderColor }}>
                数据行 {i + 1}
              </td>
              <td className="border-t px-3 py-1.5 text-right text-muted-foreground" style={{ borderColor: styles.borderColor }}>
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
    <div className="rounded-lg bg-muted/40 p-3">
      <div className="space-y-2 rounded bg-background p-2.5 shadow-sm ring-1 ring-border" style={{ minHeight: 92 }}>
        <div className="flex items-center justify-between gap-2 border-b border-dashed border-border pb-1.5">
          {hf.showLogo ? (
            <span className="flex items-center gap-1 text-[9px] font-medium text-muted-foreground">
              <ImageIcon className="h-3 w-3" /> LOGO
            </span>
          ) : (
            <span />
          )}
          <span className="max-w-[70%] truncate text-[9px] text-muted-foreground">{hf.headerText || "页眉文本"}</span>
        </div>
        <div className="space-y-1 py-0.5">
          <div className="h-1 w-full rounded-full bg-muted-foreground/20" />
          <div className="h-1 w-5/6 rounded-full bg-muted-foreground/20" />
          <div className="h-1 w-3/4 rounded-full bg-muted-foreground/20" />
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-dashed border-border pt-1.5">
          <span className="max-w-[60%] truncate text-[9px] text-muted-foreground">{hf.footerText || "页脚文本"}</span>
          {hf.showPageNumber && <span className="text-[9px] text-muted-foreground">第 1 页</span>}
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

const DEFAULT_PAGE_SETTINGS: PageSettings = { paperSize: "A4", orientation: "portrait", marginTop: 2.54, marginBottom: 2.54, marginLeft: 3.17, marginRight: 3.17 };
const DEFAULT_BODY_STYLES: BodyStyles = { fontFamily: "宋体", fontSize: 12, lineHeight: 1.5, paragraphSpacing: 0, firstLineIndent: 2 };
const DEFAULT_HEADING_STYLES: HeadingStyle[] = [
  { level: 1, fontFamily: "黑体", fontSize: 16, fontWeight: 700, color: "#000000", numbering: "decimal" },
  { level: 2, fontFamily: "黑体", fontSize: 14, fontWeight: 700, color: "#000000", numbering: "decimal" },
];

const COVER_DEFAULT: CoverTemplate = { showLogo: true, logoPosition: "center", showTitle: true, showClient: true, showDate: true, showProjectNumber: true };
const TABLE_DEFAULT: TableStyles = { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true };
const FIGURE_DEFAULT: FigureStyles = { captionPosition: "below", numbering: "chapter", showSource: true };
const HF_DEFAULT: HeaderFooter = { headerText: "", footerText: "", showPageNumber: true, showLogo: false };
const APPENDIX_DEFAULT: AppendixRules = { numbering: "A-B-C", separateToc: false };
const TOC_DEFAULT: TocSettings = { maxDepth: 3, showPageNumbers: true, leaderDots: true };

const headingInputCls = "w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs text-foreground outline-none transition-all hover:border-primary/40 focus:border-primary focus:ring-2 focus:ring-primary/20";

// ─────────────────────────────────────────────────────────────────────────────
// Editor
// ─────────────────────────────────────────────────────────────────────────────

interface LayoutTemplateEditorProps {
  template: LayoutTemplate | null;
  onSave: (data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">) => Promise<void>;
  onCancel: () => void;
}

export function LayoutTemplateEditor({ template, onSave, onCancel }: LayoutTemplateEditorProps) {
  const isEdit = template !== null;

  const [name, setName] = useState(template?.name ?? "");
  const [reportType, setReportType] = useState(template?.reportType ?? "general");
  const [pageSettings, setPageSettings] = useState<PageSettings>(template?.pageSettings ?? DEFAULT_PAGE_SETTINGS);
  const [coverTemplate, setCoverTemplate] = useState<CoverTemplate | null>(template?.coverTemplate ?? null);
  const [coverMaster, setCoverMaster] = useState<CoverMaster | null>(template?.coverMaster ?? null);
  const [tocSettings, setTocSettings] = useState<TocSettings | null>(template?.tocSettings ?? null);
  const [bodyStyles, setBodyStyles] = useState<BodyStyles>(template?.bodyStyles ?? DEFAULT_BODY_STYLES);
  const [headingStyles, setHeadingStyles] = useState<HeadingStyle[]>(template?.headingStyles ?? DEFAULT_HEADING_STYLES);
  const [tableStyles, setTableStyles] = useState<TableStyles | null>(template?.tableStyles ?? null);
  const [figureStyles, setFigureStyles] = useState<FigureStyles | null>(template?.figureStyles ?? null);
  const [headerFooter, setHeaderFooter] = useState<HeaderFooter | null>(template?.headerFooter ?? null);
  const [referenceStyle, setReferenceStyle] = useState(template?.referenceStyle ?? "gb7714");
  const [appendixRules, setAppendixRules] = useState<AppendixRules | null>(template?.appendixRules ?? null);

  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // patch helpers — collapse the repeated `{ ...(x ?? DEFAULT), patch }` boilerplate
  const patchCover = useCallback((p: Partial<CoverTemplate>) => setCoverTemplate((c) => ({ ...(c ?? COVER_DEFAULT), ...p })), []);
  const patchSlot = useCallback((index: number, p: Partial<CoverSlot>) => setCoverMaster((m) => (m ? { ...m, slots: m.slots.map((s, i) => (i === index ? { ...s, ...p } : s)) } : m)), []);
  const patchTable = useCallback((p: Partial<TableStyles>) => setTableStyles((t) => ({ ...(t ?? TABLE_DEFAULT), ...p })), []);
  const patchFigure = useCallback((p: Partial<FigureStyles>) => setFigureStyles((f) => ({ ...(f ?? FIGURE_DEFAULT), ...p })), []);
  const patchHF = useCallback((p: Partial<HeaderFooter>) => setHeaderFooter((h) => ({ ...(h ?? HF_DEFAULT), ...p })), []);
  const patchAppendix = useCallback((p: Partial<AppendixRules>) => setAppendixRules((a) => ({ ...(a ?? APPENDIX_DEFAULT), ...p })), []);
  const patchToc = useCallback((p: Partial<TocSettings>) => setTocSettings((t) => ({ ...(t ?? TOC_DEFAULT), ...p })), []);

  const handleSave = useCallback(async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        reportType,
        pageSettings,
        coverTemplate,
        coverMaster,
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
  }, [name, reportType, pageSettings, coverTemplate, coverMaster, tocSettings, bodyStyles, headingStyles, tableStyles, figureStyles, headerFooter, referenceStyle, appendixRules, onSave]);

  const applyImported = useCallback((data: Record<string, unknown>) => {
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
    const cm = data.cover_master as CoverMaster | null | undefined;
    if (cm?.mode === "master") {
      setCoverMaster(cm);
    } else {
      // 无母版时才走旧 toggle 兜底（保留既有行为）
      const ct = data.cover_template as CoverTemplate | null | undefined;
      if (data.cover_detected === true && ct && (ct.showLogo || ct.showTitle || ct.showClient || ct.showDate || ct.showProjectNumber)) {
        setCoverTemplate(ct);
      }
    }
  }, []);

  const handleImportedFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setImporting(true);
      try {
        const { outputApi } = await import("@/extensions/output/api");
        const data = await outputApi.importLayout(file);
        applyImported(data);
        toast.success("已从样例文档提取排版");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "无法从该文件提取排版信息");
      } finally {
        setImporting(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [applyImported],
  );

  const updateHeading = (index: number, field: keyof HeadingStyle, value: string | number) =>
    setHeadingStyles((prev) => prev.map((h, i) => (i === index ? { ...h, [field]: value } : h)));
  const addHeadingLevel = () => {
    const lastLevel = headingStyles[headingStyles.length - 1]?.level ?? 0;
    setHeadingStyles((prev) => [...prev, { level: lastLevel + 1, fontFamily: "黑体", fontSize: 12, fontWeight: 700, color: "#000000", numbering: "decimal" }]);
  };
  const removeHeadingLevel = (index: number) => setHeadingStyles((prev) => prev.filter((_, i) => i !== index));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-background shadow-2xl ring-1 ring-border">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border bg-gradient-to-b from-muted/40 to-background px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-inset ring-primary/15">
              <FileText className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-base font-semibold text-foreground">{isEdit ? "编辑排版模板" : "新建排版模板"}</h2>
              <p className="text-xs text-muted-foreground">配置报告导出的页面、字体与版式参数</p>
            </div>
          </div>
          <button type="button" onClick={onCancel} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
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
                  <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：环评报告（国标）" className={inputCls} />
                </Field>
                <Field label="报告类型">
                  <AdminSelect value={reportType} onChange={setReportType} options={REPORT_TYPE_OPTIONS} className="w-full" />
                </Field>
              </div>
              <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-primary/30 bg-primary/5 p-3">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={importing}
                  className="flex items-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
                >
                  {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                  {importing ? "提取中..." : "从样例导入排版"}
                </button>
                <span className="text-xs text-muted-foreground">上传 .docx 样例，自动识别并填充以下各项参数</span>
                <input ref={fileInputRef} type="file" accept=".docx" onChange={handleImportedFile} className="hidden" />
              </div>
            </div>
          </Section>

          {/* 页面设置 */}
          <Section icon={FileText} title="页面设置" defaultOpen>
            <div className="grid grid-cols-[1fr_auto] gap-5">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="纸张尺寸">
                    <AdminSelect value={pageSettings.paperSize} onChange={(v) => setPageSettings({ ...pageSettings, paperSize: v as PageSettings["paperSize"] })} options={PAPER_OPTIONS} className="w-full" />
                  </Field>
                  <Field label="方向">
                    <AdminSelect value={pageSettings.orientation} onChange={(v) => setPageSettings({ ...pageSettings, orientation: v as PageSettings["orientation"] })} options={ORIENTATION_OPTIONS} className="w-full" />
                  </Field>
                </div>
                <Field label="页边距" hint="cm">
                  <div className="grid grid-cols-4 gap-2">
                    {([
                      ["上", "marginTop", pageSettings.marginTop],
                      ["下", "marginBottom", pageSettings.marginBottom],
                      ["左", "marginLeft", pageSettings.marginLeft],
                      ["右", "marginRight", pageSettings.marginRight],
                    ] as const).map(([lbl, key, val]) => (
                      <div key={key} className="space-y-1 text-center">
                        <span className="text-[10px] text-muted-foreground">{lbl}</span>
                        <input
                          type="number"
                          step="0.01"
                          value={val}
                          onChange={(e) => setPageSettings({ ...pageSettings, [key]: parseFloat(e.target.value) || 0 })}
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
                  <input type="text" value={bodyStyles.fontFamily} onChange={(e) => setBodyStyles({ ...bodyStyles, fontFamily: e.target.value })} className={inputCls} />
                </Field>
                <Field label="字号" hint="pt">
                  <input type="number" value={bodyStyles.fontSize} onChange={(e) => setBodyStyles({ ...bodyStyles, fontSize: parseInt(e.target.value) || 12 })} className={inputCls} />
                </Field>
                <Field label="行高" hint="倍">
                  <input type="number" step="0.1" value={bodyStyles.lineHeight} onChange={(e) => setBodyStyles({ ...bodyStyles, lineHeight: parseFloat(e.target.value) || 1.5 })} className={inputCls} />
                </Field>
                <Field label="段后距" hint="pt">
                  <input type="number" value={bodyStyles.paragraphSpacing} onChange={(e) => setBodyStyles({ ...bodyStyles, paragraphSpacing: parseInt(e.target.value) || 0 })} className={inputCls} />
                </Field>
                <Field label="首行缩进" hint="字符">
                  <input type="number" value={bodyStyles.firstLineIndent} onChange={(e) => setBodyStyles({ ...bodyStyles, firstLineIndent: parseInt(e.target.value) || 0 })} className={inputCls} />
                </Field>
              </div>
              <BodyPreview styles={bodyStyles} />
            </div>
          </Section>

          {/* 标题样式 */}
          <Section icon={Heading1} title="标题样式">
            <div className="space-y-2.5">
              {headingStyles.map((h, i) => (
                <div key={i} className="rounded-lg border border-border bg-muted/20 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="flex h-6 items-center rounded-md bg-primary/10 px-2 text-[11px] font-semibold text-primary">H{h.level}</span>
                    <button type="button" onClick={() => removeHeadingLevel(i)} className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-destructive">
                      <Trash2 className="h-3 w-3" /> 删除
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                    <input type="text" value={h.fontFamily} onChange={(e) => updateHeading(i, "fontFamily", e.target.value)} placeholder="字体" className={headingInputCls} />
                    <input type="number" value={h.fontSize} onChange={(e) => updateHeading(i, "fontSize", parseInt(e.target.value) || 12)} placeholder="字号" className={headingInputCls} />
                    <input type="number" value={h.fontWeight} onChange={(e) => updateHeading(i, "fontWeight", parseInt(e.target.value) || 400)} placeholder="粗细" className={headingInputCls} />
                    <div className="flex h-[34px] items-center gap-2 rounded-md border border-input bg-background px-2">
                      <input type="color" value={h.color} onChange={(e) => updateHeading(i, "color", e.target.value)} className="h-5 w-5 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0" />
                      <span className="font-mono text-[10px] uppercase text-muted-foreground">{h.color}</span>
                    </div>
                    <AdminSelect value={h.numbering} onChange={(v) => updateHeading(i, "numbering", v)} options={HEADING_NUMBERING_OPTIONS} className="w-full" />
                  </div>
                  <div className="mt-2.5 rounded-md bg-background px-3 py-2 ring-1 ring-border">
                    <HeadingPreview h={h} />
                  </div>
                </div>
              ))}
              <button type="button" onClick={addHeadingLevel} className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary">
                <Plus className="h-4 w-4" /> 添加标题级别
              </button>
            </div>
          </Section>

          {/* 表格样式 */}
          <Section icon={Table2} title="表格样式">
            <div className="grid grid-cols-[1fr_auto] gap-5">
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <ColorField label="表头背景" value={tableStyles?.headerBg ?? TABLE_DEFAULT.headerBg} onChange={(v) => patchTable({ headerBg: v })} />
                  <ColorField label="表头字色" value={tableStyles?.headerColor ?? TABLE_DEFAULT.headerColor} onChange={(v) => patchTable({ headerColor: v })} />
                  <ColorField label="边框色" value={tableStyles?.borderColor ?? TABLE_DEFAULT.borderColor} onChange={(v) => patchTable({ borderColor: v })} />
                </div>
                <Toggle checked={tableStyles?.stripeRows ?? TABLE_DEFAULT.stripeRows} onChange={(v) => patchTable({ stripeRows: v })} label="斑马纹（隔行底纹）" icon={Table2} />
              </div>
              <TablePreview styles={tableStyles ?? TABLE_DEFAULT} />
            </div>
          </Section>

          {/* 图表样式 */}
          <Section icon={BarChart3} title="图表样式">
            <div className="grid grid-cols-2 gap-3">
              <Field label="标题位置">
                <AdminSelect value={figureStyles?.captionPosition ?? FIGURE_DEFAULT.captionPosition} onChange={(v) => patchFigure({ captionPosition: v as "above" | "below" })} options={CAPTION_POSITION_OPTIONS} className="w-full" />
              </Field>
              <Field label="编号方式">
                <AdminSelect value={figureStyles?.numbering ?? FIGURE_DEFAULT.numbering} onChange={(v) => patchFigure({ numbering: v as "chapter" | "continuous" })} options={FIGURE_NUMBERING_OPTIONS} className="w-full" />
              </Field>
            </div>
            <div className="mt-3">
              <Toggle checked={figureStyles?.showSource ?? FIGURE_DEFAULT.showSource} onChange={(v) => patchFigure({ showSource: v })} label="显示数据来源" icon={BarChart3} />
            </div>
          </Section>

          {/* 页眉页脚 */}
          <Section icon={PanelTop} title="页眉页脚">
            <div className="grid grid-cols-[1fr_auto] gap-5">
              <div className="space-y-3">
                <Field label="页眉文本">
                  <input type="text" value={headerFooter?.headerText ?? ""} onChange={(e) => patchHF({ headerText: e.target.value })} placeholder="如：项目消防设计专篇" className={inputCls} />
                </Field>
                <Field label="页脚文本">
                  <input type="text" value={headerFooter?.footerText ?? ""} onChange={(e) => patchHF({ footerText: e.target.value })} placeholder="如：设计院名称" className={inputCls} />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Toggle checked={headerFooter?.showPageNumber ?? HF_DEFAULT.showPageNumber} onChange={(v) => patchHF({ showPageNumber: v })} label="显示页码" />
                  <Toggle checked={headerFooter?.showLogo ?? HF_DEFAULT.showLogo} onChange={(v) => patchHF({ showLogo: v })} label="显示 Logo" />
                </div>
              </div>
              <HeaderFooterPreview hf={headerFooter ?? HF_DEFAULT} />
            </div>
          </Section>

          {/* 封面配置 */}
          <Section icon={ImageIcon} title="封面配置">
            {coverMaster ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate text-muted-foreground">来自样例：<span className="font-medium text-foreground">{coverMaster.sourceFile || "（未命名）"}</span></span>
                  <span className="ml-auto shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{coverMaster.boundary === "before_toc" ? "目录前" : "首标题前"}</span>
                </div>
                <div className="space-y-1.5">
                  <p className="text-[11px] font-medium text-muted-foreground">{`槽位（生成时替换"变量"，保留"字面"）`}</p>
                  {coverMaster.slots.map((slot, i) => (
                    <div key={slot.id} className="flex items-center gap-2 rounded-lg border border-border px-2 py-1.5">
                      <span className="w-16 shrink-0 text-[11px] font-medium text-muted-foreground">{slot.label}</span>
                      <input
                        className="h-7 flex-1 rounded-md border border-border bg-background px-2 text-xs disabled:opacity-50"
                        value={slot.sampleValue}
                        onChange={(e) => patchSlot(i, { sampleValue: e.target.value })}
                        disabled={slot.kind === "literal"}
                      />
                      <button
                        type="button"
                        onClick={() => patchSlot(i, { kind: slot.kind === "variable" ? "literal" : "variable" })}
                        className={`shrink-0 rounded-md px-2 py-1 text-[10px] font-medium ring-1 ring-inset ring-border transition-colors hover:bg-muted ${slot.kind === "variable" ? "text-primary" : "text-muted-foreground"}`}
                        title={slot.kind === "variable" ? "点击切为字面（原样保留不替换）" : "点击切为变量（生成时替换）"}
                      >
                        {slot.kind === "variable" ? "变量" : "字面"}
                      </button>
                    </div>
                  ))}
                </div>
                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={importing} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50">
                  <FileUp className="h-3.5 w-3.5" />
                  {importing ? "提取中…" : "重新从样例导入封面"}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <Toggle checked={coverTemplate?.showLogo ?? false} onChange={(v) => patchCover({ showLogo: v })} label="显示 Logo" icon={ImageIcon} />
                  <Toggle checked={coverTemplate?.showTitle ?? false} onChange={(v) => patchCover({ showTitle: v })} label="显示标题" icon={Type} />
                  <Toggle checked={coverTemplate?.showClient ?? false} onChange={(v) => patchCover({ showClient: v })} label="显示建设单位" />
                  <Toggle checked={coverTemplate?.showDate ?? false} onChange={(v) => patchCover({ showDate: v })} label="显示日期" />
                  <Toggle checked={coverTemplate?.showProjectNumber ?? false} onChange={(v) => patchCover({ showProjectNumber: v })} label="显示项目编号" />
                </div>
                {((coverTemplate?.showLogo ?? false) || (coverTemplate?.showTitle ?? false) || (coverTemplate?.showClient ?? false) || (coverTemplate?.showDate ?? false) || (coverTemplate?.showProjectNumber ?? false)) && (
                  <div className="rounded-lg bg-muted/30 p-5">
                    <p className="mb-3 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">预览</p>
                    <div className="mx-auto max-w-[240px] space-y-2.5 text-center">
                      {coverTemplate?.showLogo && (
                        <div className="mx-auto flex h-12 w-20 items-center justify-center rounded-md bg-primary/10 text-[10px] font-medium text-primary ring-1 ring-inset ring-primary/15">LOGO</div>
                      )}
                      {coverTemplate?.showTitle && <div className="text-lg font-bold text-foreground">报告标题</div>}
                      <div className="space-y-1.5 pt-1 text-xs text-muted-foreground">
                        {coverTemplate?.showClient && <div>建设单位：XXXX</div>}
                        {coverTemplate?.showDate && <div>日期：2026-08</div>}
                        {coverTemplate?.showProjectNumber && <div>项目编号：XXXX</div>}
                      </div>
                    </div>
                  </div>
                )}
                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={importing} className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/5 disabled:opacity-50">
                  <FileUp className="h-3.5 w-3.5" />
                  {importing ? "提取中…" : "从样例 .docx 导入真实封面"}
                </button>
              </div>
            )}
          </Section>

          {/* 目录设置 */}
          <Section icon={ListOrdered} title="目录设置">
            <div className="space-y-3">
              <Toggle checked={tocSettings !== null} onChange={(v) => setTocSettings(v ? TOC_DEFAULT : null)} label="包含目录" icon={ListOrdered} />
              {tocSettings && (
                <div className="space-y-3 pl-1">
                  <Field label="收录级别">
                    <AdminSelect value={String(tocSettings.maxDepth)} onChange={(v) => patchToc({ maxDepth: Number(v) })} options={[1, 2, 3, 4].map((n) => ({ value: String(n), label: `${n} 级` }))} className="w-full" />
                  </Field>
                  <div className="grid grid-cols-2 gap-2">
                    <Toggle checked={tocSettings.showPageNumbers} onChange={(v) => patchToc({ showPageNumbers: v })} label="显示页码" />
                    <Toggle checked={tocSettings.leaderDots} onChange={(v) => patchToc({ leaderDots: v })} label="目录点线" />
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
                  <AdminSelect value={referenceStyle} onChange={setReferenceStyle} options={REFERENCE_OPTIONS} className="w-full" />
                </Field>
                <Field label="附录编号">
                  <AdminSelect value={appendixRules?.numbering ?? APPENDIX_DEFAULT.numbering} onChange={(v) => patchAppendix({ numbering: v as "A-B-C" | "I-II-III" | "1-2-3" })} options={APPENDIX_NUMBERING_OPTIONS} className="w-full" />
                </Field>
              </div>
              <Toggle checked={appendixRules?.separateToc ?? false} onChange={(v) => patchAppendix({ separateToc: v })} label="附录独立目录" icon={Paperclip} />
            </div>
          </Section>
        </div>

        {/* Footer */}
        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border bg-muted/30 px-6 py-4">
          <button type="button" onClick={onCancel} className="rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted">
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!name.trim() || saving}
            className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
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
