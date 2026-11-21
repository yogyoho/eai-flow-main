"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function AIGenerateNode({
  data,
  selected,
}: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`bg-card min-w-[140px] rounded-lg border-2 px-3 py-2 ${
        selected ? "border-blue-500 shadow-lg" : "border-blue-300"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !bg-blue-400"
      />
      <div className="text-xs font-semibold text-blue-700 dark:text-blue-300">
        {data.label || "AI 生成"}
      </div>
      {data.chapterRange && data.chapterRange.length > 0 && (
        <div className="text-muted-foreground mt-1 text-[10px]">
          章节: {data.chapterRange.join("-")}
        </div>
      )}
      {data.aiAssist && (
        <div className="mt-1 text-[10px] text-blue-600 dark:text-blue-400">
          AI 辅助
        </div>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !bg-blue-400"
      />
    </div>
  );
}
