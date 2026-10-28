"use client";

import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Cloud,
  Maximize2,
  Redo2,
  Rocket,
  Save,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";

export function DesignerToolbar({
  name,
  code,
  version,
  isPublish,
  dirty,
  saving,
  publishing,
  zoom,
  onUndo,
  onRedo,
  onZoomIn,
  onZoomOut,
  onFit,
  onSave,
  onPublish,
}: {
  name: string;
  code: string;
  version?: string | null;
  isPublish?: number | null;
  dirty: boolean;
  saving: boolean;
  publishing: boolean;
  zoom: number;
  onUndo: () => void;
  onRedo: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onSave: () => void;
  onPublish: () => void;
}) {
  return (
    <header className="flex h-[58px] shrink-0 items-center gap-3 border-b border-border bg-card/95 px-3 backdrop-blur-xl sm:px-4">
      <Button asChild variant="ghost" size="icon-sm" title="返回流程列表">
        <Link href="/">
          <ArrowLeft className="h-4 w-4" />
        </Link>
      </Button>
      <div className="hidden h-6 w-px bg-border sm:block" />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="truncate text-[13.5px] font-semibold">{name || "未命名流程"}</p>
          {dirty ? (
            <span className="flex items-center gap-1 text-[10px] text-amber-600">
              <Cloud className="h-3 w-3" />
              未保存
            </span>
          ) : (
            <span className="hidden items-center gap-1 text-[10px] text-emerald-600 sm:flex">
              <CheckCircle2 className="h-3 w-3" />
              已同步
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          <span className="font-mono">{code}</span>
          {version && <span>· v{version}</span>}
          {isPublish === 1 && <span className="text-emerald-600">· 已发布</span>}
        </div>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <div className="hidden items-center rounded-lg border border-border sm:flex">
          <Button variant="ghost" size="icon-sm" title="撤销" onClick={onUndo}>
            <Undo2 className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" title="重做" onClick={onRedo}>
            <Redo2 className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="hidden items-center rounded-lg border border-border lg:flex">
          <Button variant="ghost" size="icon-sm" title="缩小" onClick={onZoomOut}>
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="w-10 text-center text-[10.5px] tabular-nums text-muted-foreground">
            {Math.round(zoom * 100)}%
          </span>
          <Button variant="ghost" size="icon-sm" title="放大" onClick={onZoomIn}>
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon-sm" title="适应画布" onClick={onFit}>
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="mx-1 h-6 w-px bg-border" />
        <Button variant="secondary" size="sm" onClick={onSave} disabled={saving}>
          <Save className="h-3.5 w-3.5" />
          {saving ? "保存中…" : "保存"}
        </Button>
        <Button size="sm" onClick={onPublish} disabled={publishing || saving}>
          <Rocket className="h-3.5 w-3.5" />
          {publishing ? "发布中…" : "发布"}
        </Button>
      </div>
    </header>
  );
}
