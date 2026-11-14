// 批三十一 M5：浏览器剪贴板 HTML 清洗与 pastePlugin 接线（jsdom DOMParser）
import { describe, expect, it, rs } from "@rstest/core";
import { Slice } from "prosemirror-model";
import { TextSelection } from "prosemirror-state";
import { type EditorView } from "prosemirror-view";

import { demoWorkbenchAst } from "@/extensions/bid-write/editor/demo";
import {
  extractPastedContent,
  pastePlugin,
  planPaste,
  type PasteNotice,
} from "@/extensions/bid-write/editor/paste";
import { createBidWriteEditorState } from "@/extensions/bid-write/editor/state";

function textPos(state: ReturnType<typeof createBidWriteEditorState>, needle: string): number {
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

describe("HTML 粘贴清洗", () => {
  it("保留块级/换行边界，剥除样式、脚本与隐藏节点", () => {
    const html = `
      <style>.x{color:red}</style>
      <p style="font-size:18px">Hello <strong>world</strong></p>
      <div hidden>隐藏内容</div>
      <div aria-hidden="true">辅助隐藏</div>
      <ul><li>第一项</li><li>第二项<br>续行</li></ul>
      <script>alert('xss')</script>
      <p>&nbsp;尾段&nbsp;</p>
    `;
    const got = extractPastedContent({ html, text: "fallback" });
    expect(got.hadHtml).toBe(true);
    expect(got.markupStripped).toBe(true);
    expect(got.lines).toEqual(["Hello world", "第一项", "第二项", "续行", "尾段"]);
    expect(got.lines).not.toContain("隐藏内容");
    expect(got.lines).not.toContain("辅助隐藏");
    expect(got.lines.join(" ")).not.toContain("alert");
  });

  it("HTML 无可见文本时回退 plain text", () => {
    const got = extractPastedContent({ html: "<img src='x'>", text: "回退文本" });
    expect(got).toEqual({
      lines: ["回退文本"],
      hadHtml: false,
      markupStripped: false,
    });
  });

  it("HTML 表格按单元格行序清洗为文本行，不生成 AST 表格", () => {
    const s0 = createBidWriteEditorState(demoWorkbenchAst());
    const pos = textPos(s0, "根据贵方招标文件");
    const s1 = s0.apply(s0.tr.setSelection(TextSelection.create(s0.doc, pos + 1)));
    const plan = planPaste(s1, {
      html: "<table><tr><td>设备 A</td><td>2</td></tr><tr><td>设备 B</td><td>3</td></tr></table>",
      text: "设备 A\t2\n设备 B\t3",
    });
    expect(plan.tr).not.toBeNull();
    const s2 = s1.apply(plan.tr!);
    expect(s2.doc.textBetween(0, s2.doc.content.size, "\n", "")).toContain(
      "设备 A 2 设备 B 3",
    );
    expect(s2.doc.textBetween(0, s2.doc.content.size, "\n", "")).not.toContain("\t");
  });
});

describe("pastePlugin", () => {
  it("dispatch 清洗后的事务并回调 notice", () => {
    let state = createBidWriteEditorState(demoWorkbenchAst());
    const pos = textPos(state, "根据贵方招标文件");
    state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, pos + 1)));
    const notices: PasteNotice[] = [];
    const dispatched = rs.fn();
    const view = {
      get state() {
        return state;
      },
      dispatch(tr) {
        dispatched(tr);
        state = state.apply(tr);
      },
    } as unknown as EditorView;
    const preventDefault = rs.fn();
    const event = {
      clipboardData: {
        getData: (type: string) => (type === "text/html" ? "<p>A</p><p>B</p>" : "A\nB"),
      },
      preventDefault,
    } as unknown as ClipboardEvent;

    const plugin = pastePlugin({ onPasteSanitized: (n) => notices.push(n) });
    const handled = plugin.props.handlePaste!.call(plugin, view, event, Slice.empty);

    expect(handled).toBe(true);
    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(dispatched).toHaveBeenCalledTimes(1);
    expect(notices[0]).toMatchObject({ lines: 2, hadHtml: true, mode: "textblock" });
    expect(state.doc.textBetween(0, state.doc.content.size, "\n", "")).toContain("A B");
  });

  it("受保护节点粘贴走 onViolation 且不 dispatch", () => {
    let state = createBidWriteEditorState(demoWorkbenchAst());
    const pos = textPos(state, "本投标函自开标之日起");
    state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, pos + 1)));
    const violations: string[] = [];
    const dispatched = rs.fn();
    const view = {
      get state() {
        return state;
      },
      dispatch: dispatched,
    } as unknown as EditorView;
    const event = {
      clipboardData: { getData: (type: string) => (type === "text/plain" ? "外部文本" : "") },
      preventDefault: rs.fn(),
    } as unknown as ClipboardEvent;

    const plugin = pastePlugin({ onViolation: (v) => violations.push(v.code) });
    const handled = plugin.props.handlePaste!.call(plugin, view, event, Slice.empty);

    expect(handled).toBe(true);
    expect(dispatched).not.toHaveBeenCalled();
    expect(violations).toEqual(["locked_paragraph"]);
  });

  it("无可见文本的图片粘贴交回默认行为", () => {
    const state = createBidWriteEditorState(demoWorkbenchAst());
    const dispatched = rs.fn();
    const preventDefault = rs.fn();
    const view = {
      get state() {
        return state;
      },
      dispatch: dispatched,
    } as unknown as EditorView;
    const event = {
      clipboardData: {
        getData: (type: string) => (type === "text/html" ? "<img src='photo.png'>" : ""),
      },
      preventDefault,
    } as unknown as ClipboardEvent;

    const plugin = pastePlugin();
    const handled = plugin.props.handlePaste!.call(plugin, view, event, Slice.empty);

    expect(handled).toBe(false);
    expect(preventDefault).not.toHaveBeenCalled();
    expect(dispatched).not.toHaveBeenCalled();
  });
});
