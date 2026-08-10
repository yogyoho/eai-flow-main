"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AssignmentStrategy } from "@/extensions/project/types";

// EAI-CUSTOM: 分工策略选择器(ADR 2026-08-10)。创建向导与项目设置共用。
const STRATEGY_LABELS: Record<AssignmentStrategy, string> = {
  by_chapter: "按章节分工",
  by_role: "按职责分工（按角色）",
};

const STRATEGY_HINT: Record<AssignmentStrategy, string> = {
  by_chapter: "每人认领/被分配若干章节，改完提交审核。",
  by_role: "成员按角色分组（撰写/审核/审批），跨全文各司其职。",
};

interface AssignmentStrategySelectProps {
  value: AssignmentStrategy;
  onChange: (v: AssignmentStrategy) => void;
  disabled?: boolean;
}

export function AssignmentStrategySelect({ value, onChange, disabled }: AssignmentStrategySelectProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-[12px] text-muted-foreground font-medium">分工策略</label>
      <Select value={value} onValueChange={(v) => onChange(v as AssignmentStrategy)} disabled={disabled}>
        <SelectTrigger className="h-8 w-full text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(STRATEGY_LABELS) as AssignmentStrategy[]).map((k) => (
            <SelectItem key={k} value={k}>
              {STRATEGY_LABELS[k]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-[11px] text-muted-foreground">
        在「人工修改确认」阶段按此策略分配修改确认工作。{STRATEGY_HINT[value]}
      </p>
    </div>
  );
}
