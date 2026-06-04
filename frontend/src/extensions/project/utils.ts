import type { ProjectChapter } from "./types";

export type ChapterStatus = "draft" | "writing" | "review" | "completed";

/** Flatten nested chapters into a flat array (depth-first). */
export function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  for (const ch of chapters) {
    result.push(ch);
    if (ch.children?.length) result.push(...flattenChapters(ch.children));
  }
  return result;
}

/**
 * Auto-infer chapter display status from content and backend status.
 * Priority: completed > review > writing > draft
 */
export function inferStatus(ch: ProjectChapter): ChapterStatus {
  if (["completed", "approved", "signed"].includes(ch.status)) return "completed";
  if (["in_review", "pending_review"].includes(ch.status)) return "review";
  if ((ch.wordCountCurrent ?? 0) > 0) return "writing";
  return "draft";
}

/** Format updatedAt into a human-friendly activity label. */
export function activityLabel(updatedAt: string | null): string | null {
  if (!updatedAt) return null;
  const diff = Date.now() - new Date(updatedAt).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 5) return "刚刚编辑";
  if (minutes < 60) return `${minutes}分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`;
  return `${Math.floor(minutes / 1440)}天前`;
}

/** Aggregate total word count across all chapters. */
export function aggregateWordCount(chapters: ProjectChapter[]): number {
  let total = 0;
  for (const ch of flattenChapters(chapters)) {
    total += ch.wordCountCurrent ?? 0;
  }
  return total;
}
