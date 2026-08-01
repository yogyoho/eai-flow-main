"use client";

// Collab Workspace 项目详情 — AgentSpace 布局（Tab：概览/文档/任务/闸门/成员）
// EAI-CUSTOM: 全新模块

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, LayoutDashboard, FileText, KanbanSquare, ShieldCheck, Users, Settings } from "lucide-react";
import { toast } from "sonner";

import "@/extensions/dashboard/dashboard.css";
import { Button } from "@/components/ui/button";

import { workspaceApi } from "./api";
import type { CollabProject } from "./types";
import { TaskBoard } from "./components/TaskBoard";
import { ApprovalsQueue } from "./components/ApprovalsQueue";
import { MembersPane } from "./components/MembersPane";
import { QuickDocEditor } from "./components/QuickDocEditor";

const TIER_LABEL: Record<string, string> = {
  tier1: "速写",
  tier2: "协作",
  tier3: "正式",
};

interface ProjectDetailProps {
  projectId: string;
}

export function ProjectDetail({ projectId }: ProjectDetailProps) {
  const router = useRouter();
  const [project, setProject] = useState<CollabProject | null>(null);
  const [tab, setTab] = useState<string>("overview");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await workspaceApi.getProject(projectId);
      setProject(data);
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const TABS = [
    { id: "overview", label: "概览", icon: LayoutDashboard },
    { id: "editor", label: "文档", icon: FileText },
    { id: "tasks", label: "任务", icon: KanbanSquare },
    { id: "gates", label: "闸门", icon: ShieldCheck },
    { id: "members", label: "成员", icon: Users },
  ];

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">加载中...</div>;
  }

  if (!project) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3">
        <p className="text-sm text-destructive">项目不存在</p>
        <Button variant="outline" size="sm" onClick={() => router.push("/agentspace")}>返回列表</Button>
      </div>
    );
  }

  return (
    <div className="dashboard-shell cyber-grid flex h-screen flex-col" style={{ padding: "0" }}>
      {/* Header — AgentSpace style */}
      <header className="flex items-center justify-between px-6 py-3 shrink-0 border-b" style={{ borderColor: "var(--db-border)" }}>
        <div className="flex items-center gap-3 min-w-0">
          <button type="button" onClick={() => router.push("/agentspace")} className="p-2 rounded-lg border border-border cursor-pointer hover:bg-muted/50">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="font-cyber text-lg font-bold tracking-widest truncate" style={{ color: "var(--db-text-primary)" }}>
                {project.name}
              </h1>
              <span className="text-[10px] uppercase font-cyber px-2 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary font-bold tracking-widest">
                {TIER_LABEL[project.tierState] ?? project.tierState}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-muted border border-border text-muted-foreground font-bold">
                {project.kind === "quickdoc" ? "快速文档" : "报告"}
              </span>
            </div>
            <p className="text-[11px] font-mono mt-0.5" style={{ color: "var(--db-text-muted)" }}>
              {project.status} · {project.sectionCount} 章节 · {project.taskCount} 任务 · {project.memberCount} 成员
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1 p-1 rounded-xl border border-border" style={{ background: "var(--db-bg-tertiary)" }}>
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1 ${
                  active ? "bg-primary text-primary-foreground" : "hover:bg-muted/50 text-muted-foreground"
                }`}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>
      </header>

      <div className="flex-1 overflow-auto">
        {tab === "overview" && <OverviewPane project={project} onRefresh={load} />}
        {tab === "editor" && <QuickDocEditor project={project} onRefresh={load} />}
        {tab === "tasks" && <TaskBoard projectId={project.id} />}
        {tab === "gates" && <ApprovalsQueue projectId={project.id} />}
        {tab === "members" && <MembersPane projectId={project.id} projectName={project.name} onRefresh={load} />}
      </div>
    </div>
  );
}

function OverviewPane({ project, onRefresh }: { project: CollabProject; onRefresh: () => void }) {
  const [tier, setTier] = useState<CollabProject["tierSignals"]>(null);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    workspaceApi.getTier(project.id).then((t) => setTier(t.signals)).catch(() => {});
  }, [project.id]);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      const r = await workspaceApi.publishDoc(project.id);
      toast.success(`已发布 ${r.synced.length} 个文档${r.skipped.length ? `，跳过 ${r.skipped.length}` : ""}`);
      onRefresh();
    } catch {
      toast.error("发布失败");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="p-6 max-w-4xl">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="db-card p-4">
          <p className="text-[10px] uppercase font-cyber tracking-widest text-muted-foreground">层级 TIER</p>
          <p className="text-2xl font-bold mt-1" style={{ color: "var(--db-text-primary)" }}>{TIER_LABEL[project.tierState]}</p>
        </div>
        <div className="db-card p-4">
          <p className="text-[10px] uppercase font-cyber tracking-widest text-muted-foreground">章节 SECTIONS</p>
          <p className="text-2xl font-bold mt-1" style={{ color: "var(--db-text-primary)" }}>{project.sectionCount}</p>
        </div>
        <div className="db-card p-4">
          <p className="text-[10px] uppercase font-cyber tracking-widest text-muted-foreground">任务 TASKS</p>
          <p className="text-2xl font-bold mt-1" style={{ color: "var(--db-text-primary)" }}>{project.taskCount}</p>
        </div>
        <div className="db-card p-4">
          <p className="text-[10px] uppercase font-cyber tracking-widest text-muted-foreground">成员 MEMBERS</p>
          <p className="text-2xl font-bold mt-1" style={{ color: "var(--db-text-primary)" }}>{project.memberCount}</p>
        </div>
      </div>

      {tier && tier.length > 0 && (
        <div className="db-card p-4 mb-6">
          <p className="text-[10px] uppercase font-cyber tracking-widest text-muted-foreground mb-2">升级信号 ESCALATION</p>
          <div className="flex flex-col gap-2">
            {tier.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs font-mono">
                <span className="px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/30 font-bold">
                  {s.signal}
                </span>
                <span className="text-muted-foreground">→</span>
                <span>{TIER_LABEL[s.to] ?? s.to}</span>
                <span className="text-muted-foreground">{s.at}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <Button size="sm" onClick={handlePublish} disabled={publishing}>
          {publishing ? "发布中..." : "发布文档 (publish-doc)"}
        </Button>
        {project.kind === "quickdoc" && (
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              try {
                await workspaceApi.promoteToReport(project.id);
                toast.success("已升级为报告");
                onRefresh();
              } catch {
                toast.error("升级失败");
              }
            }}
          >
            升级为报告
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={async () => {
          try {
            await workspaceApi.release(project.id);
            toast.success("已提交发布");
            onRefresh();
          } catch { toast.error("发布提交失败"); }
        }}>
          提交发布
        </Button>
      </div>
    </div>
  );
}
