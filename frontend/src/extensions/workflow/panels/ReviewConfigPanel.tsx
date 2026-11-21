"use client";

import { ShieldCheck } from "lucide-react";

import type { DAGNodeData, NotificationConfig } from "../types";

import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

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
    <div className="space-y-4 p-4">
      {/* Section header */}
      <div className="flex items-center gap-2">
        <div className="h-4 w-1 rounded-full bg-red-500" />
        <span className="text-xs font-semibold tracking-wider text-red-600 uppercase dark:text-red-400">
          审核属性
        </span>
      </div>

      {/* Review name */}
      <div className="space-y-1.5">
        <label className="text-muted-foreground text-xs font-medium">
          审核名称
        </label>
        <input
          value={data.label || ""}
          onChange={(e) => onUpdate({ label: e.target.value })}
          className="border-border bg-background w-full rounded-md border px-2.5 py-1.5 text-sm transition-colors focus:border-red-400 focus:ring-2 focus:ring-red-500/20 focus:outline-none"
        />
      </div>

      {/* Review mode — radio group styled as cards */}
      <div className="space-y-1.5">
        <label className="text-muted-foreground text-xs font-medium">
          审核模式
        </label>
        <div className="mt-1 space-y-2">
          {MODES.map((mode) => {
            const isSelected = data.mode === mode.value;
            return (
              <label
                key={mode.value}
                className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-all ${
                  isSelected
                    ? "border-red-300 bg-red-50/60 shadow-sm dark:border-red-700"
                    : "border-border bg-background hover:border-red-200 hover:bg-red-50/30 dark:border-red-800"
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
                  <div
                    className={`text-xs font-medium ${isSelected ? "text-red-700 dark:text-red-300" : "text-foreground"}`}
                  >
                    {mode.label}
                  </div>
                  <div className="text-muted-foreground mt-0.5 text-[10px]">
                    {mode.desc}
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </div>

      {/* Info box */}
      <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
        <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>审核人分配将在工作流启动后，由经理在工作台配置</span>
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
