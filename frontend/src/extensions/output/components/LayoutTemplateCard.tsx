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
  /** Disables the edit button while the editor fetches this template's full detail. */
  editingPending?: boolean;
}

export function LayoutTemplateCard({
  template,
  onEdit,
  onRefresh,
  editingPending = false,
}: LayoutTemplateCardProps) {
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
        "border-border bg-background relative rounded-xl border p-5 shadow-sm",
        "hover:border-primary/30 transition-all hover:shadow-md",
        "w-full text-left",
      )}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Action buttons — top right */}
      {showActions && !deleting && (
        <div className="bg-background/90 border-border/50 absolute top-3 right-3 z-10 flex items-center gap-1 rounded-lg border p-1 shadow-sm backdrop-blur-sm">
          <button
            type="button"
            onClick={handleEdit}
            title="编辑"
            disabled={editingPending}
            className="text-muted-foreground hover:bg-accent hover:text-primary rounded p-1.5 transition-colors disabled:cursor-wait disabled:opacity-50"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {!template.isBuiltin && (
            <button
              type="button"
              onClick={handleDuplicate}
              title="复制"
              className="text-muted-foreground hover:bg-accent hover:text-primary rounded p-1.5 transition-colors"
            >
              <Copy className="h-3.5 w-3.5" />
            </button>
          )}
          {!template.isBuiltin && (
            <button
              type="button"
              onClick={handleDelete}
              title="删除"
              className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive rounded p-1.5 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="from-primary/20 to-primary/5 text-primary flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="text-foreground truncate text-sm font-medium">
            {template.name}
          </h3>
          <div className="flex items-center gap-2">
            <span className="border-primary/20 bg-primary/10 text-primary inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium">
              {template.reportType}
            </span>
            {template.isBuiltin && (
              <span className="border-muted-foreground/20 bg-muted text-muted-foreground inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium">
                内置
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="border-border/50 text-muted-foreground mt-4 space-y-1.5 border-t pt-3 text-xs">
        {template.pageSettings && (
          <div className="flex justify-between">
            <span>页面尺寸</span>
            <span className="text-foreground">
              {template.pageSettings.paperSize}
              {template.pageSettings.orientation === "landscape"
                ? " 横向"
                : " 纵向"}
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
