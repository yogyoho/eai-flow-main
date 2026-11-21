"use client";

import {
  Eye,
  GitCompare,
  History,
  Loader2,
  RotateCcw,
  Save,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import type { CollabVersion, VersionDiffResponse } from "../types";

import { DiffViewer } from "./DiffViewer";

interface VersionPanelProps {
  versions: CollabVersion[];
  loading: boolean;
  diffLoading: boolean;
  diffResult: VersionDiffResponse | null;
  onCreateVersion: (
    summary?: string,
    generateAiSummary?: boolean,
    content?: string,
  ) => Promise<void>;
  onRestoreVersion: (version: number) => Promise<void>;
  onPreviewVersion: (version: number) => Promise<void>;
  onDiffVersions: (from: number, to: number) => Promise<void>;
  onClose: () => void;
}

export function VersionPanel({
  versions,
  loading,
  diffLoading,
  diffResult,
  onCreateVersion,
  onRestoreVersion,
  onPreviewVersion,
  onDiffVersions,
  onClose,
}: VersionPanelProps) {
  const [diffMode, setDiffMode] = useState(false);
  const [selectedVersions, setSelectedVersions] = useState<number[]>([]);
  const [aiSummaryEnabled, setAiSummaryEnabled] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<CollabVersion | null>(
    null,
  );
  const [restoring, setRestoring] = useState(false);
  const onDiffVersionsRef = useRef(onDiffVersions);
  onDiffVersionsRef.current = onDiffVersions;

  // Reset selection when exiting diff mode
  useEffect(() => {
    if (!diffMode) {
      setSelectedVersions([]);
    }
  }, [diffMode]);

  const toggleVersionSelection = useCallback((version: number) => {
    setSelectedVersions((prev) => {
      if (prev.includes(version)) {
        return prev.filter((v) => v !== version);
      }
      if (prev.length >= 2) {
        return [prev[1]!, version];
      }
      return [...prev, version];
    });
  }, []);

  // Auto-trigger diff when 2 versions are selected
  useEffect(() => {
    if (diffMode && selectedVersions.length === 2) {
      void onDiffVersionsRef.current(
        selectedVersions[0]!,
        selectedVersions[1]!,
      );
    }
  }, [diffMode, selectedVersions]);

  const handleRestore = useCallback(async () => {
    if (!restoreTarget) return;
    setRestoring(true);
    try {
      await onRestoreVersion(restoreTarget.version);
      setRestoreTarget(null);
    } catch {
      // toast already shown by useVersions
    } finally {
      setRestoring(false);
    }
  }, [restoreTarget, onRestoreVersion]);

  return (
    <div className="border-border bg-background flex h-full w-80 flex-col border-l">
      <div className="border-border flex items-center justify-between border-b p-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4" />
          <span className="text-sm font-medium">版本历史</span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant={diffMode ? "secondary" : "ghost"}
            className="h-7 px-2 text-xs"
            onClick={() => setDiffMode(!diffMode)}
            title="差异对比"
          >
            <GitCompare className="mr-1 h-3 w-3" />
            对比
          </Button>
          <Button size="sm" variant="outline" onClick={onClose}>
            关闭
          </Button>
        </div>
      </div>

      <div className="border-border space-y-2 border-b p-3">
        <Button
          size="sm"
          className="w-full"
          variant="outline"
          onClick={() => onCreateVersion(undefined, aiSummaryEnabled)}
        >
          <Save className="mr-1 h-3 w-3" />
          保存当前版本
        </Button>
        <label className="text-muted-foreground flex cursor-pointer items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={aiSummaryEnabled}
            onChange={(e) => setAiSummaryEnabled(e.target.checked)}
            className="border-border h-3.5 w-3.5 rounded"
          />
          <Sparkles className="h-3 w-3" />
          AI 生成变更摘要
        </label>
      </div>

      {diffMode && (
        <div className="border-border border-b">
          <DiffViewer diff={diffResult} loading={diffLoading} />
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {loading && versions.length === 0 ? (
          <p className="text-muted-foreground py-8 text-center text-sm">
            加载中...
          </p>
        ) : versions.length === 0 ? (
          <p className="text-muted-foreground py-8 text-center text-sm">
            暂无版本记录
          </p>
        ) : (
          <div className="divide-border divide-y">
            {versions.map((v, idx) => {
              const isSelected = selectedVersions.includes(v.version);
              const isCurrent = idx === 0;

              return (
                <div
                  key={v.id}
                  className={`cursor-pointer p-3 transition-colors ${
                    isSelected ? "bg-primary/10" : "hover:bg-muted/50"
                  }`}
                  onClick={() => {
                    if (diffMode) {
                      toggleVersionSelection(v.version);
                    } else {
                      void onPreviewVersion(v.version);
                    }
                  }}
                >
                  <div className="mb-1 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {diffMode && (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleVersionSelection(v.version)}
                          className="border-border h-3.5 w-3.5 rounded"
                          onClick={(e) => e.stopPropagation()}
                        />
                      )}
                      <span className="text-xs font-medium">v{v.version}</span>
                      {isCurrent && (
                        <Badge
                          variant="secondary"
                          className="h-4 border-0 bg-emerald-100 px-1.5 text-[10px] text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
                        >
                          当前
                        </Badge>
                      )}
                    </div>
                    <span className="text-muted-foreground text-[10px]">
                      {new Date(v.created_at).toLocaleString("zh-CN", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                  {v.summary && (
                    <p className="text-muted-foreground mb-1 text-xs">
                      {v.summary}
                    </p>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground text-[10px]">
                      {v.full_name ?? v.username ?? "未知"}
                    </span>
                    {!diffMode && (
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 px-2 text-[10px]"
                          onClick={(e) => {
                            e.stopPropagation();
                            void onPreviewVersion(v.version);
                          }}
                        >
                          <Eye className="mr-1 h-3 w-3" />
                          预览
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 px-2 text-[10px]"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRestoreTarget(v);
                          }}
                        >
                          <RotateCcw className="mr-1 h-3 w-3" />
                          恢复
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Restore Confirmation Dialog */}
      <Dialog
        open={!!restoreTarget}
        onOpenChange={(open) => !open && setRestoreTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认恢复版本</DialogTitle>
            <DialogDescription>
              将文档内容恢复到版本 v{restoreTarget?.version}
              ，当前内容将被覆盖。恢复后会自动创建一个新版本记录。
            </DialogDescription>
          </DialogHeader>
          {restoreTarget?.summary && (
            <div className="bg-muted text-muted-foreground rounded-md p-3 text-sm">
              {restoreTarget.summary}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRestoreTarget(null)}
              disabled={restoring}
            >
              取消
            </Button>
            <Button onClick={handleRestore} disabled={restoring}>
              {restoring && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              确认恢复
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
