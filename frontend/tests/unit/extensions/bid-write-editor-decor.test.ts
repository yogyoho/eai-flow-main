// 批廿八 M2 T2:装饰层——assert:apply 侧信道映射 + 纯装饰不污染(方案 §六/§十二)。
// node env:EditorState.apply 直跑插件 apply,无 DOM(widget 工厂不被调用)。
import { describe, expect, test } from "@rstest/core";
import { type Node as PMNode } from "prosemirror-model";
import type { EditorState, PluginKey } from "prosemirror-state";
import { DecorationSet } from "prosemirror-view";

import {
  ASSERT_APPLY_META,
  assertionTr,
  buildProvenanceDecorations,
  liveAssertKey,
  PROVENANCE_JUMP_META,
  provenanceAt,
  provenanceKey,
  type DecorationLike,
} from "@/extensions/bid-write/editor/decor";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { serializeDoc } from "@/extensions/bid-write/editor/doc";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";

function demoState() {
  return createBidWriteEditorState(demoWorkbenchAst(), {});
}

function findSlotRange(state: EditorState, slotId: string): [number, number] | null {
  let hit: [number, number] | null = null;
  state.doc.descendants((node: PMNode, pos: number) => {
    if (node.type.name === "para" && String(node.attrs.slot_id ?? "") === slotId) {
      hit = [pos + 1, pos + 1 + node.content.size];
    }
  });
  return hit;
}

function decosOf(state: EditorState, key: PluginKey<DecorationSet>): DecorationLike[] {
  const set = key.getState(state);
  return (set ? set.find() : []) as unknown as DecorationLike[];
}

describe("liveAssert side-channel", () => {
  test("assert:apply → bl-opening 挂 D1 inline decoration;doc 文本零污染", () => {
    const state = demoState();
    const beforeJson = state.doc.toJSON();
    const tr = assertionTr(state, {
      states: { "bl-opening": { state: "D1", err_code: "SK-PS-003" } },
      skipped: [],
      run_at: "2026-11-14T00:00:00Z",
    });
    expect(tr.getMeta(ASSERT_APPLY_META)).toBeTruthy();
    expect(tr.getMeta("source")).toBe("decor");
    expect(tr.getMeta("addToHistory")).toBe(false);
    const s2 = state.apply(tr);
    const range = findSlotRange(state, "bl-opening")!;
    const hit = decosOf(s2, liveAssertKey).find(
      (d) => d.from === range[0] && d.to === range[1],
    );
    expect(hit).toBeTruthy();
    expect(String(hit!.type.attrs?.class)).toContain("bwx-assert-d1");
    expect(s2.doc.toJSON()).toEqual(beforeJson); // 装饰绝不写回节点文本(§六)
    expect(serializeDoc(s2.doc)).toEqual(serializeDoc(state.doc)); // 导出面零污染
  });

  test("D2/SKIPPED 不产生装饰(SKIPPED 只进状态栏,不得当作通过)", () => {
    const state = demoState();
    const s2 = state.apply(
      assertionTr(state, {
        states: { "bl-opening": { state: "D2" } },
        skipped: [{ code: "SK-PS-006", count: 1 }],
        run_at: "x",
      }),
    );
    expect(decosOf(s2, liveAssertKey).length).toBe(0);
  });

  test("后续用户编辑 tr 将既有装饰 map 到新位置(不丢)", () => {
    const state = demoState();
    const s2 = state.apply(
      assertionTr(state, { states: { "bl-opening": { state: "D1" } }, skipped: [], run_at: "x" }),
    );
    const before = decosOf(s2, liveAssertKey).length;
    const range = findSlotRange(s2, "bl-opening")!;
    const s3 = s2.apply(s2.tr.insertText("Z", range[0]));
    expect(decosOf(s3, liveAssertKey).length).toBe(before);
  });

  test("空侧信道(编辑器初始)= 无装饰", () => {
    const state = demoState();
    expect(decosOf(state, liveAssertKey).length).toBe(0);
  });
});

describe("provenance", () => {
  test("widget 角标挂在标记文本尾(build 只产 widget,1 标记=1 枚)", () => {
    const state = demoState();
    expect(decosOf(state, provenanceKey).length).toBe(1);
  });

  test("provenanceAt 命中 [B-014][M-88][P.34];普通文本 null", () => {
    const state = demoState();
    let markedPos = -1;
    let plainPos = -1;
    state.doc.descendants((node: PMNode, pos: number) => {
      if (node.type.name !== "text") return;
      if (node.marks.some((m) => m.type.name === "provenance") && markedPos < 0) markedPos = pos;
      if (node.marks.length === 0 && plainPos < 0) plainPos = pos;
    });
    expect(provenanceAt(state, markedPos)).toEqual({ clause_id: "B-014", entity_id: "M-88", anchor: "P.34" });
    expect(provenanceAt(state, plainPos)).toBeNull();
  });

  test("broken 面:entity_id 空 → widget 仍挂(build 面接受;红色由 CSS 断言)", () => {
    const state = demoState();
    const doc = state.doc;
    const set = buildProvenanceDecorations(doc);
    expect(set).toBeInstanceOf(DecorationSet);
    expect(set.find().length).toBe(1);
  });

  test("jump meta 通道:decor tr 带 provenance:jump 不改文档不进撤销", () => {
    const state = demoState();
    const tr = state.tr;
    tr.setMeta(PROVENANCE_JUMP_META, { clause_id: "B-014", entity_id: "M-88", anchor: "P.34" });
    tr.setMeta("source", "decor");
    tr.setMeta("addToHistory", false);
    const s2 = state.apply(tr);
    expect(s2.doc.eq(state.doc)).toBe(true);
    expect(tr.getMeta("addToHistory")).toBe(false);
  });
});
