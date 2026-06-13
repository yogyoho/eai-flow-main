"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Pencil } from "lucide-react";

import type { WorkflowNodeData } from "../types";

export function TaskNode({ data, selected }: NodeProps & { data: WorkflowNodeData }) {
  const roles = data.requiredRoles || [];

  return (
    <div className={`px-3 py-2.5 rounded-lg border-2 bg-white min-w-[140px] transition-shadow ${selected ? "border-teal-400 shadow-lg ring-2 ring-teal-200" : "border-teal-200 hover:shadow-sm"}`}>
      <Handle type="target" position={Position.Top} className="!bg-teal-400 !w-2.5 !h-2.5" />
      <div className="flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-lg bg-teal-100 flex items-center justify-center shrink-0">
          <Pencil className="w-4 h-4 text-teal-600" />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-medium text-teal-700 truncate">{data.label ?? "任务"}</div>
          {data.team && <div className="text-[10px] text-gray-500">团队: {data.team}</div>}
        </div>
      </div>
      {data.aiAssist && <div className="text-[10px] text-teal-500 mt-1 ml-[38px]">AI 辅助</div>}
      {roles.length > 0 && (
        <div className="flex flex-wrap gap-0.5 mt-1 ml-[38px]">
          {roles.map((slot) => (
            <span key={slot.roleKey} className="text-[9px] px-1.5 py-0.5 rounded bg-teal-100 text-teal-700 font-medium"
              title={`${slot.label} ×${slot.count}`}>{slot.label.slice(0, 2)}×{slot.count}</span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-teal-400 !w-2.5 !h-2.5" />
    </div>
  );
}
