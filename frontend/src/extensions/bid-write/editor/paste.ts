// EAI-CUSTOM 批三十一 M5——富文本粘贴清洗(方案 §5 粘贴面):
//  · 外部 HTML 只取可见文本,block/br 转行边界;script/style/隐藏节点剔除;
//  · 文本块内多行合并为单行(不把 Word 的段落/表格结构塞进 cell);
//  · 块级上下文按行生成 para(AST schema 不变,外部标签永不直接落库);
//  · 锁定段/金额格/来源列/枚举复用 M1 findProtected,拒绝绕过;
//  · 跨块选区拒绝,避免一次粘贴替换掉章节结构。
import { Fragment, Slice } from "prosemirror-model";
import {
  type EditorState,
  Plugin,
  TextSelection,
  type Transaction,
} from "prosemirror-state";

import {
  findProtected,
  type ConstraintViolation,
  type OnViolation,
} from "./constraints";

const SKIP_TAGS = new Set([
  "SCRIPT",
  "STYLE",
  "NOSCRIPT",
  "TEMPLATE",
  "SVG",
  "IFRAME",
  "OBJECT",
  "EMBED",
  "CANVAS",
]);

const BLOCK_TAGS = new Set([
  "ADDRESS",
  "ARTICLE",
  "ASIDE",
  "BLOCKQUOTE",
  "CAPTION",
  "DD",
  "DIV",
  "DL",
  "DT",
  "FIELDSET",
  "FIGCAPTION",
  "FIGURE",
  "FOOTER",
  "FORM",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HEADER",
  "HR",
  "LI",
  "MAIN",
  "NAV",
  "OL",
  "P",
  "PRE",
  "SECTION",
  "TABLE",
  "TBODY",
  "TD",
  "TFOOT",
  "TH",
  "THEAD",
  "TR",
  "UL",
]);

export interface PastedContent {
  lines: string[];
  hadHtml: boolean;
  markupStripped: boolean;
}

export type PasteMode = "textblock" | "blocks";
export type PasteRejected = "cross_block" | "unsupported" | "empty";

export interface PastePlan {
  content: PastedContent;
  mode: PasteMode | null;
  tr: Transaction | null;
  blocked: ConstraintViolation | null;
  rejected: PasteRejected | null;
}

export interface PasteNotice {
  lines: number;
  hadHtml: boolean;
  markupStripped: boolean;
  mode: PasteMode | null;
  rejected: PasteRejected | null;
}

function normalizeLines(raw: string): string[] {
  return raw
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.replace(/\u00a0/g, " ").replace(/[\t\f\v ]+/g, " ").trim())
    .filter(Boolean);
}

function isHidden(element: Element): boolean {
  if (element.hasAttribute("hidden")) return true;
  if (element.getAttribute("aria-hidden") === "true") return true;
  const style = (element as HTMLElement).style;
  return style?.display === "none" || style?.visibility === "hidden";
}

function collectHtmlText(node: Node, out: string[]): void {
  if (node.nodeType === Node.TEXT_NODE) {
    out.push((node.nodeValue ?? "").replace(/\u00a0/g, " "));
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;

  const element = node as Element;
  const tag = element.tagName.toUpperCase();
  if (SKIP_TAGS.has(tag) || isHidden(element)) return;
  if (tag === "BR") {
    out.push("\n");
    return;
  }

  const isBlock = BLOCK_TAGS.has(tag);
  if (isBlock) out.push("\n");
  for (const child of Array.from(element.childNodes)) collectHtmlText(child, out);
  if (isBlock) out.push("\n");
}

function htmlToLines(html: string): string[] {
  if (typeof DOMParser === "undefined") return [];
  const doc = new DOMParser().parseFromString(html, "text/html");
  const parts: string[] = [];
  collectHtmlText(doc.body, parts);
  return normalizeLines(parts.join(""));
}

/** clipboard HTML → 可见文本行;HTML 无可见文本时回退 plain text。 */
export function extractPastedContent(input: {
  html?: string | null;
  text?: string | null;
}): PastedContent {
  const html = input.html ?? "";
  if (html.trim()) {
    const lines = htmlToLines(html);
    if (lines.length > 0) {
      return {
        lines,
        hadHtml: true,
        markupStripped: /<[a-z][^>]*>/i.test(html),
      };
    }
  }
  return {
    lines: normalizeLines(input.text ?? ""),
    hadHtml: false,
    markupStripped: false,
  };
}

function emptyPlan(content: PastedContent, rejected: PasteRejected): PastePlan {
  return { content, mode: null, tr: null, blocked: null, rejected };
}

/** 按当前选区规划粘贴事务;不 dispatch,便于单测与插件统一预检。 */
export function planPaste(
  state: EditorState,
  input: { html?: string | null; text?: string | null },
): PastePlan {
  const content = extractPastedContent(input);
  if (content.lines.length === 0) return emptyPlan(content, "empty");

  const selection = state.selection;
  if (!selection.empty && !selection.$from.sameParent(selection.$to)) {
    return emptyPlan(content, "cross_block");
  }
  const blocked = findProtected(state.doc, selection.from, selection.to);
  if (blocked) {
    return { content, mode: null, tr: null, blocked, rejected: null };
  }

  const parent = selection.$from.parent;
  if (parent.isTextblock) {
    const text = content.lines.join(" ");
    const tr = state.tr.insertText(text, selection.from, selection.to);
    const end = Math.min(tr.doc.content.size, selection.from + text.length);
    tr.setSelection(TextSelection.near(tr.doc.resolve(end)));
    tr.scrollIntoView();
    return { content, mode: "textblock", tr, blocked: null, rejected: null };
  }

  if (parent.type.name === "doc" || parent.type.name === "section" || parent.type.name === "deviation_note") {
    const para = state.schema.nodes.para;
    if (!para) return emptyPlan(content, "unsupported");
    const paras = content.lines.map((line) => para.create(null, state.schema.text(line)));
    const tr = state.tr.replaceSelection(new Slice(Fragment.fromArray(paras), 0, 0));
    tr.setSelection(TextSelection.near(tr.doc.resolve(tr.selection.to)));
    tr.scrollIntoView();
    return { content, mode: "blocks", tr, blocked: null, rejected: null };
  }

  return emptyPlan(content, "unsupported");
}

export interface PastePluginOptions {
  onViolation?: OnViolation;
  onPasteSanitized?: (notice: PasteNotice) => void;
}

export function pastePlugin(options: PastePluginOptions = {}): Plugin {
  return new Plugin({
    props: {
      handlePaste(view, event) {
        const data = event.clipboardData;
        if (!data) return false;
        const html = data.getData("text/html");
        const text = data.getData("text/plain");
        if (!html && !text) return false;

        const plan = planPaste(view.state, { html, text });
        if (plan.blocked) {
          event.preventDefault();
          options.onViolation?.(plan.blocked);
          return true;
        }
        if (plan.rejected === "empty") return false;
        if (plan.rejected) {
          event.preventDefault();
          options.onPasteSanitized?.({
            lines: plan.content.lines.length,
            hadHtml: plan.content.hadHtml,
            markupStripped: plan.content.markupStripped,
            mode: null,
            rejected: plan.rejected,
          });
          return true;
        }
        if (!plan.tr) return false;

        event.preventDefault();
        view.dispatch(plan.tr);
        options.onPasteSanitized?.({
          lines: plan.content.lines.length,
          hadHtml: plan.content.hadHtml,
          markupStripped: plan.content.markupStripped,
          mode: plan.mode,
          rejected: null,
        });
        return true;
      },
    },
  });
}
