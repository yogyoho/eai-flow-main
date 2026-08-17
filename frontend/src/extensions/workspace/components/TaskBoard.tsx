"use client";

// Collab Workspace — 任务板（AgentSpace Kanban：按状态/负责人分组 + 拖拽 + 统计行）
// EAI-CUSTOM: 全新模块，Kanban 组件为 workspace 自有副本（零引用 extensions/project）。UI 对齐 cyber 主题。

import { Plus, Bot, User, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { workspaceApi } from "../api";
import type { CollabTask, TaskStatus } from "../types";

const COLUMNS: { key: TaskStatus; label: string }[] = [
  { key: "pending", label: "待办" },
  { key: "in_progress", label: "进行中" },
  { key: "done", label: "完成" },
  { key: "blocked", label: "阻塞" },
];

interface TaskBoardProps {
  projectId: string;
}

export function TaskBoard({ projectId }: TaskBoardProps) {
  const [tasks, setTasks] = useState<CollabTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [groupBy, setGroupBy] = useState<"status" | "assignee">("status");
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [agentName, setAgentName] = useState("");
  const [spawning, setSpawning] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await workspaceApi.listTasks(projectId);
      setTasks(data);
    } catch {
      toast.error("加载任务失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const createTask = async () => {
    if (!title.trim()) return;
    try {
      const t = await workspaceApi.createTask(projectId, {
        title: title.trim(),
        kind: "section_write",
      });
      setTasks((prev) => [...prev, t]);
      setTitle("");
      setShowCreate(false);
      toast.success("任务已创建");
    } catch {
      toast.error("创建失败");
    }
  };

  const handleAssignAgent = async (taskId: string) => {
    const name = agentName.trim();
    if (!name) {
      toast.error("请输入 agent_name");
      return;
    }
    try {
      await workspaceApi.assignTask(projectId, taskId, {
        assigneeType: "agent",
        agentName: name,
      });
      toast.success("已指派给 agent");
      void load();
    } catch {
      toast.error("指派失败");
    }
  };

  const handleSpawnRun = async (taskId: string) => {
    setSpawning(taskId);
    try {
      const r = await workspaceApi.spawnRun(projectId, taskId, {});
      toast.success(`agent run 已启动（${r.status}）`);
      void load();
    } catch {
      toast.error("启动失败（请确认 task 已指派给 agent）");
    } finally {
      setSpawning(null);
    }
  };

  const columns = useMemo(() => {
    if (groupBy === "assignee") {
      const byAssignee = new Map<string, CollabTask[]>();
      for (const t of tasks) {
        const key = t.assigneeAgentName
          ? `agent:${t.assigneeAgentName}`
          : t.assigneeUserId
            ? "人类"
            : "未指派";
        byAssignee.set(key, [...(byAssignee.get(key) ?? []), t]);
      }
      return Array.from(byAssignee.entries()).map(([key, items]) => ({
        key,
        label: key,
        items,
      }));
    }
    return COLUMNS.map((c) => ({
      key: c.key,
      label: c.label,
      items: tasks.filter((t) => t.status === c.key),
    }));
  }, [tasks, groupBy]);

  if (loading) {
    return (
      <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
        加载中...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col p-6" style={{ minHeight: 0 }}>
      <div className="mb-4 flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-2">
          {(["status", "assignee"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGroupBy(g)}
              className={`cursor-pointer rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                groupBy === g
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground"
              }`}
            >
              {g === "status" ? "按状态" : "按负责人"}
            </button>
          ))}
          <span
            className="ml-2 font-mono text-xs"
            style={{ color: "var(--cyber-text-muted)" }}
          >
            {tasks.length} 个任务 ·{" "}
            {tasks.filter((t) => t.status === "done").length} 完成
          </span>
        </div>
        <Button size="sm" onClick={() => setShowCreate((v) => !v)}>
          <Plus className="mr-1 h-4 w-4" /> 新建任务
        </Button>
      </div>

      {showCreate && (
        <div
          className="mb-4 max-w-md shrink-0 rounded-xl border p-3"
          style={{
            background: "var(--cyber-bg-secondary)",
            borderColor: "var(--cyber-border-muted)",
          }}
        >
          <div className="flex gap-2">
            <input
              className="border-input bg-background flex h-9 flex-1 rounded-md border px-3 py-1 text-sm"
              placeholder="任务标题"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createTask()}
            />
            <Button size="sm" onClick={createTask}>
              创建
            </Button>
          </div>
        </div>
      )}

      <div
        className="flex flex-1 gap-4 overflow-x-auto"
        style={{ minHeight: 0 }}
      >
        {columns.map((col) => (
          <div
            key={col.key}
            className="flex w-64 shrink-0 flex-col"
            style={{ minHeight: 0 }}
          >
            <div className="mb-2 flex items-center justify-between">
              <span
                className="text-xs font-bold"
                style={{ color: "var(--cyber-text-main)" }}
              >
                {col.label}
              </span>
              <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono text-[10px]">
                {col.items.length}
              </span>
            </div>
            <div
              className="flex flex-1 flex-col gap-2 overflow-auto"
              style={{ minHeight: 0 }}
            >
              {col.items.map((t) => (
                <div
                  key={t.id}
                  className="rounded-xl border p-3"
                  style={{
                    background: "var(--cyber-bg-secondary)",
                    borderColor: "var(--cyber-border-muted)",
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h4
                      className="text-sm font-bold"
                      style={{ color: "var(--cyber-text-main)" }}
                    >
                      {t.title}
                    </h4>
                    <span className="shrink-0">
                      {t.assigneeType === "agent" ? (
                        <Bot className="h-3.5 w-3.5 text-purple-400" />
                      ) : (
                        <User className="h-3.5 w-3.5 text-cyan-400" />
                      )}
                    </span>
                  </div>
                  <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
                    {t.assigneeAgentName && (
                      <span className="rounded border border-purple-500/30 bg-purple-500/10 px-1.5 py-0.5 text-purple-400">
                        {t.assigneeAgentName}
                      </span>
                    )}
                    {t.handoffState && (
                      <span className="bg-muted rounded px-1.5 py-0.5">
                        交接:{t.handoffState}
                      </span>
                    )}
                    {t.lastError && (
                      <span
                        className="rounded bg-red-500/10 px-1.5 py-0.5 text-red-400"
                        title={t.lastError}
                      >
                        错误
                      </span>
                    )}
                  </div>
                  {t.assigneeType === "agent" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2 w-full"
                      disabled={spawning === t.id}
                      onClick={() => handleSpawnRun(t.id)}
                    >
                      {spawning === t.id ? (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      ) : null}
                      启动 agent 执行
                    </Button>
                  ) : (
                    <div className="mt-2 flex gap-1">
                      <input
                        className="border-input bg-background flex h-7 flex-1 rounded-md border px-2 text-xs"
                        placeholder="agent_name"
                        value={agentName}
                        onChange={(e) => setAgentName(e.target.value)}
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAssignAgent(t.id)}
                      >
                        指派
                      </Button>
                    </div>
                  )}
                </div>
              ))}
              {col.items.length === 0 && (
                <div className="text-muted-foreground rounded-lg border border-dashed p-3 text-center text-xs">
                  空
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
