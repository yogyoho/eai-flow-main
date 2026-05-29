"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function ReviewNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`px-3 py-2 rounded-lg border-2 bg-white min-w-[140px] ${
        selected ? "border-red-500 shadow-lg" : "border-red-300"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-red-400 !w-2 !h-2" />
      <div className="text-xs font-semibold text-red-700">{data.label || "审核"}</div>
      {data.mode && (
        <div className="text-[10px] text-gray-500 mt-1">
          模式: {data.mode === "chapter" ? "章节" : data.mode === "dimension" ? "维度" : "混合"}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-red-400 !w-2 !h-2" />
    </div>
  );
}
