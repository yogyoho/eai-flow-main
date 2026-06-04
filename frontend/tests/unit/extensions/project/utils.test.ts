import { describe, expect, it } from "vitest";

import type { ProjectChapter } from "@/extensions/project/types";

import {
  type ChapterStatus,
  activityLabel,
  flattenChapters,
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

  it("returns 'draft' when no content", () => {
    expect(inferStatus(base())).toBe<ChapterStatus>("draft");
  });

  it("returns 'writing' when wordCountCurrent > 0", () => {
    expect(inferStatus(base({ wordCountCurrent: 100 }))).toBe<ChapterStatus>("writing");
  });

  it("returns 'review' for in_review status", () => {
    expect(inferStatus(base({ status: "in_review" }))).toBe<ChapterStatus>("review");
  });

  it("returns 'review' for pending_review status", () => {
    expect(inferStatus(base({ status: "pending_review", wordCountCurrent: 500 }))).toBe<ChapterStatus>("review");
  });

  it("returns 'completed' for completed status", () => {
    expect(inferStatus(base({ status: "completed" }))).toBe<ChapterStatus>("completed");
  });

  it("returns 'completed' for approved status", () => {
    expect(inferStatus(base({ status: "approved", wordCountCurrent: 1000 }))).toBe<ChapterStatus>("completed");
  });

  it("returns 'completed' for signed status", () => {
    expect(inferStatus(base({ status: "signed" }))).toBe<ChapterStatus>("completed");
  });

  it("completed takes priority over review", () => {
    expect(inferStatus(base({ status: "approved" }))).toBe<ChapterStatus>("completed");
  });

  it("review takes priority over writing", () => {
    expect(inferStatus(base({ status: "in_review", wordCountCurrent: 500 }))).toBe<ChapterStatus>("review");
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
