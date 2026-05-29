"use client";

import type { DAGNodeData } from "../types";

interface ReviewConfigPanelProps {
  data: DAGNodeData;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
}

const MODES = [
  { value: "chapter", label: "按章节分配" },
  { value: "dimension", label: "按维度分工" },
  { value: "mixed", label: "混合模式" },
] as const;

export function ReviewConfigPanel({ data, onUpdate }: ReviewConfigPanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="text-sm font-semibold text-red-700">审核属性</div>
      <div>
        <label className="text-xs text-muted-foreground">审核名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full mt-1 px-2 py-1 text-sm border rounded"
        />
      </div>
      <div>
        <label className="text-xs text-muted-foreground">审核模式</label>
        <div className="mt-1 space-y-2">
          {MODES.map((mode) => (
            <label key={mode.value} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="reviewMode"
                value={mode.value}
                checked={data.mode === mode.value}
                onChange={() => onUpdate({ mode: mode.value })}
              />
              {mode.label}
            </label>
          ))}
        </div>
      </div>
      <div className="text-xs text-muted-foreground bg-amber-50 p-2 rounded">
        审核人分配将在工作流启动后，由经理在工作台配置
      </div>
    </div>
  );
}
