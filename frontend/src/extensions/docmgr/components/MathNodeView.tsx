"use client";

import { NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import katex from "katex";
import { useEffect, useRef } from "react";

import { normalizeLatexForKatex } from "@/core/streamdown/latexNormalize";

// ponytail: atom node 的 NodeView —— 只读渲染公式,点击 prompt 改源码。
// 不做公式内光标编辑(避免选区/撤销地狱)。prompt 是最省事的入口,体验不足再升 popover。
const KATEX_OPTS = { output: "html", throwOnError: false, strict: false } as const;

export function MathNodeView({ node, updateAttributes }: NodeViewProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const latex: string = node.attrs.latex ?? "";
  const isBlock = node.type.name === "mathBlock";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    try {
      // normalize ²³¹℃° 等 KaTeX text-mode 缺字形的字符 → 正规上标
      katex.render(normalizeLatexForKatex(latex), el, { ...KATEX_OPTS, displayMode: isBlock });
    } catch {
      el.textContent = latex; // throwOnError:false 下一般不会到这;防御
    }
  }, [latex, isBlock]);

  const onEdit = () => {
    const next = window.prompt("编辑公式 LaTeX 源码", latex);
    if (next !== null) updateAttributes({ latex: next });
  };

  return (
    <NodeViewWrapper
      as={isBlock ? "div" : "span"}
      style={
        isBlock
          ? { textAlign: "center", margin: "1em 0" }
          : { display: "inline", verticalAlign: "baseline" }
      }
    >
      <span
        ref={ref}
        onClick={onEdit}
        title="点击编辑公式源码"
        style={{ cursor: "pointer" }}
      />
    </NodeViewWrapper>
  );
}
