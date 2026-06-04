"use client";

import {
  BookOpen,
  FileText,
  LayoutGrid,
  List,
  Loader2,
  Trash2,
  Users,
  UserPlus,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import { AddMemberDialog } from "@/extensions/project/components/AddMemberDialog";
import { StatusDistribution } from "@/extensions/project/components/StatusDistribution";
import { WorkflowProgressCompact } from "@/extensions/project/components/WorkflowProgressCompact";
import { KanbanBoard } from "@/extensions/project/components/KanbanBoard/KanbanBoard";
import type { KanbanCardData } from "@/extensions/project/components/KanbanBoard/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ProjectChapter,
  type ReportProject,
} from "@/extensions/project/types";
import {
  activityLabel,
  aggregateWordCount,
  type ChapterStatus,
  flattenChapters,
  inferStatus,
} from "@/extensions/project/utils";

interface OverviewTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
  visibleChapterIds?: string[];
  workflowGraph?: any;
}

// ── Status Badge Styles ──

const STATUS_BADGE_STYLES: Record<ChapterStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  writing: "bg-blue-100 text-blue-600",
  review: "bg-amber-100 text-amber-600",
  completed: "bg-emerald-100 text-emerald-600",
};

const STATUS_LABELS: Record<ChapterStatus, string> = {
  draft: "待编写",
  writing: "编写中",
  review: "审核中",
  completed: "已完成",
};

// ── Stat Card (matches ProjectCard style) ──

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  sub?: string;
}) {
  return (
    <div className="flex cursor-default flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
      <div className="flex-1 p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-sm font-bold text-primary">
            <Icon className="h-[18px] w-[18px]" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[22px] font-semibold text-foreground leading-tight">{value}</p>
            <p className="text-[12px] text-muted-foreground">{label}</p>
          </div>
        </div>
      </div>
      {sub && (
        <div className="border-t border-border bg-muted/50 px-5 py-2">
          <p className="text-[11px] text-muted-foreground">{sub}</p>
        </div>
      )}
    </div>
  );
}

// ── Chapter Node (list view) ──

function ChapterNode({ chapter, depth }: { chapter: ProjectChapter; depth: number }) {
  const status = inferStatus(chapter);
  const activity = activityLabel(chapter.updatedAt);

  return (
    <>
      <div
        className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-accent/40 transition-colors"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
      >
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-sm text-foreground">{chapter.title}</span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE_STYLES[status]}`}>
          {STATUS_LABELS[status]}
        </span>
        {activity && (
          <span className="text-[11px] text-muted-foreground/70 shrink-0">{activity}</span>
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

export function OverviewTab({ project, projectId, onRefresh, identity, workflowGraph }: OverviewTabProps) {
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [kanbanView, setKanbanView] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const canManageMembers = identity?.isAdmin || identity?.hasAnyPermission(["member:add", "member:remove"]);

  // Convert chapters to kanban card data
  const kanbanCards = useMemo<KanbanCardData[]>(() => {
    const flat = flattenChapters(project.chapters ?? []);
    const statusMap: Record<ChapterStatus, KanbanCardData["status"]> = {
      draft: "draft",
      writing: "writing",
      review: "review",
      completed: "completed",
    };
    return flat.map((ch) => ({
      id: ch.id,
      title: ch.title,
      status: statusMap[inferStatus(ch)],
      assignee: ch.assignedName ?? undefined,
      wordCount: ch.wordCountCurrent ?? undefined,
      targetWordCount: ch.wordCountTarget > 0 ? ch.wordCountTarget : undefined,
    }));
  }, [project.chapters]);

  const handleCardMove = useCallback(
    async (cardId: string, newStatus: string) => {
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

  // Derived stats
  const flatChapters = useMemo(() => flattenChapters(project.chapters ?? []), [project.chapters]);
  const activeCount = useMemo(
    () => flatChapters.filter((ch) => inferStatus(ch) === "writing").length,
    [flatChapters],
  );
  const totalCount = flatChapters.length;
  const totalWords = useMemo(() => aggregateWordCount(project.chapters ?? []), [project.chapters]);

  // Member management handlers
  const handleRoleChange = async (userId: string, role: MemberRole) => {
    try {
      await projectApi.updateMember(projectId, userId, { role });
      onRefresh();
      toast.success("角色已更新");
    } catch {
      toast.error("更新角色失败");
    }
  };

  const handleRemoveMember = async (userId: string) => {
    setRemovingId(userId);
    try {
      await projectApi.removeMember(projectId, userId);
      onRefresh();
      toast.success("成员已移除");
    } catch {
      toast.error("移除失败");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <ScrollArea className="h-full">
      <div className="p-6 space-y-6 max-w-5xl">
        {/* Header — simplified, no duplicates */}
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-foreground">项目概览</h2>
          <p className="text-[13px] text-muted-foreground">
            创建于{" "}
            {project.createdAt
              ? new Date(project.createdAt).toLocaleDateString("zh-CN", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })
              : "未知"}
          </p>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard icon={BookOpen} label="活跃章节" value={`${activeCount}/${totalCount}`} sub="编写中" />
          <StatCard icon={Users} label="成员数" value={project.members?.length ?? 0} />
          <StatCard icon={FileText} label="文件数" value={fileCount !== null ? String(fileCount) : "..."} />
          <StatCard icon={FileText} label="已写字数" value={totalWords.toLocaleString()} sub="累计" />
        </div>

        {/* Chapter Status Distribution */}
        {totalCount > 0 && <StatusDistribution chapters={project.chapters ?? []} />}

        {/* Workflow Progress (conditional) */}
        {project.workflowId && (
          <WorkflowProgressCompact projectId={projectId} workflowGraph={workflowGraph ?? null} />
        )}

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Chapter Progress — 3 cols */}
          <div className="lg:col-span-3">
            <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
              <div className="flex items-center justify-between p-5 pb-0">
                <h3 className="text-sm font-medium text-foreground">章节进度</h3>
                {kanbanCards.length > 0 && (
                  <div className="flex items-center gap-1 rounded-md border border-border p-0.5">
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
                <div className="p-5 pt-3 overflow-x-auto">
                  <KanbanBoard cards={kanbanCards} onCardMove={handleCardMove} />
                </div>
              ) : (
                <div className="p-5 pt-3">
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
          </div>

          {/* Right Sidebar — Members — 2 cols */}
          <div className="lg:col-span-2">
            <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
              <div className="flex items-center justify-between p-5 pb-0">
                <h3 className="text-sm font-medium text-foreground">项目成员</h3>
                {canManageMembers && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-[12px]"
                    onClick={() => setAddMemberOpen(true)}
                  >
                    <UserPlus className="h-3.5 w-3.5 mr-1" />
                    添加成员
                  </Button>
                )}
              </div>
              <div className="p-5 pt-3 divide-y divide-border/40">
                {project.members?.length > 0 ? (
                  project.members.map((m) => (
                    <div key={m.id} className="flex items-center gap-2.5 px-3 py-2.5">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-medium text-primary">
                        {(m.username ?? "?").charAt(0).toUpperCase()}
                      </div>
                      <span className="flex-1 text-sm text-foreground truncate">{m.username}</span>
                      {canManageMembers && m.role !== "owner" ? (
                        <Select
                          value={m.role}
                          onValueChange={(role) => handleRoleChange(m.userId, role as MemberRole)}
                        >
                          <SelectTrigger className="h-6 w-20 text-[11px] border-none bg-secondary p-0 pl-2">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(MEMBER_ROLE_LABELS)
                              .filter(([key]) => key !== "owner")
                              .map(([key, label]) => (
                                <SelectItem key={key} value={key}>
                                  {label}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge variant="secondary" className="text-[10px] font-normal">
                          {MEMBER_ROLE_LABELS[m.role as keyof typeof MEMBER_ROLE_LABELS] ?? m.role}
                        </Badge>
                      )}
                      {canManageMembers && m.role !== "owner" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                          disabled={removingId === m.userId}
                          onClick={() => handleRemoveMember(m.userId)}
                        >
                          {removingId === m.userId ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      )}
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

      {/* Add Member Dialog */}
      <AddMemberDialog
        projectId={projectId}
        open={addMemberOpen}
        onOpenChange={setAddMemberOpen}
        onAdded={onRefresh}
      />
    </ScrollArea>
  );
}
