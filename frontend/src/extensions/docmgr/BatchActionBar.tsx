"use client";

import { FolderInput, Star, Trash2, X, Layers } from "lucide-react";

import { Button } from "@/components/ui/button";

interface BatchActionBarProps {
  selectedCount: number;
  onMove: () => void;
  onStar: () => void;
  onDelete: () => void;
  onCancel: () => void;
  // EAI-CUSTOM (bug-3109 v4 WP-1.4): 多册合并导出(≥2 个勾选; 后端整单失败指认册名)
  onMergeExport?: () => void;
  mergeExporting?: boolean;
}

export default function BatchActionBar({
  selectedCount,
  onMove,
  onStar,
  onDelete,
  onCancel,
  onMergeExport,
  mergeExporting = false,
}: BatchActionBarProps) {
  if (selectedCount === 0) return null;

  return (
    <div className="bg-background border-border fixed right-0 bottom-0 left-0 z-50 border-t shadow-lg">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
        <span className="text-foreground text-sm">
          已选择{" "}
          <span className="text-primary font-semibold">{selectedCount}</span>{" "}
          个文件
        </span>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onMove}>
            <FolderInput className="h-4 w-4" />
            移动
          </Button>
          <Button variant="outline" size="sm" onClick={onStar}>
            <Star className="h-4 w-4" />
            收藏
          </Button>
          {onMergeExport && (
            <Button
              variant="outline"
              size="sm"
              onClick={onMergeExport}
              disabled={mergeExporting}
            >
              <Layers className="h-4 w-4" />
              {mergeExporting ? "合并中…" : "合并导出"}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" />
            删除
          </Button>
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X className="h-4 w-4" />
            取消
          </Button>
        </div>
      </div>
    </div>
  );
}
