"use client";

import {
  X,
  ChevronRight,
  ChevronDown,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Download,
  Send,
} from "lucide-react";
import React, { useState, useEffect } from "react";

import { kfApi } from "@/extensions/api";
import type {
  ExtractionTaskResponse,
  TemplateResult,
  TemplateDocument,
  TemplateSection,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface Props {
  task: ExtractionTaskResponse;
  result: TemplateResult | null;
  onClose: () => void;
  onExport: () => void;
}

function SectionNode({
  section,
  depth = 0,
}: {
  section: TemplateSection;
  depth?: number;
}) {
  const [expanded, setExpanded] = useState(depth === 0);
  const hasChildren = section.children && section.children.length > 0;

  const scoreColor = (score?: number) => {
    if (!score) return "text-muted-foreground";
    if (score >= 85) return "text-emerald-500";
    if (score >= 60) return "text-amber-500";
    return "text-red-500";
  };

  return (
    <div>
      <div
        className={cn(
          "hover:bg-muted/50 flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 transition-colors",
          depth > 0 && "ml-4",
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => hasChildren && setExpanded(!expanded)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="hover:bg-accent rounded p-0.5 transition-colors"
          >
            {expanded ? (
              <ChevronDown className="text-muted-foreground h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="text-muted-foreground h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <div className="w-4" />
        )}

        <span className="text-foreground flex-1 truncate text-sm font-medium">
          {section.title}
        </span>

        {section.completeness_score != null && (
          <span
            className={cn(
              "text-xs font-medium tabular-nums",
              scoreColor(section.completeness_score),
            )}
          >
            {section.completeness_score}%
          </span>
        )}

        {section.completeness_score != null &&
          section.completeness_score >= 85 && (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
          )}
        {section.completeness_score != null &&
          section.completeness_score < 60 && (
            <AlertCircle className="h-3.5 w-3.5 text-red-500" />
          )}
      </div>

      {expanded && hasChildren && (
        <div className="border-border/50 ml-4 border-l">
          {section.children!.map((child) => (
            <SectionNode key={child.id} section={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExtractionResultModal({
  task,
  result,
  onClose,
  onExport,
}: Props) {
  const [template, setTemplate] = useState<TemplateDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    if (!result?.template_id) {
      setLoading(false);
      return;
    }
    kfApi
      .getTemplate(result.template_id)
      .then((t) => {
        setTemplate(t);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [result?.template_id]);

  const handlePublish = async () => {
    if (!result?.template_id) return;
    setPublishing(true);
    try {
      await kfApi.publishTemplate(result.template_id);
      onClose();
    } catch {
      /* ignore */
    }
    setPublishing(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="border-border flex shrink-0 items-center justify-between border-b px-6 py-4">
          <div>
            <h3 className="text-foreground text-lg font-semibold">
              抽取结果: {result?.name ?? task.name}{" "}
              {result?.version && `(${result.version})`}
            </h3>
            {result && (
              <p className="text-muted-foreground mt-0.5 text-sm">
                {result.chapters}章 / {result.sections}节 · 完整度{" "}
                {result.completeness_score}%
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {result?.template_id && (
              <>
                <button
                  onClick={onExport}
                  className="border-border hover:bg-muted/50 flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors"
                >
                  <Download className="h-4 w-4" /> 导出
                </button>
                <button
                  disabled={publishing}
                  onClick={handlePublish}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors disabled:opacity-50"
                >
                  {publishing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  发布
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="hover:bg-accent rounded-lg p-1.5 transition-colors"
            >
              <X className="text-muted-foreground h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="text-muted-foreground flex items-center justify-center py-20">
              <Loader2 className="mr-2 h-6 w-6 animate-spin" />
              加载模板详情...
            </div>
          ) : !template ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center py-20">
              <AlertCircle className="mb-3 h-10 w-10 opacity-40" />
              <p>无法加载模板详情</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* 统计信息 */}
              <div className="bg-muted/30 border-border flex items-center gap-6 rounded-xl border p-4">
                <div className="text-center">
                  <div className="text-primary text-2xl font-bold">
                    {result?.chapters ?? 0}
                  </div>
                  <div className="text-muted-foreground text-xs">一级章节</div>
                </div>
                <div className="text-center">
                  <div className="text-primary text-2xl font-bold">
                    {result?.sections ?? 0}
                  </div>
                  <div className="text-muted-foreground text-xs">总节数</div>
                </div>
                <div className="text-center">
                  <div
                    className={cn(
                      "text-2xl font-bold",
                      (result?.completeness_score ?? 0) >= 85
                        ? "text-emerald-500"
                        : (result?.completeness_score ?? 0) >= 60
                          ? "text-amber-500"
                          : "text-red-500",
                    )}
                  >
                    {result?.completeness_score ?? 0}%
                  </div>
                  <div className="text-muted-foreground text-xs">完整度</div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <span
                    className={cn(
                      "rounded-full border px-2 py-1 text-xs font-medium",
                      template.status === "published"
                        ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-500"
                        : "border-amber-500/20 bg-amber-500/10 text-amber-500",
                    )}
                  >
                    {template.status === "published" ? "已发布" : "草稿"}
                  </span>
                </div>
              </div>

              {/* 章节树 */}
              <div className="space-y-1">
                <h4 className="text-foreground mb-2 text-sm font-semibold">
                  章节结构
                </h4>
                {template.root_sections.map((section) => (
                  <SectionNode key={section.id} section={section} />
                ))}
              </div>

              {/* 选中章节详情 */}
              {template.cross_section_rules &&
                template.cross_section_rules.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-foreground text-sm font-semibold">
                      跨章节规则
                    </h4>
                    {template.cross_section_rules.map((rule) => (
                      <div
                        key={rule.rule_id}
                        className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm"
                      >
                        <span className="font-medium text-amber-500">
                          {rule.description}
                        </span>
                        <div className="mt-1 text-xs text-amber-500/70">
                          涉及章节: {rule.source_sections.join(", ")} →{" "}
                          {rule.target_sections.join(", ")}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-border flex shrink-0 justify-end border-t px-6 py-4">
          <button
            onClick={onClose}
            className="border-border hover:bg-muted/50 rounded-lg border px-4 py-2 text-sm transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
