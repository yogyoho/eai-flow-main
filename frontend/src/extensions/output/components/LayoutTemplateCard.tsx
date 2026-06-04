"use client";

import { Copy, FileText, Pencil, Trash2 } from "lucide-react";
import React, { useState } from "react";
import { toast } from "sonner";

import { outputApi } from "@/extensions/output/api";
import type { LayoutTemplate } from "@/extensions/output/types";
import { cn } from "@/lib/utils";

interface LayoutTemplateCardProps {
  template: LayoutTemplate;
  onEdit?: (template: LayoutTemplate) => void;
  onRefresh?: () => void;
}

export function LayoutTemplateCard({ template, onEdit, onRefresh }: LayoutTemplateCardProps) {
  const [showActions, setShowActions] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDuplicate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await outputApi.duplicateTemplate(template.id);
      toast.success(`已复制「${template.name}」`);
      onRefresh?.();
    } catch {
      toast.error("复制失败");
    }
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除「${template.name}」吗？此操作不可撤销。`)) return;
    setDeleting(true);
    try {
      await outputApi.deleteTemplate(template.id);
      toast.success(`已删除「${template.name}」`);
      onRefresh?.();
    } catch {
      toast.error("删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    onEdit?.(template);
  };

  return (
    <div
      className={cn(
        "relative rounded-xl border border-border bg-background p-5 shadow-sm",
        "transition-all hover:border-primary/30 hover:shadow-md",
        "text-left w-full",
      )}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Action buttons — top right */}
      {showActions && !deleting && (
        <div className="absolute right-3 top-3 flex items-center gap-1 rounded-lg bg-background/90 p-1 shadow-sm border border-border/50 backdrop-blur-sm z-10">
          <button type="button" onClick={handleEdit} title="编辑" className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-primary transition-colors">
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {!template.isBuiltin && (
            <button type="button" onClick={handleDuplicate} title="复制" className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-primary transition-colors">
              <Copy className="h-3.5 w-3.5" />
            </button>
          )}
          {!template.isBuiltin && (
            <button type="button" onClick={handleDelete} title="删除" className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 text-primary">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="truncate text-sm font-medium text-foreground">
            {template.name}
          </h3>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              {template.reportType}
            </span>
            {template.isBuiltin && (
              <span className="inline-flex items-center rounded-full border border-muted-foreground/20 bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                内置
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-1.5 border-t border-border/50 pt-3 text-xs text-muted-foreground">
        {template.pageSettings && (
          <div className="flex justify-between">
            <span>页面尺寸</span>
            <span className="text-foreground">
              {template.pageSettings.paperSize}
              {template.pageSettings.orientation === "landscape" ? " 横向" : " 纵向"}
            </span>
          </div>
        )}
        {template.bodyStyles && (
          <div className="flex justify-between">
            <span>正文字体</span>
            <span className="text-foreground">
              {template.bodyStyles.fontFamily} {template.bodyStyles.fontSize}pt
            </span>
          </div>
        )}
        {template.referenceStyle && (
          <div className="flex justify-between">
            <span>参考文献</span>
            <span className="text-foreground">{template.referenceStyle}</span>
          </div>
        )}
      </div>
    </div>
  );
}
