"use client";

import { Button } from "@/components/ui/button";
import { Eye, History, RotateCcw, Save } from "lucide-react";
import type { CollabVersion } from "../types";

interface VersionPanelProps {
  versions: CollabVersion[];
  loading: boolean;
  onCreateVersion: (summary?: string) => Promise<void>;
  onRestoreVersion: (version: number) => Promise<void>;
  onPreviewVersion: (version: number) => Promise<void>;
  onClose: () => void;
}

export function VersionPanel({ versions, loading, onCreateVersion, onRestoreVersion, onPreviewVersion, onClose }: VersionPanelProps) {
  return (
    <div className="w-80 border-l border-border flex flex-col h-full bg-background">
      <div className="p-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4" />
          <span className="font-medium text-sm">版本历史</span>
        </div>
        <Button size="sm" variant="outline" onClick={onClose}>
          关闭
        </Button>
      </div>

      <div className="p-3 border-b border-border">
        <Button size="sm" className="w-full" variant="outline" onClick={() => onCreateVersion()}>
          <Save className="w-3 h-3 mr-1" />
          保存当前版本
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && versions.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">加载中...</p>
        ) : versions.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">暂无版本记录</p>
        ) : (
          <div className="divide-y divide-border">
            {versions.map((v) => (
              <div key={v.id} className="p-3 hover:bg-muted/50 transition-colors cursor-pointer"
                onClick={() => onPreviewVersion(v.version)}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium">v{v.version}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(v.created_at).toLocaleString("zh-CN", {
                      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </div>
                {v.summary && <p className="text-xs text-muted-foreground mb-1">{v.summary}</p>}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-muted-foreground">
                    {v.full_name || v.username || "未知"}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-[10px] px-2"
                      onClick={(e) => { e.stopPropagation(); onPreviewVersion(v.version); }}
                    >
                      <Eye className="w-3 h-3 mr-1" />
                      预览
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-[10px] px-2"
                      onClick={(e) => { e.stopPropagation(); if (confirm(`确定恢复到版本 v${v.version}？`)) onRestoreVersion(v.version); }}
                    >
                      <RotateCcw className="w-3 h-3 mr-1" />
                      恢复
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
