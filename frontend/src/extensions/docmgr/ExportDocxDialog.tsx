"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Download,
  FileUp,
  LayoutTemplate as LayoutTemplateIcon,
  List,
  Loader2,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CoverConfigSection } from "@/extensions/output/components/CoverConfigSection";
import {
  normalizeCoverElements,
  normalizeCoverTemplate,
} from "@/extensions/output/cover-state";
import type {
  BodyStyles,
  Cover,
  CoverMaster,
  CoverTemplate,
  FigureStyles,
  HeaderFooter,
  HeadingStyle,
  LayoutTemplate,
  PageSettings,
  TableStyles,
  WatermarkType,
} from "@/extensions/output/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Reusable small components
// ---------------------------------------------------------------------------

function FieldLabel({
  children,
  hint,
}: {
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="text-muted-foreground mb-1 block text-xs font-medium">
      {children}
      {hint && <span className="ml-1 font-normal opacity-60">{hint}</span>}
    </label>
  );
}

const PAPER_OPTIONS = [
  { value: "A4", label: "A4 (210×297mm)" },
  { value: "A3", label: "A3 (297×420mm)" },
  { value: "B5", label: "B5 (176×250mm)" },
  { value: "letter", label: "Letter (216×279mm)" },
];

const ORIENTATION_OPTIONS = [
  { value: "portrait", label: "纵向" },
  { value: "landscape", label: "横向" },
];

const HEADING_NUMBERING_OPTIONS = [
  { value: "decimal", label: "1, 2, 3" },
  { value: "chinese", label: "一, 二, 三" },
  { value: "none", label: "无编号" },
];

const WATERMARK_OPTIONS: { value: WatermarkType | "none"; label: string }[] = [
  { value: "none", label: "无水印" },
  { value: "draft", label: "初稿" },
  { value: "review", label: "送审稿" },
  { value: "final", label: "正式稿" },
];

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

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
  {
    level: 1,
    fontFamily: "黑体",
    fontSize: 22,
    fontWeight: 700,
    color: "#000000",
    numbering: "decimal",
  },
  {
    level: 2,
    fontFamily: "黑体",
    fontSize: 16,
    fontWeight: 700,
    color: "#000000",
    numbering: "decimal",
  },
  {
    level: 3,
    fontFamily: "楷体",
    fontSize: 14,
    fontWeight: 700,
    color: "#333333",
    numbering: "decimal",
  },
  {
    level: 4,
    fontFamily: "楷体",
    fontSize: 12,
    fontWeight: 700,
    color: "#333333",
    numbering: "none",
  },
];

const DEFAULT_TABLE_STYLES: TableStyles = {
  headerBg: "#2B579A",
  headerColor: "#FFFFFF",
  borderColor: "#CCCCCC",
  stripeRows: true,
};

const DEFAULT_FIGURE_STYLES: FigureStyles = {
  captionPosition: "below",
  numbering: "chapter",
  showSource: true,
};

const DEFAULT_HEADER_FOOTER: HeaderFooter = {
  headerText: "",
  footerText: "",
  showPageNumber: true,
  showLogo: false,
};

// ---------------------------------------------------------------------------
// Section config for left nav
// ---------------------------------------------------------------------------

interface SectionDef {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const SECTIONS: SectionDef[] = [
  {
    id: "template",
    label: "排版模板",
    icon: <LayoutTemplateIcon className="h-3.5 w-3.5" />,
  },
  {
    id: "page",
    label: "页面设置",
    icon: <span className="text-[10px] font-bold">⬜</span>,
  },
  {
    id: "body",
    label: "正文样式",
    icon: <span className="text-[10px] font-bold">T</span>,
  },
  {
    id: "headings",
    label: "标题样式",
    icon: <span className="text-[10px] font-bold">H</span>,
  },
  {
    id: "table",
    label: "表格样式",
    icon: <span className="text-[10px] font-bold">▦</span>,
  },
  {
    id: "figure",
    label: "图表样式",
    icon: <span className="text-[10px] font-bold">▣</span>,
  },
  {
    id: "headerFooter",
    label: "页眉页脚",
    icon: <span className="text-[10px] font-bold">☰</span>,
  },
  {
    id: "watermark",
    label: "水印设置",
    icon: <Sparkles className="h-3.5 w-3.5" />,
  },
  { id: "toc", label: "目录设置", icon: <List className="h-3.5 w-3.5" /> },
  { id: "cover", label: "封面", icon: <span className="text-[10px]">📄</span> },
];

// ---------------------------------------------------------------------------
// Styled Checkbox (animated SVG check, inspired by role-management PermCheckbox)
// ---------------------------------------------------------------------------

function StyledCheckbox({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-[18px] w-[18px] shrink-0 cursor-pointer items-center justify-center rounded-[5px] border-[1.5px] transition-all duration-200 ease-out select-none",
        checked
          ? "bg-primary border-primary shadow-[0_1px_4px_rgba(var(--color-primary),0.3)]"
          : "border-muted-foreground/30 hover:border-primary/40 bg-transparent",
        disabled && "pointer-events-none opacity-40",
      )}
    >
      <svg
        viewBox="0 0 14 14"
        fill="none"
        className="h-[11px] w-[11px]"
        aria-hidden="true"
      >
        <motion.path
          d="M3 7.5L5.8 10.2L11 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn(
            checked ? "text-primary-foreground" : "text-transparent",
          )}
          initial={false}
          animate={
            checked
              ? { pathLength: 1, opacity: 1 }
              : { pathLength: 0, opacity: 0 }
          }
          transition={{ duration: 0.18, ease: "easeOut" }}
        />
      </svg>
      <AnimatePresence>
        {checked && (
          <motion.span
            className="bg-primary/30 absolute inset-0 rounded-[5px]"
            initial={{ scale: 1, opacity: 0.6 }}
            animate={{ scale: 1.6, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
          />
        )}
      </AnimatePresence>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Styled Radio Card (card-style single-select, like role management cards)
// ---------------------------------------------------------------------------

function RadioCard({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group w-full rounded-xl border p-3 text-left transition-all duration-200",
        selected
          ? "bg-card border-primary/30 ring-primary/10 shadow-sm ring-1"
          : "bg-muted/30 hover:bg-accent hover:border-border/60 border-transparent",
      )}
    >
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-200",
            selected
              ? "border-primary"
              : "border-muted-foreground/30 group-hover:border-muted-foreground/50",
          )}
        >
          {selected && (
            <motion.span
              className="bg-primary h-2 w-2 rounded-full"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", bounce: 0.3, duration: 0.3 }}
            />
          )}
        </span>
        <span
          className={cn(
            "text-sm font-medium transition-colors",
            selected
              ? "text-primary"
              : "text-muted-foreground group-hover:text-foreground",
          )}
        >
          {label}
        </span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Input class
// ---------------------------------------------------------------------------

const inputCls =
  "w-full rounded-md border border-border bg-muted/60 px-2.5 py-1.5 text-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20";
const colorCls =
  "h-8 w-full rounded-md border border-border cursor-pointer bg-transparent";

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

interface ExportDocxDialogProps {
  docId: string | null;
  docTitle: string;
  // ponytail: content-mode fallback — personal/thread files have a synthetic id
  // ({thread_id}/{rel_path}, not a UUID), so they can't hit /documents/{id}/export.
  // When docId is null but content is provided, POST to /export-content instead.
  content?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ExportDocxDialog({
  docId,
  docTitle,
  content,
  open,
  onOpenChange,
}: ExportDocxDialogProps) {
  // ── State ──
  const [activeSection, setActiveSection] = useState("template");
  const [templates, setTemplates] = useState<LayoutTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] =
    useState<string>("__default__");
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [importing, setImporting] = useState(false);

  const [pageSettings, setPageSettings] = useState<PageSettings>({
    ...DEFAULT_PAGE_SETTINGS,
  });
  const [bodyStyles, setBodyStyles] = useState<BodyStyles>({
    ...DEFAULT_BODY_STYLES,
  });
  const [headingStyles, setHeadingStyles] = useState<HeadingStyle[]>(
    DEFAULT_HEADING_STYLES.map((h) => ({ ...h })),
  );
  const [tableStyles, setTableStyles] = useState<TableStyles>({
    ...DEFAULT_TABLE_STYLES,
  });
  const [figureStyles, setFigureStyles] = useState<FigureStyles>({
    ...DEFAULT_FIGURE_STYLES,
  });
  const [headerFooter, setHeaderFooter] = useState<HeaderFooter>({
    ...DEFAULT_HEADER_FOOTER,
  });
  const [watermark, setWatermark] = useState<WatermarkType | "none">("none");
  const [withToc, setWithToc] = useState(false);
  const [tocDepth, setTocDepth] = useState(3);
  // EAI-CUSTOM: 封面 = 排版模版同款三态（template 5 开关 / master 槽位 / elements 元素）
  const [coverTemplate, setCoverTemplate] = useState<CoverTemplate | null>(
    null,
  );
  const [coverMaster, setCoverMaster] = useState<CoverMaster | null>(null);
  const [coverElements, setCoverElements] = useState<Cover | null>(null);

  const [saveAsTemplate, setSaveAsTemplate] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [exporting, setExporting] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // ── Load templates ──
  useEffect(() => {
    if (!open) return;
    setLoadingTemplates(true);
    void import("@/extensions/output/api").then(({ outputApi }) => {
      outputApi
        .listTemplates()
        .then((t) => setTemplates(t))
        .catch(() => setTemplates([]))
        .finally(() => setLoadingTemplates(false));
    });
  }, [open]);

  // ── Apply template ──
  const applyTemplate = useCallback((tpl: LayoutTemplate | null) => {
    if (!tpl) {
      setPageSettings({ ...DEFAULT_PAGE_SETTINGS });
      setBodyStyles({ ...DEFAULT_BODY_STYLES });
      setHeadingStyles(DEFAULT_HEADING_STYLES.map((h) => ({ ...h })));
      setTableStyles({ ...DEFAULT_TABLE_STYLES });
      setFigureStyles({ ...DEFAULT_FIGURE_STYLES });
      setHeaderFooter({ ...DEFAULT_HEADER_FOOTER });
      setCoverElements(null);
      setCoverMaster(null);
      setCoverTemplate(null);
      return;
    }
    setPageSettings(tpl.pageSettings ?? { ...DEFAULT_PAGE_SETTINGS });
    setBodyStyles(tpl.bodyStyles ?? { ...DEFAULT_BODY_STYLES });
    setHeadingStyles(
      tpl.headingStyles?.length
        ? tpl.headingStyles.map((h) => ({ ...h }))
        : DEFAULT_HEADING_STYLES.map((h) => ({ ...h })),
    );
    setTableStyles(tpl.tableStyles ?? { ...DEFAULT_TABLE_STYLES });
    setFigureStyles(tpl.figureStyles ?? { ...DEFAULT_FIGURE_STYLES });
    setHeaderFooter(tpl.headerFooter ?? { ...DEFAULT_HEADER_FOOTER });
    // EAI-CUSTOM: 模板封面数据（elements/master/template 三态）随模板一并带入，
    // 避免"选了排版模板但封面仍需手动建"。
    setCoverElements(tpl.coverElements ?? null);
    setCoverMaster(tpl.coverMaster ?? null);
    setCoverTemplate(tpl.coverTemplate ?? null);
  }, []);

  const handleTemplateChange = useCallback(
    (id: string) => {
      setSelectedTemplateId(id);
      if (id === "__default__") {
        applyTemplate(null);
      } else {
        const tpl = templates.find((t) => t.id === id);
        if (tpl) applyTemplate(tpl);
      }
    },
    [templates, applyTemplate],
  );

  // ── Import layout ──
  const handleImportLayout = useCallback(async () => {
    fileInputRef.current?.click();
  }, []);

  const handleFileSelected = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setImporting(true);
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/api/extensions/docmgr/import-layout", {
          method: "POST",
          body: form,
          credentials: "include",
          headers: {
            "X-CSRF-Token":
              document.cookie
                .split(";")
                .map((c) => c.trim())
                .find((c) => c.startsWith("csrf_token="))
                ?.split("=")[1] ?? "",
          },
        });
        if (!res.ok) throw new Error("导入失败");
        const data = await res.json();
        // Apply imported layout
        if (data.page_settings)
          setPageSettings(data.page_settings as PageSettings);
        if (data.body_styles) setBodyStyles(data.body_styles as BodyStyles);
        if (data.heading_styles)
          setHeadingStyles(
            (data.heading_styles as HeadingStyle[]).map((h) => ({ ...h })),
          );
        if (data.table_styles) setTableStyles(data.table_styles as TableStyles);
        if (data.figure_styles)
          setFigureStyles(data.figure_styles as FigureStyles);
        if (data.header_footer)
          setHeaderFooter(data.header_footer as HeaderFooter);
        setSelectedTemplateId("__imported__");
        toast.success("已从文档导入排版设置");
      } catch {
        toast.error("无法从该文件提取排版信息，请确保为 .docx 格式");
      } finally {
        setImporting(false);
        // Reset file input
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [],
  );

  // ── Reset ──
  const handleReset = useCallback(() => {
    setSelectedTemplateId("__default__");
    applyTemplate(null);
  }, [applyTemplate]);

  // ── Scroll spy ──
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const id = entry.target.getAttribute("data-section");
            if (id) setActiveSection(id);
          }
        }
      },
      { root: container, rootMargin: "-10% 0px -70% 0px" },
    );
    const els = container.querySelectorAll("[data-section]");
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [open]);

  const scrollToSection = useCallback((id: string) => {
    setActiveSection(id);
    sectionRefs.current[id]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, []);

  // ── Export ──
  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      // Save as template if checked
      if (saveAsTemplate && templateName.trim()) {
        const { outputApi } = await import("@/extensions/output/api");
        // EAI-CUSTOM: 封面三态原样入库（5 开关 / 母版槽位 / 元素），不再做预设字段映射
        await outputApi.createTemplate({
          name: templateName.trim(),
          reportType: "general",
          pageSettings,
          bodyStyles,
          headingStyles,
          tableStyles,
          figureStyles,
          headerFooter,
          referenceStyle: "gb7714",
          coverTemplate: normalizeCoverTemplate(coverTemplate),
          coverMaster,
          coverElements: normalizeCoverElements(coverElements),
          tocSettings: withToc
            ? { maxDepth: tocDepth, showPageNumbers: true, leaderDots: true }
            : null,
          appendixRules: null,
        });
      }

      // Build layout_template for backend (EAI-CUSTOM: 含完整封面模型，generate_docx_simple 消费)
      const layoutTemplate = {
        page_settings: pageSettings,
        body_styles: bodyStyles,
        heading_styles: headingStyles,
        table_styles: tableStyles,
        figure_styles: figureStyles,
        header_footer: headerFooter,
        ...(coverElements && { cover_elements: coverElements }),
        ...(coverMaster && { cover_master: coverMaster }),
        ...(coverTemplate && { cover_template: coverTemplate }),
      };

      // Personal/thread files (docId null) → content-based endpoint; else by document id.
      const useContent = !docId && content !== undefined;
      const exportUrl = useContent
        ? `/api/extensions/docmgr/export-content`
        : `/api/extensions/docmgr/documents/${docId}/export`;
      const payload = useContent
        ? {
            content: content ?? "",
            format: "docx",
            layout_template: layoutTemplate,
            watermark: watermark === "none" ? null : watermark,
            filename: docTitle,
            with_toc: withToc,
            toc_depth: tocDepth,
          }
        : {
            format: "docx",
            layout_template: layoutTemplate,
            watermark: watermark === "none" ? null : watermark,
            with_toc: withToc,
            toc_depth: tocDepth,
          };
      const res = await fetch(exportUrl, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token":
            document.cookie
              .split(";")
              .map((c) => c.trim())
              .find((c) => c.startsWith("csrf_token="))
              ?.split("=")[1] ?? "",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.text().catch(() => "");
        throw new Error(err || `导出失败 (${res.status})`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${docTitle}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      onOpenChange(false);
      toast.success("Word 文档导出成功");
    } catch (e) {
      toast.error(`导出失败: ${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setExporting(false);
    }
  }, [
    docId,
    docTitle,
    content,
    saveAsTemplate,
    templateName,
    pageSettings,
    bodyStyles,
    headingStyles,
    tableStyles,
    figureStyles,
    headerFooter,
    watermark,
    withToc,
    tocDepth,
    coverTemplate,
    coverMaster,
    coverElements,
    onOpenChange,
  ]);

  // ── Heading helpers ──
  const updateHeading = (
    index: number,
    field: keyof HeadingStyle,
    value: string | number,
  ) => {
    setHeadingStyles((prev) =>
      prev.map((h, i) => (i === index ? { ...h, [field]: value } : h)),
    );
  };
  const addHeadingLevel = () => {
    const lastLevel = headingStyles[headingStyles.length - 1]?.level ?? 0;
    setHeadingStyles((prev) => [
      ...prev,
      {
        level: lastLevel + 1,
        fontFamily: "黑体",
        fontSize: 12,
        fontWeight: 700,
        color: "#333333",
        numbering: "none",
      },
    ]);
  };
  const removeHeadingLevel = (index: number) => {
    setHeadingStyles((prev) => prev.filter((_, i) => i !== index));
  };

  if (!open) return null;

  // ── Render ──
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        onClick={(e) => e.target === e.currentTarget && onOpenChange(false)}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.97, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.97, y: 8 }}
          transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="bg-background border-border/60 flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border shadow-2xl"
        >
          {/* ── Header ── */}
          <div className="border-border/60 bg-muted/20 flex shrink-0 items-center justify-between border-b px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="bg-primary/10 flex h-9 w-9 items-center justify-center rounded-xl">
                <Download className="text-primary h-4 w-4" />
              </div>
              <div>
                <h2 className="text-foreground text-base font-semibold">
                  导出 Word 文档
                </h2>
                <p className="text-muted-foreground mt-0.5 max-w-md truncate text-xs">
                  {docTitle}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="text-muted-foreground hover:bg-muted hover:text-foreground flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* ── Body: sidebar + form ── */}
          <div className="flex min-h-0 flex-1">
            {/* Left nav */}
            <nav className="border-border/60 bg-muted/10 w-44 shrink-0 space-y-0.5 overflow-y-auto border-r px-2 py-3">
              {SECTIONS.map((sec) => (
                <button
                  key={sec.id}
                  type="button"
                  onClick={() => scrollToSection(sec.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-all",
                    activeSection === sec.id
                      ? "bg-primary/8 text-primary font-medium shadow-sm"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <span className="shrink-0 opacity-70">{sec.icon}</span>
                  {sec.label}
                </button>
              ))}
            </nav>

            {/* Right form */}
            <div
              ref={scrollContainerRef}
              className="flex-1 space-y-6 overflow-y-auto px-6 py-5"
            >
              {/* Section: Template selection */}
              <div
                data-section="template"
                ref={(el) => {
                  sectionRefs.current.template = el;
                }}
              >
                <SectionTitle icon={<LayoutTemplateIcon className="h-4 w-4" />}>
                  排版模板
                </SectionTitle>
                <div className="mt-3 space-y-3">
                  <div>
                    <FieldLabel>选择排版模板</FieldLabel>
                    <Select
                      value={selectedTemplateId}
                      onValueChange={handleTemplateChange}
                    >
                      <SelectTrigger className="border-border bg-muted/60 h-9 w-full rounded-lg border text-sm">
                        <SelectValue placeholder="选择模板...">
                          {selectedTemplateId === "__default__"
                            ? "使用默认排版"
                            : selectedTemplateId === "__imported__"
                              ? "已导入排版"
                              : (templates.find(
                                  (t) => t.id === selectedTemplateId,
                                )?.name ?? "选择模板...")}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="z-[9999]">
                        <SelectItem value="__default__">
                          使用默认排版
                        </SelectItem>
                        {templates.map((t) => (
                          <SelectItem key={t.id} value={t.id}>
                            {t.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {loadingTemplates && (
                      <p className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
                        <Loader2 className="h-3 w-3 animate-spin" /> 加载模板...
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleImportLayout}
                      disabled={importing}
                      className="gap-1.5"
                    >
                      {importing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <FileUp className="h-3.5 w-3.5" />
                      )}
                      {importing ? "导入中..." : "导入排版"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleReset}
                      className="gap-1.5"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      重置
                    </Button>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".docx"
                    onChange={handleFileSelected}
                    className="hidden"
                  />
                </div>
              </div>

              {/* Divider */}
              <Divider />

              {/* Section: Page settings */}
              <div
                data-section="page"
                ref={(el) => {
                  sectionRefs.current.page = el;
                }}
              >
                <SectionTitle icon={<span className="text-xs">⬜</span>}>
                  页面设置
                </SectionTitle>
                <div className="mt-3 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <FieldLabel>纸张尺寸</FieldLabel>
                      <Select
                        value={pageSettings.paperSize}
                        onValueChange={(v) =>
                          setPageSettings({
                            ...pageSettings,
                            paperSize: v as PageSettings["paperSize"],
                          })
                        }
                      >
                        <SelectTrigger className="h-8 w-full text-sm">
                          <SelectValue>
                            {PAPER_OPTIONS.find(
                              (o) => o.value === pageSettings.paperSize,
                            )?.label ?? pageSettings.paperSize}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent className="z-[9999]">
                          {PAPER_OPTIONS.map((o) => (
                            <SelectItem key={o.value} value={o.value}>
                              {o.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <FieldLabel>方向</FieldLabel>
                      <Select
                        value={pageSettings.orientation}
                        onValueChange={(v) =>
                          setPageSettings({
                            ...pageSettings,
                            orientation: v as PageSettings["orientation"],
                          })
                        }
                      >
                        <SelectTrigger className="h-8 w-full text-sm">
                          <SelectValue>
                            {pageSettings.orientation === "portrait"
                              ? "纵向"
                              : "横向"}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent className="z-[9999]">
                          {ORIENTATION_OPTIONS.map((o) => (
                            <SelectItem key={o.value} value={o.value}>
                              {o.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div>
                    <FieldLabel>页边距 (cm)</FieldLabel>
                    <div className="mt-1 grid grid-cols-4 gap-2">
                      {(
                        [
                          ["上", "marginTop"],
                          ["下", "marginBottom"],
                          ["左", "marginLeft"],
                          ["右", "marginRight"],
                        ] as const
                      ).map(([label, key]) => (
                        <div key={key} className="text-center">
                          <span className="text-muted-foreground text-[10px]">
                            {label}
                          </span>
                          <input
                            type="number"
                            step="0.01"
                            value={pageSettings[key]}
                            onChange={(e) =>
                              setPageSettings({
                                ...pageSettings,
                                [key]: parseFloat(e.target.value) || 0,
                              })
                            }
                            className={cn(
                              inputCls,
                              "mt-0.5 text-center text-xs",
                            )}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <Divider />

              {/* Section: Body styles */}
              <div
                data-section="body"
                ref={(el) => {
                  sectionRefs.current.body = el;
                }}
              >
                <SectionTitle
                  icon={<span className="text-xs font-bold">T</span>}
                >
                  正文样式
                </SectionTitle>
                <div className="mt-3 grid grid-cols-3 gap-3">
                  <div>
                    <FieldLabel>字体</FieldLabel>
                    <input
                      type="text"
                      value={bodyStyles.fontFamily}
                      onChange={(e) =>
                        setBodyStyles({
                          ...bodyStyles,
                          fontFamily: e.target.value,
                        })
                      }
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                  <div>
                    <FieldLabel>字号 (pt)</FieldLabel>
                    <input
                      type="number"
                      value={bodyStyles.fontSize}
                      onChange={(e) =>
                        setBodyStyles({
                          ...bodyStyles,
                          fontSize: parseInt(e.target.value) || 12,
                        })
                      }
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                  <div>
                    <FieldLabel>行高</FieldLabel>
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
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                  <div>
                    <FieldLabel>段落间距 (pt)</FieldLabel>
                    <input
                      type="number"
                      value={bodyStyles.paragraphSpacing}
                      onChange={(e) =>
                        setBodyStyles({
                          ...bodyStyles,
                          paragraphSpacing: parseInt(e.target.value) || 0,
                        })
                      }
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                  <div>
                    <FieldLabel>首行缩进 (字符)</FieldLabel>
                    <input
                      type="number"
                      value={bodyStyles.firstLineIndent}
                      onChange={(e) =>
                        setBodyStyles({
                          ...bodyStyles,
                          firstLineIndent: parseInt(e.target.value) || 0,
                        })
                      }
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                </div>
              </div>

              <Divider />

              {/* Section: Heading styles */}
              <div
                data-section="headings"
                ref={(el) => {
                  sectionRefs.current.headings = el;
                }}
              >
                <SectionTitle
                  icon={<span className="text-xs font-bold">H</span>}
                >
                  标题样式
                </SectionTitle>
                <div className="mt-3 space-y-2">
                  {headingStyles.map((h, i) => (
                    <div
                      key={i}
                      className="border-border/50 bg-muted/20 flex items-center gap-2 rounded-lg border p-2.5"
                    >
                      <span className="bg-primary/10 text-primary flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-bold">
                        {h.level}
                      </span>
                      <div className="grid flex-1 grid-cols-5 gap-2">
                        <input
                          type="text"
                          value={h.fontFamily}
                          onChange={(e) =>
                            updateHeading(i, "fontFamily", e.target.value)
                          }
                          placeholder="字体"
                          className={cn(inputCls, "h-7 text-xs")}
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
                          className={cn(inputCls, "h-7 text-xs")}
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
                          className={cn(inputCls, "h-7 text-xs")}
                        />
                        <input
                          type="color"
                          value={h.color}
                          onChange={(e) =>
                            updateHeading(i, "color", e.target.value)
                          }
                          className="border-border h-7 cursor-pointer rounded border bg-transparent"
                        />
                        <Select
                          value={h.numbering}
                          onValueChange={(v) =>
                            updateHeading(i, "numbering", v)
                          }
                        >
                          <SelectTrigger className="h-7 w-full text-xs">
                            <SelectValue>
                              {HEADING_NUMBERING_OPTIONS.find(
                                (o) => o.value === h.numbering,
                              )?.label ?? "无"}
                            </SelectValue>
                          </SelectTrigger>
                          <SelectContent className="z-[9999]">
                            {HEADING_NUMBERING_OPTIONS.map((o) => (
                              <SelectItem key={o.value} value={o.value}>
                                {o.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeHeadingLevel(i)}
                        className="text-destructive/60 hover:text-destructive shrink-0 text-xs transition-colors"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={addHeadingLevel}
                    className="text-primary/80 hover:text-primary text-xs transition-colors"
                  >
                    + 添加标题级别
                  </button>
                </div>
              </div>

              <Divider />

              {/* Section: Table styles */}
              <div
                data-section="table"
                ref={(el) => {
                  sectionRefs.current.table = el;
                }}
              >
                <SectionTitle icon={<span className="text-xs">▦</span>}>
                  表格样式
                </SectionTitle>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <FieldLabel>表头背景色</FieldLabel>
                    <input
                      type="color"
                      value={tableStyles.headerBg}
                      onChange={(e) =>
                        setTableStyles({
                          ...tableStyles,
                          headerBg: e.target.value,
                        })
                      }
                      className={colorCls}
                    />
                  </div>
                  <div>
                    <FieldLabel>表头字色</FieldLabel>
                    <input
                      type="color"
                      value={tableStyles.headerColor}
                      onChange={(e) =>
                        setTableStyles({
                          ...tableStyles,
                          headerColor: e.target.value,
                        })
                      }
                      className={colorCls}
                    />
                  </div>
                  <div>
                    <FieldLabel>边框色</FieldLabel>
                    <input
                      type="color"
                      value={tableStyles.borderColor}
                      onChange={(e) =>
                        setTableStyles({
                          ...tableStyles,
                          borderColor: e.target.value,
                        })
                      }
                      className={colorCls}
                    />
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <StyledCheckbox
                        checked={tableStyles.stripeRows}
                        onChange={(v) =>
                          setTableStyles({ ...tableStyles, stripeRows: v })
                        }
                      />
                      斑马纹行
                    </label>
                  </div>
                </div>
              </div>

              <Divider />

              {/* Section: Figure styles */}
              <div
                data-section="figure"
                ref={(el) => {
                  sectionRefs.current.figure = el;
                }}
              >
                <SectionTitle icon={<span className="text-xs">▣</span>}>
                  图表样式
                </SectionTitle>
                <div className="mt-3 grid grid-cols-3 gap-3">
                  <div>
                    <FieldLabel>标题位置</FieldLabel>
                    <Select
                      value={figureStyles.captionPosition}
                      onValueChange={(v) =>
                        setFigureStyles({
                          ...figureStyles,
                          captionPosition: v as "above" | "below",
                        })
                      }
                    >
                      <SelectTrigger className="h-8 w-full text-sm">
                        <SelectValue>
                          {figureStyles.captionPosition === "above"
                            ? "图上方"
                            : "图下方"}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="z-[9999]">
                        <SelectItem value="above">图上方</SelectItem>
                        <SelectItem value="below">图下方</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <FieldLabel>编号方式</FieldLabel>
                    <Select
                      value={figureStyles.numbering}
                      onValueChange={(v) =>
                        setFigureStyles({
                          ...figureStyles,
                          numbering: v as "chapter" | "continuous",
                        })
                      }
                    >
                      <SelectTrigger className="h-8 w-full text-sm">
                        <SelectValue>
                          {figureStyles.numbering === "chapter"
                            ? "按章节"
                            : "连续编号"}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="z-[9999]">
                        <SelectItem value="chapter">按章节</SelectItem>
                        <SelectItem value="continuous">连续编号</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <StyledCheckbox
                        checked={figureStyles.showSource}
                        onChange={(v) =>
                          setFigureStyles({ ...figureStyles, showSource: v })
                        }
                      />
                      显示来源
                    </label>
                  </div>
                </div>
              </div>

              <Divider />

              {/* Section: Header & Footer */}
              <div
                data-section="headerFooter"
                ref={(el) => {
                  sectionRefs.current.headerFooter = el;
                }}
              >
                <SectionTitle icon={<span className="text-xs">☰</span>}>
                  页眉页脚
                </SectionTitle>
                <div className="mt-3 space-y-3">
                  <div>
                    <FieldLabel>页眉文本</FieldLabel>
                    <input
                      type="text"
                      value={headerFooter.headerText}
                      onChange={(e) =>
                        setHeaderFooter({
                          ...headerFooter,
                          headerText: e.target.value,
                        })
                      }
                      placeholder="留空则不显示"
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                  <div>
                    <FieldLabel>页脚文本</FieldLabel>
                    <input
                      type="text"
                      value={headerFooter.footerText}
                      onChange={(e) =>
                        setHeaderFooter({
                          ...headerFooter,
                          footerText: e.target.value,
                        })
                      }
                      placeholder="留空则不显示"
                      className={cn(inputCls, "h-8")}
                    />
                  </div>
                  <div className="flex gap-6">
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <StyledCheckbox
                        checked={headerFooter.showPageNumber}
                        onChange={(v) =>
                          setHeaderFooter({
                            ...headerFooter,
                            showPageNumber: v,
                          })
                        }
                      />
                      显示页码
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <StyledCheckbox
                        checked={headerFooter.showLogo}
                        onChange={(v) =>
                          setHeaderFooter({ ...headerFooter, showLogo: v })
                        }
                      />
                      显示 Logo
                    </label>
                  </div>
                </div>
              </div>

              <Divider />

              {/* Section: Watermark */}
              <div
                data-section="watermark"
                ref={(el) => {
                  sectionRefs.current.watermark = el;
                }}
              >
                <SectionTitle icon={<Sparkles className="h-4 w-4" />}>
                  水印设置
                </SectionTitle>
                <div className="mt-3">
                  <div className="grid grid-cols-2 gap-2">
                    {WATERMARK_OPTIONS.map((opt) => (
                      <RadioCard
                        key={opt.value}
                        label={opt.label}
                        selected={watermark === opt.value}
                        onClick={() => setWatermark(opt.value)}
                      />
                    ))}
                  </div>
                </div>
              </div>

              {/* Section: Cover */}
              <div
                data-section="cover"
                ref={(el) => {
                  sectionRefs.current.cover = el;
                }}
              >
                <SectionTitle icon={<span className="text-[10px]">📄</span>}>
                  封面
                </SectionTitle>
                <div className="mt-3 space-y-3">
                  <CoverConfigSection
                    value={{
                      template: coverTemplate,
                      master: coverMaster,
                      elements: coverElements,
                    }}
                    onChange={({ template, master, elements }) => {
                      setCoverTemplate(template);
                      setCoverMaster(master);
                      setCoverElements(elements);
                    }}
                  />
                </div>
              </div>

              {/* Section: Table of Contents */}
              <div
                data-section="toc"
                ref={(el) => {
                  sectionRefs.current.toc = el;
                }}
              >
                <SectionTitle icon={<List className="h-4 w-4" />}>
                  目录设置
                </SectionTitle>
                <div className="mt-3 flex items-center gap-4">
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <StyledCheckbox checked={withToc} onChange={setWithToc} />
                    包含目录
                  </label>
                  <label
                    className={cn(
                      "flex items-center gap-1.5 text-sm transition-opacity",
                      !withToc && "pointer-events-none opacity-40",
                    )}
                  >
                    收录到
                    <select
                      value={tocDepth}
                      disabled={!withToc}
                      onChange={(e) => setTocDepth(Number(e.target.value))}
                      className={cn(inputCls, "h-7 w-16 text-xs")}
                    >
                      {[1, 2, 3, 4].map((n) => (
                        <option key={n} value={n}>
                          {n} 级
                        </option>
                      ))}
                    </select>
                    级标题
                  </label>
                </div>
              </div>

              {/* Bottom spacer */}
              <div className="h-4" />
            </div>
          </div>

          {/* ── Footer ── */}
          <div className="border-border/60 bg-muted/10 shrink-0 border-t px-6 py-3">
            <div className="flex items-center justify-between">
              {/* Save as template */}
              <div className="flex items-center gap-2">
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <StyledCheckbox
                    checked={saveAsTemplate}
                    onChange={(v) => setSaveAsTemplate(v)}
                  />
                  保存为排版模板
                </label>
                {saveAsTemplate && (
                  <input
                    type="text"
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    placeholder="模板名称"
                    className={cn(inputCls, "h-7 w-40 text-xs")}
                    autoFocus
                  />
                )}
              </div>
              {/* Actions */}
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenChange(false)}
                >
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={handleExport}
                  disabled={exporting}
                  className="gap-1.5"
                >
                  {exporting ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> 导出中...
                    </>
                  ) : (
                    <>
                      <Download className="h-3.5 w-3.5" /> 导出 Word
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function SectionTitle({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground">{icon}</span>
      <h3 className="text-foreground text-sm font-semibold">{children}</h3>
    </div>
  );
}

function Divider() {
  return <div className="border-border/40 border-t" />;
}
