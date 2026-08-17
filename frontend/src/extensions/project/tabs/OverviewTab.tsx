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
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { AddMemberDialog } from "@/extensions/project/components/AddMemberDialog";
import { KanbanBoard } from "@/extensions/project/components/KanbanBoard/KanbanBoard";
import type { KanbanCardData } from "@/extensions/project/components/KanbanBoard/types";
import { RoleBoard } from "@/extensions/project/components/RoleBoard";
import { StatusDistribution } from "@/extensions/project/components/StatusDistribution";
import { WorkflowProgressCompact } from "@/extensions/project/components/WorkflowProgressCompact";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import {
  MEMBER_ROLE_LABELS,
  type ProjectChapter,
  type ReportProject,
} from "@/extensions/project/types";
import {
  activityLabel,
  aggregateWordCount,
  type ChapterStatus,
  deriveBlockState,
  flattenChapters,
  hasAnyContent,
  inferStatus,
} from "@/extensions/project/utils";
import { workflowApi } from "@/extensions/workflow/api";
import type { WorkflowGraph } from "@/extensions/workflow/types";

interface OverviewTabProps {
  project: ReportProject;
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
  visibleChapterIds?: string[];
  workflowGraph?: WorkflowGraph | null;
}

// ── Status Badge Styles ──

const STATUS_BADGE_STYLES: Record<ChapterStatus, string> = {
  pending: "bg-muted text-muted-foreground", // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)
  draft: "bg-primary/10 text-primary",
  reviewing: "bg-warning/10 text-warning",
  approved: "bg-success/10 text-success",
};

const STATUS_LABELS: Record<ChapterStatus, string> = {
  pending: "未开始",
  draft: "编写中",
  reviewing: "审核中",
  approved: "已完成",
};

// ── Stat Card (cyber-themed, matches SciFiProjectDetail style) ──

const STAT_CARD_COLORS = {
  blue: {
    border: "border-primary/15 bg-primary/5",
    text: "text-primary",
    dot: "bg-primary/10",
  },
  green: {
    border: "border-success/15 bg-success/5",
    text: "text-success",
    dot: "bg-success/10",
  },
  cyan: {
    border: "border-info/15 bg-info/5",
    text: "text-info",
    dot: "bg-info/10",
  },
  amber: {
    border: "border-warning/15 bg-warning/5",
    text: "text-warning",
    dot: "bg-warning/10",
  },
} as const;

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "blue",
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  sub?: string;
  color?: keyof typeof STAT_CARD_COLORS;
}) {
  const c = STAT_CARD_COLORS[color];
  return (
    <div
      className={`group relative flex flex-col justify-between overflow-hidden rounded-xl border p-4 transition-all hover:scale-[1.015] ${c.border}`}
    >
      <span className={`absolute top-0 right-0 h-2 w-2 ${c.dot}`} />
      <div className="flex items-center justify-between gap-2.5">
        <span
          className="text-xs font-bold"
          style={{ color: "var(--cyber-text-main)" }}
        >
          {label}
        </span>
        <div className={`rounded-md border p-1 ${c.border} ${c.text}`}>
          <Icon
            className={`h-4 w-4 ${color === "blue" ? "animate-pulse" : ""}`}
          />
        </div>
      </div>
      <div
        className={`font-cyber my-2 text-3xl font-extrabold ${c.text} ${
          color === "blue" ? "text-shadow-glow" : ""
        }`}
      >
        {value}
      </div>
      {sub && (
        <p
          className="font-mono text-[10px] tracking-wider"
          style={{ color: "var(--cyber-text-muted)" }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}

// ── Chapter Node (list view) ──

function ChapterNode({
  chapter,
  depth,
  onMarkComplete,
  onEdit,
  completingId,
}: {
  chapter: ProjectChapter;
  depth: number;
  onMarkComplete?: (chapterId: string) => void;
  onEdit?: (chapterId: string) => void;
  completingId?: string | null;
}) {
  const status = inferStatus(chapter);
  const activity = activityLabel(chapter.updatedAt);
  const isCompleting = completingId === chapter.id;
  const canComplete = status !== "approved" && status !== "reviewing"; // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)

  return (
    <>
      <div
        className="hover:bg-accent/40 group flex items-center gap-3 rounded-lg px-3 py-2 transition-colors"
        style={{ paddingLeft: `${depth * 20 + 12}px` }}
      >
        <FileText className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
        <span className="text-foreground flex-1 truncate text-xs font-normal">
          {chapter.title}
        </span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE_STYLES[status]}`}
        >
          {STATUS_LABELS[status]}
        </span>
        {activity && (
          <span className="text-muted-foreground/70 shrink-0 text-[11px]">
            {activity}
          </span>
        )}
        {chapter.assignedName && (
          <span className="text-muted-foreground/70 shrink-0 text-[11px]">
            {chapter.assignedName}
          </span>
        )}
        {/* Hover actions */}
        <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {onEdit && (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors"
              onClick={() => onEdit(chapter.id)}
            >
              编辑
            </button>
          )}
          {onMarkComplete && canComplete && (
            <button
              type="button"
              className="text-success hover:bg-success/10 rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors hover:opacity-80"
              disabled={isCompleting}
              onClick={() => onMarkComplete(chapter.id)}
            >
              {isCompleting ? "..." : "完成"}
            </button>
          )}
        </div>
      </div>
      {chapter.children?.map((child) => (
        <ChapterNode
          key={child.id}
          chapter={child}
          depth={depth + 1}
          onMarkComplete={onMarkComplete}
          onEdit={onEdit}
          completingId={completingId}
        />
      ))}
    </>
  );
}

// ── Main Component ──

export function OverviewTab({
  project,
  projectId,
  onRefresh,
  identity,
  workflowGraph,
}: OverviewTabProps) {
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [kanbanView, setKanbanView] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [completingId, setCompletingId] = useState<string | null>(null);
  const canManageMembers =
    (identity?.isAdmin ?? false) ||
    identity?.hasAnyPermission(["member:add", "member:remove"]);

  const handleMarkComplete = useCallback(
    async (chapterId: string) => {
      setCompletingId(chapterId);
      try {
        await projectApi.updateChapterStatus(projectId, chapterId, "reviewing"); // EAI-CUSTOM: submit for review (ADR 2026-08-02 P4)
        toast.success("章节已提交审核");
        onRefresh();
      } catch {
        toast.error("标记完成失败");
      } finally {
        setCompletingId(null);
      }
    },
    [projectId, onRefresh],
  );

  // Handle edit chapter — switch to editor tab with chapter selected
  const handleEditChapter = useCallback(
    async (chapterId: string) => {
      try {
        // Try backend openChapter API — falls back gracefully if unavailable
        try {
          const doc = await projectApi.openChapter(projectId, chapterId);
          sessionStorage.setItem("openChapterDoc", JSON.stringify(doc));
        } catch {
          // Backend endpoint not available — proceed with tab switch only
        }
        const flat = flattenChapters(project.chapters ?? []);
        const chapter = flat.find((c) => c.id === chapterId);
        sessionStorage.setItem("openChapterTitle", chapter?.title ?? "");
        window.dispatchEvent(
          new CustomEvent("switchTab", { detail: { tab: "editor" } }),
        );
      } catch {
        toast.error("打开章节失败");
      }
    },
    [projectId, project.chapters],
  );

  // Convert chapters to kanban card data
  const kanbanCards = useMemo<KanbanCardData[]>(() => {
    const flat = flattenChapters(project.chapters ?? []);
    const statusMap: Record<ChapterStatus, KanbanCardData["status"]> = {
      pending: "pending", // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)
      draft: "draft",
      reviewing: "reviewing",
      approved: "approved",
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
        pending: "pending", // EAI-CUSTOM: canonical columns (ADR 2026-08-02 P4)
        draft: "draft",
        reviewing: "reviewing",
        approved: "approved",
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

  const loadStats = useCallback(async () => {
    try {
      const stats = await projectApi.getStats(projectId);
      setFileCount(stats.documentCount);
    } catch {
      setFileCount(0);
    }
  }, [projectId]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  // Sync documents on mount
  useEffect(() => {
    projectApi
      .syncDocs(projectId)
      .then(() => loadStats())
      .catch(() => {
        /* ignore sync errors */
      });
  }, [projectId, loadStats]);

  // Listen for phase-advanced and doc-status-changed events to refresh stats
  useEffect(() => {
    const handleRefresh = () => {
      void loadStats();
      onRefresh();
    };
    window.addEventListener("phase-advanced", handleRefresh);
    window.addEventListener(
      "doc-status-changed",
      handleRefresh as EventListener,
    );
    return () => {
      window.removeEventListener("phase-advanced", handleRefresh);
      window.removeEventListener(
        "doc-status-changed",
        handleRefresh as EventListener,
      );
    };
  }, [loadStats, onRefresh]);

  // Derived stats
  const flatChapters = useMemo(
    () => flattenChapters(project.chapters ?? []),
    [project.chapters],
  );
  const activeCount = useMemo(
    () => flatChapters.filter((ch) => inferStatus(ch) === "draft").length, // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)
    [flatChapters],
  );
  const totalCount = flatChapters.length;
  const totalWords = useMemo(
    () => aggregateWordCount(project.chapters ?? []),
    [project.chapters],
  );

  // Member management handlers
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

  // EAI-CUSTOM: 章节进度区块状态机(ADR 2026-08-10)
  const blockState = useMemo(
    () =>
      deriveBlockState(
        project.temporalWorkflowId,
        hasAnyContent(project.chapters ?? []),
      ),
    [project.temporalWorkflowId, project.chapters],
  );

  const [starting, setStarting] = useState(false);
  const canStartGenerate =
    ((identity?.isAdmin ?? false) ||
      identity?.projectRole === "owner" ||
      (identity?.hasAnyPermission(["project:advance", "project:edit"]) ??
        false)) &&
    !!project.workflowId;

  const handleStartGenerate = useCallback(async () => {
    if (!project.workflowId) return;
    setStarting(true);
    try {
      await workflowApi.startWorkflow(projectId, project.workflowId);
      toast.success("AI 开始生成初稿");
      onRefresh();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "启动失败，请稍后重试");
    } finally {
      setStarting(false);
    }
  }, [project.workflowId, projectId, onRefresh]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:px-8">
        {/* Stats Grid — cyber-themed cards matching SciFiProjectDetail */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={BookOpen}
            label="活跃章节"
            value={`${activeCount}/${totalCount}`}
            sub="编写中 / CYBERNETIC CO-WRITING"
            color="blue"
          />
          <StatCard
            icon={Users}
            label="成员数"
            value={project.members?.length ?? 0}
            sub="ACTIVE RESEARCHERS"
            color="green"
          />
          <StatCard
            icon={FileText}
            label="文件数"
            value={fileCount !== null ? String(fileCount) : "..."}
            sub="COMPILED DOSSIERS"
            color="cyan"
          />
          <StatCard
            icon={BookOpen}
            label="已写字数"
            value={totalWords.toLocaleString()}
            sub="累计 / ACCUMULATIVE GLYPHS"
            color="amber"
          />
        </div>

        {/* Chapter Status Distribution */}
        {totalCount > 0 && (
          <StatusDistribution chapters={project.chapters ?? []} />
        )}

        {/* Workflow Progress — always show card; prompts setup if no workflow */}
        <WorkflowProgressCompact
          projectId={projectId}
          workflowGraph={workflowGraph ?? null}
          canAdvancePhase={
            (identity?.isAdmin ?? false) ||
            identity?.projectRole === "owner" ||
            (identity?.hasAnyPermission(["project:advance", "project:edit"]) ??
              false)
          }
          onPhaseCompleted={onRefresh}
        />

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
          {/* Chapter Progress — 3 cols — EAI-CUSTOM: 状态驱动(ADR 2026-08-10) */}
          <div className="lg:col-span-3">
            <div className="border-border bg-background flex flex-col overflow-hidden rounded-xl border shadow-sm transition-all hover:shadow-md">
              <div className="flex items-center justify-between px-5 pt-4 pb-0">
                <h3 className="text-foreground text-sm font-medium">
                  章节进度
                </h3>
                {blockState === "human_edit" &&
                  project.assignmentStrategy !== "by_role" &&
                  kanbanCards.length > 0 && (
                    <div className="border-border flex items-center gap-1 rounded-md border p-0.5">
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

              {blockState === "not_generated" && (
                <div className="px-5 pt-4 pb-6">
                  <div className="flex flex-col items-center text-center">
                    <div className="bg-primary/10 mb-4 flex h-12 w-12 items-center justify-center rounded-full">
                      <Wand2 className="text-primary h-6 w-6" />
                    </div>
                    <p className="text-foreground mb-1 text-sm font-medium">
                      尚未生成初稿
                    </p>
                    <p className="text-muted-foreground mb-4 text-xs">
                      AI
                      将按所选大纲生成初稿（可能调整结构），随后进入「人工修改确认」。
                    </p>
                    <Button
                      onClick={() => {
                        void handleStartGenerate();
                      }}
                      disabled={!canStartGenerate || starting}
                      className="mb-5"
                    >
                      {starting ? (
                        <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                      ) : (
                        <Wand2 className="mr-1.5 h-4 w-4" />
                      )}
                      开始 AI 生成初稿
                    </Button>
                    {!project.workflowId && (
                      <p className="text-muted-foreground mb-4 text-[11px]">
                        请先在「项目设置」关联工作流后再开始生成。
                      </p>
                    )}
                    <ol className="w-full max-w-sm space-y-2 text-left">
                      <li className="text-muted-foreground flex items-start gap-2 text-xs">
                        <span className="bg-primary/10 text-primary mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
                          1
                        </span>
                        AI 按所选大纲生成初稿（可能调整结构）
                      </li>
                      <li className="text-muted-foreground flex items-start gap-2 text-xs">
                        <span className="bg-primary/10 text-primary mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
                          2
                        </span>
                        进入「人工修改确认」阶段
                      </li>
                      <li className="text-muted-foreground flex items-start gap-2 text-xs">
                        <span className="bg-primary/10 text-primary mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-medium">
                          3
                        </span>
                        按「
                        {project.assignmentStrategy === "by_role"
                          ? "按职责"
                          : "按章节"}
                        」分工修改确认
                      </li>
                    </ol>
                  </div>
                </div>
              )}

              {blockState === "generating" && (
                <div className="flex flex-col items-center justify-center px-5 pt-4 pb-6 text-center">
                  <Loader2 className="text-primary mb-3 h-7 w-7 animate-spin" />
                  <p className="text-foreground text-sm font-medium">
                    AI 正在生成初稿…
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    生成完成后将进入「人工修改确认」，届时可按分工策略修改确认。
                  </p>
                </div>
              )}

              {blockState === "human_edit" &&
                (project.assignmentStrategy === "by_role" ? (
                  <RoleBoard
                    members={project.members ?? []}
                    chapters={project.chapters ?? []}
                    onEdit={handleEditChapter}
                  />
                ) : kanbanView ? (
                  <div className="cyber-scroll max-h-[480px] overflow-x-auto overflow-y-auto px-5 pt-2 pr-1 pb-4">
                    <KanbanBoard
                      cards={kanbanCards}
                      onCardMove={handleCardMove}
                      onCardEdit={handleEditChapter}
                    />
                  </div>
                ) : (
                  <div className="px-5 pt-2 pb-4">
                    {project.chapters?.length > 0 ? (
                      <div className="cyber-scroll divide-border/40 max-h-[480px] divide-y overflow-y-auto pr-1">
                        {project.chapters.map((ch) => (
                          <ChapterNode
                            key={ch.id}
                            chapter={ch}
                            depth={0}
                            onMarkComplete={handleMarkComplete}
                            onEdit={handleEditChapter}
                            completingId={completingId}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-12">
                        <BookOpen className="text-muted-foreground/30 mb-2 h-8 w-8" />
                        <p className="text-muted-foreground text-sm">
                          暂无章节
                        </p>
                        <p className="text-muted-foreground/60 mt-1 text-xs">
                          从模板创建项目或手动添加章节
                        </p>
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </div>

          {/* Right Sidebar — Members — 2 cols */}
          <div className="lg:col-span-2">
            <div className="border-border bg-background flex flex-col overflow-hidden rounded-xl border shadow-sm transition-all hover:shadow-md">
              <div className="flex items-center justify-between px-5 pt-4 pb-0">
                <h3 className="text-foreground text-sm font-medium">
                  项目成员
                </h3>
                {canManageMembers && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-[12px]"
                    onClick={() => setAddMemberOpen(true)}
                  >
                    <UserPlus className="mr-1 h-3.5 w-3.5" />
                    添加成员
                  </Button>
                )}
              </div>
              <div className="divide-border/40 divide-y px-5 pt-2 pb-4">
                {project.members?.length > 0 ? (
                  project.members.map((m) => (
                    <div
                      key={m.id}
                      className="flex items-center gap-2.5 px-3 py-2.5"
                    >
                      <div className="bg-primary/10 text-primary flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-medium">
                        {(m.username ?? "?").charAt(0).toUpperCase()}
                      </div>
                      <span className="text-foreground flex-1 truncate text-sm">
                        {m.username}
                      </span>
                      <Badge
                        variant="secondary"
                        className="shrink-0 text-[10px] font-normal"
                      >
                        {MEMBER_ROLE_LABELS[m.role] ?? m.role}
                      </Badge>
                      {canManageMembers && m.role !== "owner" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-muted-foreground hover:text-destructive h-6 w-6 p-0"
                          disabled={removingId === m.userId}
                          onClick={() => {
                            void handleRemoveMember(m.userId);
                          }}
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
                    <Users className="text-muted-foreground/30 mx-auto mb-1.5 h-6 w-6" />
                    <p className="text-muted-foreground text-xs">暂无成员</p>
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
    </div>
  );
}
