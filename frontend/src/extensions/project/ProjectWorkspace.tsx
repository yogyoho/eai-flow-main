"use client";

import { ArrowLeft, Loader2, MessageSquare, Settings } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/extensions/hooks/useAuth";
import { projectApi } from "@/extensions/project/api";
import { SettingsDialog } from "@/extensions/project/components/SettingsDialog";
import { createProjectIdentity, getVisibleTabs, type ProjectIdentity } from "@/extensions/project/tabRegistry";
import {
  MEMBER_ROLE_LABELS,
  type ProjectPermissions,
  type ReportProject,
} from "@/extensions/project/types";
import { workflowApi } from "@/extensions/workflow/api";
import { isLegacyGraph, migrateLegacyToUnified } from "@/extensions/workflow/templates/migration";
import type { WorkflowGraph } from "@/extensions/workflow/types";

const OverviewTab = dynamic(() => import("./tabs/OverviewTab").then((m) => ({ default: m.OverviewTab })), { ssr: false });
const EditorTab = dynamic(() => import("./tabs/EditorTab").then((m) => ({ default: m.EditorTab })), { ssr: false });
const ReviewTab = dynamic(() => import("./tabs/ReviewTab").then((m) => ({ default: m.ReviewTab })), { ssr: false });

interface ProjectWorkspaceProps {
  projectId: string;
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [entering, setEntering] = useState(false);
  const [identity, setIdentity] = useState<ProjectIdentity | null>(null);
  const [workflowGraph, setWorkflowGraph] = useState<WorkflowGraph | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [lastSync, setLastSync] = useState<{ time: string; synced: number } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const { user: currentUser } = useAuth();

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      // Retry permissions once on failure (backend sometimes 500s on first call)
      let perms: ProjectPermissions;
      try {
        perms = await projectApi.getMyPermissions(projectId);
      } catch {
        await new Promise((r) => setTimeout(r, 500));
        try {
          perms = await projectApi.getMyPermissions(projectId);
        } catch {
          perms = { role: null, permissions: [], phaseDuties: null, isAdmin: false };
        }
      }
      setProject(data);
      setIdentity(createProjectIdentity(perms));
      // Load workflow graph if project has an associated workflow definition
      if (data.workflowId) {
        workflowApi.get(data.workflowId).then((def) => {
          if (!def.graphJson) { setWorkflowGraph(null); return; }
          const raw = def.graphJson as unknown as Record<string, unknown>;
          setWorkflowGraph(isLegacyGraph(raw)
            ? migrateLegacyToUnified(raw as Parameters<typeof migrateLegacyToUnified>[0])
            : def.graphJson);
        }).catch(() => setWorkflowGraph(null));
      } else if (data.currentPhaseNode || data.temporalWorkflowId) {
        // No workflow_id linked, but project has active Temporal workflow —
        // leave workflowGraph null; WorkflowProgressCompact will fetch status via project-scoped API
        setWorkflowGraph(null);
      } else {
        setWorkflowGraph(null);
      }
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        loadProject();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [loadProject]);

  // Load file count + sync docs (for header subtitle)
  const loadStats = useCallback(async () => {
    try {
      const stats = await projectApi.getStats(projectId);
      setFileCount(stats.documentCount);
    } catch {
      setFileCount(0);
    }
  }, [projectId]);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    try {
      const result = await projectApi.syncDocs(projectId);
      setLastSync({ time: new Date().toLocaleTimeString("zh-CN"), synced: result.synced ?? 0 });
      loadStats();
    } catch {
      // Non-critical
    } finally {
      setSyncing(false);
    }
  }, [projectId, loadStats]);

  useEffect(() => {
    if (project) {
      handleSync();
    }
  }, [project, handleSync]);

  // Header subtitle data
  const totalCount = useMemo(
    () => project?.chapters?.length ?? 0,
    [project?.chapters],
  );

  // Derive visible tabs from identity
  const visibleTabs = identity ? getVisibleTabs(identity) : [];

  // Derive visible chapter IDs from permissions for chapter-level filtering.
  const visibleChapterIds = useMemo(() => {
    if (!identity) return undefined;
    if (identity.projectRole === "owner") return undefined;
    if (identity.hasAnyPermission(["chapter:write_any"])) return undefined;

    if (!identity.phaseDuties) return undefined;
    const ids: string[] = [];
    for (const [key, info] of Object.entries(identity.phaseDuties)) {
      if (info.duty === "writer" || info.duty === "write") {
        ids.push(key.replace(/^chapter-/, ""));
      }
    }
    return ids.length > 0 ? ids : undefined;
  }, [identity]);

  // If activeTab is no longer visible, reset to first visible tab
  useEffect(() => {
    if (visibleTabs.length > 0 && !visibleTabs.some((t) => t.id === activeTab)) {
      setActiveTab(visibleTabs[0]!.id);
    }
  }, [visibleTabs, activeTab]);

  // Listen for switchTab custom events (from OverviewTab chapter edit)
  useEffect(() => {
    const handleSwitchTab = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.tab && visibleTabs.some((t) => t.id === detail.tab)) {
        setActiveTab(detail.tab);
      }
    };
    window.addEventListener("switchTab", handleSwitchTab);
    return () => window.removeEventListener("switchTab", handleSwitchTab);
  }, [visibleTabs]);

  const canSeeSettings = identity?.isAdmin ||
    identity?.hasAnyPermission(["settings:edit", "project:edit", "project:delete"]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-sm text-destructive">项目不存在</p>
        <Link href="/projects">
          <Button variant="outline" size="sm">返回项目列表</Button>
        </Link>
      </div>
    );
  }

  // Shared tab props
  const tabProps = {
    project,
    projectId,
    onRefresh: loadProject,
    identity,
    visibleChapterIds,
    workflowGraph,
  };

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "var(--cyber-bg-primary)" }}
    >
      <header
        className="flex flex-col px-6 shrink-0 pb-4 pt-3"
        style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Left: back button + title + subtitle */}
          <div className="flex items-center gap-3 min-w-0">
            <Link href="/projects">
              <button
                type="button"
                className="p-2 rounded-lg border flex items-center justify-center group cursor-pointer shrink-0"
                style={{
                  background: "var(--cyber-bg-tertiary)",
                  borderColor: "var(--cyber-border-muted)",
                  color: "var(--cyber-text-muted)",
                }}
              >
                <ArrowLeft className="h-4 w-4 group-hover:-translate-x-0.5 transition-transform" />
              </button>
            </Link>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-bold tracking-tight truncate" style={{ color: "var(--cyber-text-main)" }}>
                  {project.name}
                </h1>
                <span className="text-[10px] uppercase font-cyber px-2.5 py-0.5 rounded border border-primary/30 bg-primary/10 text-primary font-bold tracking-widest shrink-0">
                  {project.reportType}
                </span>
                {identity && identity.projectRole && (
                  <span className="text-[10px] px-2 py-0.5 rounded bg-muted border border-border text-muted-foreground font-bold shrink-0">
                    {MEMBER_ROLE_LABELS[identity.projectRole as keyof typeof MEMBER_ROLE_LABELS] ?? identity.projectRole}
                  </span>
                )}
              </div>
              {/* Subtitle — matches SciFiProjectDetail */}
              <p className="text-[11px] font-mono mt-1" style={{ color: "var(--cyber-text-muted)" }}>
                创建于: {project.createdAt
                  ? new Date(project.createdAt).toLocaleDateString("zh-CN")
                  : "未知"}
                <span className="mx-1.5">•</span>
                章节: {totalCount}
                <span className="mx-1.5">•</span>
                文件数: {fileCount !== null ? fileCount : "..."}
                {lastSync && (
                  <>
                    <span className="mx-1.5">•</span>
                    {syncing ? (
                      <span className="inline-flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" />同步中...</span>
                    ) : (
                      <>上次同步: {lastSync.time} · 新增 {lastSync.synced} 个文件</>
                    )}
                  </>
                )}
              </p>
            </div>
          </div>

          {/* Right: tabs + actions */}
          <div className="flex items-center gap-2 shrink-0">
            {/* Tabs in header — cyber-themed matching SciFiProjectDetail */}
            <div
              className="flex items-center gap-2 p-1 rounded-xl overflow-x-auto"
              style={{
                background: "var(--cyber-bg-tertiary)",
                border: "1px solid var(--cyber-border-muted)",
              }}
            >
              {visibleTabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                const activeColors: Record<string, string> = {
                  overview: "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(7,70,255,0.3)]",
                  editor: "bg-[#7c3aed] text-white shadow-[0_0_10px_rgba(124,58,237,0.3)]",
                  review: "bg-success text-white shadow-[0_0_10px_rgba(82,196,26,0.3)]",
                };
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 ${
                      isActive
                        ? (activeColors[tab.id] ?? "bg-primary text-primary-foreground")
                        : "hover:bg-muted/50"
                    }`}
                    style={!isActive ? { color: "var(--cyber-text-muted)" } : undefined}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {tab.label}
                  </button>
                );
              })}

              <div className="h-4 w-[1px] mx-1" style={{ background: "var(--cyber-border-muted)" }} />

              {/* Enter conversation */}
              <button
                type="button"
                disabled={entering}
                onClick={async () => {
                  setEntering(true);
                  try {
                    const { threadId } = await projectApi.enter(projectId);
                    window.open(`/workspace/chats/${threadId}?from=project&projectId=${projectId}&projectName=${encodeURIComponent(project.name)}`, "_blank");
                  } catch {
                    toast.error("进入对话失败");
                  } finally {
                    setEntering(false);
                  }
                }}
                className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-primary hover:opacity-90 text-primary-foreground flex items-center gap-1.5 transition-all shadow-md group cursor-pointer"
              >
                <MessageSquare className="h-3.5 w-3.5 group-hover:scale-110 transition-transform" />
                <span>{entering ? "进入中..." : "进入对话"}</span>
              </button>
            </div>

            {/* Settings gear icon */}
            {canSeeSettings && (
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className="p-1.5 rounded-lg border cursor-pointer"
                style={{
                  background: "var(--cyber-bg-tertiary)",
                  borderColor: "var(--cyber-border-muted)",
                  color: "var(--cyber-text-muted)",
                }}
              >
                <Settings className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-hidden">
        {activeTab === "overview" ? (
          <OverviewTab {...tabProps} />
        ) : activeTab === "editor" ? (
          <EditorTab {...tabProps} />
        ) : activeTab === "review" ? (
          <ReviewTab {...tabProps} />
        ) : null}
      </div>

      {/* Settings Dialog */}
      <SettingsDialog
        project={project}
        projectId={projectId}
        onRefresh={loadProject}
        identity={identity}
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
      />
    </div>
  );
}
