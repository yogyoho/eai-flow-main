"use client";

import { FileText } from "lucide-react";
import React from "react";

import type { LayoutTemplate } from "@/extensions/output/types";
import { cn } from "@/lib/utils";

interface LayoutTemplateCardProps {
  template: LayoutTemplate;
  onClick?: () => void;
}

export function LayoutTemplateCard({ template, onClick }: LayoutTemplateCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xl border border-border bg-background p-5 shadow-sm",
        "transition-all hover:border-primary/30 hover:shadow-md",
        "text-left w-full",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 text-primary">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="truncate text-sm font-medium text-foreground">
            {template.name}
          </h3>
          <span className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
            {template.reportType}
          </span>
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
    </button>
  );
}
