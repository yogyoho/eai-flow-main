"use client";

import { Download, FileUp, FolderOpen, Loader2, X } from "lucide-react";
import React, { useCallback, useRef, useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import type { GenerateOutputRequest, GenerateSource, LayoutTemplate, OutputFormat, WatermarkType } from "@/extensions/output/types";
import { WATERMARK_LABELS } from "@/extensions/output/types";
import { cn } from "@/lib/utils";

const FORMAT_OPTIONS = [
  { value: "docx", label: "Word 文档" },
  { value: "pdf", label: "PDF 文档" },
];

const WATERMARK_OPTIONS = [
  { value: "draft", label: WATERMARK_LABELS.draft },
  { value: "review", label: WATERMARK_LABELS.review },
  { value: "final", label: WATERMARK_LABELS.final },
];

const SOURCE_OPTIONS = [
  { value: "project", label: "项目报告" },
  { value: "markdown", label: "Markdown 文件" },
];

interface OutputConfigPanelProps {
  templates: LayoutTemplate[];
  onGenerate: (req: GenerateOutputRequest) => void;
  loading: boolean;
}

export function OutputConfigPanel({ templates, onGenerate, loading }: OutputConfigPanelProps) {
  const [source, setSource] = useState<GenerateSource>("project");
  const [projectId, setProjectId] = useState("");
  const [markdownFile, setMarkdownFile] = useState<File | null>(null);
  const [format, setFormat] = useState<OutputFormat>("docx");
  const [templateId, setTemplateId] = useState("");
  const [watermark, setWatermark] = useState<WatermarkType>("draft");
  const [dragOver, setDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const templateOptions = templates.map((t) => ({ value: t.id, label: t.name }));

  const canGenerate =
    templateId !== "" &&
    (source === "project" ? projectId.trim() !== "" : markdownFile !== null);

  const handleGenerate = () => {
    if (!canGenerate) return;
    onGenerate({
      source,
      projectId: source === "project" ? projectId.trim() : undefined,
      markdownFile: source === "markdown" ? markdownFile ?? undefined : undefined,
      format,
      layoutTemplateId: templateId,
      watermark,
    });
  };

  const handleFileSelect = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".md") && !file.name.endsWith(".markdown") && !file.type !== "text/markdown") {
      // Accept anyway — some systems don't set MIME for .md
    }
    setMarkdownFile(file);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const inputCls = "w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20";

  return (
    <div className="space-y-6">
      <h3 className="text-base font-medium text-foreground">生成配置</h3>

      <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        {/* Source mode toggle */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">内容来源</label>
          <AdminSelect
            value={source}
            onChange={(v) => setSource(v as GenerateSource)}
            options={SOURCE_OPTIONS}
            className="w-full"
          />
        </div>

        {/* Project ID (project mode) */}
        {source === "project" && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">项目 ID</label>
            <div className="relative">
              <FolderOpen className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                placeholder="请输入项目 ID"
                className={cn(inputCls, "pl-9")}
              />
            </div>
          </div>
        )}

        {/* Markdown upload (markdown mode) */}
        {source === "markdown" && (
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">Markdown 文件</label>
            {markdownFile ? (
              <div className="flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
                <FileUp className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{markdownFile.name}</p>
                  <p className="text-xs text-muted-foreground">{(markdownFile.size / 1024).toFixed(1)} KB</p>
                </div>
                <button
                  type="button"
                  onClick={() => setMarkdownFile(null)}
                  className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 transition-all",
                  dragOver
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/40 hover:bg-muted/50",
                )}
              >
                <FileUp className={cn("mb-3 h-8 w-8", dragOver ? "text-primary" : "text-muted-foreground")} />
                <p className="text-sm font-medium text-foreground">拖拽文件到此处或点击上传</p>
                <p className="mt-1 text-xs text-muted-foreground">支持 .md / .markdown 文件</p>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.markdown,text/markdown"
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files)}
            />
          </div>
        )}

        {/* Format */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">输出格式</label>
          <AdminSelect
            value={format}
            onChange={(v) => setFormat(v as OutputFormat)}
            options={FORMAT_OPTIONS}
            className="w-full"
          />
        </div>

        {/* Layout Template */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">排版模板</label>
          <AdminSelect
            value={templateId}
            onChange={setTemplateId}
            options={templateOptions}
            placeholder="请选择排版模板"
            className="w-full"
          />
        </div>

        {/* Watermark */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">水印类型</label>
          <AdminSelect
            value={watermark}
            onChange={(v) => setWatermark(v as WatermarkType)}
            options={WATERMARK_OPTIONS}
            className="w-full"
          />
        </div>
      </div>

      {/* Generate Button */}
      <button
        type="button"
        onClick={handleGenerate}
        disabled={!canGenerate || loading}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            生成中...
          </>
        ) : (
          <>
            <Download className="h-4 w-4" />
            生成报告
          </>
        )}
      </button>
    </div>
  );
}
