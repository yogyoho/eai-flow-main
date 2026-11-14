// 批廿九 M3——deviationPlugin 自愈展开单测(node env;EditorState.apply 直跑 appendTransaction)。
import { describe, expect, it } from "@rstest/core";
import { undo } from "prosemirror-history";
import { type Node as PMNode } from "prosemirror-model";

import { setEnumValue } from "@/extensions/bid-write/editor/constraints";
import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import { ALT_LABEL, REASON_LABEL } from "@/extensions/bid-write/editor/deviation";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";

interface NoteHit {
  pos: number;
  node: PMNode;
}

function enumPos(doc: PMNode): number {
  let hit = -1;
  doc.descendants((node, pos) => {
    if (hit < 0 && node.type.name === "enum_cell") hit = pos;
  });
  if (hit < 0) throw new Error("demo 文档无 enum_cell");
  return hit;
}

function findNote(doc: PMNode): NoteHit | null {
  let hit: NoteHit | null = null;
  doc.descendants((node, pos) => {
    if (!hit && node.type.name === "deviation_note") hit = { pos, node };
  });
  return hit;
}

const labels = (note: PMNode) =>
  Array.from({ length: note.childCount }, (_, i) => String(note.child(i).attrs.label ?? ""));

/** 测试填充用:整 para replaceWith 保 label attrs。
    tr.insertText 裸位置插进空 textblock 时 PM fitter 会在父层新建默认 para
    (label 丢失),必须整块替换。 */
function fillPara(state: ReturnType<typeof createBidWriteEditorState>, pos: number, label: string, text: string) {
  const para = state.doc.nodeAt(pos)!;
  const tr = state.tr.replaceWith(
    pos,
    pos + para.nodeSize,
    state.schema.nodes.para!.create({ label }, state.schema.text(text)),
  );
  return state.apply(tr);
}

const flip = (state: ReturnType<typeof createBidWriteEditorState>, value: string) => {
  const tr = setEnumValue(state, enumPos(state.doc), value);
  expect(tr).not.toBeNull();
  return state.apply(tr!);
};

describe("deviation 自愈展开", () => {
  it("翻负偏离 → 表后出现 note(row_id 关联,双 labeled para)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const tr = setEnumValue(s0, enumPos(s0.doc), "负偏离");
    expect(tr).not.toBeNull();
    const s1 = s0.apply(tr!);
    const note = findNote(s1.doc);
    expect(note).not.toBeNull();
    expect(String(note!.node.attrs.row_id ?? "")).toBe("R-sum");
    expect(labels(note!.node)).toEqual([REASON_LABEL, ALT_LABEL]);
    expect(note!.node.textContent).toBe("");
    expect(tr!.getMeta("source")).toBeUndefined(); // 用户 tr 本身仍 user 源
  });

  it("一撤=策略翻回+展开面消失(appended tr 并入同一 undo 事件)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = flip(s0, "负偏离");
    expect(findNote(s1.doc)).not.toBeNull();
    let s2 = s1;
    undo(s1, (u) => {
      s2 = s1.apply(u);
    });
    expect(findNote(s2.doc)).toBeNull();
    s2.doc.descendants((node) => {
      if (node.type.name === "enum_cell") expect(String(node.attrs.current)).toBe("完全响应");
    });
  });

  it("手删 note → 任意后续 doc 变更自愈重现", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = flip(s0, "负偏离");
    const note = findNote(s1.doc)!;
    const del = s1.tr.delete(note.pos, note.pos + note.node.nodeSize);
    const s2 = s1.apply(del);
    expect(findNote(s2.doc)).not.toBeNull();
  });

  it("双字段填满 → 翻回完全响应 → note 保留(孤儿,文本零丢失)", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = flip(s0, "负偏离");
    const note = findNote(s1.doc)!;
    const s2 = fillPara(s1, note.pos + 1, REASON_LABEL, "性能无法满足");
    const note2 = findNote(s2.doc)!;
    const s3 = fillPara(s2, note2.pos + 1 + note2.node.child(0).nodeSize, ALT_LABEL, "分批交付");
    const s4 = flip(s3, "完全响应");
    const kept = findNote(s4.doc);
    expect(kept).not.toBeNull();
    expect(kept!.node.textContent).toContain("性能无法满足");
    expect(kept!.node.textContent).toContain("分批交付");
  });

  it("双字段全空 → 翻回完全响应 → note 收拢删除", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = flip(s0, "负偏离");
    const s2 = flip(s1, "完全响应");
    expect(findNote(s2.doc)).toBeNull();
  });

  it("收拢后再翻负偏离 → 自愈重建空展开面", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst(), {});
    const s1 = flip(s0, "负偏离");
    const s2 = flip(s1, "完全响应");
    const s3 = flip(s2, "负偏离");
    const note = findNote(s3.doc);
    expect(note).not.toBeNull();
    expect(labels(note!.node)).toEqual([REASON_LABEL, ALT_LABEL]);
  });
});
