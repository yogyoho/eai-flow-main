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

function SectionNode({ section, depth = 0 }: { section: TemplateSection; depth?: number }) {
  const [expanded, setExpanded] = useState(depth === 0);
  const hasChildren = section.children && section.children.length > 0;

  const scoreColor = (score?: number) => {
    if (!score) return "text-muted-foreground";
    if (score >= 85) return "text-emerald-600";
    if (score >= 60) return "text-amber-600";
    return "text-red-600";
  };

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors",
          depth > 0 && "ml-4"
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => hasChildren && setExpanded(!expanded)}
      >
        {hasChildren ? (
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="p-0.5 hover:bg-accent rounded transition-colors"
          >
            {expanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
            )}
          </button>
        ) : (
          <div className="w-4" />
        )}

        <span className="text-sm font-medium text-foreground flex-1 truncate">
          {section.title}
        </span>

        {section.completeness_score != null && (
          <span className={cn("text-xs tabular-nums font-medium", scoreColor(section.completeness_score))}>
            {section.completeness_score}%
          </span>
        )}

        {section.completeness_score != null && section.completeness_score >= 85 && (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
        )}
        {section.completeness_score != null && section.completeness_score < 60 && (
          <AlertCircle className="w-3.5 h-3.5 text-red-500" />
        )}
      </div>

      {expanded && hasChildren && (
        <div className="border-l border-border/50 ml-4">
          {section.children!.map((child) => (
            <SectionNode key={child.id} section={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExtractionResultModal({ task, result, onClose, onExport }: Props) {
  const [template, setTemplate] = useState<TemplateDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    if (!result?.template_id) {
      setLoading(false);
      return;
    }
    kfApi.getTemplate(result.template_id)
      .then((t) => { setTemplate(t); setLoading(false); })
      .catch(() => { setLoading(false); });
  }, [result?.template_id]);

  const handlePublish = async () => {
    if (!result?.template_id) return;
    setPublishing(true);
    try {
      await kfApi.publishTemplate(result.template_id);
      onClose();
    } catch { /* ignore */ }
    setPublishing(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-border shrink-0">
          <div>
            <h3 className="text-lg font-semibold text-foreground">
              抽取结果: {result?.name || task.name} {result?.version && `(${result.version})`}
            </h3>
            {result && (
              <p className="text-sm text-muted-foreground mt-0.5">
                {result.chapters}章 / {result.sections}节 · 完整度 {result.completeness_score}%
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {result?.template_id && (
              <>
                <button
                  onClick={onExport}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <Download className="w-4 h-4" /> 导出
                </button>
                <button
                  disabled={publishing}
                  onClick={handlePublish}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
                >
                  {publishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  发布
                </button>
              </>
            )}
            <button onClick={onClose} className="p-1.5 hover:bg-accent rounded-lg transition-colors">
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              加载模板详情...
            </div>
          ) : !template ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <AlertCircle className="w-10 h-10 mb-3 opacity-40" />
              <p>无法加载模板详情</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* 统计信息 */}
              <div className="flex items-center gap-6 p-4 bg-muted/30 rounded-xl border border-border">
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary">{result?.chapters || 0}</div>
                  <div className="text-xs text-muted-foreground">一级章节</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary">{result?.sections || 0}</div>
                  <div className="text-xs text-muted-foreground">总节数</div>
                </div>
                <div className="text-center">
                  <div className={cn(
                    "text-2xl font-bold",
                    (result?.completeness_score || 0) >= 85 ? "text-emerald-600" :
                    (result?.completeness_score || 0) >= 60 ? "text-amber-600" : "text-red-600"
                  )}>
                    {result?.completeness_score || 0}%
                  </div>
                  <div className="text-xs text-muted-foreground">完整度</div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <span className={cn(
                    "px-2 py-1 rounded-full text-xs font-medium border",
                    template.status === "published"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : "bg-amber-50 text-amber-700 border-amber-200"
                  )}>
                    {template.status === "published" ? "已发布" : "草稿"}
                  </span>
                </div>
              </div>

              {/* 章节树 */}
              <div className="space-y-1">
                <h4 className="text-sm font-semibold text-foreground mb-2">章节结构</h4>
                {template.root_sections.map((section) => (
                  <SectionNode key={section.id} section={section} />
                ))}
              </div>

              {/* 选中章节详情 */}
              {template.cross_section_rules && template.cross_section_rules.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-foreground">跨章节规则</h4>
                  {template.cross_section_rules.map((rule) => (
                    <div key={rule.rule_id} className="p-3 bg-amber-50 border border-amber-100 rounded-lg text-sm">
                      <span className="font-medium text-amber-800">{rule.description}</span>
                      <div className="text-xs text-amber-600 mt-1">
                        涉及章节: {rule.source_sections.join(", ")} → {rule.target_sections.join(", ")}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border shrink-0 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-muted/50 transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
