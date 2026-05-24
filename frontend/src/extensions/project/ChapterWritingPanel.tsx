"use client";

import { CheckCircle2, Clock, Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import type { ProjectChapter } from "@/extensions/project/types";
import { CHAPTER_STATUS_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface ChapterWritingPanelProps {
  projectId: string;
  projectName: string;
  chapters: ProjectChapter[];
}

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  return chapters.flatMap((c) => [c, ...flattenChapters(c.children)]);
}

const STATUS_STYLES: Record<string, string> = {
  pending: "text-muted-foreground",
  writing: "text-primary font-medium",
  draft: "text-amber-600",
  completed: "text-green-600",
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <Clock className="h-4 w-4 text-muted-foreground" />,
  writing: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
  draft: <CheckCircle2 className="h-4 w-4 text-amber-500" />,
  completed: <CheckCircle2 className="h-4 w-4 text-green-500" />,
};

export function ChapterWritingPanel({ projectId, projectName, chapters }: ChapterWritingPanelProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const flat = flattenChapters(chapters);

  const completedCount = flat.filter((c) => c.status === "completed" || c.status === "draft").length;
  const totalCount = flat.length;
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const handleStartWriting = useCallback(async () => {
    setLoading(true);
    try {
      const result = await projectApi.startWriting(projectId);
      router.push(`/workspace/chats/${result.threadId}?from=project`);
    } catch {
      toast.error("启动 AI 撰写失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, router]);

  return (
    <div className="flex h-full">
      {/* Left: Chapter progress list */}
      <div className="flex-1 p-6 overflow-y-auto">
        <h2 className="text-lg font-bold text-foreground mb-4">章节撰写进度</h2>
        <div className="space-y-1">
          {flat.map((chapter) => (
            <div
              key={chapter.id}
              className={cn(
                "flex items-center gap-3 rounded-lg px-4 py-3 transition-colors",
                "hover:bg-muted/50",
              )}
            >
              <span className="shrink-0">{STATUS_ICONS[chapter.status] ?? STATUS_ICONS.pending}</span>
              <div className="flex-1 min-w-0">
                <p className={cn("text-sm truncate", STATUS_STYLES[chapter.status] ?? "")}>
                  {chapter.title}
                </p>
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {chapter.wordCountCurrent.toLocaleString()}/{chapter.wordCountTarget.toLocaleString()} 字
              </span>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {CHAPTER_STATUS_LABELS[chapter.status]}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Right: Progress summary + CTA */}
      <div className="w-80 border-l border-border bg-muted/30 p-6 flex flex-col gap-6">
        {/* Progress card */}
        <div className="rounded-xl border border-border bg-background p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">撰写进度</h3>
          <div className="flex items-end gap-2 mb-2">
            <span className="text-3xl font-bold text-foreground">{progressPct}%</span>
            <span className="text-sm text-muted-foreground mb-1">完成</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-foreground">{completedCount}</div>
              <div className="text-xs text-muted-foreground">已完成</div>
            </div>
            <div>
              <div className="text-lg font-bold text-foreground">
                {flat.filter((c) => c.status === "writing").length}
              </div>
              <div className="text-xs text-muted-foreground">撰写中</div>
            </div>
            <div>
              <div className="text-lg font-bold text-foreground">
                {flat.filter((c) => c.status === "pending").length}
              </div>
              <div className="text-xs text-muted-foreground">待撰写</div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <Button
          size="lg"
          className="w-full gap-2"
          onClick={handleStartWriting}
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {loading ? "正在启动..." : "开始 AI 撰写"}
        </Button>
        <p className="text-xs text-muted-foreground text-center">
          点击后将跳转到 DeerFlow 对话页，AI 将逐章撰写报告
        </p>
      </div>
    </div>
  );
}
