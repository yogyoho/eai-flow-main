"use client";

import { ArrowLeft, FileText, Loader2, MessageSquare, Settings } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { ApprovalFlowEditor } from "@/extensions/project/ApprovalFlowEditor";
import { type ReportProject } from "@/extensions/project/types";

interface ProjectWorkspaceProps {
  projectId: string;
}

type ViewTab = "info" | "files" | "approval";

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const router = useRouter();
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ViewTab>("info");
  const [showApprovalEditor, setShowApprovalEditor] = useState(false);
  const [entering, setEntering] = useState(false);

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      setProject(data);
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

  return (
    <div className="flex h-full flex-col">
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
        <Link href="/projects">
          <Button variant="ghost" size="icon" className="h-8 w-8 mr-2">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-[15px] font-semibold text-[#0F172A] mr-4">{project.name}</h1>
        <span className="inline-flex h-[22px] items-center rounded-[4px] px-2 text-[11px] font-medium bg-[#F9FAFB] text-[#94A3B8]">
          {project.reportType}
        </span>

        <div className="flex-1" />

        <Button
          size="sm"
          className="h-[30px] mr-2 bg-primary text-primary-foreground hover:bg-primary/90"
          disabled={entering}
          onClick={async () => {
            setEntering(true);
            try {
              const { threadId } = await projectApi.enter(projectId);
              router.push(`/workspace/chats/${threadId}?from=project&projectId=${projectId}&projectName=${encodeURIComponent(project.name)}`);
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
        <Button
          variant="outline"
          size="sm"
          className="h-[30px] mr-2"
          onClick={() => {
            setShowApprovalEditor(!showApprovalEditor);
            if (!showApprovalEditor) setActiveTab("info");
          }}
        >
          <Settings className="h-3.5 w-3.5 mr-1" />
          审批流程设置
        </Button>
      </header>

      {/* Tab bar */}
      {!showApprovalEditor && (
        <div className="flex border-b border-border px-6 shrink-0">
          <button
            type="button"
            className={`px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors ${
              activeTab === "info"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setActiveTab("info")}
          >
            项目信息
          </button>
          <button
            type="button"
            className={`px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors ${
              activeTab === "files"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setActiveTab("files")}
          >
            项目文件
          </button>
        </div>
      )}

      <div className="flex-1 overflow-hidden">
        {showApprovalEditor ? (
          <ApprovalFlowEditor
            onSave={(nodes) => {
              console.log("Approval flow saved:", nodes);
              setShowApprovalEditor(false);
            }}
          />
        ) : activeTab === "files" ? (
          <ProjectFilesTab projectId={projectId} />
        ) : (
          <ProjectInfoPanel project={project} />
        )}
      </div>
    </div>
  );
}

function ProjectInfoPanel({ project }: { project: ReportProject }) {
  return (
    <div className="p-6 max-w-3xl">
      <h2 className="text-sm font-medium text-[#0F172A] mb-4">项目信息</h2>
      <dl className="space-y-3 text-sm">
        <div className="flex">
          <dt className="w-24 text-[#94A3B8] shrink-0">项目名称</dt>
          <dd className="text-[#0F172A]">{project.name}</dd>
        </div>
        <div className="flex">
          <dt className="w-24 text-[#94A3B8] shrink-0">报告类型</dt>
          <dd className="text-[#0F172A]">{project.reportType}</dd>
        </div>
        <div className="flex">
          <dt className="w-24 text-[#94A3B8] shrink-0">项目状态</dt>
          <dd className="text-[#0F172A]">{project.status}</dd>
        </div>
        <div className="flex">
          <dt className="w-24 text-[#94A3B8] shrink-0">创建时间</dt>
          <dd className="text-[#0F172A]">{project.createdAt ? new Date(project.createdAt).toLocaleString("zh-CN") : "-"}</dd>
        </div>
        {project.members && project.members.length > 0 && (
          <div className="flex">
            <dt className="w-24 text-[#94A3B8] shrink-0">项目成员</dt>
            <dd className="text-[#0F172A]">
              {project.members.map((m) => m.username ?? m.userId).join("、")}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

function ProjectFilesTab({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(false);
        const data = await projectApi.getFiles(projectId);
        if (!cancelled) setFiles(data);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center">
        <p className="text-sm text-destructive">加载文件列表失败</p>
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <FileText className="h-10 w-10 text-muted-foreground/40 mb-3" />
        <p className="text-sm text-muted-foreground">暂无项目文件</p>
        <p className="text-xs text-muted-foreground/60 mt-1">成员进入对话后生成的文件将聚合显示在这里</p>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-medium text-[#0F172A]">项目文件</h2>
        <span className="text-xs text-muted-foreground">{files.length} 个文件</span>
      </div>
      <div className="flex flex-col gap-2">
        {files.map((file, idx) => (
          <div
            key={String(file.name ?? idx)}
            className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-accent/50 transition-colors"
          >
            <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-foreground truncate">{String(file.name ?? "未命名")}</p>
              <div className="flex items-center gap-2 mt-0.5">
                {file.member != null && (
                  <span className="text-[11px] text-muted-foreground">
                    {String(file.member)}
                  </span>
                )}
                {file.size != null && (
                  <span className="text-[11px] text-muted-foreground">
                    {Number(file.size) > 1024
                      ? `${(Number(file.size) / 1024).toFixed(1)} KB`
                      : `${String(file.size)} B`}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
