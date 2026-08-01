"use client";

// Collab Workspace 首页 — 项目列表（AgentSpace 布局 + dashboard 样式）
// EAI-CUSTOM: 全新模块

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, FolderKanban, FileText, Users, Clock } from "lucide-react";
import { toast } from "sonner";

import "@/extensions/dashboard/dashboard.css";
import { Button } from "@/components/ui/button";

import { workspaceApi } from "./api";
import type { CollabProject } from "./types";

const TIER_LABEL: Record<string, string> = {
  tier1: "速写",
  tier2: "协作",
  tier3: "正式",
};

export function WorkspaceHome() {
  const router = useRouter();
  const [projects, setProjects] = useState<CollabProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"quickdoc" | "report">("quickdoc");
  const [showCreate, setShowCreate] = useState(false);

  const load = async () => {
    try {
      const data = await workspaceApi.listProjects();
      setProjects(data);
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error("请输入项目名称");
      return;
    }
    setCreating(true);
    try {
      const p = await workspaceApi.createProject(name.trim(), kind);
      toast.success("项目已创建");
      router.push(`/agentspace/${p.id}`);
    } catch {
      toast.error("创建失败");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="dashboard-shell cyber-grid" style={{ minHeight: "100vh", padding: "24px" }}>
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-cyber text-xl font-bold tracking-widest" style={{ color: "var(--db-text-primary)" }}>
            协作工作台 <span className="text-primary">COLLAB WORKSPACE</span>
          </h1>
          <p className="text-xs font-mono mt-1" style={{ color: "var(--db-text-muted)" }}>
            项目 · 任务 · 数字员工 · 闸门
          </p>
        </div>
        <Button size="sm" onClick={() => setShowCreate((v) => !v)}>
          <Plus className="h-4 w-4 mr-1" /> 新建项目
        </Button>
      </header>

      {showCreate && (
        <div className="db-card p-4 mb-6 max-w-md">
          <div className="flex flex-col gap-3">
            <input
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
              placeholder="项目名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <div className="flex gap-2">
              {(["quickdoc", "report"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-xs font-bold transition ${
                    kind === k ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
                  }`}
                >
                  {k === "quickdoc" ? "快速文档" : "多章节报告"}
                </button>
              ))}
            </div>
            <Button onClick={handleCreate} disabled={creating} className="w-full">
              {creating ? "创建中..." : "创建"}
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">加载中...</div>
      ) : projects.length === 0 ? (
        <div className="db-card p-10 text-center">
          <p className="text-sm text-muted-foreground">还没有项目。新建一个快速文档或报告项目开始。</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => router.push(`/agentspace/${p.id}`)}
              className="db-card p-4 text-left transition hover:border-primary/40 hover:shadow-lg cursor-pointer group"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  {p.kind === "quickdoc" ? (
                    <FileText className="h-4 w-4 text-cyan-400" />
                  ) : (
                    <FolderKanban className="h-4 w-4 text-purple-400" />
                  )}
                  <span className="text-sm font-bold group-hover:text-primary" style={{ color: "var(--db-text-primary)" }}>
                    {p.name}
                  </span>
                </div>
                <span className="text-[10px] uppercase font-cyber px-2 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary font-bold tracking-widest">
                  {TIER_LABEL[p.tierState] ?? p.tierState}
                </span>
              </div>
              <div className="flex items-center gap-3 text-[11px] font-mono mt-3" style={{ color: "var(--db-text-muted)" }}>
                <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" />{p.memberCount}</span>
                <span className="inline-flex items-center gap-1"><FileText className="h-3 w-3" />{p.kind === "quickdoc" ? "单文档" : `${p.sectionCount} 章节`}</span>
                <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{p.updatedAt ? new Date(p.updatedAt).toLocaleDateString("zh-CN") : "—"}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
