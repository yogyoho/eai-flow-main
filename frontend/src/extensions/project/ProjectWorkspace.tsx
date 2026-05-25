"use client";

import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { AiToolsTab } from "@/extensions/project/components/AiToolsTab";
import { ApprovalTab } from "@/extensions/project/components/ApprovalTab";
import { DashboardTab } from "@/extensions/project/components/DashboardTab";
import { KanbanBoard } from "@/extensions/project/components/KanbanBoard";
import { MembersTab } from "@/extensions/project/components/MembersTab";
import { OutlineTab } from "@/extensions/project/components/OutlineTab";
import {
  type WorkspaceTab,
  WorkspaceTabs,
} from "@/extensions/project/components/WorkspaceTabs";
import { useProjectPermissions } from "@/extensions/project/hooks/useProjectPermissions";
import { type ChapterStatus, type ProjectChapter, type ReportProject } from "@/extensions/project/types";

// ── Helpers ──

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  const walk = (items: ProjectChapter[]) => {
    for (const c of items) {
      result.push(c);
      if (c.children?.length) walk(c.children);
    }
  };
  walk(chapters);
  return result;
}

const COMPLETED_STATUSES: Set<ChapterStatus> = new Set(["completed", "approved"]);
const IN_PROGRESS_STATUSES: Set<ChapterStatus> = new Set(["writing", "editing", "pending_review"]);

// ── Component ──

interface ProjectWorkspaceProps {
  projectId: string;
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      setProject(data);
      // Setup-stage projects redirect to outline tab
      if (data.status === "setup") {
        router.replace(`/projects/${projectId}?tab=outline`);
      }
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, router]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  // Auto-refresh when returning to the tab
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        loadProject();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [loadProject]);

  // ── Permissions-driven tabs ──

  const { role: _role, can: _can, visibleTabs, defaultTab, isLoading: permissionsLoading } =
    useProjectPermissions(projectId, project?.currentStage ?? 0);

  // Determine active tab from URL or default
  const urlTab = searchParams.get("tab");
  const activeTab: WorkspaceTab = urlTab && visibleTabs.find((t) => t.id === urlTab)
    ? urlTab
    : defaultTab;

  // ── Status badges ──

  const badges = useMemo(() => {
    if (!project) return [];
    const all = flattenChapters(project.chapters ?? []);
    const total = all.length;
    const completed = all.filter((c) => COMPLETED_STATUSES.has(c.status)).length;
    const inProgress = all.filter((c) => IN_PROGRESS_STATUSES.has(c.status)).length;
    const result: { label: string; className: string }[] = [];
    if (total > 0) result.push({ label: `${total} 章节`, className: "bg-[#F9FAFB] text-[#94A3B8]" });
    if (completed > 0) result.push({ label: `已完成 ${completed}`, className: "bg-[#ECFDF5] text-[#10B981]" });
    if (inProgress > 0) result.push({ label: `撰写中 ${inProgress}`, className: "bg-[#EFF6FF] text-[#3B82F6]" });
    return result;
  }, [project]);

  // ── Loading / Error states ──

  if (loading || permissionsLoading) {
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

  return (
    <div className="flex h-full flex-col">
      {/* ── Header with integrated tabs ── */}
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
        <Link href="/projects">
          <Button variant="ghost" size="icon" className="h-8 w-8 mr-2">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-[15px] font-semibold text-[#0F172A] mr-6">{project.name}</h1>

        {/* Status badges */}
        <div className="flex items-center gap-2 mr-6">
          {badges.map((badge) => (
            <span
              key={badge.label}
              className={`inline-flex h-[22px] items-center rounded-[4px] px-2 text-[11px] font-medium ${badge.className}`}
            >
              {badge.label}
            </span>
          ))}
        </div>

        {/* Tab navigation — permission-driven dynamic tabs */}
        <WorkspaceTabs
          projectId={projectId}
          currentTab={activeTab}
          tabs={visibleTabs}
        />

        <div className="flex-1" />

        <Button variant="outline" size="sm" className="h-[30px]">
          管理成员
        </Button>
      </header>

      {/* ── Content area ── */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "my-workspace" && <KanbanBoard project={project} onRefresh={loadProject} />}
        {activeTab === "dashboard" && <DashboardTab project={project} />}
        {activeTab === "kanban" && <KanbanBoard project={project} onRefresh={loadProject} />}
        {activeTab === "outline" && <OutlineTab project={project} onRefresh={loadProject} />}
        {activeTab === "members" && <MembersTab project={project} onRefresh={loadProject} />}
        {activeTab === "approval" && (
          <ApprovalTab project={project} onRefresh={loadProject} />
        )}
        {activeTab === "ai-tools" && <AiToolsTab project={project} onRefresh={loadProject} />}
      </div>
    </div>
  );
}
