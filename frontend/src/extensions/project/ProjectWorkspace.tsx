"use client";

import { ArrowLeft, Loader2, MessageSquare, Settings } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { SettingsDialog } from "@/extensions/project/components/SettingsDialog";
import { useAuth } from "@/extensions/hooks/useAuth";
import {
  MEMBER_ROLE_LABELS,
  type ProjectPermissions,
  type ReportProject,
} from "@/extensions/project/types";
import { createProjectIdentity, getVisibleTabs, type ProjectIdentity } from "@/extensions/project/tabRegistry";
import { workflowApi } from "@/extensions/workflow/api";
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
      // Load workflow graph if project has an associated workflow
      if (data.workflowId) {
        workflowApi.get(data.workflowId).then((def) => {
          setWorkflowGraph(def.graphJson ?? null);
        }).catch(() => setWorkflowGraph(null));
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
    <div className="flex h-full flex-col">
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0 gap-1">
        <Link href="/projects">
          <Button variant="ghost" size="icon" className="h-8 w-8 mr-2">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-[15px] font-semibold text-[#0F172A] mr-4">{project.name}</h1>
        <span className="inline-flex h-[22px] items-center rounded-[4px] px-2 text-[11px] font-medium bg-[#F9FAFB] text-[#94A3B8]">
          {project.reportType}
        </span>
        {identity && identity.projectRole && (
          <span className="inline-flex h-[22px] items-center rounded-[4px] px-2 text-[11px] font-medium bg-primary/10 text-primary ml-2">
            {MEMBER_ROLE_LABELS[identity.projectRole as keyof typeof MEMBER_ROLE_LABELS] ?? identity.projectRole}
          </span>
        )}

        <div className="flex-1" />

        {/* Tabs in header */}
        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}

        {/* Settings gear icon */}
        {canSeeSettings && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 ml-1"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="h-4 w-4" />
          </Button>
        )}

        {/* Enter conversation */}
        <Button
          size="sm"
          className="h-[30px] ml-2 bg-primary text-primary-foreground hover:bg-primary/90"
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
        >
          <MessageSquare className="h-3.5 w-3.5 mr-1" />
          {entering ? "进入中..." : "进入对话"}
        </Button>
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
