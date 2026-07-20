import { Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { MathNodeView } from "../components/MathNodeView";

const latexAttr = {
  default: "",
  parseHTML: (el: HTMLElement) => el.getAttribute("data-latex") ?? "",
};

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
});
