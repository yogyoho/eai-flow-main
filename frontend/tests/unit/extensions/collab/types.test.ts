import { expect, test } from "vitest";

import type { CollabVersion, VersionDiffResponse } from "@/extensions/types";

test("CollabVersion interface has expected fields", () => {
  const version: CollabVersion = {
    id: 1,
    doc_id: "doc-1",
    version: 3,
    summary: "test summary",
    created_by: "user-1",
    created_at: "2026-01-01T00:00:00Z",
    username: "testuser",
    full_name: "Test User",
  };

  expect(version.id).toBe(1);
  expect(version.doc_id).toBe("doc-1");
  expect(version.version).toBe(3);
  expect(version.summary).toBe("test summary");
  expect(version.created_by).toBe("user-1");
  expect(version.created_at).toBe("2026-01-01T00:00:00Z");
  expect(version.username).toBe("testuser");
  expect(version.full_name).toBe("Test User");
});

test("CollabVersion allows null optional fields", () => {
  const version: CollabVersion = {
    id: 2,
    doc_id: "doc-2",
    version: 1,
    summary: null,
    created_by: null,
    created_at: "2026-01-01T00:00:00Z",
  };

  expect(version.summary).toBeNull();
  expect(version.created_by).toBeNull();
  expect(version.username).toBeUndefined();
  expect(version.full_name).toBeUndefined();
});

test("VersionDiffResponse interface has expected shape", () => {
  const diff: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: "summary v1",
    to_summary: "summary v2",
    from_created_at: "2026-01-01T00:00:00Z",
    to_created_at: "2026-01-02T00:00:00Z",
    diff_blocks: [
      { type: "added", content: "new line" },
      { type: "removed", content: "old line" },
      { type: "changed", content: "modified", from_content: "old", to_content: "modified" },
    ],
    ai_summary: "AI detected 3 changes",
  };

  expect(diff.from_version).toBe(1);
  expect(diff.to_version).toBe(2);
  expect(diff.from_summary).toBe("summary v1");
  expect(diff.to_summary).toBe("summary v2");
  expect(diff.diff_blocks).toHaveLength(3);
  expect(diff.diff_blocks[0]?.type).toBe("added");
  expect(diff.diff_blocks[1]?.type).toBe("removed");
  expect(diff.diff_blocks[2]?.type).toBe("changed");
  expect(diff.ai_summary).toBe("AI detected 3 changes");
});

test("VersionDiffResponse allows null optional fields", () => {
  const diff: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [],
    ai_summary: null,
  };

  expect(diff.from_summary).toBeNull();
  expect(diff.to_summary).toBeNull();
  expect(diff.ai_summary).toBeNull();
  expect(diff.diff_blocks).toHaveLength(0);
});

test("VersionDiffResponse diff_block supports block_id field", () => {
  const diff: VersionDiffResponse = {
    from_version: 1,
    to_version: 2,
    from_summary: null,
    to_summary: null,
    from_created_at: null,
    to_created_at: null,
    diff_blocks: [
      { type: "added", content: "new", block_id: "block-1" },
    ],
    ai_summary: null,
  };

  expect(diff.diff_blocks[0]?.block_id).toBe("block-1");
});
