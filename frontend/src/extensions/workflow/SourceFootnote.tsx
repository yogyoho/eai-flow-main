"use client";

export interface SourceFootnoteProps {
  sources: Array<{
    id: string;
    blockIndex: number;
    sourceType: string;
    sourceRef: string;
    snippet: string | null;
    confidence: number | null;
  }>;
}

const TYPE_LABELS: Record<string, string> = {
  rag_retrieval: "RAG检索",
  knowledge_base: "知识库",
  regulation: "法规引用",
  ai_generated: "AI生成",
  human_written: "人工编写",
  template: "模板",
  external_data: "外部数据",
};

const TYPE_BADGE_COLORS: Record<string, string> = {
  rag_retrieval: "bg-blue-100 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300",
  knowledge_base: "bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400",
  regulation: "bg-green-100 dark:bg-green-500/15 text-green-700 dark:text-green-300",
  ai_generated: "bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300",
  human_written: "bg-purple-100 dark:bg-purple-500/15 text-purple-700",
  template: "bg-muted text-muted-foreground",
  external_data: "bg-cyan-100 dark:bg-cyan-500/15 text-cyan-700",
};

export function SourceFootnote({ sources }: SourceFootnoteProps) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <div className="text-muted-foreground text-xs font-semibold">
        溯源标注
      </div>
      {sources.map((source, idx) => (
        <div key={source.id} className="flex items-baseline gap-2 text-xs">
          <span className="font-bold text-amber-600 dark:text-amber-400">[{idx + 1}]</span>
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] ${TYPE_BADGE_COLORS[source.sourceType] ?? "bg-muted"}`}
          >
            {TYPE_LABELS[source.sourceType] ?? source.sourceType}
          </span>
          <span className="text-muted-foreground flex-1 truncate">
            {source.sourceRef}
          </span>
          {source.confidence !== null && (
            <span className="text-muted-foreground text-[10px]">
              {(source.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
