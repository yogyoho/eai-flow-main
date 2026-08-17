"use client";

// Collab Workspace — 闸门队列（AgentSpace approvals 双栏布局）
// EAI-CUSTOM: 全新模块。UI 对齐 cyber 主题。

import { Check, X, RotateCcw, Bot } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { workspaceApi } from "../api";
import type { CollabGate } from "../types";

const STATE_LABEL: Record<string, string> = {
  pending: "待审批",
  approved: "已批准",
  rejected: "已驳回",
};
const STATE_TONE: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-500",
  approved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-red-500/10 text-red-500",
};

interface ApprovalsQueueProps {
  projectId: string;
}

export function ApprovalsQueue({ projectId }: ApprovalsQueueProps) {
  const [gates, setGates] = useState<CollabGate[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await workspaceApi.listGates(projectId);
      setGates(data);
    } catch {
      toast.error("加载闸门失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered =
    filter === "all" ? gates : gates.filter((g) => g.state === filter);
  const selected = gates.find((g) => g.id === selectedId) ?? null;

  const judge = async (action: "approve" | "reject") => {
    if (!selected) return;
    try {
      await workspaceApi.judgeGate(
        projectId,
        selected.id,
        action,
        comment || undefined,
      );
      toast.success(action === "approve" ? "已批准" : "已驳回");
      setComment("");
      setSelectedId(null);
      void load();
    } catch {
      toast.error("操作失败");
    }
  };

  const reopen = async (gateId: string) => {
    try {
      await workspaceApi.reopenGate(projectId, gateId);
      toast.success("已重新打开");
      void load();
    } catch {
      toast.error("失败");
    }
  };

  const FILTERS = [
    { key: "all", label: "全部" },
    { key: "pending", label: "待审批" },
    { key: "approved", label: "已批准" },
    { key: "rejected", label: "已驳回" },
  ];

  if (loading) {
    return (
      <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
        加载中...
      </div>
    );
  }

  return (
    <div className="flex h-full" style={{ minHeight: 0 }}>
      {/* List pane */}
      <div
        className="flex w-80 shrink-0 flex-col border-r"
        style={{ borderColor: "var(--cyber-border-muted)" }}
      >
        <div
          className="flex flex-wrap gap-1 border-b p-3"
          style={{ borderColor: "var(--cyber-border-muted)" }}
        >
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`cursor-pointer rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                filter === f.key
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              {f.label}
              <span className="ml-1 text-[10px]">
                {
                  gates.filter((g) => f.key === "all" || g.state === f.key)
                    .length
                }
              </span>
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-auto">
          {filtered.map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => setSelectedId(g.id)}
              className={`hover:bg-muted/30 w-full cursor-pointer border-b p-3 text-left transition ${selectedId === g.id ? "bg-primary/5" : ""}`}
              style={{ borderColor: "var(--cyber-border-muted)" }}
            >
              <div className="flex items-center justify-between">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${STATE_TONE[g.state] ?? ""}`}
                >
                  {STATE_LABEL[g.state] ?? g.state}
                </span>
                <span className="text-muted-foreground font-mono text-[10px]">
                  {g.scope === "task" ? "任务闸门" : "发布闸门"}
                </span>
              </div>
              <p
                className="mt-1 text-sm font-bold"
                style={{ color: "var(--cyber-text-main)" }}
              >
                {g.scope === "task"
                  ? `任务闸门 #${g.taskId?.slice(0, 8) ?? ""}`
                  : "项目发布闸门"}
              </p>
              <p className="text-muted-foreground mt-0.5 font-mono text-[11px]">
                {g.participants
                  ?.map((p) =>
                    p.type === "agent"
                      ? `🤖${p.agent_name ?? p.agentName ?? ""}`
                      : "👤",
                  )
                  .join(" · ")}
              </p>
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="text-muted-foreground p-6 text-center text-xs">
              无闸门
            </div>
          )}
        </div>
      </div>

      {/* Detail pane */}
      <div className="flex-1 overflow-auto p-5">
        {!selected ? (
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            选择左侧闸门查看详情
          </div>
        ) : (
          <div className="max-w-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2
                className="text-base font-bold"
                style={{ color: "var(--cyber-text-main)" }}
              >
                {selected.scope === "task" ? "任务闸门" : "项目发布闸门"}
              </h2>
              <span
                className={`rounded px-2 py-0.5 text-xs font-bold ${STATE_TONE[selected.state] ?? ""}`}
              >
                {STATE_LABEL[selected.state] ?? selected.state}
              </span>
            </div>

            <div
              className="mb-4 rounded-xl border p-4"
              style={{
                background: "var(--cyber-bg-secondary)",
                borderColor: "var(--cyber-border-muted)",
              }}
            >
              <p
                className="font-cyber mb-2 text-[10px] tracking-widest uppercase"
                style={{ color: "var(--cyber-text-muted)" }}
              >
                参与者 PARTICIPANTS
              </p>
              <div className="flex flex-col gap-1.5">
                {selected.participants?.map((p, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 font-mono text-xs"
                  >
                    {p.type === "agent" ? (
                      <Bot className="h-3.5 w-3.5 text-purple-400" />
                    ) : (
                      <span>👤</span>
                    )}
                    <span>
                      {p.type === "agent"
                        ? (p.agent_name ?? p.agentName ?? "")
                        : (p.user_id ?? p.userId ?? "")}
                    </span>
                    <span className="text-muted-foreground">
                      权重 {p.weight}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div
              className="mb-4 rounded-xl border p-4"
              style={{
                background: "var(--cyber-bg-secondary)",
                borderColor: "var(--cyber-border-muted)",
              }}
            >
              <p
                className="font-cyber mb-2 text-[10px] tracking-widest uppercase"
                style={{ color: "var(--cyber-text-muted)" }}
              >
                模式 MODE
              </p>
              <p className="font-mono text-xs">{selected.mode}</p>
              {selected.deadlineAt && (
                <p className="text-muted-foreground mt-1 font-mono text-xs">
                  截止 {new Date(selected.deadlineAt).toLocaleString("zh-CN")}
                </p>
              )}
            </div>

            {selected.state === "pending" ? (
              <div className="flex flex-col gap-2">
                <textarea
                  className="border-input bg-background flex min-h-[72px] w-full rounded-md border px-3 py-2 text-sm"
                  placeholder="审批意见（可选）"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => judge("approve")}
                    className="flex-1"
                  >
                    <Check className="mr-1 h-4 w-4" /> 批准
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => judge("reject")}
                    className="flex-1"
                  >
                    <X className="mr-1 h-4 w-4" /> 驳回
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => reopen(selected.id)}
                >
                  <RotateCcw className="mr-1 h-4 w-4" /> 重新打开
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
