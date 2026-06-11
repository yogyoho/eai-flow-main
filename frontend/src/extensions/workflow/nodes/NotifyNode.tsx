"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Bell } from "lucide-react";

import type { DAGNodeData } from "../types";

export function NotifyNode({ data, selected }: NodeProps & { data: DAGNodeData }) {
  return (
    <div
      className={`px-3 py-2.5 rounded-lg border-2 bg-white min-w-[140px] transition-shadow ${
        selected ? "border-sky-400 shadow-lg ring-2 ring-sky-200" : "border-sky-200 hover:shadow-sm"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-sky-400 !w-2.5 !h-2.5" />
      <div className="flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-lg bg-sky-100 flex items-center justify-center shrink-0">
          <Bell className="w-4 h-4 text-sky-600" />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-medium text-sky-700 truncate">{data.label || "通知"}</div>
          {data.team && <div className="text-[10px] text-gray-500">团队: {data.team}</div>}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-sky-400 !w-2.5 !h-2.5" />
    </div>
  );
}
