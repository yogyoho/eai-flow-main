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

export function TraceabilityPanel({ projectId, chapterId }: TraceabilityPanelProps) {
  const [sources, setSources] = useState<SourceData[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [missing, setMissing] = useState<Array<{ blockIndex: number; preview: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chapterId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      workflowApi.getSources(projectId, chapterId).catch(() => ({ sources: [], stats: {} })),
      workflowApi.getMissingSources(projectId, chapterId).catch(() => ({ missing: [] })),
    ]).then(([sourceRes, missingRes]) => {
      setSources(sourceRes.sources);
      setStats(sourceRes.stats);
      setMissing(missingRes.missing);
    }).catch(() => {
      setError("无法加载溯源数据");
    }).finally(() => setLoading(false));
  }, [projectId, chapterId]);

  if (!chapterId) {
    return <div className="p-4 text-sm text-muted-foreground">选择章节查看溯源信息</div>;
  }
  if (loading) return <div className="p-4 text-sm text-muted-foreground">加载中...</div>;
  if (error) {
    return <div className="p-4 text-sm text-muted-foreground">{error}</div>;
  }

  return (
    <div className="p-4 space-y-4">
      <div className="text-sm font-semibold">本章溯源</div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(stats).map(([type, count]) => (
          <div key={type} className="flex justify-between px-2 py-1 bg-muted/50 rounded text-xs">
            <span>{type}</span>
            <span className="font-medium">{count}</span>
          </div>
        ))}
        {Object.keys(stats).length === 0 && (
          <div className="text-xs text-muted-foreground col-span-2">暂无溯源信息</div>
        )}
      </div>
      {missing.length > 0 && (
        <div className="p-2 bg-red-50 border border-red-200 rounded">
          <div className="text-xs font-semibold text-red-700">缺少来源标注</div>
          <div className="mt-1 space-y-1">
            {missing.map((m, i) => (
              <div key={i} className="text-[10px] text-red-600">第 {m.blockIndex + 1} 段: &quot;{m.preview}&quot;...</div>
            ))}
          </div>
        </div>
      )}
      <SourceFootnote sources={sources} />
    </div>
  );
}
