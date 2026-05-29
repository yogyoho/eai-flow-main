"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function ConditionNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div className="relative w-20 h-20">
      <Handle type="target" position={Position.Top} className="!bg-amber-400 !w-2 !h-2" />
      <div
        className={`absolute inset-2 border-2 flex items-center justify-center ${
          selected ? "border-amber-500 shadow-lg" : "border-amber-300"
        } bg-amber-50`}
        style={{ transform: "rotate(45deg)", borderRadius: 4 }}
      >
        <span
          className="text-[10px] font-medium text-amber-800 text-center leading-tight"
          style={{ transform: "rotate(-45deg)" }}
        >
          {data.expression || data.label || "条件"}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400 !w-2 !h-2" />
    </div>
  );
}
