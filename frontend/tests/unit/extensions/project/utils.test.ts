import { describe, expect, it } from "@rstest/core";

import type { ProjectChapter } from "@/extensions/project/types";
import {
  type ChapterBlockState,
  type ChapterStatus,
  activityLabel,
  deriveBlockState,
  flattenChapters,
  groupByRole,
  hasAnyContent,
  inferStatus,
} from "@/extensions/project/utils";

describe("flattenChapters", () => {
  it("flattens nested chapters", () => {
    const chapters: ProjectChapter[] = [
      {
        id: "1", projectId: "p", parentId: null, title: "Ch1", level: 1,
        sortOrder: 0, status: "pending", content: null,
        assignedTo: null, assignedName: null,
        wordCountTarget: 0, wordCountCurrent: 0,
        purpose: null, generationHint: null, children: [
          {
            id: "1-1", projectId: "p", parentId: "1", title: "Ch1-1", level: 2,
            sortOrder: 0, status: "pending", content: null,
            assignedTo: null, assignedName: null,
            wordCountTarget: 0, wordCountCurrent: 0,
            purpose: null, generationHint: null, children: [],
            createdAt: null, updatedAt: null,
          },
        ],
        createdAt: null, updatedAt: null,
      },
      {
        id: "2", projectId: "p", parentId: null, title: "Ch2", level: 1,
        sortOrder: 1, status: "pending", content: null,
        assignedTo: null, assignedName: null,
        wordCountTarget: 0, wordCountCurrent: 0,
        purpose: null, generationHint: null, children: [],
        createdAt: null, updatedAt: null,
      },
    ];
    const flat = flattenChapters(chapters);
    expect(flat).toHaveLength(3);
    expect(flat.map((c) => c.id)).toEqual(["1", "1-1", "2"]);
  });

  it("returns empty for empty input", () => {
    expect(flattenChapters([])).toEqual([]);
  });
});

describe("inferStatus", () => {
  const base = (overrides: Partial<ProjectChapter> = {}): ProjectChapter => ({
    id: "1", projectId: "p", parentId: null, title: "Test", level: 1,
    sortOrder: 0, status: "pending", content: null,
    assignedTo: null, assignedName: null,
    wordCountTarget: 0, wordCountCurrent: 0,
    purpose: null, generationHint: null, children: [],
    createdAt: null, updatedAt: null,
    ...overrides,
  });

  it("returns 'pending' when no content", () => {
    expect(inferStatus(base())).toBe<ChapterStatus>("pending");
  });

  it("returns 'draft' when wordCountCurrent > 0", () => {
    expect(inferStatus(base({ wordCountCurrent: 100 }))).toBe<ChapterStatus>("draft");
  });

  it("returns 'reviewing' for reviewing status", () => {
    expect(inferStatus(base({ status: "reviewing" }))).toBe<ChapterStatus>("reviewing");
  });

  it("returns 'reviewing' for legacy in_review/pending_review", () => {
    expect(inferStatus(base({ status: "in_review", wordCountCurrent: 500 }))).toBe<ChapterStatus>("reviewing");
    expect(inferStatus(base({ status: "pending_review", wordCountCurrent: 500 }))).toBe<ChapterStatus>("reviewing");
  });

  it("returns 'approved' for approved status", () => {
    expect(inferStatus(base({ status: "approved", wordCountCurrent: 1000 }))).toBe<ChapterStatus>("approved");
  });

  it("returns 'approved' for legacy completed/signed", () => {
    expect(inferStatus(base({ status: "completed" }))).toBe<ChapterStatus>("approved");
    expect(inferStatus(base({ status: "signed" }))).toBe<ChapterStatus>("approved");
  });

  it("approved takes priority over reviewing", () => {
    expect(inferStatus(base({ status: "approved", wordCountCurrent: 500 }))).toBe<ChapterStatus>("approved");
  });

  it("reviewing takes priority over draft", () => {
    expect(inferStatus(base({ status: "reviewing", wordCountCurrent: 500 }))).toBe<ChapterStatus>("reviewing");
  });
});

describe("activityLabel", () => {
  it("returns null for null input", () => {
    expect(activityLabel(null)).toBeNull();
  });

  it("returns '刚刚编辑' for < 5 minutes", () => {
    const fourMinutesAgo = new Date(Date.now() - 4 * 60 * 1000).toISOString();
    expect(activityLabel(fourMinutesAgo)).toBe("刚刚编辑");
  });

  it("returns 'X分钟前' for < 60 minutes", () => {
    const thirtyMinAgo = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    expect(activityLabel(thirtyMinAgo)).toBe("30分钟前");
  });

  it("returns 'X小时前' for < 24 hours", () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(activityLabel(threeHoursAgo)).toBe("3小时前");
  });

  it("returns 'X天前' for >= 24 hours", () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(activityLabel(twoDaysAgo)).toBe("2天前");
  });
});

// EAI-CUSTOM: 状态机 + 分工纯函数(ADR 2026-08-10)

const baseChapter = (overrides: Partial<ProjectChapter> = {}): ProjectChapter => ({
  id: "1", projectId: "p", parentId: null, title: "Test", level: 1,
  sortOrder: 0, status: "pending", content: null,
  assignedTo: null, assignedName: null,
  wordCountTarget: 0, wordCountCurrent: 0,
  purpose: null, generationHint: null, children: [],
  createdAt: null, updatedAt: null,
  ...overrides,
});

describe("hasAnyContent", () => {
  it("returns false when no chapters have content", () => {
    expect(hasAnyContent([baseChapter(), baseChapter({ children: [baseChapter()] })])).toBe(false);
  });

  it("returns true when any chapter has content", () => {
    expect(hasAnyContent([baseChapter(), baseChapter({ content: "hello" })])).toBe(true);
  });

  it("returns true for nested content", () => {
    expect(hasAnyContent([baseChapter({ children: [baseChapter({ content: "x" })] })])).toBe(true);
  });

  it("ignores whitespace-only content", () => {
    expect(hasAnyContent([baseChapter({ content: "   \n\t " })])).toBe(false);
  });

  it("returns false for empty input", () => {
    expect(hasAnyContent([])).toBe(false);
  });
});

describe("deriveBlockState", () => {
  it("not_generated when temporal workflow id is null/undefined/empty", () => {
    expect(deriveBlockState(null, false)).toBe<ChapterBlockState>("not_generated");
    expect(deriveBlockState(undefined, false)).toBe<ChapterBlockState>("not_generated");
    expect(deriveBlockState("", false)).toBe<ChapterBlockState>("not_generated");
  });

  it("generating when workflow started but no content", () => {
    expect(deriveBlockState("wf-123", false)).toBe<ChapterBlockState>("generating");
  });

  it("human_edit when at least one chapter has content", () => {
    expect(deriveBlockState("wf-123", true)).toBe<ChapterBlockState>("human_edit");
  });

  it("content takes priority over workflow id presence", () => {
    expect(deriveBlockState(null, true)).toBe<ChapterBlockState>("not_generated");
  });
});

describe("groupByRole", () => {
  it("groups items by role", () => {
    const items = [
      { role: "writer", id: "1" },
      { role: "writer", id: "2" },
      { role: "reviewer", id: "3" },
    ];
    expect(groupByRole(items)).toEqual({
      writer: [{ role: "writer", id: "1" }, { role: "writer", id: "2" }],
      reviewer: [{ role: "reviewer", id: "3" }],
    });
  });

  it("returns empty object for empty input", () => {
    expect(groupByRole([])).toEqual({});
  });
});
