"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function MergeNode({ selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`flex h-12 w-12 items-center justify-center rounded-full border-2 bg-white ${
        selected ? "border-green-500 shadow-lg" : "border-green-300"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2 !w-2 !bg-green-400"
      />
      <span className="text-lg text-green-700">&#x2295;</span>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2 !w-2 !bg-green-400"
      />
    </div>
  );
}
