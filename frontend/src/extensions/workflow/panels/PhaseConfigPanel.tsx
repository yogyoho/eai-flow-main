"use client";

import type { DAGNodeData } from "../types";

interface PhaseConfigPanelProps {
  data: DAGNodeData;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
}

export function PhaseConfigPanel({ data, onUpdate }: PhaseConfigPanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="text-sm font-semibold text-purple-700">阶段属性</div>
      <div>
        <label className="text-xs text-muted-foreground">阶段名称</label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="w-full mt-1 px-2 py-1 text-sm border rounded"
        />
      </div>
      <div>
        <label className="text-xs text-muted-foreground">团队</label>
        <input
          value={data.team || ""}
          onChange={(e) => onUpdate({ team: e.target.value })}
          className="w-full mt-1 px-2 py-1 text-sm border rounded"
          placeholder="如: A组"
        />
      </div>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={data.aiAssist ?? false}
          onChange={(e) => onUpdate({ aiAssist: e.target.checked })}
          className="rounded"
        />
        <label className="text-sm">AI 辅助</label>
      </div>
      {data.inputFrom && data.inputFrom.length > 0 && (
        <div>
          <label className="text-xs text-muted-foreground">输入上下文</label>
          <div className="mt-1 space-y-1">
            {data.inputFrom.map((id) => (
              <div key={id} className="text-xs bg-purple-50 px-2 py-1 rounded">
                ← {id}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
