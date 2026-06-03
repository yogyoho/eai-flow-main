"use client";

import {
  BookOpen,
  FileText,
  LayoutGrid,
  List,
  Loader2,
  MessageSquare,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { KanbanBoard } from "@/extensions/project/components/KanbanBoard/KanbanBoard";
import type { KanbanCardData } from "@/extensions/project/components/KanbanBoard/types";
import { projectApi } from "@/extensions/project/api";
import {
  MEMBER_ROLE_LABELS,
  PROJECT_STATUS_LABELS,
  REPORT_TYPE_LABELS,
  type ProjectChapter,
  type ReportProject,
} from "@/extensions/project/types";
import { type ProjectIdentity } from "@/extensions/project/tabRegistry";

interface OverviewTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
}

// ── Helpers ──

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  for (const ch of chapters) {
    result.push(ch);
    if (ch.children?.length) result.push(...flattenChapters(ch.children));
  }
  return result;
}

function aggregateWordProgress(chapters: ProjectChapter[]) {
  let current = 0;
  let target = 0;
  for (const ch of flattenChapters(chapters)) {
    current += ch.wordCountCurrent ?? 0;
    target += ch.wordCountTarget ?? 0;
  }
  return { current, target };
}

// ── Stat Card ──

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: LucideIcon;
  label: string;
  value: number | string;
  sub?: string;
}) {
  return (
    <Card className="border-border/60 shadow-none hover:shadow-sm transition-shadow">
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/8">
          <Icon className="h-[18px] w-[18px] text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-[22px] font-semibold text-foreground leading-tight">{value}</p>
          <p className="text-[12px] text-muted-foreground">{label}</p>
          {sub && <p className="text-[11px] text-muted-foreground/70 mt-0.5">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Chapter Progress Node ──

function ChapterNode({ chapter, depth }: { chapter: ProjectChapter; depth: number }) {
  const progress =
    chapter.wordCountTarget > 0
      ? Math.min(100, Math.round(((chapter.wordCountCurrent ?? 0) / chapter.wordCountTarget) * 100))
      : 0;
  const hasContent = (chapter.wordCountCurrent ?? 0) > 0;

  return (
    <>
      <div
        className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-accent/40 transition-colors"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
      >
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-sm text-foreground">{chapter.title}</span>
        {hasContent && (
          <div className="flex items-center gap-2 shrink-0">
            <Progress value={progress} className="h-1.5 w-16" />
            <span className="text-[11px] text-muted-foreground w-8 text-right">{progress}%</span>
          </div>
        )}
        {chapter.assignedName && (
          <span className="text-[11px] text-muted-foreground/70 shrink-0">{chapter.assignedName}</span>
        )}
      </div>
      {chapter.children?.map((child) => (
        <ChapterNode key={child.id} chapter={child} depth={depth + 1} />
      ))}
    </>
  );
}

// ── Main Component ──

export function OverviewTab({ project, projectId, onRefresh, identity }: OverviewTabProps) {
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [entering, setEntering] = useState(false);
  const [kanbanView, setKanbanView] = useState(false);

  // Convert chapters to kanban card data
  const kanbanCards = useMemo<KanbanCardData[]>(() => {
    const flat = flattenChapters(project.chapters ?? []);
    const statusMap: Record<string, KanbanCardData["status"]> = {
      not_started: "draft",
      pending: "draft",
      writing: "writing",
      in_review: "review",
      pending_review: "review",
      approved: "completed",
      completed: "completed",
      signed: "completed",
    };
    return flat.map((ch) => ({
      id: ch.id,
      title: ch.title,
      status: statusMap[ch.status] ?? "draft",
      assignee: ch.assignedName ?? undefined,
      wordCount: ch.wordCountCurrent ?? undefined,
      targetWordCount: ch.wordCountTarget > 0 ? ch.wordCountTarget : undefined,
    }));
  }, [project.chapters]);

  const handleCardMove = useCallback(
    async (cardId: string, newStatus: string) => {
      // Reverse-map kanban status back to chapter status
      const reverseMap: Record<string, string> = {
        draft: "pending",
        writing: "writing",
        review: "in_review",
        completed: "completed",
      };
      const chapterStatus = reverseMap[newStatus] ?? "pending";
      try {
        await projectApi.updateChapterStatus(projectId, cardId, chapterStatus);
        onRefresh();
      } catch {
        /* error handled silently */
      }
    },
    [projectId, onRefresh],
  );

  const loadFiles = useCallback(async () => {
    try {
      const files = await projectApi.getFiles(projectId);
      setFileCount(files.length);
    } catch {
      setFileCount(0);
    }
  }, [projectId]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const { current: wordCurrent, target: wordTarget } = useMemo(
    () => aggregateWordProgress(project.chapters ?? []),
    [project.chapters],
  );
  const wordPercent = wordTarget > 0 ? Math.round((wordCurrent / wordTarget) * 100) : 0;

  return (
    <ScrollArea className="h-full">
      <div className="p-6 space-y-6 max-w-5xl">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-foreground">{project.name}</h2>
              <Badge variant="secondary" className="text-[11px] font-normal">
                {REPORT_TYPE_LABELS[project.reportType] ?? project.reportType}
              </Badge>
              <Badge
                variant="outline"
                className={`text-[11px] font-normal ${
                  project.status === "completed"
                    ? "border-emerald-300 text-emerald-700 bg-emerald-50"
                    : project.status === "archived"
                      ? "border-gray-300 text-gray-600 bg-gray-50"
                      : "border-blue-300 text-blue-700 bg-blue-50"
                }`}
              >
                {PROJECT_STATUS_LABELS[project.status] ?? project.status}
              </Badge>
            </div>
            <p className="text-[13px] text-muted-foreground">
              创建于{" "}
              {project.createdAt
                ? new Date(project.createdAt).toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" })
                : "未知"}
            </p>
          </div>
          <Button
            size="sm"
            className="h-8 bg-primary text-primary-foreground hover:bg-primary/90"
            disabled={entering}
            onClick={async () => {
              setEntering(true);
              try {
                const { threadId } = await projectApi.enter(projectId);
                window.location.href = `/workspace/chats/${threadId}?from=project&projectId=${projectId}&projectName=${encodeURIComponent(project.name)}`;
              } catch {
                /* toast handled by parent */
              } finally {
                setEntering(false);
              }
            }}
          >
            <MessageSquare className="h-3.5 w-3.5 mr-1.5" />
            {entering ? "进入中..." : "进入对话"}
          </Button>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={BookOpen}
            label="章节数"
            value={project.chapterCount ?? project.chapters?.length ?? 0}
          />
          <StatCard
            icon={Users}
            label="成员数"
            value={project.members?.length ?? 0}
          />
          <StatCard
            icon={FileText}
            label="文件数"
            value={fileCount !== null ? String(fileCount) : "..."}
          />
          <StatCard
            icon={FileText}
            label="字数进度"
            value={`${wordPercent}%`}
            sub={`${wordCurrent.toLocaleString()} / ${wordTarget.toLocaleString()}`}
          />
        </div>

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Chapter Progress — 3 cols */}
          <div className="lg:col-span-3">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-foreground">章节进度</h3>
              {kanbanCards.length > 0 && (
                <div className="flex items-center gap-1 rounded-md border border-border/60 p-0.5">
                  <Button
                    variant={kanbanView ? "ghost" : "secondary"}
                    size="icon-sm"
                    onClick={() => setKanbanView(false)}
                    title="列表视图"
                  >
                    <List className="size-3.5" />
                  </Button>
                  <Button
                    variant={kanbanView ? "secondary" : "ghost"}
                    size="icon-sm"
                    onClick={() => setKanbanView(true)}
                    title="看板视图"
                  >
                    <LayoutGrid className="size-3.5" />
                  </Button>
                </div>
              )}
            </div>

            {kanbanView ? (
              <div className="rounded-lg border border-border/60 bg-card p-4 overflow-x-auto">
                <KanbanBoard cards={kanbanCards} onCardMove={handleCardMove} />
              </div>
            ) : (
              <div className="rounded-lg border border-border/60 bg-card">
                {project.chapters?.length > 0 ? (
                  <div className="divide-y divide-border/40">
                    {project.chapters.map((ch) => (
                      <ChapterNode key={ch.id} chapter={ch} depth={0} />
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-12">
                    <BookOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
                    <p className="text-sm text-muted-foreground">暂无章节</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">从模板创建项目或手动添加章节</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Sidebar — 2 cols */}
          <div className="lg:col-span-2 space-y-5">
            {/* Members */}
            <div>
              <h3 className="text-sm font-medium text-foreground mb-3">项目成员</h3>
              <div className="rounded-lg border border-border/60 bg-card divide-y divide-border/40">
                {project.members?.length > 0 ? (
                  project.members.map((m) => (
                    <div key={m.id} className="flex items-center gap-2.5 px-3 py-2.5">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-medium text-primary">
                        {(m.username ?? "?").charAt(0).toUpperCase()}
                      </div>
                      <span className="flex-1 text-sm text-foreground truncate">{m.username}</span>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {MEMBER_ROLE_LABELS[m.role as keyof typeof MEMBER_ROLE_LABELS] ?? m.role}
                      </Badge>
                    </div>
                  ))
                ) : (
                  <div className="px-3 py-6 text-center">
                    <Users className="h-6 w-6 text-muted-foreground/30 mx-auto mb-1.5" />
                    <p className="text-xs text-muted-foreground">暂无成员</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </ScrollArea>
  );
}
