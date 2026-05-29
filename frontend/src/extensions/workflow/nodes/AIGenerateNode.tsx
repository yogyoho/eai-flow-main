"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function AIGenerateNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`px-3 py-2 rounded-lg border-2 bg-white min-w-[140px] ${
        selected ? "border-blue-500 shadow-lg" : "border-blue-300"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-400 !w-2 !h-2" />
      <div className="text-xs font-semibold text-blue-700">{data.label || "AI 生成"}</div>
      {data.chapterRange && data.chapterRange.length > 0 && (
        <div className="text-[10px] text-gray-500 mt-1">章节: {data.chapterRange.join("-")}</div>
      )}
      {data.aiAssist && <div className="text-[10px] text-blue-500 mt-1">AI 辅助</div>}
      <Handle type="source" position={Position.Bottom} className="!bg-blue-400 !w-2 !h-2" />
    </div>
  );
}
