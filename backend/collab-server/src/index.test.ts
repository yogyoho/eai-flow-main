import { describe, it, expect, vi, beforeEach } from "vitest";
import * as Y from "yjs";

// --- Mocks ---

const mockLoadDocument = vi.fn();
const mockLoadMarkdownForDoc = vi.fn();
const mockGetDocumentVersion = vi.fn();
const mockStoreDocument = vi.fn();
const mockRecordUpdate = vi.fn();
const mockCreateVersion = vi.fn();
const mockPruneVersions = vi.fn();
const mockCanAccessDocument = vi.fn();
const mockAuthenticateConnection = vi.fn();
const mockValidateOrigin = vi.fn();

vi.mock("./persistence.js", () => ({
  loadDocument: (...args: unknown[]) => mockLoadDocument(...args),
  loadMarkdownForDoc: (...args: unknown[]) => mockLoadMarkdownForDoc(...args),
  getDocumentVersion: (...args: unknown[]) => mockGetDocumentVersion(...args),
  storeDocument: (...args: unknown[]) => mockStoreDocument(...args),
  recordUpdate: (...args: unknown[]) => mockRecordUpdate(...args),
  createVersion: (...args: unknown[]) => mockCreateVersion(...args),
  pruneVersions: (...args: unknown[]) => mockPruneVersions(...args),
  canAccessDocument: (...args: unknown[]) => mockCanAccessDocument(...args),
  hasCollabData: vi.fn(),
}));

vi.mock("./auth.js", () => ({
  authenticateConnection: (...args: unknown[]) => mockAuthenticateConnection(...args),
  validateOrigin: (...args: unknown[]) => mockValidateOrigin(...args),
}));

// Mock @hocuspocus/server
const serverConfig: Record<string, unknown> = {};
// EAI-CUSTOM (bug B11): serverConfig 索引出的值类型为 unknown，不可直接调用
// (TS2349/TS2571) —— 此前 tsc 在 Docker 镜像构建 (npm run build) 就已红，这里
// 给出显式回调签名。
type CollabCallback = (payload: Record<string, unknown>) => Promise<void>;
vi.mock("@hocuspocus/server", () => ({
  Server: {
    configure: (opts: Record<string, unknown>) => {
      Object.assign(serverConfig, opts);
      return { listen: () => Promise.resolve() };
    },
  },
}));

// Import after mocks (this triggers Server.configure which captures the callbacks)
const indexModule = await import("./index.js");

describe("onLoadDocument — markdown fallback", () => {
  // Extract the onLoadDocument callback from the captured config
  const onLoadDocument = () => serverConfig.onLoadDocument as CollabCallback;

  beforeEach(() => {
    mockLoadDocument.mockReset();
    mockLoadMarkdownForDoc.mockReset();
    mockGetDocumentVersion.mockReset();
    mockGetDocumentVersion.mockResolvedValue(0);
  });

  it("applies existing Yjs data when collab_documents has entry", async () => {
    const doc = new Y.Doc();
    // Create a separate doc with content to generate an update
    const sourceDoc = new Y.Doc();
    sourceDoc.getXmlFragment("document-store").insert(0, [new Y.XmlText("existing content")]);
    const existingUpdate = Y.encodeStateAsUpdate(sourceDoc);

    mockLoadDocument.mockResolvedValueOnce(existingUpdate);

    await onLoadDocument()({ document: doc, documentName: "doc-existing" } as never);

    // The fragment should contain the content from the existing Yjs data
    const fragment = doc.getXmlFragment("document-store");
    expect(fragment.toString()).toContain("existing content");
    expect(mockLoadMarkdownForDoc).not.toHaveBeenCalled();
  });

  it("sets pendingMarkdown in Yjs metadata when no collab data exists", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce("# 华宇大厦消防设计专篇\n\n第一章 总则");

    await onLoadDocument()({ document: doc, documentName: "doc-new" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBe("# 华宇大厦消防设计专篇\n\n第一章 总则");
    expect(mockLoadMarkdownForDoc).toHaveBeenCalledWith("doc-new");
  });

  it("does NOT set pendingMarkdown when document has no markdown content", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce(null);

    await onLoadDocument()({ document: doc, documentName: "doc-empty" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBeUndefined();
  });

  it("does NOT set pendingMarkdown when markdown is whitespace-only", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce("   \n  \t  ");

    await onLoadDocument()({ document: doc, documentName: "doc-whitespace" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBeUndefined();
  });

  it("sets pendingMarkdown for file_ref documents that have file content", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce("# File content from disk\n\nSome content here");

    await onLoadDocument()({ document: doc, documentName: "doc-fileref" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBe("# File content from disk\n\nSome content here");
  });
});

describe("Yjs metadata round-trip (server → client)", () => {
  it("pendingMarkdown survives Yjs encode/decode cycle", () => {
    const serverDoc = new Y.Doc();
    const meta = serverDoc.getMap("_collabMeta");
    meta.set("pendingMarkdown", "# 标题\n\n中文内容 with **bold**");

    const update = Y.encodeStateAsUpdate(serverDoc);

    // Simulate client receiving the update
    const clientDoc = new Y.Doc();
    Y.applyUpdate(clientDoc, update);

    const clientMeta = clientDoc.getMap("_collabMeta");
    expect(clientMeta.get("pendingMarkdown")).toBe("# 标题\n\n中文内容 with **bold**");
  });

  it("clearing pendingMarkdown propagates through Yjs", () => {
    const doc1 = new Y.Doc();
    const meta1 = doc1.getMap("_collabMeta");
    meta1.set("pendingMarkdown", "test content");

    const update1 = Y.encodeStateAsUpdate(doc1);

    const doc2 = new Y.Doc();
    Y.applyUpdate(doc2, update1);
    expect(doc2.getMap("_collabMeta").get("pendingMarkdown")).toBe("test content");

    // Client clears the flag
    doc2.getMap("_collabMeta").delete("pendingMarkdown");
    const update2 = Y.encodeStateAsUpdate(doc2);

    // Server receives the update
    Y.applyUpdate(doc1, update2);
    expect(doc1.getMap("_collabMeta").get("pendingMarkdown")).toBeUndefined();
  });
});

describe("extractTextFromYDoc (bug B11 协同链审计)", () => {
  const extract = () => indexModule.extractTextFromYDoc as (ydoc: Y.Doc) => string;

  /** Build a BlockNote-style document-store fragment: XmlElement blocks with XmlText children. */
  function buildBlockNoteDoc(): Y.Doc {
    const doc = new Y.Doc();
    const fragment = doc.getXmlFragment("document-store");
    const paragraph = new Y.XmlElement("paragraph");
    const pText = new Y.XmlText();
    pText.insert(0, "Hello 世界");
    paragraph.insert(0, [pText]);
    const heading = new Y.XmlElement("heading");
    const hText = new Y.XmlText();
    hText.insert(0, "第一章 总则");
    heading.insert(0, [hText]);
    fragment.insert(0, [paragraph, heading]);
    return doc;
  }

  it("extracts non-empty text from the document-store fragment", () => {
    const text = extract()(buildBlockNoteDoc());
    expect(text).toContain("Hello 世界");
    expect(text).toContain("第一章 总则");
    // blocks joined with newline, one line per top-level block
    expect(text.split("\n")).toEqual(["Hello 世界", "第一章 总则"]);
  });

  it("survives the Yjs encode/apply round-trip used by onStoreDocument", () => {
    const source = buildBlockNoteDoc();
    const restored = new Y.Doc();
    Y.applyUpdate(restored, Y.encodeStateAsUpdate(source));
    const text = extract()(restored);
    expect(text).toContain("Hello 世界");
    expect(text).toContain("第一章 总则");
  });

  it("handles a fragment with a direct XmlText child", () => {
    const doc = new Y.Doc();
    doc.getXmlFragment("document-store").insert(0, [new Y.XmlText("existing content")]);
    expect(extract()(doc)).toContain("existing content");
  });

  it("returns empty string for a document with no document-store content", () => {
    expect(extract()(new Y.Doc())).toBe("");
  });

  it("does not read the legacy 'blocks' map (bug B11 regression guard)", () => {
    // 旧实现读 getMap("blocks") — 客户端从不写这个 map，恒空导致 snapshot_text 为空。
    // 这里只往 "blocks" map 写内容，断言新实现不再消费它。
    const doc = new Y.Doc();
    const el = new Y.XmlElement("paragraph");
    const t = new Y.XmlText();
    t.insert(0, "legacy map content");
    el.insert(0, [t]);
    doc.getMap("blocks").set("b1", el);
    expect(extract()(doc)).toBe("");
  });
});

describe("version pruning (bug B11: collab_versions 无限增长)", () => {
  const onDisconnect = () => serverConfig.onDisconnect as CollabCallback;

  beforeEach(() => {
    mockCreateVersion.mockReset();
    mockPruneVersions.mockReset();
    mockPruneVersions.mockResolvedValue(0);
  });

  it("prunes history after createVersion on disconnect", async () => {
    mockCreateVersion.mockResolvedValueOnce(42);
    const doc = new Y.Doc();

    await onDisconnect()({ document: doc, documentName: "doc-prune", context: { userId: "user-1" } } as never);

    expect(mockCreateVersion).toHaveBeenCalledWith("doc-prune", expect.any(Uint8Array), "user-1", "Auto-save on disconnect", expect.any(String));
    // 裁剪在 createVersion 之后执行，按 doc 维度
    expect(mockPruneVersions).toHaveBeenCalledTimes(1);
    expect(mockPruneVersions).toHaveBeenCalledWith("doc-prune");
    const createOrder = mockCreateVersion.mock.invocationCallOrder[0];
    const pruneOrder = mockPruneVersions.mock.invocationCallOrder[0];
    expect(pruneOrder).toBeGreaterThan(createOrder);
  });
});
