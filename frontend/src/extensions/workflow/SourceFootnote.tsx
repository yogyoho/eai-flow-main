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
  rag_retrieval: "bg-blue-100 text-blue-700",
  knowledge_base: "bg-blue-50 text-blue-600",
  regulation: "bg-green-100 text-green-700",
  ai_generated: "bg-amber-100 text-amber-700",
  human_written: "bg-purple-100 text-purple-700",
  template: "bg-gray-100 text-gray-600",
  external_data: "bg-cyan-100 text-cyan-700",
};

export function SourceFootnote({ sources }: SourceFootnoteProps) {
  if (sources.length === 0) return null;
  return (
    <div className="border-t pt-3 mt-3 space-y-2">
      <div className="text-xs font-semibold text-muted-foreground">溯源标注</div>
      {sources.map((source, idx) => (
        <div key={source.id} className="flex gap-2 items-baseline text-xs">
          <span className="font-bold text-amber-600">[{idx + 1}]</span>
          <span className={`px-1.5 py-0.5 rounded text-[10px] ${TYPE_BADGE_COLORS[source.sourceType] || "bg-gray-100"}`}>
            {TYPE_LABELS[source.sourceType] || source.sourceType}
          </span>
          <span className="text-muted-foreground flex-1 truncate">{source.sourceRef}</span>
          {source.confidence !== null && (
            <span className="text-[10px] text-muted-foreground">{(source.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
      ))}
    </div>
  );
}
