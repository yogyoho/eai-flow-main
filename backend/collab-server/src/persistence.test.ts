import { describe, it, expect, vi, beforeEach } from "vitest";
import * as Y from "yjs";

// Mock pg — Pool must be a constructable function
const mockQuery = vi.fn();
function MockPool() {
  return { query: mockQuery };
}
vi.mock("pg", () => ({
  Pool: MockPool,
  default: { Pool: MockPool },
}));

// Mock fs for file_ref tests
vi.mock("fs", () => ({
  default: {
    existsSync: (...args: unknown[]) => mockExistsSync(...args),
    readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
    statSync: (...args: unknown[]) => mockStatSync(...args),
  },
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
  readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
  statSync: (...args: unknown[]) => mockStatSync(...args),
}));
const mockReadFileSync = vi.fn();
const mockExistsSync = vi.fn();
const mockStatSync = vi.fn();

// Import after mocks
const { loadMarkdownForDoc, hasCollabData, storeDocument, pruneVersions, MAX_VERSIONS_PER_DOC } = await import(
  "./persistence.js"
);

describe("loadMarkdownForDoc", () => {
  beforeEach(() => {
    mockQuery.mockReset();
    mockReadFileSync.mockReset();
    mockExistsSync.mockReset();
    mockStatSync.mockReset();
  });

  it("returns content from ai_documents when content field exists", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ content: "# 标题\n\n段落内容", doc_type: "document", file_ref_path: null }],
    });

    const result = await loadMarkdownForDoc("doc-123");
    expect(result).toBe("# 标题\n\n段落内容");
    expect(mockQuery).toHaveBeenCalledWith(
      "SELECT content, doc_type, file_ref_path FROM ai_documents WHERE id = $1",
      ["doc-123"],
    );
  });

  it("returns null when document does not exist", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const result = await loadMarkdownForDoc("nonexistent");
    expect(result).toBeNull();
  });

  it("reads file content for file_ref documents when file exists", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ content: null, doc_type: "file_ref", file_ref_path: "/tmp/test.md" }],
    });
    mockExistsSync.mockReturnValue(true);
    mockStatSync.mockReturnValue({ size: 1024 });
    mockReadFileSync.mockReturnValue("# 文件内容\n\n这是文件内容");

    const result = await loadMarkdownForDoc("doc-456");
    expect(result).toBe("# 文件内容\n\n这是文件内容");
    expect(mockReadFileSync).toHaveBeenCalledWith("/tmp/test.md", "utf-8");
  });

  it("returns null for file_ref when file does not exist", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ content: null, doc_type: "file_ref", file_ref_path: "/tmp/missing.md" }],
    });
    mockExistsSync.mockReturnValue(false);

    const result = await loadMarkdownForDoc("doc-789");
    expect(result).toBeNull();
  });

  it("returns null when file_ref file exceeds 10MB", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ content: null, doc_type: "file_ref", file_ref_path: "/tmp/huge.md" }],
    });
    mockExistsSync.mockReturnValue(true);
    mockStatSync.mockReturnValue({ size: 11 * 1024 * 1024 }); // 11MB

    const result = await loadMarkdownForDoc("doc-huge");
    expect(result).toBeNull();
  });

  it("returns null when content is empty string", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ content: "", doc_type: "document", file_ref_path: null }],
    });

    const result = await loadMarkdownForDoc("doc-empty");
    expect(result).toBeNull();
  });
});

describe("hasCollabData", () => {
  beforeEach(() => {
    mockQuery.mockReset();
  });

  it("returns true when collab_documents has entry", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [{ "?column?": 1 }] });

    const result = await hasCollabData("doc-with-yjs");
    expect(result).toBe(true);
  });

  it("returns false when no collab_documents entry", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const result = await hasCollabData("doc-no-yjs");
    expect(result).toBe(false);
  });
});

describe("storeDocument (Yjs round-trip)", () => {
  beforeEach(() => {
    mockQuery.mockReset();
  });

  it("stores Yjs update and can be loaded back", async () => {
    // Create a Yjs doc, write content, encode it
    const doc = new Y.Doc();
    const fragment = doc.getXmlFragment("document-store");
    const meta = doc.getMap("_collabMeta");
    meta.set("pendingMarkdown", "# Test Content");
    const update = Y.encodeStateAsUpdate(doc);

    // Store the update via Buffer
    const storedBuffer = Buffer.from(update);

    mockQuery.mockResolvedValueOnce({ rowCount: 1 });

    await storeDocument("doc-test", update, "user-1");

    // Verify the query was called with a Buffer
    expect(mockQuery).toHaveBeenCalledTimes(1);
    const call = mockQuery.mock.calls[0];
    expect(call[0]).toContain("INSERT INTO collab_documents");
    expect(call[1][0]).toBe("doc-test");
    expect(call[1][2]).toBe("user-1");

    // Verify the stored buffer can be decoded back into a Yjs doc
    const restoredDoc = new Y.Doc();
    Y.applyUpdate(restoredDoc, new Uint8Array(storedBuffer));
    const restoredMeta = restoredDoc.getMap("_collabMeta");
    expect(restoredMeta.get("pendingMarkdown")).toBe("# Test Content");
  });
});

describe("pruneVersions (bug B11: collab_versions 无限增长)", () => {
  beforeEach(() => {
    mockQuery.mockReset();
  });

  it("issues a DELETE scoped to the doc keeping only the newest N versions", async () => {
    mockQuery.mockResolvedValueOnce({ rowCount: 3 });

    const pruned = await pruneVersions("doc-1");

    expect(pruned).toBe(3);
    expect(mockQuery).toHaveBeenCalledTimes(1);
    const [sql, params] = mockQuery.mock.calls[0];
    expect(sql).toContain("DELETE FROM collab_versions");
    expect(params[0]).toBe("doc-1");
    expect(params[1]).toBe(50); // 默认保留最近 50 条
  });

  it("honours a custom keep limit", async () => {
    mockQuery.mockResolvedValueOnce({ rowCount: 0 });

    await pruneVersions("doc-2", 5);

    const [, params] = mockQuery.mock.calls[0];
    expect(params).toEqual(["doc-2", 5]);
  });

  it("exports the default retention cap of 50", () => {
    expect(MAX_VERSIONS_PER_DOC).toBe(50);
  });
});
