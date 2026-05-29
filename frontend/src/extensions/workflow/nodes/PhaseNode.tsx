"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function PhaseNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`px-3 py-2 rounded-lg border-2 bg-white min-w-[140px] ${
        selected ? "border-purple-500 shadow-lg" : "border-purple-300"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-purple-400 !w-2 !h-2" />
      <div className="text-xs font-semibold text-purple-700">{data.label || "阶段"}</div>
      {data.team && <div className="text-[10px] text-gray-500 mt-1">团队: {data.team}</div>}
      {data.chapterRange && data.chapterRange.length > 0 && (
        <div className="text-[10px] text-gray-500">章节: {data.chapterRange.join("-")}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-purple-400 !w-2 !h-2" />
    </div>
  );
}
