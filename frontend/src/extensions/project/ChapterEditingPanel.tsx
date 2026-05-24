"use client";

import { ArrowRight, Loader2, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import type { ProjectChapter, ReportProject } from "@/extensions/project/types";
import { CHAPTER_STATUS_LABELS, MEMBER_ROLE_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

import { ChapterAssignDropdown } from "./ChapterAssignDropdown";

interface ChapterEditingPanelProps {
  project: ReportProject;
  onRefresh: () => void;
}

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  return chapters.flatMap((c) => [c, ...flattenChapters(c.children)]);
}

const STATUS_DOT: Record<string, string> = {
  pending: "bg-muted-foreground",
  draft: "bg-amber-500",
  editing: "bg-blue-500",
  writing: "bg-blue-500",
  completed: "bg-green-500",
};

export function ChapterEditingPanel({ project, onRefresh }: ChapterEditingPanelProps) {
  const router = useRouter();
  const [loadingChapterId, setLoadingChapterId] = useState<string | null>(null);

  const flat = flattenChapters(project.chapters);
  const completedCount = flat.filter((c) => c.status === "completed").length;
  const editingCount = flat.filter((c) => c.status === "editing" || c.status === "writing").length;
  const unassignedCount = flat.filter((c) => !c.assignedTo && c.status !== "completed").length;
  const progressPct = flat.length > 0 ? Math.round((completedCount / flat.length) * 100) : 0;

  const handleStartEditing = useCallback(async (chapterId: string) => {
    setLoadingChapterId(chapterId);
    try {
      const result = await projectApi.startChapterEditing(project.id, chapterId);
      router.push(`/workspace/chats/${result.threadId}?from=project`);
    } catch {
      toast.error("启动编辑失败");
    } finally {
      setLoadingChapterId(null);
    }
  }, [project.id, router]);

  return (
    <div className="flex h-full">
      {/* Left: Chapter table */}
      <div className="flex-1 p-6 overflow-y-auto">
        <h2 className="text-lg font-bold text-foreground mb-4">章节分配与编辑</h2>
        <div className="rounded-xl border border-border overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_120px_100px_140px] gap-2 bg-muted/50 px-4 py-2.5 text-xs font-medium text-muted-foreground">
            <span>章节</span>
            <span>编写人</span>
            <span>状态</span>
            <span className="text-right">操作</span>
          </div>
          {/* Rows */}
          {flat.map((chapter) => (
            <div
              key={chapter.id}
              className="grid grid-cols-[1fr_120px_100px_140px] gap-2 items-center px-4 py-3 border-t border-border hover:bg-muted/30 transition-colors"
            >
              <span className="text-sm text-foreground truncate">{chapter.title}</span>
              <span className="text-sm">
                {chapter.assignedName ? (
                  <span className="text-foreground">{chapter.assignedName}</span>
                ) : chapter.status !== "completed" ? (
                  <ChapterAssignDropdown
                    projectId={project.id}
                    chapterId={chapter.id}
                    members={project.members}
                    currentAssignee={chapter.assignedTo}
                    onAssigned={onRefresh}
                  />
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </span>
              <span className="flex items-center gap-1.5">
                <span className={cn("h-2 w-2 rounded-full shrink-0", STATUS_DOT[chapter.status] ?? STATUS_DOT.pending)} />
                <span className="text-xs text-muted-foreground">{CHAPTER_STATUS_LABELS[chapter.status]}</span>
              </span>
              <span className="flex justify-end">
                {chapter.status === "completed" ? (
                  <Button variant="ghost" size="sm" className="h-7 text-xs">
                    查看
                  </Button>
                ) : (
                  <Button
                    variant={chapter.status === "editing" || chapter.status === "writing" ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-xs gap-1"
                    onClick={() => handleStartEditing(chapter.id)}
                    disabled={loadingChapterId === chapter.id}
                  >
                    {loadingChapterId === chapter.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <ArrowRight className="h-3 w-3" />
                    )}
                    {chapter.status === "editing" || chapter.status === "writing" ? "进入编辑" : "开始编辑"}
                  </Button>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Right: Sidebar */}
      <div className="w-80 border-l border-border bg-muted/30 p-6 flex flex-col gap-6 overflow-y-auto">
        {/* Progress */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">编辑进度</h3>
          <div className="h-2 rounded-full bg-muted overflow-hidden mb-3">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-green-600">{completedCount}</div>
              <div className="text-xs text-muted-foreground">已完成</div>
            </div>
            <div>
              <div className="text-lg font-bold text-blue-600">{editingCount}</div>
              <div className="text-xs text-muted-foreground">编辑中</div>
            </div>
            <div>
              <div className="text-lg font-bold text-amber-600">{unassignedCount}</div>
              <div className="text-xs text-muted-foreground">待分配</div>
            </div>
          </div>
        </div>

        {/* Team */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Users className="h-4 w-4" />
            团队成员
          </h3>
          <div className="space-y-2">
            {project.members.map((m) => (
              <div key={m.userId} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{m.username}</span>
                <span className="text-xs text-muted-foreground">{MEMBER_ROLE_LABELS[m.role]}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Tips */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-2">协作编辑说明</h3>
          <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
            <li>分配编写人后，点击「开始编辑」进入对话页</li>
            <li>AI Agent 会协助润色、补充内容、检查一致性</li>
            <li>每个章节独立对话，互不干扰</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
