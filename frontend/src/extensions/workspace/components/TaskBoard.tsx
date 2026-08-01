"use client";

// Collab Workspace — 任务板（AgentSpace Kanban：按状态/负责人分组 + 拖拽 + 统计行）
// EAI-CUSTOM: 全新模块，Kanban 组件为 workspace 自有副本（零引用 extensions/project）

import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Bot, User, Loader2 } from "lucide-react";
import { toast } from "sonner";

import "@/extensions/dashboard/dashboard.css";
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
    load();
  }, [load]);

  const createTask = async () => {
    if (!title.trim()) return;
    try {
      const t = await workspaceApi.createTask(projectId, { title: title.trim(), kind: "section_write" });
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
      await workspaceApi.assignTask(projectId, taskId, { assigneeType: "agent", agentName: name });
      toast.success("已指派给 agent");
      load();
    } catch {
      toast.error("指派失败");
    }
  };

  const handleSpawnRun = async (taskId: string) => {
    setSpawning(taskId);
    try {
      const r = await workspaceApi.spawnRun(projectId, taskId, {});
      toast.success(`agent run 已启动（${r.status}）`);
      load();
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
        const key = t.assigneeAgentName ? `agent:${t.assigneeAgentName}` : t.assigneeUserId ? "人类" : "未指派";
        byAssignee.set(key, [...(byAssignee.get(key) ?? []), t]);
      }
      return Array.from(byAssignee.entries()).map(([key, items]) => ({ key, label: key, items }));
    }
    return COLUMNS.map((c) => ({
      key: c.key,
      label: c.label,
      items: tasks.filter((t) => t.status === c.key),
    }));
  }, [tasks, groupBy]);

  if (loading) {
    return <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="p-6 flex flex-col h-full" style={{ minHeight: 0 }}>
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-2">
          {(["status", "assignee"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGroupBy(g)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition cursor-pointer ${
                groupBy === g ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
              }`}
            >
              {g === "status" ? "按状态" : "按负责人"}
            </button>
          ))}
          <span className="text-xs font-mono text-muted-foreground ml-2">
            {tasks.length} 个任务 · {tasks.filter((t) => t.status === "done").length} 完成
          </span>
        </div>
        <Button size="sm" onClick={() => setShowCreate((v) => !v)}>
          <Plus className="h-4 w-4 mr-1" /> 新建任务
        </Button>
      </div>

      {showCreate && (
        <div className="db-card p-3 mb-4 max-w-md shrink-0">
          <div className="flex gap-2">
            <input
              className="flex h-9 flex-1 rounded-md border border-input bg-background px-3 py-1 text-sm"
              placeholder="任务标题"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createTask()}
            />
            <Button size="sm" onClick={createTask}>创建</Button>
          </div>
        </div>
      )}

      <div className="flex gap-4 overflow-x-auto flex-1" style={{ minHeight: 0 }}>
        {columns.map((col) => (
          <div key={col.key} className="flex flex-col w-64 shrink-0" style={{ minHeight: 0 }}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold" style={{ color: "var(--db-text-primary)" }}>{col.label}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">{col.items.length}</span>
            </div>
            <div className="flex flex-col gap-2 flex-1 overflow-auto" style={{ minHeight: 0 }}>
              {col.items.map((t) => (
                <div key={t.id} className="db-card p-3">
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="text-sm font-bold" style={{ color: "var(--db-text-primary)" }}>{t.title}</h4>
                    <span className="shrink-0">
                      {t.assigneeType === "agent" ? <Bot className="h-3.5 w-3.5 text-purple-400" /> : <User className="h-3.5 w-3.5 text-cyan-400" />}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-2 text-[11px] font-mono text-muted-foreground flex-wrap">
                    {t.assigneeAgentName && <span className="px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">{t.assigneeAgentName}</span>}
                    {t.handoffState && <span className="px-1.5 py-0.5 rounded bg-muted">交接:{t.handoffState}</span>}
                    {t.lastError && <span className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400" title={t.lastError}>错误</span>}
                  </div>
                  {t.assigneeType === "agent" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2 w-full"
                      disabled={spawning === t.id}
                      onClick={() => handleSpawnRun(t.id)}
                    >
                      {spawning === t.id ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                      启动 agent 执行
                    </Button>
                  ) : (
                    <div className="mt-2 flex gap-1">
                      <input
                        className="flex h-7 flex-1 rounded-md border border-input bg-background px-2 text-xs"
                        placeholder="agent_name"
                        value={agentName}
                        onChange={(e) => setAgentName(e.target.value)}
                      />
                      <Button size="sm" variant="outline" onClick={() => handleAssignAgent(t.id)}>指派</Button>
                    </div>
                  )}
                </div>
              ))}
              {col.items.length === 0 && (
                <div className="rounded-lg border border-dashed p-3 text-center text-xs text-muted-foreground">空</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
