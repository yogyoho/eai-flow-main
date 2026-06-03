"use client";

import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import React, { useState, useCallback } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import type {
  AppendixRules,
  BodyStyles,
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

// --- Section toggle ---
function Section({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors"
      >
        {title}
        {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && <div className="border-t border-border px-4 py-4 space-y-4">{children}</div>}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="block text-sm font-medium text-foreground">{children}</label>;
}

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

interface LayoutTemplateEditorProps {
  template: LayoutTemplate | null;
  onSave: (data: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">) => Promise<void>;
  onCancel: () => void;
}

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
  paragraphSpacing: 6,
  firstLineIndent: 2,
};

const DEFAULT_HEADING_STYLES: HeadingStyle[] = [
  { level: 1, fontFamily: "黑体", fontSize: 16, fontWeight: 700, color: "#333333", numbering: "decimal" },
  { level: 2, fontFamily: "黑体", fontSize: 14, fontWeight: 700, color: "#333333", numbering: "decimal" },
];

export function LayoutTemplateEditor({ template, onSave, onCancel }: LayoutTemplateEditorProps) {
  const isEdit = template !== null;

  const [name, setName] = useState(template?.name ?? "");
  const [reportType, setReportType] = useState(template?.reportType ?? "general");
  const [pageSettings, setPageSettings] = useState<PageSettings>(template?.pageSettings ?? DEFAULT_PAGE_SETTINGS);
  const [coverTemplate, setCoverTemplate] = useState<CoverTemplate | null>(template?.coverTemplate ?? null);
  const [tocSettings, setTocSettings] = useState<TocSettings | null>(template?.tocSettings ?? null);
  const [bodyStyles, setBodyStyles] = useState<BodyStyles>(template?.bodyStyles ?? DEFAULT_BODY_STYLES);
  const [headingStyles, setHeadingStyles] = useState<HeadingStyle[]>(template?.headingStyles ?? DEFAULT_HEADING_STYLES);
  const [tableStyles, setTableStyles] = useState<TableStyles | null>(template?.tableStyles ?? null);
  const [figureStyles, setFigureStyles] = useState<FigureStyles | null>(template?.figureStyles ?? null);
  const [headerFooter, setHeaderFooter] = useState<HeaderFooter | null>(template?.headerFooter ?? null);
  const [referenceStyle, setReferenceStyle] = useState(template?.referenceStyle ?? "gb7714");
  const [appendixRules, setAppendixRules] = useState<AppendixRules | null>(template?.appendixRules ?? null);

  const [saving, setSaving] = useState(false);

  const handleSave = useCallback(async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        reportType,
        pageSettings,
        coverTemplate,
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
  }, [name, reportType, pageSettings, coverTemplate, tocSettings, bodyStyles, headingStyles, tableStyles, figureStyles, headerFooter, referenceStyle, appendixRules, onSave]);

  const updateHeading = (index: number, field: keyof HeadingStyle, value: string | number) => {
    setHeadingStyles((prev) => prev.map((h, i) => (i === index ? { ...h, [field]: value } : h)));
  };

  const addHeadingLevel = () => {
    const lastLevel = headingStyles[headingStyles.length - 1]?.level ?? 0;
    setHeadingStyles((prev) => [...prev, { level: lastLevel + 1, fontFamily: "黑体", fontSize: 12, fontWeight: 700, color: "#333333", numbering: "decimal" }]);
  };

  const removeHeadingLevel = (index: number) => {
    setHeadingStyles((prev) => prev.filter((_, i) => i !== index));
  };

  const inputCls = "w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 shrink-0">
          <h2 className="text-lg font-semibold text-foreground">{isEdit ? "编辑排版模板" : "新建排版模板"}</h2>
          <button type="button" onClick={onCancel} className="text-muted-foreground hover:text-foreground text-sm">✕</button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {/* 基本信息 */}
          <Section title="基本信息" defaultOpen>
            <div className="space-y-3">
              <div>
                <FieldLabel>模板名称</FieldLabel>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：环评报告（国标）" className={inputCls} />
              </div>
              <div>
                <FieldLabel>报告类型</FieldLabel>
                <AdminSelect value={reportType} onChange={setReportType} options={REPORT_TYPE_OPTIONS} className="w-full" />
              </div>
            </div>
          </Section>

          {/* 页面设置 */}
          <Section title="页面设置" defaultOpen>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <FieldLabel>纸张尺寸</FieldLabel>
                <AdminSelect value={pageSettings.paperSize} onChange={(v) => setPageSettings({ ...pageSettings, paperSize: v as PageSettings["paperSize"] })} options={PAPER_OPTIONS} className="w-full" />
              </div>
              <div>
                <FieldLabel>方向</FieldLabel>
                <AdminSelect value={pageSettings.orientation} onChange={(v) => setPageSettings({ ...pageSettings, orientation: v as PageSettings["orientation"] })} options={ORIENTATION_OPTIONS} className="w-full" />
              </div>
            </div>
            <div>
              <FieldLabel>页边距 (cm)</FieldLabel>
              <div className="grid grid-cols-4 gap-3 mt-1">
                <div className="text-center"><span className="text-xs text-muted-foreground">上</span><input type="number" step="0.01" value={pageSettings.marginTop} onChange={(e) => setPageSettings({ ...pageSettings, marginTop: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
                <div className="text-center"><span className="text-xs text-muted-foreground">下</span><input type="number" step="0.01" value={pageSettings.marginBottom} onChange={(e) => setPageSettings({ ...pageSettings, marginBottom: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
                <div className="text-center"><span className="text-xs text-muted-foreground">左</span><input type="number" step="0.01" value={pageSettings.marginLeft} onChange={(e) => setPageSettings({ ...pageSettings, marginLeft: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
                <div className="text-center"><span className="text-xs text-muted-foreground">右</span><input type="number" step="0.01" value={pageSettings.marginRight} onChange={(e) => setPageSettings({ ...pageSettings, marginRight: parseFloat(e.target.value) || 0 })} className={cn(inputCls, "mt-1")} /></div>
              </div>
            </div>
          </Section>

          {/* 封面配置 */}
          <Section title="封面配置">
            <div className="grid grid-cols-2 gap-4">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showLogo ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showLogo: e.target.checked })} className="rounded" /> 显示Logo</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showTitle ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showTitle: e.target.checked })} className="rounded" /> 显示标题</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showClient ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showClient: e.target.checked })} className="rounded" /> 显示客户</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showDate ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showDate: e.target.checked })} className="rounded" /> 显示日期</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={coverTemplate?.showProjectNumber ?? false} onChange={(e) => setCoverTemplate({ ...(coverTemplate ?? { showLogo: true, logoPosition: "center" as const, showTitle: true, showClient: true, showDate: true, showProjectNumber: true }), showProjectNumber: e.target.checked })} className="rounded" /> 显示项目编号</label>
            </div>
          </Section>

          {/* 正文样式 */}
          <Section title="正文样式" defaultOpen>
            <div className="grid grid-cols-2 gap-4">
              <div><FieldLabel>字体</FieldLabel><input type="text" value={bodyStyles.fontFamily} onChange={(e) => setBodyStyles({ ...bodyStyles, fontFamily: e.target.value })} className={inputCls} /></div>
              <div><FieldLabel>字号 (pt)</FieldLabel><input type="number" value={bodyStyles.fontSize} onChange={(e) => setBodyStyles({ ...bodyStyles, fontSize: parseInt(e.target.value) || 12 })} className={inputCls} /></div>
              <div><FieldLabel>行高</FieldLabel><input type="number" step="0.1" value={bodyStyles.lineHeight} onChange={(e) => setBodyStyles({ ...bodyStyles, lineHeight: parseFloat(e.target.value) || 1.5 })} className={inputCls} /></div>
              <div><FieldLabel>段落间距 (pt)</FieldLabel><input type="number" value={bodyStyles.paragraphSpacing} onChange={(e) => setBodyStyles({ ...bodyStyles, paragraphSpacing: parseInt(e.target.value) || 0 })} className={inputCls} /></div>
              <div><FieldLabel>首行缩进 (字符)</FieldLabel><input type="number" value={bodyStyles.firstLineIndent} onChange={(e) => setBodyStyles({ ...bodyStyles, firstLineIndent: parseInt(e.target.value) || 0 })} className={inputCls} /></div>
            </div>
          </Section>

          {/* 标题样式 */}
          <Section title="标题样式">
            <div className="space-y-3">
              {headingStyles.map((h, i) => (
                <div key={i} className="flex items-end gap-3 rounded-lg border border-border/50 p-3">
                  <div className="shrink-0"><span className="text-xs font-medium text-muted-foreground">级别 {h.level}</span></div>
                  <div className="flex-1 grid grid-cols-5 gap-2">
                    <input type="text" value={h.fontFamily} onChange={(e) => updateHeading(i, "fontFamily", e.target.value)} placeholder="字体" className="w-full rounded-md border border-border bg-muted px-2 py-1.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/20" />
                    <input type="number" value={h.fontSize} onChange={(e) => updateHeading(i, "fontSize", parseInt(e.target.value) || 12)} placeholder="字号" className="w-full rounded-md border border-border bg-muted px-2 py-1.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/20" />
                    <input type="number" value={h.fontWeight} onChange={(e) => updateHeading(i, "fontWeight", parseInt(e.target.value) || 400)} placeholder="粗细" className="w-full rounded-md border border-border bg-muted px-2 py-1.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/20" />
                    <input type="color" value={h.color} onChange={(e) => updateHeading(i, "color", e.target.value)} className="h-9 w-full rounded border border-border cursor-pointer" />
                    <AdminSelect value={h.numbering} onChange={(v) => updateHeading(i, "numbering", v)} options={HEADING_NUMBERING_OPTIONS} className="w-full" />
                  </div>
                  <button type="button" onClick={() => removeHeadingLevel(i)} className="shrink-0 text-destructive text-xs hover:underline">删除</button>
                </div>
              ))}
              <button type="button" onClick={addHeadingLevel} className="text-sm text-primary hover:underline">+ 添加级别</button>
            </div>
          </Section>

          {/* 表格样式 */}
          <Section title="表格样式">
            <div className="grid grid-cols-2 gap-4">
              <div><FieldLabel>表头背景色</FieldLabel><input type="color" value={tableStyles?.headerBg ?? "#2B579A"} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), headerBg: e.target.value })} className="h-10 w-full rounded border border-border cursor-pointer" /></div>
              <div><FieldLabel>表头字色</FieldLabel><input type="color" value={tableStyles?.headerColor ?? "#FFFFFF"} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), headerColor: e.target.value })} className="h-10 w-full rounded border border-border cursor-pointer" /></div>
              <div><FieldLabel>边框色</FieldLabel><input type="color" value={tableStyles?.borderColor ?? "#CCCCCC"} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), borderColor: e.target.value })} className="h-10 w-full rounded border border-border cursor-pointer" /></div>
              <div className="flex items-end"><label className="flex items-center gap-2 text-sm pb-2"><input type="checkbox" checked={tableStyles?.stripeRows ?? true} onChange={(e) => setTableStyles({ ...(tableStyles ?? { headerBg: "#2B579A", headerColor: "#FFFFFF", borderColor: "#CCCCCC", stripeRows: true }), stripeRows: e.target.checked })} className="rounded" /> 斑马纹</label></div>
            </div>
          </Section>

          {/* 图表样式 */}
          <Section title="图表样式">
            <div className="grid grid-cols-3 gap-4">
              <div><FieldLabel>标题位置</FieldLabel><AdminSelect value={figureStyles?.captionPosition ?? "below"} onChange={(v) => setFigureStyles({ ...(figureStyles ?? { captionPosition: "below" as const, numbering: "chapter" as const, showSource: true }), captionPosition: v as "above" | "below" })} options={CAPTION_POSITION_OPTIONS} className="w-full" /></div>
              <div><FieldLabel>编号方式</FieldLabel><AdminSelect value={figureStyles?.numbering ?? "chapter"} onChange={(v) => setFigureStyles({ ...(figureStyles ?? { captionPosition: "below" as const, numbering: "chapter" as const, showSource: true }), numbering: v as "chapter" | "continuous" })} options={FIGURE_NUMBERING_OPTIONS} className="w-full" /></div>
              <div className="flex items-end"><label className="flex items-center gap-2 text-sm pb-2"><input type="checkbox" checked={figureStyles?.showSource ?? true} onChange={(e) => setFigureStyles({ ...(figureStyles ?? { captionPosition: "below" as const, numbering: "chapter" as const, showSource: true }), showSource: e.target.checked })} className="rounded" /> 显示来源</label></div>
            </div>
          </Section>

          {/* 页眉页脚 */}
          <Section title="页眉页脚">
            <div className="space-y-3">
              <div><FieldLabel>页眉文本</FieldLabel><input type="text" value={headerFooter?.headerText ?? ""} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), headerText: e.target.value })} className={inputCls} /></div>
              <div><FieldLabel>页脚文本</FieldLabel><input type="text" value={headerFooter?.footerText ?? ""} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), footerText: e.target.value })} className={inputCls} /></div>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={headerFooter?.showPageNumber ?? true} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), showPageNumber: e.target.checked })} className="rounded" /> 显示页码</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={headerFooter?.showLogo ?? false} onChange={(e) => setHeaderFooter({ ...(headerFooter ?? { headerText: "", footerText: "", showPageNumber: true, showLogo: false }), showLogo: e.target.checked })} className="rounded" /> 显示Logo</label>
              </div>
            </div>
          </Section>

          {/* 参考文献与附录 */}
          <Section title="参考文献与附录">
            <div className="grid grid-cols-2 gap-4">
              <div><FieldLabel>参考文献格式</FieldLabel><AdminSelect value={referenceStyle} onChange={setReferenceStyle} options={REFERENCE_OPTIONS} className="w-full" /></div>
              <div><FieldLabel>附录编号</FieldLabel><AdminSelect value={appendixRules?.numbering ?? "A-B-C"} onChange={(v) => setAppendixRules({ ...(appendixRules ?? { numbering: "A-B-C" as const, separateToc: false }), numbering: v as "A-B-C" | "I-II-III" | "1-2-3" })} options={APPENDIX_NUMBERING_OPTIONS} className="w-full" /></div>
            </div>
            <label className="flex items-center gap-2 text-sm mt-3"><input type="checkbox" checked={appendixRules?.separateToc ?? false} onChange={(e) => setAppendixRules({ ...(appendixRules ?? { numbering: "A-B-C" as const, separateToc: false }), separateToc: e.target.checked })} className="rounded" /> 附录独立目录</label>
          </Section>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4 shrink-0">
          <button type="button" onClick={onCancel} className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors">取消</button>
          <button type="button" onClick={handleSave} disabled={!name.trim() || saving} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {saving ? <><Loader2 className="h-4 w-4 animate-spin" /> 保存中...</> : "保存模板"}
          </button>
        </div>
      </div>
    </div>
  );
}
