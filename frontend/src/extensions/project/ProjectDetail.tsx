"use client";

import {
  Archive,
  ChevronLeft,
  Edit,
  FolderCheck,
  Loader2,
  MoreVertical,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { projectApi } from "@/extensions/project/api";
import {
  CHAPTER_STATUS_LABELS,
  MEMBER_ROLE_LABELS,
  PROJECT_STATUS_LABELS,
  REPORT_TYPE_LABELS,
  type ReportOutline,
  type ReportProject,
} from "@/extensions/project/types";
import { KanbanBoard } from "@/extensions/project/components/KanbanBoard";
import { MemberList } from "@/extensions/project/components/MemberList";
import { MilestoneTimeline } from "@/extensions/project/components/MilestoneTimeline";
import { OutlineTree } from "@/extensions/project/components/OutlineTree";
import { StatusBadge } from "@/extensions/project/components/StatusBadge";
import { ApprovalPanel } from "@/extensions/approval/ApprovalPanel";

type TabId = "overview" | "kanban" | "outline" | "members" | "approval";

const TAB_ITEMS: { id: TabId; label: string }[] = [
  { id: "overview", label: "概览" },
  { id: "kanban", label: "看板" },
  { id: "outline", label: "大纲" },
  { id: "members", label: "成员" },
  { id: "approval", label: "审批" },
];

function flattenChapters(items: ReportOutline[]): ReportOutline[] {
  const result: ReportOutline[] = [];
  for (const item of items) {
    result.push(item);
    if (item.children.length > 0) {
      result.push(...flattenChapters(item.children));
    }
  }
  return result;
}

interface ProjectDetailProps {
  projectId: string;
}

export function ProjectDetail({ projectId }: ProjectDetailProps) {
  const params = useSearchParams();
  const currentTab = (params.get("tab") ?? "overview") as TabId;

  const [project, setProject] = useState<ReportProject | null>(null);
  const [outline, setOutline] = useState<ReportOutline[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await projectApi.get(projectId);
      setProject(data);
      if (data.outline) {
        setOutline([data.outline]);
      } else {
        setOutline([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  const handleRefresh = useCallback(() => {
    loadProject();
  }, [loadProject]);

  const handleChapterClick = useCallback((chapterId: string) => {
    // TODO: navigate to chapter editor in Task 8
    console.log("Chapter clicked:", chapterId);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-destructive">{error ?? "项目不存在"}</p>
        <Button variant="outline" size="sm" onClick={handleRefresh}>
          重试
        </Button>
      </div>
    );
  }

  const allChapters = flattenChapters(outline);
  const completedCount = allChapters.filter(
    (c) => c.status === "approved" || c.status === "signed",
  ).length;
  const completionRate =
    allChapters.length > 0
      ? Math.round((completedCount / allChapters.length) * 100)
      : 0;
  const totalWords = allChapters.reduce(
    (sum, c) => sum + c.wordCountCurrent,
    0,
  );
  const totalTarget = allChapters.reduce(
    (sum, c) => sum + c.wordCountTarget,
    0,
  );
  const wordProgress =
    totalTarget > 0 ? Math.round((totalWords / totalTarget) * 100) : 0;

  return (
    <div className="flex flex-col h-full bg-muted">
      {/* Header bar */}
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
        <Link href="/projects">
          <Button variant="ghost" size="icon">
            <ChevronLeft className="h-5 w-5" />
          </Button>
        </Link>
        <span className="font-bold text-lg tracking-tight text-foreground mr-4">
          {project.name}
        </span>
        <StatusBadge status={project.status} type="project" />
        <div className="ml-auto">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem>
                <Edit className="h-4 w-4 mr-2" />
                编辑项目
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Archive className="h-4 w-4 mr-2" />
                归档项目
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive">
                <Trash2 className="h-4 w-4 mr-2" />
                删除项目
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Tabs + Content */}
      <div className="flex-1 overflow-hidden min-w-0 min-h-0 bg-background flex flex-col">
        {/* Tab navigation */}
        <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground px-6 border-b border-border shrink-0">
          {TAB_ITEMS.map(({ id, label }) => {
            const href = `/projects/${projectId}?tab=${id}`;
            const isActive = currentTab === id;
            return (
              <Link
                key={id}
                href={href}
                className={cn(
                  "flex items-center h-10 transition-colors border-b-2",
                  isActive
                    ? "text-primary border-primary"
                    : "border-transparent hover:text-foreground",
                )}
              >
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-6">
          {currentTab === "overview" && (
            <div className="flex flex-col gap-6 max-w-4xl">
              {/* Project info card */}
              <div className="rounded-xl border border-border bg-background p-6">
                <h2 className="text-2xl font-bold tracking-tight text-foreground mb-4">
                  项目信息
                </h2>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">
                      报告类型
                    </div>
                    <div className="text-sm font-medium text-foreground">
                      {REPORT_TYPE_LABELS[project.reportType]}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">
                      委托方
                    </div>
                    <div className="text-sm font-medium text-foreground">
                      {project.client}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">
                      目标标准
                    </div>
                    <div className="text-sm font-medium text-foreground">
                      {project.targetStandard || "--"}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">
                      创建时间
                    </div>
                    <div className="text-sm font-medium text-foreground">
                      {new Intl.DateTimeFormat("zh-CN", {
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                      }).format(new Date(project.createdAt))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Progress stats */}
              <div className="rounded-xl border border-border bg-background p-6">
                <h2 className="text-2xl font-bold tracking-tight text-foreground mb-4">
                  进度统计
                </h2>
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  {/* Completion rate */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-muted-foreground">
                        章节完成率
                      </span>
                      <span className="text-sm font-medium text-foreground">
                        {completionRate}%
                      </span>
                    </div>
                    <Progress value={completionRate} className="h-2" />
                    <div className="text-xs text-muted-foreground mt-1">
                      已完成 {completedCount} / {allChapters.length} 个章节
                    </div>
                  </div>

                  {/* Word count progress */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-muted-foreground">
                        字数进度
                      </span>
                      <span className="text-sm font-medium text-foreground">
                        {wordProgress}%
                      </span>
                    </div>
                    <Progress value={wordProgress} className="h-2" />
                    <div className="text-xs text-muted-foreground mt-1">
                      已撰写 {totalWords.toLocaleString()} /{" "}
                      {totalTarget.toLocaleString()} 字
                    </div>
                  </div>
                </div>
              </div>

              {/* Milestones */}
              <div className="rounded-xl border border-border bg-background p-6">
                <h2 className="text-2xl font-bold tracking-tight text-foreground mb-4">
                  里程碑
                </h2>
                <MilestoneTimeline milestones={project.milestones} />
              </div>
            </div>
          )}

          {currentTab === "kanban" && (
            <div className="h-full">
              <KanbanBoard
                outline={outline}
                onChapterClick={handleChapterClick}
              />
            </div>
          )}

          {currentTab === "outline" && (
            <div className="max-w-4xl">
              <OutlineTree
                items={outline}
                onChapterClick={handleChapterClick}
              />
            </div>
          )}

          {currentTab === "members" && (
            <div className="max-w-2xl">
              <MemberList
                members={project.members}
                projectId={projectId}
                onUpdate={handleRefresh}
              />
            </div>
          )}

          {currentTab === "approval" && project && (
            <div className="p-6">
              <ApprovalPanel
                projectId={project.id}
                reportType={project.reportType}
                currentUserId=""
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
