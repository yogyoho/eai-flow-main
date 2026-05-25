"use client";

import { useMemo } from "react";

import { ChevronRight, FileText } from "lucide-react";

import { type ProjectChapter, type ReportProject } from "@/extensions/project/types";
import { cn } from "@/lib/utils";

// ── Column definitions ──

interface ColumnDef {
  label: string;
  accent: string;
  accentLight: string;
  accentBg: string;
  statuses: string[];
}

const COLUMNS: ColumnDef[] = [
  {
    label: "未开始",
    accent: "bg-[#94A3B8]",
    accentLight: "text-[#94A3B8]",
    accentBg: "bg-[#94A3B8]/10",
    statuses: ["not_started", "pending"],
  },
  {
    label: "撰写中",
    accent: "bg-[#3B82F6]",
    accentLight: "text-[#3B82F6]",
    accentBg: "bg-[#3B82F6]/10",
    statuses: ["writing", "editing", "draft"],
  },
  {
    label: "审核中",
    accent: "bg-[#7C3AED]",
    accentLight: "text-[#7C3AED]",
    accentBg: "bg-[#7C3AED]/10",
    statuses: ["pending_review", "rejected"],
  },
  {
    label: "已完成",
    accent: "bg-[#22C55E]",
    accentLight: "text-[#22C55E]",
    accentBg: "bg-[#22C55E]/10",
    statuses: ["completed"],
  },
  {
    label: "已批准",
    accent: "bg-[#14B8A6]",
    accentLight: "text-[#14B8A6]",
    accentBg: "bg-[#14B8A6]/10",
    statuses: ["approved", "signed"],
  },
];

// ── Helpers ──

function avatarColor(name: string): string {
  const palette = [
    "bg-blue-500",
    "bg-emerald-500",
    "bg-violet-500",
    "bg-rose-500",
    "bg-amber-500",
    "bg-cyan-500",
  ];
  return palette[(name.charCodeAt(0) ?? 0) % palette.length] ?? palette[0]!;
}

/** Collect all chapters matching any of the given statuses, preserving hierarchy. */
function collectByStatuses(
  chapters: ProjectChapter[],
  statuses: Set<string>,
): { parent: ProjectChapter; children: ProjectChapter[] }[] {
  const groups: { parent: ProjectChapter; children: ProjectChapter[] }[] = [];

  for (const ch of chapters) {
    const childMatches = ch.children?.filter((c) => statuses.has(c.status)) ?? [];

    if (statuses.has(ch.status)) {
      groups.push({ parent: ch, children: childMatches });
    } else if (childMatches.length > 0) {
      groups.push({ parent: ch, children: childMatches });
    }
    // Recurse into children that themselves have children
    const nested = collectByStatuses(ch.children ?? [], statuses);
    groups.push(...nested);
  }

  return groups;
}

/** Deduplicate groups — a parent already captured shouldn't appear again as a nested group. */
function dedupGroups(
  groups: { parent: ProjectChapter; children: ProjectChapter[] }[],
): { parent: ProjectChapter; children: ProjectChapter[] }[] {
  const seen = new Set<string>();
  const result: { parent: ProjectChapter; children: ProjectChapter[] }[] = [];
  for (const g of groups) {
    if (seen.has(g.parent.id)) continue;
    seen.add(g.parent.id);
    for (const c of g.children) seen.add(c.id);
    result.push(g);
  }
  return result;
}

// ── Child Task Card ──

function ChildTaskCard({ chapter, columnAccent }: { chapter: ProjectChapter; columnAccent: string }) {
  const progress =
    chapter.wordCountTarget > 0
      ? Math.round((chapter.wordCountCurrent / chapter.wordCountTarget) * 100)
      : 0;
  const clampedProgress = Math.min(progress, 100);

  return (
    <div className="rounded-lg border border-[#E2E8F0]/60 bg-white p-2.5 flex flex-col gap-1.5 cursor-pointer shadow-[0_1px_2px_rgba(0,0,0,0.03)] hover:shadow-[0_3px_8px_rgba(0,0,0,0.07)] hover:border-[#CBD5E1] transition-all duration-200">
      {/* Title */}
      <div className="text-[12px] font-medium leading-snug text-[#334155] line-clamp-2">
        {chapter.title}
      </div>

      {/* Progress */}
      {chapter.wordCountTarget > 0 && (
        <div className="flex items-center gap-2">
          <div className="h-1 rounded-full bg-[#F1F5F9] overflow-hidden flex-1">
            <div
              className={cn("h-full rounded-full transition-all duration-500", columnAccent)}
              style={{ width: `${clampedProgress}%` }}
            />
          </div>
          <span className={cn("text-[10px] font-medium shrink-0", clampedProgress >= 100 ? "text-[#22C55E]" : "text-[#94A3B8]")}>
            {clampedProgress}%
          </span>
        </div>
      )}

      {/* Assignee */}
      <div className="flex items-center gap-1.5">
        {chapter.assignedName ? (
          <>
            <div className={cn("h-4 w-4 rounded-full flex items-center justify-center text-[8px] font-medium text-white shrink-0", avatarColor(chapter.assignedName))}>
              {chapter.assignedName.slice(0, 1)}
            </div>
            <span className="text-[11px] text-[#64748B] truncate">{chapter.assignedName}</span>
          </>
        ) : (
          <span className="text-[11px] text-[#CBD5E1]">未分配</span>
        )}
      </div>
    </div>
  );
}

// ── Parent Group Card ──

function GroupCard({
  parent,
  children,
  columnAccent,
  parentMatchesColumn,
}: {
  parent: ProjectChapter;
  children: ProjectChapter[];
  columnAccent: string;
  parentMatchesColumn: boolean;
}) {
  const hasChildren = children.length > 0;

  // Leaf node — no children, show as a standalone card
  if (!hasChildren && parentMatchesColumn) {
    return <StandaloneTaskCard chapter={parent} columnAccent={columnAccent} />;
  }

  return (
    <div className="rounded-xl border border-[#E2E8F0]/80 bg-white overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.04)] hover:shadow-[0_4px_12px_rgba(0,0,0,0.08)] transition-shadow duration-200">
      {/* Parent header */}
      <div className={cn(
        "px-3 py-2 flex items-center gap-2 border-b border-[#F1F5F9]",
        parentMatchesColumn ? "bg-[#F8FAFC]" : "bg-[#F8FAFC]/50",
      )}>
        <ChevronRight className="h-3.5 w-3.5 text-[#94A3B8] shrink-0" />
        <span className={cn(
          "text-[13px] leading-snug line-clamp-1",
          parentMatchesColumn ? "font-semibold text-[#0F172A]" : "font-medium text-[#64748B]",
        )}>
          {parent.title}
        </span>
        {parentMatchesColumn && parent.wordCountTarget > 0 && (
          <span className="ml-auto text-[10px] text-[#94A3B8] shrink-0">
            {parent.wordCountCurrent.toLocaleString()}/{parent.wordCountTarget.toLocaleString()}
          </span>
        )}
        <span className={cn(
          "ml-auto shrink-0 inline-flex items-center justify-center rounded-full px-1.5 h-4 text-[10px] font-medium",
          !parentMatchesColumn && "ml-auto",
        )}
        style={{ marginLeft: parentMatchesColumn && parent.wordCountTarget > 0 ? undefined : "auto" }}
        >
          <span className="text-[#94A3B8]">{children.length}</span>
        </span>
      </div>

      {/* Children list */}
      <div className="flex flex-col gap-1.5 p-2 pl-5">
        {children.map((child) => (
          <ChildTaskCard key={child.id} chapter={child} columnAccent={columnAccent} />
        ))}
      </div>
    </div>
  );
}

// ── Standalone Task Card (leaf node with no children) ──

function StandaloneTaskCard({ chapter, columnAccent }: { chapter: ProjectChapter; columnAccent: string }) {
  const progress =
    chapter.wordCountTarget > 0
      ? Math.round((chapter.wordCountCurrent / chapter.wordCountTarget) * 100)
      : 0;
  const clampedProgress = Math.min(progress, 100);

  return (
    <div className="rounded-xl border border-[#E2E8F0]/80 bg-white p-3.5 flex flex-col gap-2.5 cursor-pointer shadow-[0_1px_3px_rgba(0,0,0,0.04)] hover:shadow-[0_4px_12px_rgba(0,0,0,0.08)] hover:border-[#CBD5E1] hover:-translate-y-0.5 transition-all duration-200">
      <div className="text-[13px] font-semibold leading-snug text-[#0F172A] line-clamp-2">
        {chapter.title}
      </div>

      {chapter.wordCountTarget > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="h-1.5 rounded-full bg-[#F1F5F9] overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-500", columnAccent)}
              style={{ width: `${clampedProgress}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-[11px] text-[#94A3B8]">
            <span>{chapter.wordCountCurrent.toLocaleString()} / {chapter.wordCountTarget.toLocaleString()} 字</span>
            <span className={cn("font-medium", clampedProgress >= 100 && "text-[#22C55E]")}>
              {clampedProgress}%
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 pt-0.5">
        {chapter.assignedName ? (
          <>
            <div className={cn("h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-medium text-white shrink-0 ring-1 ring-white shadow-sm", avatarColor(chapter.assignedName))}>
              {chapter.assignedName.slice(0, 2)}
            </div>
            <span className="text-[12px] text-[#475569] truncate">{chapter.assignedName}</span>
          </>
        ) : (
          <>
            <div className="h-6 w-6 rounded-full bg-[#F1F5F9] flex items-center justify-center text-[10px] text-[#94A3B8] shrink-0">--</div>
            <span className="text-[12px] text-[#94A3B8]">未分配</span>
          </>
        )}
      </div>
    </div>
  );
}

// ── Main Component ──

interface KanbanBoardProps {
  project: ReportProject;
  onRefresh: () => void;
  can?: (action: string) => boolean;
  role?: string | null;
}

export function KanbanBoard({ project, can: _can, role: _role }: KanbanBoardProps) {
  const outline = project.chapters ?? [];

  const grouped = useMemo(() => {
    return COLUMNS.map((col) => {
      const statuses = new Set(col.statuses);
      const rawGroups = collectByStatuses(outline, statuses);
      const groups = dedupGroups(rawGroups);
      // Compute total chapters in column (for the badge count)
      let count = 0;
      for (const g of groups) {
        if (statuses.has(g.parent.status)) count++;
        count += g.children.filter((c) => statuses.has(c.status)).length;
      }
      return { ...col, groups, count };
    });
  }, [outline]);

  return (
    <div className="flex gap-4 overflow-x-auto p-5 h-full">
      {grouped.map((column) => {
        const statuses = new Set(column.statuses);

        return (
          <div
            key={column.label}
            className="flex flex-col min-w-[272px] w-[272px] shrink-0"
          >
            {/* Column header with pill badge */}
            <div className="flex items-center gap-2 mb-3 px-1">
              <span className={cn("h-2.5 w-2.5 rounded-full shrink-0", column.accent)} />
              <span className="text-[13px] font-semibold text-foreground">
                {column.label}
              </span>
              <span
                className={cn(
                  "ml-auto inline-flex items-center justify-center rounded-full px-2 h-5 text-[11px] font-medium",
                  column.accentBg,
                  column.accentLight,
                )}
              >
                {column.count}
              </span>
            </div>

            {/* Column body with subtle background */}
            <div className="flex flex-col gap-2.5 flex-1 overflow-y-auto rounded-xl bg-[#F8FAFC]/80 p-2.5">
              {column.groups.map((group) => (
                <GroupCard
                  key={group.parent.id}
                  parent={group.parent}
                  children={group.children}
                  columnAccent={column.accent}
                  parentMatchesColumn={statuses.has(group.parent.status)}
                />
              ))}
              {column.count === 0 && (
                <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[#E2E8F0] py-8 text-[12px] text-[#94A3B8]">
                  <FileText className="h-5 w-5 text-[#CBD5E1]" />
                  <span>暂无章节</span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
