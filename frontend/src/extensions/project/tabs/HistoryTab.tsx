"use client";

import {
  Clock,
  History,
  Loader2,
  Plus,
  RotateCcw,
  Save,
  ArrowLeftRight,
} from "lucide-react";
import { useState } from "react";

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
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

import { DiffViewer } from "@/extensions/collab/DiffViewer";
import { useVersions } from "@/extensions/collab/useVersions";
import type { ReportProject } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";

interface HistoryTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
}

export function HistoryTab({ project, projectId }: HistoryTabProps) {
  const docId = `project-${projectId}`;
  const { versions, loading, diffResult, diffLoading, createVersion, restoreVersion, diffVersions, reload } =
    useVersions(docId);

  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compareFrom, setCompareFrom] = useState<number | null>(null);
  const [compareTo, setCompareTo] = useState<number | null>(null);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [restoreVersionNum, setRestoreVersionNum] = useState<number | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [saving, setSaving] = useState(false);

  const currentVersion = versions.length > 0 ? versions[0]!.version : null;

  const handleSaveVersion = async () => {
    setSaving(true);
    try {
      await createVersion(undefined, true);
      await reload();
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = async () => {
    if (!restoreVersionNum) return;
    setRestoring(true);
    try {
      await restoreVersion(restoreVersionNum);
      setRestoreDialogOpen(false);
      await reload();
    } finally {
      setRestoring(false);
    }
  };

  const handleVersionClick = (version: number) => {
    if (compareMode) {
      if (compareFrom === null) {
        setCompareFrom(version);
      } else if (compareTo === null && version !== compareFrom) {
        setCompareTo(version);
        // Fire diff
        const from = Math.min(compareFrom, version);
        const to = Math.max(compareFrom, version);
        diffVersions(from, to);
      } else {
        // Reset selection
        setCompareFrom(version);
        setCompareTo(null);
      }
    } else {
      setSelectedVersion(version === selectedVersion ? null : version);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Version List — Left */}
      <div className="w-[320px] shrink-0 border-r border-border/40 flex flex-col">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border/40 shrink-0">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-[12px]"
            disabled={saving}
            onClick={handleSaveVersion}
          >
            <Plus className="h-3 w-3 mr-1" />
            {saving ? "保存中..." : "保存版本"}
          </Button>
          <Button
            size="sm"
            variant={compareMode ? "default" : "outline"}
            className="h-7 text-[12px]"
            onClick={() => {
              setCompareMode(!compareMode);
              setCompareFrom(null);
              setCompareTo(null);
            }}
          >
            <ArrowLeftRight className="h-3 w-3 mr-1" />
            {compareMode ? "退出对比" : "对比模式"}
          </Button>
          <div className="flex-1" />
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={reload}>
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* List */}
        <ScrollArea className="flex-1">
          <div className="p-3 space-y-2">
            {versions.length > 0 ? (
              versions.map((v) => {
                const isSelected =
                  compareMode
                    ? compareFrom === v.version || compareTo === v.version
                    : selectedVersion === v.version;
                const isCurrent = v.version === currentVersion;
                return (
                  <button
                    key={v.version}
                    type="button"
                    onClick={() => handleVersionClick(v.version)}
                    className={`w-full text-left rounded-lg border p-3 transition-all ${
                      isSelected
                        ? "border-primary/40 bg-primary/5 ring-1 ring-primary/20"
                        : "border-border/40 hover:bg-accent/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-foreground">v{v.version}</span>
                        {isCurrent && (
                          <Badge className="text-[9px] h-4 px-1.5 bg-primary/10 text-primary border-0">
                            当前
                          </Badge>
                        )}
                      </div>
                      {compareMode && isSelected && (
                        <Badge variant="outline" className="text-[9px] h-4">
                          {compareFrom === v.version ? "A" : "B"}
                        </Badge>
                      )}
                    </div>
                    {v.summary && (
                      <p className="text-[12px] text-muted-foreground line-clamp-2 mt-0.5">{v.summary}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1.5">
                      {v.username && (
                        <div className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-[8px] font-medium text-primary">
                          {v.username.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <span className="text-[11px] text-muted-foreground">
                        {v.username ?? "未知用户"}
                      </span>
                      <span className="text-[10px] text-muted-foreground/60">
                        {v.created_at
                          ? new Date(v.created_at).toLocaleString("zh-CN", {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : ""}
                      </span>
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="flex flex-col items-center justify-center py-16">
                <History className="h-8 w-8 text-muted-foreground/25 mb-2" />
                <p className="text-sm text-muted-foreground">暂无版本记录</p>
                <p className="text-xs text-muted-foreground/60 mt-1">点击"保存版本"创建第一个版本</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Detail / Diff Panel — Right */}
      <div className="flex-1 min-w-0 flex flex-col">
        {diffLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : diffResult && compareMode ? (
          <ScrollArea className="h-full">
            <div className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <Badge variant="outline">v{diffResult.from_version}</Badge>
                <ArrowLeftRight className="h-3.5 w-3.5 text-muted-foreground" />
                <Badge variant="outline">v{diffResult.to_version}</Badge>
              </div>
              <DiffViewer diff={diffResult} loading={false} />
            </div>
          </ScrollArea>
        ) : selectedVersion !== null && !compareMode ? (
          <ScrollArea className="h-full">
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-foreground">
                  版本 v{selectedVersion} 详情
                </h3>
                {selectedVersion !== currentVersion && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-[12px]"
                    onClick={() => {
                      setRestoreVersionNum(selectedVersion);
                      setRestoreDialogOpen(true);
                    }}
                  >
                    <RotateCcw className="h-3 w-3 mr-1" />
                    恢复到此版本
                  </Button>
                )}
              </div>
              {(() => {
                const v = versions.find((ver) => ver.version === selectedVersion);
                if (!v) return <p className="text-sm text-muted-foreground">未找到版本信息</p>;
                return (
                  <div className="space-y-3">
                    {v.summary && (
                      <div className="rounded-lg border border-border/40 p-3 bg-muted/20">
                        <p className="text-xs text-muted-foreground mb-1">AI 摘要</p>
                        <p className="text-sm text-foreground">{v.summary}</p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <span className="text-muted-foreground">创建者</span>
                        <p className="text-foreground mt-0.5">{v.username ?? "未知"}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">创建时间</span>
                        <p className="text-foreground mt-0.5">
                          {v.created_at
                            ? new Date(v.created_at).toLocaleString("zh-CN")
                            : "未知"}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </ScrollArea>
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <History className="h-8 w-8 text-muted-foreground/25 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">
                {compareMode ? "选择两个版本进行对比" : "选择左侧版本查看详情"}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Restore Confirmation Dialog */}
      <Dialog open={restoreDialogOpen} onOpenChange={setRestoreDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>确认恢复版本</DialogTitle>
            <DialogDescription>
              确定要将文档恢复到版本 v{restoreVersionNum} 吗？此操作将创建一个新版本。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setRestoreDialogOpen(false)} disabled={restoring}>
              取消
            </Button>
            <Button size="sm" onClick={handleRestore} disabled={restoring}>
              {restoring ? "恢复中..." : "确认恢复"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
