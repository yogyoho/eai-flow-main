"use client";

import {
  BookOpen,
  Copy,
  Image as ImageIcon,
  ListOrdered,
  Loader2,
  PanelTop,
  Pencil,
  Table,
  Trash2,
} from "lucide-react";
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

/** Paper width/height ratios (portrait) for the preview thumbnail. */
const PAPER_RATIO: Record<"A4" | "A3" | "B5" | "letter", number> = {
  A4: 210 / 297,
  A3: 297 / 420,
  B5: 176 / 250,
  letter: 216 / 279,
};

function FeatureChip({
  icon: Icon,
  label,
}: {
  icon: React.ElementType;
  label: string;
}) {
  return (
    <span className="border-border/60 bg-muted/40 text-muted-foreground inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium">
      <Icon className="text-primary/70 size-2.5 shrink-0" aria-hidden />
      {label}
    </span>
  );
}

export function LayoutTemplateCard({
  template,
  onEdit,
  onRefresh,
  editingPending = false,
}: LayoutTemplateCardProps) {
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

  const handleEdit = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    onEdit?.(template);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onEdit?.(template);
    }
  };

  // Page-preview hero geometry: real paper aspect ratio, flipped for landscape.
  const ps = template.pageSettings;
  const baseRatio = ps ? PAPER_RATIO[ps.paperSize] : 210 / 297;
  const ratio = ps?.orientation === "landscape" ? 1 / baseRatio : baseRatio;

  const hasCover = Boolean(
    template.coverTemplate ?? template.coverMaster ?? template.coverElements,
  );

  const metaParts: string[] = [];
  if (ps) {
    metaParts.push(
      `${ps.paperSize} · ${ps.orientation === "landscape" ? "横向" : "纵向"}`,
    );
  }
  if (template.bodyStyles) {
    metaParts.push(
      `${template.bodyStyles.fontFamily} ${template.bodyStyles.fontSize}pt`,
    );
    if (template.bodyStyles.lineHeight != null) {
      metaParts.push(`${template.bodyStyles.lineHeight} 倍行距`);
    }
  }

  const chips: { icon: React.ElementType; label: string }[] = [];
  if (hasCover) chips.push({ icon: BookOpen, label: "封面" });
  if (template.tocSettings) chips.push({ icon: ListOrdered, label: "目录" });
  if (template.headerFooter) chips.push({ icon: PanelTop, label: "页眉页脚" });
  if (template.tableStyles) chips.push({ icon: Table, label: "表格" });
  if (template.figureStyles) chips.push({ icon: ImageIcon, label: "图注" });

  return (
    <div
      className={cn(
        "group bg-background relative flex overflow-hidden rounded-xl border text-left",
        "border-border shadow-sm transition-all hover:shadow-md",
        onEdit && "cursor-pointer",
      )}
      onClick={onEdit ? () => handleEdit() : undefined}
      role={onEdit ? "button" : undefined}
      tabIndex={onEdit ? 0 : undefined}
      onKeyDown={onEdit ? handleKeyDown : undefined}
    >
      {/* Hover accent hairline */}
      <div className="via-primary/50 pointer-events-none absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />

      {/* LEFT — page-preview hero (reflects real paper size / orientation / cover) */}
      <div className="bg-muted/30 border-border/50 relative flex w-32 shrink-0 items-center justify-center border-r p-3">
        <div
          className="border-border/70 from-background to-muted/40 relative h-36 overflow-hidden rounded-md border bg-gradient-to-b shadow-[0_6px_16px_-6px_var(--shadow-2)] transition-transform duration-300 ease-out group-hover:-translate-y-1 group-hover:rotate-[-1.5deg]"
          style={{ aspectRatio: ratio }}
          aria-hidden
        >
          <div className="absolute inset-0 flex flex-col gap-1 p-1.5">
            {hasCover && (
              <div className="from-primary/20 via-primary/10 to-primary/5 flex flex-[0_0_36%] flex-col items-center justify-center gap-1 rounded-[2px] bg-gradient-to-br">
                <div className="bg-primary/45 h-[3px] w-1/2 rounded-full" />
                <div className="bg-primary/25 h-[2px] w-1/3 rounded-full" />
              </div>
            )}
            <div className="bg-foreground/45 h-[3px] w-3/4 rounded-full" />
            <div className="flex flex-col gap-[2.5px] pt-0.5">
              <div className="bg-muted-foreground/35 h-[2px] w-full rounded-full" />
              <div className="bg-muted-foreground/35 h-[2px] w-[92%] rounded-full" />
              <div className="bg-muted-foreground/35 h-[2px] w-2/3 rounded-full" />
              <div className="bg-muted-foreground/30 h-[2px] w-full rounded-full" />
              <div className="bg-muted-foreground/30 h-[2px] w-1/2 rounded-full" />
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT — content */}
      <div className="flex min-w-0 flex-1 flex-col p-4">
        {/* Name + report type */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-foreground truncate text-sm font-semibold tracking-tight">
              {template.name}
            </h3>
            <p className="text-muted-foreground mt-0.5 truncate text-xs">
              {template.reportType}
            </p>
          </div>
          {template.isBuiltin && (
            <span className="border-border/70 bg-muted/50 text-muted-foreground shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium">
              内置
            </span>
          )}
        </div>

        {/* Dense spec line */}
        {metaParts.length > 0 && (
          <p className="text-muted-foreground/80 mt-2 truncate text-[11px]">
            {metaParts.join("   ·   ")}
          </p>
        )}

        {/* Capability chips */}
        {chips.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <FeatureChip key={c.label} icon={c.icon} label={c.label} />
            ))}
          </div>
        )}

        {/* Footer action bar — pinned bottom, dims to full on hover */}
        <div className="border-border/50 mt-auto flex items-center justify-end gap-0.5 border-t pt-2.5 opacity-70 transition-opacity duration-200 group-hover:opacity-100">
          <button
            type="button"
            onClick={handleEdit}
            title="编辑"
            disabled={editingPending}
            className="text-muted-foreground hover:bg-accent hover:text-primary inline-flex size-7 items-center justify-center rounded-md transition-colors disabled:cursor-wait disabled:opacity-40"
          >
            {editingPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Pencil className="size-3.5" />
            )}
          </button>
          {!template.isBuiltin && (
            <button
              type="button"
              onClick={(e) => {
                void handleDuplicate(e);
              }}
              title="复制"
              className="text-muted-foreground hover:bg-accent hover:text-primary inline-flex size-7 items-center justify-center rounded-md transition-colors"
            >
              <Copy className="size-3.5" />
            </button>
          )}
          {!template.isBuiltin && (
            <button
              type="button"
              onClick={(e) => {
                void handleDelete(e);
              }}
              title="删除"
              disabled={deleting}
              className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive inline-flex size-7 items-center justify-center rounded-md transition-colors disabled:opacity-40"
            >
              {deleting ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
