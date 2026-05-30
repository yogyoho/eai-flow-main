"use client";

export interface SourceAnnotationProps {
  index: number;
  sourceType: string;
  sourceRef: string;
  confidence: number | null;
}

const TYPE_COLORS: Record<string, string> = {
  rag_retrieval: "bg-blue-100 border-b-2 border-blue-400",
  knowledge_base: "bg-blue-50 border-b-2 border-blue-300",
  regulation: "bg-green-100 border-b-2 border-green-400",
  ai_generated: "bg-amber-100 border-b-2 border-amber-400",
  human_written: "bg-purple-100 border-b-2 border-purple-300",
  template: "bg-gray-100 border-b-2 border-gray-400",
  external_data: "bg-cyan-100 border-b-2 border-cyan-700",
};

export function SourceAnnotation({ index, sourceType, sourceRef, confidence }: SourceAnnotationProps) {
  const colorClass = TYPE_COLORS[sourceType] || "bg-gray-100 border-b-2 border-gray-300";
  return (
    <span className={`inline ${colorClass} px-0.5 rounded-sm group relative`}>
      <sup className="text-[10px] font-medium text-amber-700">{index}</sup>
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-[10px] rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
        {sourceType}: {sourceRef.slice(0, 60)}
        {confidence !== null && <span className="ml-1 text-gray-400">{(confidence * 100).toFixed(0)}%</span>}
      </span>
    </span>
  );
}
