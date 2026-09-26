"use client";

export interface SourceAnnotationProps {
  index: number;
  sourceType: string;
  sourceRef: string;
  confidence: number | null;
}

const TYPE_COLORS: Record<string, string> = {
  rag_retrieval: "bg-blue-100 dark:bg-blue-500/15 border-b-2 border-blue-400",
  knowledge_base: "bg-blue-50 dark:bg-blue-950/40 border-b-2 border-blue-300 dark:border-blue-700",
  regulation: "bg-green-100 dark:bg-green-500/15 border-b-2 border-green-400",
  ai_generated: "bg-amber-100 dark:bg-amber-500/15 border-b-2 border-amber-400",
  human_written: "bg-purple-100 dark:bg-purple-500/15 border-b-2 border-purple-300",
  template: "bg-muted border-b-2 border-gray-400",
  external_data: "bg-cyan-100 dark:bg-cyan-500/15 border-b-2 border-cyan-700",
};

export function SourceAnnotation({
  index,
  sourceType,
  sourceRef,
  confidence,
}: SourceAnnotationProps) {
  const colorClass =
    TYPE_COLORS[sourceType] ?? "bg-muted border-b-2 border-input";
  return (
    <span className={`inline ${colorClass} group relative rounded-sm px-0.5`}>
      <sup className="text-[10px] font-medium text-amber-700 dark:text-amber-300">{index}</sup>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 rounded bg-gray-900 px-2 py-1 text-[10px] whitespace-nowrap text-white opacity-0 transition-opacity group-hover:opacity-100">
        {sourceType}: {sourceRef.slice(0, 60)}
        {confidence !== null && (
          <span className="ml-1 text-muted-foreground">
            {(confidence * 100).toFixed(0)}%
          </span>
        )}
      </span>
    </span>
  );
}
