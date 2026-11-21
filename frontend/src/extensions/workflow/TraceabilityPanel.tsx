"use client";

import { useEffect, useState } from "react";

import { workflowApi } from "./api";
import { SourceFootnote } from "./SourceFootnote";

interface SourceData {
  id: string;
  blockIndex: number;
  sourceType: string;
  sourceRef: string;
  snippet: string | null;
  confidence: number | null;
}

interface TraceabilityPanelProps {
  projectId: string;
  chapterId: string | null;
}

export function TraceabilityPanel({
  projectId,
  chapterId,
}: TraceabilityPanelProps) {
  const [sources, setSources] = useState<SourceData[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [missing, setMissing] = useState<
    Array<{ blockIndex: number; preview: string }>
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chapterId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      workflowApi
        .getSources(projectId, chapterId)
        .catch(() => ({ sources: [], stats: {} })),
      workflowApi
        .getMissingSources(projectId, chapterId)
        .catch(() => ({ missing: [] })),
    ])
      .then(([sourceRes, missingRes]) => {
        setSources(sourceRes.sources);
        setStats(sourceRes.stats);
        setMissing(missingRes.missing);
      })
      .catch(() => {
        setError("无法加载溯源数据");
      })
      .finally(() => setLoading(false));
  }, [projectId, chapterId]);

  if (!chapterId) {
    return (
      <div className="text-muted-foreground p-4 text-sm">
        选择章节查看溯源信息
      </div>
    );
  }
  if (loading)
    return <div className="text-muted-foreground p-4 text-sm">加载中...</div>;
  if (error) {
    return <div className="text-muted-foreground p-4 text-sm">{error}</div>;
  }

  return (
    <div className="space-y-4 p-4">
      <div className="text-sm font-semibold">本章溯源</div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(stats).map(([type, count]) => (
          <div
            key={type}
            className="bg-muted/50 flex justify-between rounded px-2 py-1 text-xs"
          >
            <span>{type}</span>
            <span className="font-medium">{count}</span>
          </div>
        ))}
        {Object.keys(stats).length === 0 && (
          <div className="text-muted-foreground col-span-2 text-xs">
            暂无溯源信息
          </div>
        )}
      </div>
      {missing.length > 0 && (
        <div className="rounded border border-red-200 bg-red-50 p-2 dark:border-red-800 dark:bg-red-950/40">
          <div className="text-xs font-semibold text-red-700 dark:text-red-300">
            缺少来源标注
          </div>
          <div className="mt-1 space-y-1">
            {missing.map((m, i) => (
              <div
                key={i}
                className="text-[10px] text-red-600 dark:text-red-400"
              >
                第 {m.blockIndex + 1} 段: &quot;{m.preview}&quot;...
              </div>
            ))}
          </div>
        </div>
      )}
      <SourceFootnote sources={sources} />
    </div>
  );
}
