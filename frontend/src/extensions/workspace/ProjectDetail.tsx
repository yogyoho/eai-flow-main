"use client";

// Collab Workspace 项目详情 — AgentSpace 布局（Tab：概览/文档/任务/闸门/成员）
// EAI-CUSTOM: 全新模块。UI 样式对齐项目详情页 (extensions/project/ProjectWorkspace) — cyber 主题

import {
  ArrowLeft,
  LayoutDashboard,
  FileText,
  KanbanSquare,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { workspaceApi } from "./api";
import { ApprovalsQueue } from "./components/ApprovalsQueue";
import { MembersPane } from "./components/MembersPane";
import { QuickDocEditor } from "./components/QuickDocEditor";
import { TaskBoard } from "./components/TaskBoard";
import type { CollabProject } from "./types";

const TIER_LABEL: Record<string, string> = {
  tier1: "速写",
  tier2: "协作",
  tier3: "正式",
};

const STATUS_LABEL: Record<string, string> = {
  active: "进行中",
  submitted_for_release: "待发布",
  released: "已发布",
  archived: "已归档",
};

// Per-tab neon active style — matches SciFiProjectDetail / ProjectWorkspace pill bar
const TAB_NEON: Record<string, string> = {
  overview:
    "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(7,70,255,0.3)]",
  editor: "bg-[#7c3aed] text-white shadow-[0_0_10px_rgba(124,58,237,0.3)]",
  tasks: "bg-[#0891b2] text-white shadow-[0_0_10px_rgba(8,145,178,0.3)]",
  gates: "bg-success text-white shadow-[0_0_10px_rgba(82,196,26,0.3)]",
  members: "bg-warning text-white shadow-[0_0_10px_rgba(245,158,11,0.3)]",
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
    void load();
  }, [load]);

  const TABS = [
    { id: "overview", label: "概览", icon: LayoutDashboard },
    { id: "editor", label: "文档", icon: FileText },
    { id: "tasks", label: "任务", icon: KanbanSquare },
    { id: "gates", label: "闸门", icon: ShieldCheck },
    { id: "members", label: "成员", icon: Users },
  ];

  if (loading) {
    return (
      <div
        className="flex h-full items-center justify-center text-sm"
        style={{ color: "var(--cyber-text-muted)" }}
      >
        加载中...
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-destructive text-sm">项目不存在</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/agentspace")}
        >
          返回列表
        </Button>
      </div>
    );
  }

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "var(--cyber-bg-primary)" }}
    >
      {/* Header — cyber-themed, matches ProjectWorkspace */}
      <header
        className="flex shrink-0 flex-col px-6 pt-3 pb-4"
        style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
      >
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          {/* Left: back button + title + subtitle */}
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => router.push("/agentspace")}
              className="group flex shrink-0 cursor-pointer items-center justify-center rounded-lg border p-2"
              style={{
                background: "var(--cyber-bg-tertiary)",
                borderColor: "var(--cyber-border-muted)",
                color: "var(--cyber-text-muted)",
              }}
            >
              <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
            </button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1
                  className="truncate text-xl font-bold tracking-tight"
                  style={{ color: "var(--cyber-text-main)" }}
                >
                  {project.name}
                </h1>
                <span className="border-primary/30 bg-primary/10 text-primary font-cyber shrink-0 rounded border px-2.5 py-0.5 text-[10px] font-bold tracking-widest uppercase">
                  {TIER_LABEL[project.tierState] ?? project.tierState}
                </span>
                <span className="border-border bg-muted text-muted-foreground shrink-0 rounded border px-2 py-0.5 text-[10px] font-bold">
                  {project.kind === "quickdoc" ? "快速文档" : "报告"}
                </span>
              </div>
              <p
                className="mt-1 font-mono text-[11px]"
                style={{ color: "var(--cyber-text-muted)" }}
              >
                {STATUS_LABEL[project.status] ?? project.status}
                <span className="mx-1.5">•</span>
                {project.sectionCount} 章节
                <span className="mx-1.5">•</span>
                {project.taskCount} 任务
                <span className="mx-1.5">•</span>
                {project.memberCount} 成员
              </p>
            </div>
          </div>

          {/* Right: tab pill container */}
          <div className="flex shrink-0 items-center gap-2">
            <div
              className="flex items-center gap-2 overflow-x-auto rounded-xl p-1"
              style={{
                background: "var(--cyber-bg-tertiary)",
                border: "1px solid var(--cyber-border-muted)",
              }}
            >
              {TABS.map((t) => {
                const Icon = t.icon;
                const active = tab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTab(t.id)}
                    className={`flex cursor-pointer items-center gap-1 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                      active
                        ? (TAB_NEON[t.id] ??
                          "bg-primary text-primary-foreground")
                        : "hover:bg-muted/50"
                    }`}
                    style={
                      !active ? { color: "var(--cyber-text-muted)" } : undefined
                    }
                  >
                    <Icon className="h-3.5 w-3.5" /> {t.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-auto">
        {tab === "overview" && (
          <OverviewPane project={project} onRefresh={load} />
        )}
        {tab === "editor" && (
          <QuickDocEditor project={project} onRefresh={load} />
        )}
        {tab === "tasks" && <TaskBoard projectId={project.id} />}
        {tab === "gates" && <ApprovalsQueue projectId={project.id} />}
        {tab === "members" && (
          <MembersPane
            projectId={project.id}
            projectName={project.name}
            onRefresh={load}
          />
        )}
      </div>
    </div>
  );
}

function OverviewPane({
  project,
  onRefresh,
}: {
  project: CollabProject;
  onRefresh: () => void;
}) {
  const [tier, setTier] = useState<CollabProject["tierSignals"]>(null);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    workspaceApi
      .getTier(project.id)
      .then((t) => setTier(t.signals))
      .catch(() => undefined);
  }, [project.id]);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      const r = await workspaceApi.publishDoc(project.id);
      toast.success(
        `已发布 ${r.synced.length} 个文档${r.skipped.length ? `，跳过 ${r.skipped.length}` : ""}`,
      );
      onRefresh();
    } catch {
      toast.error("发布失败");
    } finally {
      setPublishing(false);
    }
  };

  const stats = [
    {
      label: "层级 TIER",
      value: TIER_LABEL[project.tierState] ?? project.tierState,
    },
    { label: "章节 SECTIONS", value: project.sectionCount },
    { label: "任务 TASKS", value: project.taskCount },
    { label: "成员 MEMBERS", value: project.memberCount },
  ];

  return (
    <div className="max-w-4xl p-6">
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-xl border p-4"
            style={{
              background: "var(--cyber-bg-secondary)",
              borderColor: "var(--cyber-border-muted)",
            }}
          >
            <p
              className="font-cyber text-[10px] tracking-widest uppercase"
              style={{ color: "var(--cyber-text-muted)" }}
            >
              {s.label}
            </p>
            <p
              className="mt-1 text-2xl font-bold"
              style={{ color: "var(--cyber-text-main)" }}
            >
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {tier && tier.length > 0 && (
        <div
          className="mb-6 rounded-xl border p-4"
          style={{
            background: "var(--cyber-bg-secondary)",
            borderColor: "var(--cyber-border-muted)",
          }}
        >
          <p
            className="font-cyber mb-2 text-[10px] tracking-widest uppercase"
            style={{ color: "var(--cyber-text-muted)" }}
          >
            升级信号 ESCALATION
          </p>
          <div className="flex flex-col gap-2">
            {tier.map((s, i) => (
              <div
                key={i}
                className="flex items-center gap-2 font-mono text-xs"
              >
                <span className="border-primary/30 bg-primary/10 text-primary rounded border px-2 py-0.5 font-bold">
                  {s.signal}
                </span>
                <span style={{ color: "var(--cyber-text-muted)" }}>→</span>
                <span style={{ color: "var(--cyber-text-main)" }}>
                  {TIER_LABEL[s.to] ?? s.to}
                </span>
                <span style={{ color: "var(--cyber-text-muted)" }}>{s.at}</span>
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
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            try {
              await workspaceApi.release(project.id);
              toast.success("已提交发布");
              onRefresh();
            } catch {
              toast.error("发布提交失败");
            }
          }}
        >
          提交发布
        </Button>
      </div>
    </div>
  );
}
