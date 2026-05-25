"use client";

import { CheckCircle2, PenLine, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/extensions/hooks/useAuth";
import { projectApi } from "@/extensions/project/api";
import { type ChapterStatus, type ProjectChapter, type ReportProject, type ProjectListItem } from "@/extensions/project/types";
import { cn } from "@/lib/utils";

// ── Types ──

interface MemberWorkspaceProps {
  can?: (action: string) => boolean;
  role?: string | null;
  projectId?: string;
  project?: ReportProject | null;
}

// ── Status grouping ──

interface StatusGroup {
  label: string;
  accent: string;
  accentLight: string;
  accentBg: string;
  statuses: Set<ChapterStatus>;
}

const STATUS_GROUPS: StatusGroup[] = [
  {
    label: "待处理",
    accent: "bg-[#D97706]",
    accentLight: "text-[#D97706]",
    accentBg: "bg-[#FFFBEB]",
    statuses: new Set<ChapterStatus>(["pending", "rejected"]),
  },
  {
    label: "进行中",
    accent: "bg-[#3B82F6]",
    accentLight: "text-[#3B82F6]",
    accentBg: "bg-[#EFF6FF]",
    statuses: new Set<ChapterStatus>(["writing", "draft", "editing"]),
  },
  {
    label: "已完成",
    accent: "bg-[#22C55E]",
    accentLight: "text-[#22C55E]",
    accentBg: "bg-[#ECFDF5]",
    statuses: new Set<ChapterStatus>(["completed", "approved"]),
  },
];

// ── Helpers ──

/** Flatten chapters into a flat list, filtering by assignedTo === userId. */
function getAssignedChapters(
  chapters: ProjectChapter[],
  userId: string,
): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  const walk = (items: ProjectChapter[]) => {
    for (const ch of items) {
      if (ch.assignedTo === userId) {
        result.push(ch);
      }
      if (ch.children?.length) {
        walk(ch.children);
      }
    }
  };
  walk(chapters);
  return result;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "凌晨好";
  if (hour < 12) return "早上好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

// ── Chapter card ──

function ChapterCard({
  chapter,
  canEdit,
  canAi,
  onEdit,
  onAiToolbox,
}: {
  chapter: ProjectChapter;
  canEdit: boolean;
  canAi: boolean;
  onEdit: () => void;
  onAiToolbox: () => void;
}) {
  const progress =
    chapter.wordCountTarget > 0
      ? Math.round((chapter.wordCountCurrent / chapter.wordCountTarget) * 100)
      : 0;
  const clampedProgress = Math.min(progress, 100);

  return (
    <div className="rounded-lg border border-border bg-background p-3 flex flex-col gap-2">
      {/* Title + status */}
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-foreground line-clamp-2">
          {chapter.title}
        </span>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
            chapter.status === "pending" || chapter.status === "rejected"
              ? "bg-[#FFFBEB] text-[#D97706]"
              : chapter.status === "writing" || chapter.status === "draft" || chapter.status === "editing"
                ? "bg-[#EFF6FF] text-[#3B82F6]"
                : "bg-[#ECFDF5] text-[#22C55E]",
          )}
        >
          {chapter.status === "pending"
            ? "待处理"
            : chapter.status === "rejected"
              ? "退回"
              : chapter.status === "writing"
                ? "撰写中"
                : chapter.status === "draft"
                  ? "初稿"
                  : chapter.status === "editing"
                    ? "编辑中"
                    : chapter.status === "completed"
                      ? "已完成"
                      : "已通过"}
        </span>
      </div>

      {/* Word count progress */}
      {chapter.wordCountTarget > 0 && (
        <div className="flex items-center gap-2">
          <div className="h-1.5 rounded-full bg-[#F1F5F9] overflow-hidden flex-1">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                clampedProgress >= 100
                  ? "bg-[#22C55E]"
                  : "bg-[#3B82F6]",
              )}
              style={{ width: `${clampedProgress}%` }}
            />
          </div>
          <span className="text-[11px] text-muted-foreground shrink-0">
            {chapter.wordCountCurrent.toLocaleString()}/{chapter.wordCountTarget.toLocaleString()} 字
          </span>
        </div>
      )}

      {/* Action buttons */}
      {(canEdit || canAi) && (
        <div className="flex items-center gap-2 pt-1">
          {canEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-[#3B82F6] hover:bg-[#EFF6FF] transition-colors"
            >
              <PenLine className="h-3 w-3" />
              编辑
            </button>
          )}
          {canAi && (
            <button
              type="button"
              onClick={onAiToolbox}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-[#7C3AED] hover:bg-[#F5F3FF] transition-colors"
            >
              <Sparkles className="h-3 w-3" />
              AI辅助
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Component ──

export function MemberWorkspace({
  can: canProp,
  role: _role,
  projectId: projectIdProp,
  project: projectProp,
}: MemberWorkspaceProps) {
  const router = useRouter();
  const { user } = useAuth();

  const can = canProp ?? (() => false);
  const resolvedProjectId = projectIdProp ?? "";

  // Standalone mode: load projects list (legacy /projects/workspace page)
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [standaloneLoading, setStandaloneLoading] = useState(!projectProp);

  useEffect(() => {
    if (!projectProp) {
      projectApi
        .list()
        .then((res) => setProjects(res.items))
        .catch(() => setProjects([]))
        .finally(() => setStandaloneLoading(false));
    }
  }, [projectProp]);

  // Standalone mode: show old dashboard-style view
  if (!projectProp) {
    if (standaloneLoading) {
      return (
        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">加载中...</div>
      );
    }

    const writingCount = projects.filter((p) => p.status === "writing").length;
    const editingCount = projects.filter((p) => p.status === "editing").length;
    const approvalCount = projects.filter((p) => p.status === "approval").length;
    const completedCount = projects.filter((p) => p.status === "published" || p.status === "archived").length;
    const todoCount = writingCount + editingCount + approvalCount;

    return (
      <div className="p-6">
        <h1 className="text-lg font-bold text-foreground">我的工作台</h1>
        <div className="mt-6">
          <p className="text-[22px] font-bold text-foreground">{getGreeting()}，{user?.full_name ?? user?.username ?? "用户"}</p>
          <p className="mt-1 text-sm text-[#475569]">今日待办 {todoCount} 项</p>
        </div>
        <div className="mt-6 grid grid-cols-4 gap-3">
          {[
            { label: "待撰写", value: writingCount, color: "text-[#2563EB]", bgColor: "bg-[#EFF6FF]", Icon: PenLine },
            { label: "待审核", value: editingCount + approvalCount, color: "text-[#7C3AED]", bgColor: "bg-[#F5F3FF]", Icon: CheckCircle2 },
            { label: "今日截止", value: 0, color: "text-[#D97706]", bgColor: "bg-[#FFFBEB]", Icon: Sparkles },
            { label: "已完成", value: completedCount, color: "text-[#059669]", bgColor: "bg-[#ECFDF5]", Icon: CheckCircle2 },
          ].map((card) => (
            <div key={card.label} className="flex items-center gap-3 rounded-lg border border-border bg-background p-4">
              <div className={cn("flex h-10 w-10 items-center justify-center rounded-full", card.bgColor)}>
                <card.Icon className={cn("h-5 w-5", card.color)} />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{card.value}</p>
                <p className="text-xs text-muted-foreground">{card.label}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-foreground">进行中的任务</h2>
          <div className="mt-3 flex flex-col gap-2">
            {projects.filter((p) => !["published", "archived"].includes(p.status)).slice(0, 8).length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">暂无进行中的任务</p>
            )}
            {projects.filter((p) => !["published", "archived"].includes(p.status)).slice(0, 8).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => router.push(`/projects/${p.id}?tab=kanban`)}
                className="flex items-center gap-3 rounded-lg border border-border bg-background px-4 py-3 text-left hover:bg-accent/50 transition-colors"
              >
                <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-[#2563EB]" />
                <span className="flex-1 truncate text-sm font-medium text-foreground">{p.name}</span>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", p.status === "writing" ? "bg-[#EFF6FF] text-[#2563EB]" : p.status === "editing" ? "bg-[#FFFBEB] text-[#D97706]" : "bg-[#F5F3FF] text-[#7C3AED]")}>
                  {p.status === "writing" ? "撰写中" : p.status === "editing" ? "编辑中" : "进行中"}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Project-scoped mode (embedded in ProjectWorkspace) ──

  const project = projectProp;
  const userId = user?.id ?? "";
  const assignedChapters = getAssignedChapters(project.chapters ?? [], userId);

  // Group by status
  const groups = STATUS_GROUPS.map((group) => {
    const chapters = assignedChapters.filter((ch) => group.statuses.has(ch.status));
    return { ...group, chapters };
  });

  const pendingCount = groups[0]?.chapters.length ?? 0;
  const inProgressCount = groups[1]?.chapters.length ?? 0;
  const completedCount = groups[2]?.chapters.length ?? 0;
  const totalCount = pendingCount + inProgressCount + completedCount;

  const canEdit = can("ai:start_editing");
  const canAi = can("ai:toolbox");

  return (
    <div className="p-6 overflow-y-auto h-full">
      {/* Header */}
      <h1 className="text-lg font-bold text-foreground">我的工作台</h1>

      {/* Greeting */}
      <div className="mt-6">
        <p className="text-[22px] font-bold text-foreground">
          {getGreeting()}，{user?.full_name ?? user?.username ?? "用户"}
        </p>
        <p className="mt-1 text-sm text-[#475569]">
          当前项目共 {totalCount} 个章节待处理
        </p>
      </div>

      {/* Stats cards */}
      <div className="mt-6 grid grid-cols-3 gap-3">
        <div className="flex items-center gap-3 rounded-lg border border-border bg-background p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#FFFBEB]">
            <PenLine className="h-5 w-5 text-[#D97706]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{pendingCount}</p>
            <p className="text-xs text-muted-foreground">待处理</p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-lg border border-border bg-background p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#EFF6FF]">
            <PenLine className="h-5 w-5 text-[#3B82F6]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{inProgressCount}</p>
            <p className="text-xs text-muted-foreground">进行中</p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-lg border border-border bg-background p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ECFDF5]">
            <CheckCircle2 className="h-5 w-5 text-[#22C55E]" />
          </div>
          <div>
            <p className="text-2xl font-bold text-foreground">{completedCount}</p>
            <p className="text-xs text-muted-foreground">已完成</p>
          </div>
        </div>
      </div>

      {/* Chapter groups */}
      <div className="mt-8 flex flex-col gap-6">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="flex items-center gap-2 mb-3">
              <span className={cn("h-2.5 w-2.5 rounded-full shrink-0", group.accent)} />
              <span className="text-sm font-semibold text-foreground">{group.label}</span>
              <span
                className={cn(
                  "inline-flex items-center justify-center rounded-full px-2 h-5 text-[11px] font-medium",
                  group.accentBg,
                  group.accentLight,
                )}
              >
                {group.chapters.length}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              {group.chapters.length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  暂无{group.label}的章节
                </p>
              )}
              {group.chapters.map((chapter) => (
                <ChapterCard
                  key={chapter.id}
                  chapter={chapter}
                  canEdit={canEdit}
                  canAi={canAi}
                  onEdit={() => router.push(`/workspace/chats/${chapter.id}?edit=true`)}
                  onAiToolbox={() => router.push(`/projects/${resolvedProjectId}?tab=ai-tools`)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {totalCount === 0 && (
        <div className="mt-12 text-center text-sm text-muted-foreground">
          当前项目暂无分配给您的章节
        </div>
      )}
    </div>
  );
}
