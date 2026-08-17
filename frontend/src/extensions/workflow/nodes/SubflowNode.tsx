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

export function SubflowNode({
  data,
  selected,
}: NodeProps & { data: DAGNodeData }) {
  const roles = data.requiredRoles ?? [];
  const taskCount = (data as Record<string, unknown>).taskCount as
    | number
    | undefined;

  return (
    <div
      className={`min-w-[150px] cursor-pointer rounded-lg border-2 bg-white px-3 py-2.5 transition-shadow ${selected ? "border-violet-500 shadow-lg ring-2 ring-violet-200" : "border-violet-300 hover:shadow-sm"}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-2.5 !w-2.5 !bg-violet-400"
      />
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-100">
          <Layers className="h-4 w-4 text-violet-600" />
        </span>
        <span className="text-xs font-semibold text-violet-700">
          {data.label || "子流程"}
        </span>
      </div>
      {data.team && (
        <div className="mt-1 ml-[38px] text-[10px] text-gray-500">
          团队: {data.team}
        </div>
      )}
      {taskCount != null && (
        <div className="mt-0.5 ml-[38px] text-[10px] text-violet-500">
          任务数: {taskCount}
        </div>
      )}
      {roles.length > 0 && (
        <div className="mt-1 ml-[38px] flex flex-wrap gap-0.5">
          <Users className="mr-0.5 h-2.5 w-2.5 text-gray-400" />
          {roles.map((slot) => (
            <span
              key={slot.roleKey}
              className={`rounded px-1 py-px text-[9px] ${ROLE_COLORS[slot.roleKey] ?? "bg-gray-100 text-gray-600"}`}
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
        className="!h-2.5 !w-2.5 !bg-violet-400"
      />
    </div>
  );
}
