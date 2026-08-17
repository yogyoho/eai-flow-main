import { Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { MathNodeView } from "../components/MathNodeView";

import { type MdInstance, mathMarkdownIt } from "./mathMarkdownIt";

const latexAttr = {
  default: "",
  parseHTML: (el: HTMLElement) => el.getAttribute("data-latex") ?? "",
};

// ponytail: tiptap-markdown 从 extension.storage.markdown.serialize 读自定义序列化
// (见 tiptap-markdown src/util/extensions.js)。让 math 节点直接输出 $...$ / $$...$$,
// 绕开 getMarkdown 对自定义 atom node 在表格/列表内丢失 latex 的问题(R1 修复)。
interface MdState {
  write: (s: string) => void;
  ensureNewLine: () => void;
  closeBlock: () => void;
}

export const MathInline = Node.create({
  name: "mathInline",
  group: "inline",
  inline: true,
  atom: true,
  addAttributes() {
    return { latex: latexAttr };
  },
  parseHTML() {
    return [{ tag: "span[data-math-inline]" }];
  },
  renderHTML({ node }) {
    return ["span", { "data-math-inline": "", "data-latex": node.attrs.latex }];
  },
  addNodeView() {
    return ReactNodeViewRenderer(MathNodeView);
  },
  addStorage() {
    return {
      markdown: {
        serialize(state: MdState, node: { attrs: { latex: string } }) {
          state.write(`$${node.attrs.latex}$`);
        },
        parse: {
          setup(md: MdInstance) {
            md.use(mathMarkdownIt);
          },
        },
      },
    };
  },
});

export const MathBlock = Node.create({
  name: "mathBlock",
  group: "block",
  atom: true,
  defining: true,
  addAttributes() {
    return { latex: latexAttr };
  },
  parseHTML() {
    return [{ tag: "div[data-math-block]" }];
  },
  renderHTML({ node }) {
    return ["div", { "data-math-block": "", "data-latex": node.attrs.latex }];
  },
  addNodeView() {
    return ReactNodeViewRenderer(MathNodeView);
  },
  addStorage() {
    return {
      markdown: {
        serialize(state: MdState, node: { attrs: { latex: string } }) {
          state.ensureNewLine();
          state.write(`$$${node.attrs.latex}$$`);
          state.closeBlock();
        },
        parse: {
          setup(md: MdInstance) {
            md.use(mathMarkdownIt);
          },
        },
      },
    };
  },
});
