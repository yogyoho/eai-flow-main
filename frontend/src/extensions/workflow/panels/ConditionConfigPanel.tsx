"use client";

import type { DAGNodeData, NotificationConfig } from "../types";

import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface ConditionConfigPanelProps {
  data: DAGNodeData;
  onUpdate: (partial: Partial<DAGNodeData>) => void;
}

const EXPR_PRESETS: { label: string; value: string }[] = [
  { label: "始终通过", value: "true" },
  { label: "始终拒绝", value: "false" },
  { label: "项目属性", value: "report." },
  { label: "章节谓词", value: "chapter.{id}." },
  { label: "阶段状态", value: "phase.{id}." },
  { label: "AI 评估", value: "ai: " },
];

export function ConditionConfigPanel({
  data,
  onUpdate,
}: ConditionConfigPanelProps) {
  const expression = data.expression ?? "";

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-2">
        <label className="text-foreground text-xs font-semibold">
          条件表达式
        </label>
        <textarea
          value={expression}
          onChange={(e) => onUpdate({ expression: e.target.value })}
          placeholder="如: chapter.ch1.word_count_current > 5000"
          rows={3}
          className="border-border w-full resize-none rounded-lg border px-2.5 py-2 font-mono text-xs focus:ring-1 focus:ring-amber-300 focus:outline-none"
        />
      </div>
      <div className="space-y-1">
        <label className="text-muted-foreground text-[10px] font-medium">
          快捷表达式
        </label>
        <div className="flex flex-wrap gap-1">
          {EXPR_PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => onUpdate({ expression: p.value })}
              className={`rounded border px-2 py-1 text-[10px] transition-colors ${
                expression === p.value
                  ? "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                  : "border-border text-muted-foreground hover:border-amber-200 hover:bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/40"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div className="text-muted-foreground bg-muted/30 space-y-1 rounded-lg p-2 text-[10px]">
        <p className="mb-1 text-xs font-medium">格式说明：</p>
        <p>
          <code>true</code> / <code>false</code> — 字面量
        </p>
        <p>
          <code>report.status</code> — 项目属性
        </p>
        <p>
          <code>chapter.ch1.word_count_current &gt; 5000</code> — 章节谓词
        </p>
        <p>
          <code>phase.p1.reviews_approved</code> — 阶段状态
        </p>
        <p>
          <code>ai: 报告是否需要补充环评分析？</code> — AI 评估
        </p>
      </div>
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) =>
          onUpdate({ notifications })
        }
      />
    </div>
  );
}
