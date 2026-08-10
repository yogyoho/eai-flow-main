import type { ProjectChapter } from "./types";

// EAI-CUSTOM: canonical chapter status buckets (ADR 2026-08-02 P4).
export type ChapterStatus = "pending" | "draft" | "reviewing" | "approved";

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
 * Priority: approved > reviewing > draft > pending.
 * Legacy backend values are folded into canonical buckets during the transition.
 */
export function inferStatus(ch: ProjectChapter): ChapterStatus {
  if (["approved", "signed", "completed"].includes(ch.status)) return "approved";
  if (["reviewing", "in_review", "pending_review", "review", "reviewed"].includes(ch.status)) return "reviewing";
  if ((ch.wordCountCurrent ?? 0) > 0 || ["draft", "writing"].includes(ch.status)) return "draft";
  return "pending";
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

// EAI-CUSTOM: 章节进度区块状态机 + 分工纯函数(ADR 2026-08-10)

/** 章节进度区块的 3 态。 */
export type ChapterBlockState = "not_generated" | "generating" | "human_edit";

/** 任意章节(递归)是否有非空 content。 */
export function hasAnyContent(chapters: ProjectChapter[]): boolean {
  return flattenChapters(chapters).some((c) => (c.content ?? "").trim().length > 0);
}

/**
 * EAI-CUSTOM: 章节进度区块状态机(ADR 2026-08-10)。
 * not_generated = 工作流未启动; generating = 已启动但无任何章节有 content;
 * human_edit = 至少一章有 content(初稿已产出)。
 * 用 chapter.content 是否存在做 ②↔③ 分界,不依赖工作流节点类型。
 */
export function deriveBlockState(
  temporalWorkflowId: string | null | undefined,
  hasAnyChapterContent: boolean,
): ChapterBlockState {
  if (!temporalWorkflowId) return "not_generated";
  if (!hasAnyChapterContent) return "generating";
  return "human_edit";
}

/** 按角色分组(泛型,适用于任何带 role 字段的对象)。 */
export function groupByRole<T extends { role: string }>(members: T[]): Record<string, T[]> {
  const groups: Record<string, T[]> = {};
  for (const m of members) {
    (groups[m.role] ??= []).push(m);
  }
  return groups;
}
