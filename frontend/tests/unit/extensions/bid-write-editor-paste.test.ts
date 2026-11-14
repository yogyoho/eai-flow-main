// 批三十一 M5：粘贴清洗纯逻辑（node env：只跑 plain text / 事务规划，HTML 解析在 DOM spec）
import { describe, expect, it } from "@rstest/core";
import { type EditorState, TextSelection } from "prosemirror-state";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import {
  extractPastedContent,
  planPaste,
} from "@/extensions/bid-write/editor/paste";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";

function textPos(state: EditorState, needle: string): number {
  let hit = -1;
  state.doc.descendants((node, pos) => {
    if (hit >= 0) return false;
    if (node.isText && (node.text ?? "").includes(needle)) {
      hit = pos + Math.max(0, (node.text ?? "").indexOf(needle));
      return false;
    }
    return true;
  });
  if (hit < 0) throw new Error(`text not found: ${needle}`);
  return hit;
}

function cellPos(
  state: EditorState,
  pick: { colRole?: string; typeName?: string },
): number {
  let hit = -1;
  state.doc.descendants((node, pos) => {
    if (hit >= 0) return false;
    const roleOk = pick.colRole ? node.attrs.col_role === pick.colRole : true;
    const typeOk = pick.typeName ? node.type.name === pick.typeName : true;
    if (roleOk && typeOk) {
      hit = pos;
      return false;
    }
    return true;
  });
  if (hit < 0) throw new Error("cell not found");
  return hit;
}

function stateAt(state: EditorState, pos: number): EditorState {
  const tr = state.tr.setSelection(TextSelection.create(state.doc, pos));
  return state.apply(tr);
}

describe("粘贴文本清洗", () => {
  it("plain text 统一换行并剔除空行", () => {
    const got = extractPastedContent({ text: "  第一行  \r\n\r\n 第二行\t " });
    expect(got).toEqual({
      lines: ["第一行", "第二行"],
      hadHtml: false,
      markupStripped: false,
    });
  });

  it("文本块内多行合并为单行（不造块级结构）", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = textPos(s0, "根据贵方招标文件");
    const s1 = stateAt(s0, pos);
    const before = s1.doc.childCount;
    const plan = planPaste(s1, { text: "第一行\n第二行" });
    expect(plan.blocked).toBeNull();
    expect(plan.rejected).toBeNull();
    expect(plan.tr).not.toBeNull();
    const s2 = s1.apply(plan.tr!);
    expect(s2.doc.childCount).toBe(before);
    expect(s2.doc.textBetween(0, s2.doc.content.size, "\n", "")).toContain(
      "第一行 第二行",
    );
  });

  it("块级上下文按行生成 para（section 内容增加）", () => {
    const ast = {
      type: "doc",
      content: [
        {
          type: "section",
          attrs: { level: 1, title: "测试", section_id: "S1" },
          content: [
            {
              type: "para",
              attrs: { slot_id: "", label: "" },
              content: [{ type: "text", text: "原有段落" }],
            },
          ],
        },
      ],
    };
    const s0 = createBidWriteEditorState(ast);
    const tr = s0.tr.setSelection(TextSelection.create(s0.doc, 1));
    const s1 = s0.apply(tr);
    const plan = planPaste(s1, { text: "第一段\n\n第二段" });
    expect(plan.rejected).toBeNull();
    const s2 = s1.apply(plan.tr!);
    const section = s2.doc.child(0);
    expect(section.childCount).toBe(3);
    expect(section.child(0).textContent).toBe("第一段");
    expect(section.child(1).textContent).toBe("第二段");
  });

  it("锁定段拒绝粘贴并给出 SK-BL-007 违规", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = textPos(s0, "本投标函自开标之日起");
    const s1 = stateAt(s0, pos + 1);
    const plan = planPaste(s1, { text: "外部文本" });
    expect(plan.tr).toBeNull();
    expect(plan.blocked?.code).toBe("locked_paragraph");
    expect(plan.blocked?.message).toContain("SK-BL-007");
  });

  it("枚举格与来源列拒绝粘贴", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const enumPlan = planPaste(stateAt(s0, cellPos(s0, { typeName: "enum_cell" }) + 1), {
      text: "自行输入",
    });
    expect(enumPlan.blocked?.code).toBe("enum_cell");

    const qtyPlan = planPaste(stateAt(s0, cellPos(s0, { colRole: "qty" }) + 1), {
      text: "999",
    });
    expect(qtyPlan.blocked?.code).toBe("readonly_source_cell");
  });

  it("跨块选区拒绝（避免替换掉整段结构）", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const from = textPos(s0, "根据贵方招标文件") + 1;
    const to = textPos(s0, "本投标函自开标之日起") + 1;
    const tr = s0.tr.setSelection(TextSelection.create(s0.doc, from, to));
    const s1 = s0.apply(tr);
    const plan = planPaste(s1, { text: "不应落库" });
    expect(plan.tr).toBeNull();
    expect(plan.rejected).toBe("cross_block");
  });

  it("空白剪贴板不生成事务", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = textPos(s0, "根据贵方招标文件");
    const plan = planPaste(stateAt(s0, pos + 1), { text: " \n\t " });
    expect(plan.tr).toBeNull();
    expect(plan.rejected).toBe("empty");
  });
});
