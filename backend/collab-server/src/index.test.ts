import { describe, it, expect, vi, beforeEach } from "vitest";
import * as Y from "yjs";

// --- Mocks ---

const mockLoadDocument = vi.fn();
const mockLoadMarkdownForDoc = vi.fn();
const mockGetDocumentVersion = vi.fn();
const mockStoreDocument = vi.fn();
const mockRecordUpdate = vi.fn();
const mockCreateVersion = vi.fn();
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
  canAccessDocument: (...args: unknown[]) => mockCanAccessDocument(...args),
  hasCollabData: vi.fn(),
}));

vi.mock("./auth.js", () => ({
  authenticateConnection: (...args: unknown[]) => mockAuthenticateConnection(...args),
  validateOrigin: (...args: unknown[]) => mockValidateOrigin(...args),
}));

// Mock @hocuspocus/server
const serverConfig: Record<string, unknown> = {};
vi.mock("@hocuspocus/server", () => ({
  Server: {
    configure: (opts: Record<string, unknown>) => {
      Object.assign(serverConfig, opts);
      return { listen: () => Promise.resolve() };
    },
  },
}));

// Import after mocks (this triggers Server.configure which captures the callbacks)
await import("./index.js");

describe("onLoadDocument — markdown fallback", () => {
  // Extract the onLoadDocument callback from the captured config
  const onLoadDocument = () => serverConfig.onLoadDocument as typeof serverConfig.onLoadDocument;

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

    await onLoadDocument()!({ document: doc, documentName: "doc-existing" } as never);

    // The fragment should contain the content from the existing Yjs data
    const fragment = doc.getXmlFragment("document-store");
    expect(fragment.toString()).toContain("existing content");
    expect(mockLoadMarkdownForDoc).not.toHaveBeenCalled();
  });

  it("sets pendingMarkdown in Yjs metadata when no collab data exists", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce("# 华宇大厦消防设计专篇\n\n第一章 总则");

    await onLoadDocument()!({ document: doc, documentName: "doc-new" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBe("# 华宇大厦消防设计专篇\n\n第一章 总则");
    expect(mockLoadMarkdownForDoc).toHaveBeenCalledWith("doc-new");
  });

  it("does NOT set pendingMarkdown when document has no markdown content", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce(null);

    await onLoadDocument()!({ document: doc, documentName: "doc-empty" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBeUndefined();
  });

  it("does NOT set pendingMarkdown when markdown is whitespace-only", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce("   \n  \t  ");

    await onLoadDocument()!({ document: doc, documentName: "doc-whitespace" } as never);

    const meta = doc.getMap("_collabMeta");
    expect(meta.get("pendingMarkdown")).toBeUndefined();
  });

  it("sets pendingMarkdown for file_ref documents that have file content", async () => {
    const doc = new Y.Doc();
    mockLoadDocument.mockResolvedValueOnce(null);
    mockLoadMarkdownForDoc.mockResolvedValueOnce("# File content from disk\n\nSome content here");

    await onLoadDocument()!({ document: doc, documentName: "doc-fileref" } as never);

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
