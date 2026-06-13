"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Layers, Users } from "lucide-react";

import type { DAGNodeData } from "../types";

const ROLE_COLORS: Record<string, string> = {
  lead: "bg-amber-100 text-amber-700",
  writer: "bg-blue-100 text-blue-700",
  reviewer: "bg-green-100 text-green-700",
  data_reviewer: "bg-teal-100 text-teal-700",
  approver: "bg-red-100 text-red-700",
};

export function SubflowNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  const roles = data.requiredRoles || [];
  const taskCount = (data as Record<string, unknown>).taskCount as number | undefined;

  return (
    <div className={`px-3 py-2.5 rounded-lg border-2 bg-white min-w-[150px] cursor-pointer transition-shadow ${selected ? "border-violet-500 shadow-lg ring-2 ring-violet-200" : "border-violet-300 hover:shadow-sm"}`}>
      <Handle type="target" position={Position.Top} className="!bg-violet-400 !w-2.5 !h-2.5" />
      <div className="flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-lg bg-violet-100 flex items-center justify-center shrink-0">
          <Layers className="w-4 h-4 text-violet-600" />
        </span>
        <span className="text-xs font-semibold text-violet-700">{data.label || "子流程"}</span>
      </div>
      {data.team && <div className="text-[10px] text-gray-500 mt-1 ml-[38px]">团队: {data.team}</div>}
      {taskCount != null && <div className="text-[10px] text-violet-500 mt-0.5 ml-[38px]">任务数: {taskCount}</div>}
      {roles.length > 0 && (
        <div className="flex flex-wrap gap-0.5 mt-1 ml-[38px]">
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
      <Handle type="source" position={Position.Bottom} className="!bg-violet-400 !w-2.5 !h-2.5" />
    </div>
  );
}
