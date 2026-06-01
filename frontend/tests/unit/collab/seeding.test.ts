import { describe, it, expect } from "vitest";
import * as Y from "yjs";

/**
 * Pure-function extraction of the seeding decision logic from BlockNoteEditor.tsx.
 * Tests validate the core algorithm without mounting React components.
 */

function shouldSeedFromServerMeta(ydoc: Y.Doc): { shouldSeed: boolean; markdown: string | null } {
  const meta = ydoc.getMap("_collabMeta");
  const pendingMarkdown = meta.get("pendingMarkdown");
  if (pendingMarkdown && typeof pendingMarkdown === "string" && pendingMarkdown.trim()) {
    return { shouldSeed: true, markdown: pendingMarkdown.trim() };
  }
  return { shouldSeed: false, markdown: null };
}

function hasRealContent(document: Array<Record<string, unknown>>): boolean {
  return document.some((block) => {
    if (block.type !== "paragraph") return true;
    const children = block.children;
    const content = block.content;
    if (Array.isArray(children) && children.length > 0) return true;
    if (Array.isArray(content)) {
      return content.some(
        (c: Record<string, unknown>) =>
          typeof c.text === "string" && (c.text as string).trim().length > 0,
      );
    }
    return false;
  });
}

describe("shouldSeedFromServerMeta", () => {
  it("returns true when pendingMarkdown is set", () => {
    const doc = new Y.Doc();
    doc.getMap("_collabMeta").set("pendingMarkdown", "# Title\nContent");

    const result = shouldSeedFromServerMeta(doc);
    expect(result.shouldSeed).toBe(true);
    expect(result.markdown).toBe("# Title\nContent");
  });

  it("returns false when no metadata exists", () => {
    const doc = new Y.Doc();
    const result = shouldSeedFromServerMeta(doc);
    expect(result.shouldSeed).toBe(false);
    expect(result.markdown).toBeNull();
  });

  it("returns false when pendingMarkdown is empty string", () => {
    const doc = new Y.Doc();
    doc.getMap("_collabMeta").set("pendingMarkdown", "");

    const result = shouldSeedFromServerMeta(doc);
    expect(result.shouldSeed).toBe(false);
  });

  it("returns false when pendingMarkdown is whitespace-only", () => {
    const doc = new Y.Doc();
    doc.getMap("_collabMeta").set("pendingMarkdown", "   \n  ");

    const result = shouldSeedFromServerMeta(doc);
    expect(result.shouldSeed).toBe(false);
  });

  it("returns false when pendingMarkdown is a number (wrong type)", () => {
    const doc = new Y.Doc();
    doc.getMap("_collabMeta").set("pendingMarkdown", 42);

    const result = shouldSeedFromServerMeta(doc);
    expect(result.shouldSeed).toBe(false);
  });

  it("trims the markdown before returning", () => {
    const doc = new Y.Doc();
    doc.getMap("_collabMeta").set("pendingMarkdown", "  # Title  \n");

    const result = shouldSeedFromServerMeta(doc);
    expect(result.markdown).toBe("# Title");
  });
});

describe("hasRealContent", () => {
  it("returns false for empty paragraph with no content", () => {
    const document = [{ type: "paragraph", content: [], children: [] }];
    expect(hasRealContent(document)).toBe(false);
  });

  it("returns false for paragraph with only empty text", () => {
    const document = [
      { type: "paragraph", content: [{ type: "text", text: "", styles: {} }], children: [] },
    ];
    expect(hasRealContent(document)).toBe(false);
  });

  it("returns false for paragraph with only whitespace text", () => {
    const document = [
      { type: "paragraph", content: [{ type: "text", text: "   ", styles: {} }], children: [] },
    ];
    expect(hasRealContent(document)).toBe(false);
  });

  it("returns true for paragraph with actual text", () => {
    const document = [
      {
        type: "paragraph",
        content: [{ type: "text", text: "Hello world", styles: {} }],
        children: [],
      },
    ];
    expect(hasRealContent(document)).toBe(true);
  });

  it("returns true for heading block (non-paragraph type)", () => {
    const document = [{ type: "heading", props: { level: 2 }, content: [], children: [] }];
    expect(hasRealContent(document)).toBe(true);
  });

  it("returns true for paragraph with children (nested blocks)", () => {
    const document = [{ type: "paragraph", content: [], children: [{ type: "paragraph" }] }];
    expect(hasRealContent(document)).toBe(true);
  });

  it("returns false for empty document array", () => {
    expect(hasRealContent([])).toBe(false);
  });
});

describe("Seeding flow: server meta → client seeding → clear flag", () => {
  it("full round-trip: server sets flag, client reads and clears", () => {
    const markdown = "# 华宇大厦消防设计专篇\n\n## 第一章 总则\n\n消防设计应符合...";

    // 1. Server creates Yjs doc with pendingMarkdown
    const doc = new Y.Doc();
    doc.getMap("_collabMeta").set("pendingMarkdown", markdown);

    // 2. Client checks for pending markdown
    const { shouldSeed, markdown: fetchedMarkdown } = shouldSeedFromServerMeta(doc);
    expect(shouldSeed).toBe(true);
    expect(fetchedMarkdown).toBe(markdown);

    // 3. Client clears the flag after seeding
    doc.getMap("_collabMeta").delete("pendingMarkdown");

    // 4. On next check, no pending markdown
    const { shouldSeed: shouldSeed2 } = shouldSeedFromServerMeta(doc);
    expect(shouldSeed2).toBe(false);
  });

  it("subsequent opens skip seeding (no pendingMarkdown)", () => {
    const doc = new Y.Doc();
    // No pendingMarkdown — simulates a document that was already seeded

    const { shouldSeed } = shouldSeedFromServerMeta(doc);
    expect(shouldSeed).toBe(false);
  });
});
