"use client";

import { StyledCheckbox } from "@/components/ui/styled-checkbox";
import type { DAGNodeData, TaskNodeData, NotificationConfig } from "../types";
import { NotificationsConfigPanel } from "./NotificationsConfigPanel";

interface AIGenerateConfigPanelProps {
  data: DAGNodeData | TaskNodeData;
  onUpdate: (partial: Partial<DAGNodeData | TaskNodeData>) => void;
}

export function AIGenerateConfigPanel({ data, onUpdate }: AIGenerateConfigPanelProps) {
  const chapterId = (data as Record<string, unknown>).chapterId as string ?? "";
  const wordCountTarget = (data as Record<string, unknown>).wordCountTarget as number | undefined;
  const generationHint = (data as Record<string, unknown>).generationHint as string ?? "";
  const aiAssist = data.aiAssist ?? true;

  return (
    <div className="p-4 space-y-4">
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">绑定章节 ID</label>
        <input
          type="text"
          value={chapterId}
          onChange={(e) => onUpdate({ chapterId: e.target.value || undefined })}
          placeholder="如: ch1, sec_intro"
          className="w-full px-2.5 py-2 text-xs font-mono border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-300"
        />
      </div>
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">目标字数</label>
        <input
          type="number"
          value={wordCountTarget ?? ""}
          onChange={(e) => onUpdate({ wordCountTarget: e.target.value ? parseInt(e.target.value) : undefined })}
          placeholder="不限制"
          className="w-full px-2.5 py-2 text-xs border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-300"
        />
      </div>
      <div className="space-y-2">
        <label className="text-xs font-semibold text-foreground">撰写提示</label>
        <textarea
          value={generationHint}
          onChange={(e) => onUpdate({ generationHint: e.target.value || undefined })}
          placeholder="对 LLM 的额外指令，如：侧重环境现状分析"
          rows={2}
          className="w-full px-2.5 py-2 text-xs border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-300 resize-none"
        />
      </div>
      <StyledCheckbox checked={aiAssist} onChange={(v) => onUpdate({ aiAssist: v })} label="AI 辅助生成" />
      <NotificationsConfigPanel
        notifications={data.notifications ?? []}
        onUpdate={(notifications: NotificationConfig[]) => onUpdate({ notifications })}
      />
    </div>
  );
}
