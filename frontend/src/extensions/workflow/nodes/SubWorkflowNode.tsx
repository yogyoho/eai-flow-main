"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { DAGNodeData } from "../types";

export function SubWorkflowNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  const nestedNodeCount =
    data.graphJson && typeof data.graphJson === "object" && "nodes" in data.graphJson
      ? (data.graphJson as { nodes: unknown[] }).nodes.length
      : 0;

  return (
    <div
      className={`px-3 py-2 rounded-lg border-2 bg-white min-w-[140px] ${
        selected ? "border-indigo-500 shadow-lg" : "border-indigo-300"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-indigo-400 !w-2 !h-2" />
      <div className="text-xs font-semibold text-indigo-700">
        {data.label || "子工作流"}
      </div>
      <div className="text-[10px] text-gray-500 mt-1">类型: 子流程</div>
      {nestedNodeCount > 0 && (
        <div className="text-[10px] text-gray-500">
          内含 {nestedNodeCount} 个节点
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !w-2 !h-2" />
    </div>
  );
}
