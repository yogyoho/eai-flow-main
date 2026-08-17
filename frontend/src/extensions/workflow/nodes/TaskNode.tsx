"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Pencil } from "lucide-react";

import type { WorkflowNodeData } from "../types";

export function TaskNode({
  data,
  selected,
}: NodeProps & { data: WorkflowNodeData }) {
  const roles = data.requiredRoles ?? [];

  return (
    <div
      className={`min-w-[140px] rounded-lg border-2 bg-white px-3 py-2.5 transition-shadow ${selected ? "border-teal-400 shadow-lg ring-2 ring-teal-200" : "border-teal-200 hover:shadow-sm"}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !bg-teal-400"
      />
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-100">
          <Pencil className="h-4 w-4 text-teal-600" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-teal-700">
            {data.label ?? "任务"}
          </div>
          {data.team && (
            <div className="text-[10px] text-gray-500">团队: {data.team}</div>
          )}
        </div>
      </div>
      {data.aiAssist && (
        <div className="mt-1 ml-[38px] text-[10px] text-teal-500">AI 辅助</div>
      )}
      {roles.length > 0 && (
        <div className="mt-1 ml-[38px] flex flex-wrap gap-0.5">
          {roles.map((slot) => (
            <span
              key={slot.roleKey}
              className="rounded bg-teal-100 px-1.5 py-0.5 text-[9px] font-medium text-teal-700"
              title={`${slot.label} ×${slot.count}`}
            >
              {slot.label.slice(0, 2)}×{slot.count}
            </span>
          ))}
        </div>
      )}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-2.5 !w-2.5 !bg-teal-400"
      />
    </div>
  );
}
