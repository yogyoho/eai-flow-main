"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Users } from "lucide-react";

import type { DAGNodeData } from "../types";

const ROLE_COLORS: Record<string, string> = {
  lead: "bg-amber-100 text-amber-700",
  writer: "bg-blue-100 text-blue-700",
  reviewer: "bg-green-100 text-green-700",
  data_reviewer: "bg-teal-100 text-teal-700",
  approver: "bg-red-100 text-red-700",
};

export function PhaseNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  const roles = data.requiredRoles || [];

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
      {roles.length > 0 && (
        <div className="flex flex-wrap gap-0.5 mt-1">
          <Users className="h-2.5 w-2.5 text-gray-400 mr-0.5" />
          {roles.map((slot) => (
            <span
              key={slot.roleKey}
              className={`text-[9px] px-1 py-px rounded ${ROLE_COLORS[slot.roleKey] || "bg-gray-100 text-gray-600"}`}
              title={`${slot.label} ×${slot.count}`}
            >
              {slot.label.slice(0, 2)}×{slot.count}
            </span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-purple-400 !w-2 !h-2" />
    </div>
  );
}
