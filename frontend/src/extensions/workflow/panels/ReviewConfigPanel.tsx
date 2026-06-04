"use client";

import { ShieldCheck } from "lucide-react";
import type { DAGNodeData } from "../types";

interface ReviewConfigPanelProps {
  data: DAGNodeData;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
}

const MODES = [
  { value: "chapter", label: "按章节分配", desc: "按文档章节分配审核人" },
  { value: "dimension", label: "按维度分工", desc: "按专业维度分配审核人" },
  { value: "mixed", label: "混合模式", desc: "章节 + 维度混合分配" },
] as const;

export function ReviewConfigPanel({ data, onUpdate }: ReviewConfigPanelProps) {
  return (
    <div className="p-4 space-y-4">
      {/* Section header */}
      <div className="flex items-center gap-2">
        <div className="w-1 h-4 rounded-full bg-red-500" />
        <span className="text-xs font-semibold uppercase tracking-wider text-red-600">审核属性</span>
      </div>

      {/* Review name */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">审核名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full px-2.5 py-1.5 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-400 transition-colors"
        />
      </div>

      {/* Review mode — radio group styled as cards */}
      <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-muted-foreground">审核模式</label>
        <div className="space-y-2 mt-1">
          {MODES.map((mode) => {
            const isSelected = data.mode === mode.value;
            return (
              <label
                key={mode.value}
                className={`flex items-start gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-all ${
                  isSelected
                    ? "border-red-300 bg-red-50/60 shadow-sm"
                    : "border-border bg-background hover:border-red-200 hover:bg-red-50/30"
                }`}
              >
                <div className="mt-0.5">
                  <input
                    type="radio"
                    name="reviewMode"
                    value={mode.value}
                    checked={isSelected}
                    onChange={() => onUpdate({ mode: mode.value })}
                    className="accent-red-500"
                  />
                </div>
                <div>
                  <div className={`text-xs font-medium ${isSelected ? "text-red-700" : "text-foreground"}`}>
                    {mode.label}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{mode.desc}</div>
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* Info box */}
      <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 p-2.5 rounded-lg">
        <ShieldCheck className="h-3.5 w-3.5 shrink-0 mt-0.5 text-amber-500" />
        <span>审核人分配将在工作流启动后，由经理在工作台配置</span>
      </div>
    </div>
  );
}
