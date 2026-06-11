"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { FolderOpen } from "lucide-react";

import type { DAGNodeData } from "../types";

export function PhaseNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  const roles = data.requiredRoles || [];

  return (
    <div
      className={`px-3 py-2.5 rounded-lg border-2 bg-white min-w-[150px] transition-shadow ${
        selected ? "border-purple-400 shadow-lg ring-2 ring-purple-200" : "border-purple-200 hover:shadow-sm"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-purple-400 !w-2.5 !h-2.5" />
      <div className="flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-lg bg-purple-100 flex items-center justify-center shrink-0">
          <FolderOpen className="w-4 h-4 text-purple-600" />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-medium text-purple-700 truncate">{data.label || "阶段"}</div>
          {data.team && <div className="text-[10px] text-gray-500">团队: {data.team}</div>}
        </div>
      </div>
      {data.chapterRange && data.chapterRange.length >= 2 && (
        <div className="text-[10px] text-purple-500 mt-1 ml-[38px]">
          章节 {data.chapterRange[0]}–{data.chapterRange[1]}
        </div>
      )}
      {roles.length > 0 && (
        <div className="flex flex-wrap gap-0.5 mt-1 ml-[38px]">
          {roles.map((slot) => (
            <span
              key={slot.roleKey}
              className="text-[9px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-medium"
              title={`${slot.label} ×${slot.count}`}
            >
              {slot.label.slice(0, 2)}×{slot.count}
            </span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-purple-400 !w-2.5 !h-2.5" />
    </div>
  );
}
