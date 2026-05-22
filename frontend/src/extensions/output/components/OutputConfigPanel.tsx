"use client";

import { Download, Loader2 } from "lucide-react";
import React, { useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import type { GenerateOutputRequest, LayoutTemplate, OutputFormat, WatermarkType } from "@/extensions/output/types";
import { WATERMARK_LABELS } from "@/extensions/output/types";

const FORMAT_OPTIONS = [
  { value: "docx", label: "Word 文档" },
  { value: "pdf", label: "PDF 文档" },
];

const WATERMARK_OPTIONS = [
  { value: "draft", label: WATERMARK_LABELS.draft },
  { value: "review", label: WATERMARK_LABELS.review },
  { value: "final", label: WATERMARK_LABELS.final },
];

interface OutputConfigPanelProps {
  templates: LayoutTemplate[];
  onGenerate: (req: GenerateOutputRequest) => void;
  loading: boolean;
}

export function OutputConfigPanel({ templates, onGenerate, loading }: OutputConfigPanelProps) {
  const [projectId, setProjectId] = useState("");
  const [format, setFormat] = useState<OutputFormat>("docx");
  const [templateId, setTemplateId] = useState("");
  const [watermark, setWatermark] = useState<WatermarkType>("draft");

  const templateOptions = [
    { value: "", label: "请选择排版模板" },
    ...templates.map((t) => ({ value: t.id, label: t.name })),
  ];

  const canGenerate = projectId.trim() !== "" && templateId !== "";

  const handleGenerate = () => {
    if (!canGenerate) return;
    onGenerate({
      projectId: projectId.trim(),
      format,
      layoutTemplateId: templateId,
      watermark,
    });
  };

  return (
    <div className="space-y-6">
      <h3 className="text-base font-medium text-foreground">生成配置</h3>

      <div className="space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        {/* Project ID */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">项目 ID</label>
          <input
            type="text"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="请输入项目 ID"
            className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm outline-none transition-all focus:border-primary focus:ring-2 focus:ring-primary/20"
          />
        </div>

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
