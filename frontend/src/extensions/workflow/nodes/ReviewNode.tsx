"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function ReviewNode({
  data,
  selected,
}: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`bg-card min-w-[140px] rounded-lg border-2 px-3 py-2 ${
        selected ? "border-red-500 shadow-lg" : "border-red-300"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !bg-red-400"
      />
      <div className="text-xs font-semibold text-red-700 dark:text-red-300">
        {data.label || "审核"}
      </div>
      {data.mode && (
        <div className="text-muted-foreground mt-1 text-[10px]">
          模式:{" "}
          {data.mode === "chapter"
            ? "章节"
            : data.mode === "dimension"
              ? "维度"
              : "混合"}
        </div>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !bg-red-400"
      />
    </div>
  );
}
