"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function MergeNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`w-12 h-12 rounded-full border-2 flex items-center justify-center bg-white ${
        selected ? "border-green-500 shadow-lg" : "border-green-300"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-green-400 !w-2 !h-2" />
      <span className="text-lg text-green-700">&#x2295;</span>
      <Handle type="source" position={Position.Bottom} className="!bg-green-400 !w-2 !h-2" />
    </div>
  );
}
