"use client";

import { useState, useEffect } from "react";
import { kfApi } from "@/extensions/api";
import type { TemplateVersionResponse, VersionCompareResult } from "@/extensions/knowledge-factory/types";

interface VersionCompareModalProps {
  templateId: string;
  open: boolean;
  onClose: () => void;
}

const STATUS_CONFIG = {
  added: { label: "新增", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
  removed: { label: "删除", color: "bg-red-500/10 text-red-500 border-red-500/20" },
  modified: { label: "修改", color: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20" },
  unchanged: { label: "未变", color: "bg-muted text-muted-foreground border-border" },
};

export default function VersionCompareModal({
  templateId,
  open,
  onClose,
}: VersionCompareModalProps) {
  const [versions, setVersions] = useState<TemplateVersionResponse[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [selectedA, setSelectedA] = useState<string | null>(null);
  const [selectedB, setSelectedB] = useState<string | null>(null);
  const [compareResult, setCompareResult] = useState<VersionCompareResult | null>(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      loadVersions();
    }
  }, [open, templateId]);

  const loadVersions = async () => {
    setLoadingVersions(true);
    try {
      const data = await kfApi.getTemplateVersions(templateId);
      setVersions(data || []);
      if (data && data.length >= 2) {
        // 默认选择最近两个版本
        setSelectedA(data[1]!.id);
        setSelectedB(data[0]!.id);
      }
    } catch (err) {
      setError("加载版本列表失败");
    } finally {
      setLoadingVersions(false);
    }
  };

  const handleCompare = async () => {
    if (!selectedA || !selectedB) return;

    setComparing(true);
    setError(null);
    setCompareResult(null);

    try {
      const data = await kfApi.compareVersions(selectedA, selectedB);
      setCompareResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "对比失败");
    } finally {
      setComparing(false);
    }
  };

  if (!open) return null;

  const getDiffStats = () => {
    if (!compareResult) return null;
    return [
      { label: "新增", count: compareResult.added_count, color: "text-emerald-500" },
      { label: "删除", count: compareResult.removed_count, color: "text-red-500" },
      { label: "修改", count: compareResult.modified_count, color: "text-yellow-500" },
      { label: "未变", count: compareResult.unchanged_count, color: "text-muted-foreground" },
    ];
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative w-full max-w-4xl rounded-lg bg-background shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold">版本对比</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 hover:bg-accent"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Version Selection */}
        <div className="flex items-center justify-center gap-4 border-b px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">版本 A:</span>
            <select
              value={selectedA || ""}
              onChange={(e) => setSelectedA(e.target.value)}
              className="rounded-md border border-input px-3 py-1.5 text-sm bg-background"
            >
              <option value="">选择版本</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.version} ({new Date(v.published_at).toLocaleDateString()})
                </option>
              ))}
            </select>
          </div>

          <svg className="h-5 w-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>

          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">版本 B:</span>
            <select
              value={selectedB || ""}
              onChange={(e) => setSelectedB(e.target.value)}
              className="rounded-md border border-input px-3 py-1.5 text-sm bg-background"
            >
              <option value="">选择版本</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.version} ({new Date(v.published_at).toLocaleDateString()})
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleCompare}
            disabled={!selectedA || !selectedB || comparing}
            className="rounded-lg bg-primary text-primary-foreground px-4 py-1.5 text-sm hover:bg-primary/90 disabled:opacity-50"
          >
            {comparing ? "对比中..." : "开始对比"}
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[50vh] overflow-y-auto p-6">
          {loadingVersions && (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary/20 border-t-primary" />
              <span className="ml-3 text-muted-foreground">加载版本列表...</span>
            </div>
          )}

          {!loadingVersions && versions.length < 2 && (
            <div className="flex flex-col items-center py-8 text-muted-foreground">
              <svg className="h-12 w-12 text-muted-foreground/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="mt-2">需要至少两个版本才能进行对比</p>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-500/10 p-4 text-red-500">
              {error}
            </div>
          )}

          {compareResult && (
            <div className="space-y-4">
              {/* Summary Stats */}
              <div className="grid grid-cols-4 gap-4">
                {getDiffStats()?.map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-lg border border-border bg-muted p-4 text-center"
                  >
                    <p className={`text-2xl font-bold ${stat.color}`}>{stat.count}</p>
                    <p className="text-sm text-muted-foreground">{stat.label}</p>
                  </div>
                ))}
              </div>

              {/* Version Info */}
              <div className="flex items-center justify-center gap-4 text-sm text-muted-foreground">
                <span>
                  <span className="font-medium">{compareResult.version_a}</span> vs{" "}
                  <span className="font-medium">{compareResult.version_b}</span>
                </span>
              </div>

              {/* Diff List */}
              <div className="space-y-2">
                {compareResult.sections.map((sec) => {
                  const config = STATUS_CONFIG[sec.status as keyof typeof STATUS_CONFIG];
                  return (
                    <div
                      key={sec.section_id}
                      className={`flex items-center gap-3 rounded-lg border px-4 py-2 ${config.color}`}
                    >
                      <span className="rounded px-2 py-0.5 text-xs font-medium">
                        {config.label}
                      </span>
                      <span
                        className="text-sm font-medium"
                        style={{ paddingLeft: `${(sec.level - 1) * 16}px` }}
                      >
                        {sec.title || "未命名章节"}
                      </span>
                      <span className="ml-auto text-xs text-muted-foreground/60">
                        {sec.status === "modified" && "内容有变更"}
                      </span>
                    </div>
                  );
                })}
              </div>

              {compareResult.sections.length === 0 && (
                <p className="text-center text-muted-foreground">未发现差异</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-md px-4 py-2 text-foreground hover:bg-accent"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
