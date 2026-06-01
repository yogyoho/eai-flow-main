/**
 * Tests for the ProseMirror traceability extension.
 *
 * Verifies plugin structure, state transitions, decoration building,
 * and the React-facing public API (registerTraceabilityPlugin,
 * updateTraceabilitySources).
 */
import { describe, expect, it } from "vitest";
import { Schema } from "prosemirror-model";
import { EditorState, Plugin } from "prosemirror-state";

import {
  registerTraceabilityPlugin,
  traceabilityPlugin,
  traceabilityPluginKey,
  updateTraceabilitySources,
  type TraceabilitySource,
} from "@/extensions/collab/traceability-extension";

// ---------------------------------------------------------------------------
// Minimal ProseMirror schema for testing
// ---------------------------------------------------------------------------

const testSchema = new Schema({
  nodes: {
    doc: { content: "paragraph+" },
    paragraph: {
      content: "text*",
      toDOM: () => ["p", 0],
      parseDOM: [{ tag: "p" }],
    },
    text: { group: "inline" },
  },
});

function createTestDoc(content: string) {
  return testSchema.node("doc", null, [
    testSchema.node("paragraph", null, [
      testSchema.text(content),
    ]),
  ]);
}

function createTestSources(): Map<number, TraceabilitySource> {
  const map = new Map<number, TraceabilitySource>();
  map.set(1, {
    index: 1,
    sourceType: "rag_retrieval",
    sourceRef: "知识库「监测数据库」→「2024年度监测报告」p.23",
    snippet: "SO₂ 日均浓度监测数据",
    confidence: 0.95,
  });
  map.set(2, {
    index: 2,
    sourceType: "regulation",
    sourceRef: "GB 3095-2012《环境空气质量标准》表2",
    snippet: "SO₂ 日均浓度限值 0.15mg/m³",
    confidence: 1.0,
  });
  map.set(3, {
    index: 3,
    sourceType: "ai_generated",
    sourceRef: "model:gpt-4o/analysis",
    snippet: null,
    confidence: 0.7,
  });
  return map;
}

// ---------------------------------------------------------------------------
// Plugin structure
// ---------------------------------------------------------------------------

describe("TraceabilityExtension — Plugin structure", () => {
  it("should be a ProseMirror Plugin", () => {
    expect(traceabilityPlugin).toBeInstanceOf(Plugin);
  });

  it("should have a plugin key named 'traceability'", () => {
    expect(traceabilityPluginKey.key).toContain("traceability");
  });

  it("should initialise with empty decorations and sources", () => {
    const doc = createTestDoc("Hello world");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const pluginState = traceabilityPluginKey.getState(state);
    expect(pluginState).toBeDefined();
    expect(pluginState!.sources.size).toBe(0);
    expect(pluginState!.decorations).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

describe("TraceabilityExtension — State transitions", () => {
  it("should update decorations when sources meta is dispatched", () => {
    const doc = createTestDoc("数据为 [1] 0.045mg/m³，符合标准 [2]。");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const sources = createTestSources();
    const tr = state.tr.setMeta(traceabilityPluginKey, { sources });
    const newState = state.apply(tr);

    const pluginState = traceabilityPluginKey.getState(newState);
    expect(pluginState!.sources.size).toBe(3);
    // Decorations should exist for [1] and [2] in the document
    const decorations = pluginState!.decorations;
    expect(decorations.find().length).toBe(2); // [1] and [2] in doc
  });

  it("should rebuild decorations when document changes (source data preserved)", () => {
    const doc = createTestDoc("数据 [1] 示例 [2] 结束 [3]");
    const sources = createTestSources();

    // Create state with sources pre-loaded via meta transaction
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });
    const tr1 = state.tr.setMeta(traceabilityPluginKey, { sources });
    const state2 = state.apply(tr1);

    // Now make a document change (insert text)
    const tr2 = state2.tr.insertText("新增内容 ", 0);
    const state3 = state2.apply(tr2);

    const pluginState = traceabilityPluginKey.getState(state3);
    expect(pluginState!.sources.size).toBe(3);
    // Decorations should still exist for [1], [2], [3] in modified doc
    const decorations = pluginState!.decorations;
    expect(decorations.find().length).toBe(3);
  });

  it("should remove decorations when sources no longer match", () => {
    const doc = createTestDoc("这是 [1] 的测试文本，还有 [4] 没有来源。");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const sources = createTestSources(); // has 1,2,3 but NOT 4
    const tr = state.tr.setMeta(traceabilityPluginKey, { sources });
    const newState = state.apply(tr);

    const pluginState = traceabilityPluginKey.getState(newState);
    // [1] has a source → decorated; [4] has no source → NOT decorated
    const decorations = pluginState!.decorations;
    expect(decorations.find().length).toBe(1); // only [1]
  });

  it("should not create decorations when no sources are loaded", () => {
    const doc = createTestDoc("数据 [1] 和 [2] 在文本中");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const pluginState = traceabilityPluginKey.getState(state);
    expect(pluginState!.sources.size).toBe(0);
    const decorations = pluginState!.decorations;
    expect(decorations.find().length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Decoration content verification
// ---------------------------------------------------------------------------

describe("TraceabilityExtension — Decoration content", () => {
  it("should apply correct inline style for source type", () => {
    const doc = createTestDoc("参考 [1] 标注。");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const sources = createTestSources();
    const tr = state.tr.setMeta(traceabilityPluginKey, { sources });
    const newState = state.apply(tr);

    const pluginState = traceabilityPluginKey.getState(newState);
    const decorations = pluginState!.decorations.find();
    expect(decorations.length).toBe(1);

    // The decoration should wrap [1] with rag_retrieval styles
    const deco = decorations[0]!;
    // "参考 [1] 标注。" — [1] is inside the paragraph text node
    expect(deco.from).toBeGreaterThan(0);
    expect(deco.to).toBeGreaterThan(deco.from);

    const attrs = deco.type.attrs as Record<string, unknown>;
    expect(attrs.style).toBeDefined();
    expect(typeof attrs.style).toBe("string");
    expect(attrs.style as string).toContain("background-color");
    expect(attrs.style as string).toContain("border-bottom");
    // Should have native tooltip with source info
    expect(attrs.title).toBeDefined();
    expect(attrs.title as string).toContain("rag_retrieval");
    expect(attrs.title as string).toContain("监测数据库");
  });

  it("should support all six source types with distinct colors", () => {
    const types = [
      "rag_retrieval",
      "knowledge_base",
      "regulation",
      "ai_generated",
      "human_written",
      "external_data",
    ];

    const styleStrings = types.map((sourceType) => {
      const source: TraceabilitySource = {
        index: 1,
        sourceType,
        sourceRef: "test",
        snippet: null,
        confidence: null,
      };
      const doc = createTestDoc("[1]");
      const state = EditorState.create({
        doc,
        plugins: [traceabilityPlugin],
      });
      const tr = state.tr.setMeta(traceabilityPluginKey, {
        sources: new Map([[1, source]]),
      });
      const newState = state.apply(tr);
      const decos = traceabilityPluginKey.getState(newState)!.decorations.find();
      return (decos[0]!.type.attrs as Record<string, unknown>).style as string;
    });

    // Each style string should be unique (different colors per type)
    const uniqueStyles = new Set(styleStrings);
    expect(uniqueStyles.size).toBe(types.length);
  });

  it("should handle markers at start and end of document", () => {
    const doc = createTestDoc("[1] 开头标记 结尾标记 [2]");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const sources = createTestSources();
    const tr = state.tr.setMeta(traceabilityPluginKey, { sources });
    const newState = state.apply(tr);

    const pluginState = traceabilityPluginKey.getState(newState);
    const decorations = pluginState!.decorations.find();
    expect(decorations.length).toBe(2);

    // Both markers should be at valid positions within the document
    expect(decorations[0]!.from).toBeGreaterThanOrEqual(0);
    expect(decorations[1]!.from).toBeGreaterThan(decorations[0]!.from);
  });
});

// ---------------------------------------------------------------------------
// Public API: registerTraceabilityPlugin (idempotency)
// ---------------------------------------------------------------------------

describe("TraceabilityExtension — registerTraceabilityPlugin", () => {
  it("should register the plugin on a view without error", () => {
    const doc = createTestDoc("测试");
    const simpleState = EditorState.create({ doc });

    // Mock a minimal EditorView-like object
    const view = {
      state: simpleState,
      updateState: (newState: EditorState) => {
        (view.state as EditorState) = newState;
      },
    };

    expect(() => registerTraceabilityPlugin(view as any)).not.toThrow();
  });

  it("should be idempotent (second call is no-op)", () => {
    const doc = createTestDoc("测试");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    const view = {
      state,
      updateState: (newState: EditorState) => {
        (view.state as EditorState) = newState;
      },
    };

    // First call registers
    expect(() => registerTraceabilityPlugin(view as any)).not.toThrow();
    // Second call should be idempotent (no crash)
    expect(() => registerTraceabilityPlugin(view as any)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Public API: updateTraceabilitySources (transaction dispatch)
// ---------------------------------------------------------------------------

describe("TraceabilityExtension — updateTraceabilitySources", () => {
  it("should dispatch a meta transaction with sources", () => {
    const doc = createTestDoc("[1] 测试");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    let dispatchedTr: any = null;
    const view = {
      state,
      dispatch: (tr: any) => {
        dispatchedTr = tr;
        // Apply the transaction so view.state stays consistent
        (view.state as EditorState) = view.state.apply(tr);
      },
    };

    const sources: TraceabilitySource[] = [
      {
        index: 1,
        sourceType: "knowledge_base",
        sourceRef: "test-ref",
        snippet: "test",
        confidence: 0.8,
      },
    ];

    updateTraceabilitySources(view as any, sources);

    expect(dispatchedTr).not.toBeNull();
    const meta = dispatchedTr!.getMeta(traceabilityPluginKey);
    expect(meta).toBeDefined();
    expect(meta.sources).toBeInstanceOf(Map);
    expect(meta.sources.get(1)!.sourceType).toBe("knowledge_base");

    // View state should now have sources loaded
    const pluginState = traceabilityPluginKey.getState(view.state);
    expect(pluginState!.sources.size).toBe(1);
  });

  it("should clear existing sources when empty array is passed", () => {
    const doc = createTestDoc("[1] 测试");
    const state = EditorState.create({
      doc,
      plugins: [traceabilityPlugin],
    });

    // Pre-load a source
    const sources = createTestSources();
    let s1 = state.apply(state.tr.setMeta(traceabilityPluginKey, { sources }));

    const view = {
      state: s1,
      dispatch: (tr: any) => {
        (view.state as EditorState) = view.state.apply(tr);
      },
    };

    // Now clear with empty array
    updateTraceabilitySources(view as any, []);

    const pluginState = traceabilityPluginKey.getState(view.state);
    expect(pluginState!.sources.size).toBe(0);
    expect(pluginState!.decorations.find().length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// TraceabilitySource type
// ---------------------------------------------------------------------------

describe("TraceabilityExtension — TraceabilitySource type", () => {
  it("should accept all valid source fields", () => {
    const source: TraceabilitySource = {
      index: 5,
      sourceType: "rag_retrieval",
      sourceRef: "doc://123",
      snippet: "Some text",
      confidence: 0.85,
    };
    expect(source.index).toBe(5);
    expect(source.sourceType).toBe("rag_retrieval");
    expect(source.sourceRef).toBe("doc://123");
    expect(source.snippet).toBe("Some text");
    expect(source.confidence).toBe(0.85);
  });

  it("should allow null snippet and confidence", () => {
    const source: TraceabilitySource = {
      index: 1,
      sourceType: "template",
      sourceRef: "template://default",
      snippet: null,
      confidence: null,
    };
    expect(source.snippet).toBeNull();
    expect(source.confidence).toBeNull();
  });
});
