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
