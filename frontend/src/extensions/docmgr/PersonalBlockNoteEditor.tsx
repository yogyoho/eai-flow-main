"use client";

// EAI-CUSTOM: Personal document BlockNote editor with AI extension + math formula support (no collaboration).
// Pattern matches BlockNoteEditor.tsx for toolbar/TOC/AI menu setup.

import type { BlockSchema, InlineContentSchema } from "@blocknote/core";
import { BlockNoteSchema, defaultBlockSpecs, defaultInlineContentSpecs, createExtension } from "@blocknote/core";
import { en as coreEn } from "@blocknote/core/locales";
import { zh as coreZh } from "@blocknote/core/locales";
import { useCreateBlockNote, FormattingToolbar, FormattingToolbarController, getFormattingToolbarItems, SuggestionMenuController, getDefaultReactSlashMenuItems } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import { AIExtension, AIMenu, AIMenuController, AIToolbarButton } from "@blocknote/xl-ai";
import { en as aiEn } from "@blocknote/xl-ai/locales";
import { zh as aiZh } from "@blocknote/xl-ai/locales";
import { DefaultChatTransport } from "ai";
import { useI18n } from "@/core/i18n/hooks";
import { mathBlockSpecs, latexInlineContentSpecs, getMathSlashMenuItems } from "@defensestation/blocknote-math";
import "@defensestation/blocknote-math/styles.css";
import "@blocknote/react/style.css";
import "@blocknote/shadcn/style.css";
import "@blocknote/xl-ai/style.css";
import { all, createLowlight } from "lowlight";
import { createHighlightPlugin } from "prosemirror-highlight";
import { createParser } from "prosemirror-highlight/lowlight";
import "highlight.js/styles/github.css";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import { convertInlineMathInContent, prepareBlocksForMarkdownExport, TEXT_BLOCK_TYPES, transformMathInBlocks } from "./utils/mathBlocks";
import { replaceTextInContent } from "./utils/docEditorUtils";

// ── Synchronous code block highlighting via lowlight ────────────────────
// ponytail: lowlight (highlight.js AST API) is synchronous — no async,
// no WASM, no "mismatched transaction". all grammars are pre-registered.
const lowlight = createLowlight(all);
const lowlightParser = createParser(lowlight);
const highlightExtension = createExtension({
  key: "personal-code-highlight",
  prosemirrorPlugins: [
    createHighlightPlugin({ parser: lowlightParser, nodeTypes: ["codeBlock"] }),
  ],
});


// ── Agent operation types ────────────────────────────────────────────
/** Anchor for agent operation targeting — text→block mapping. */
export interface DocAnchor {
  text: string;        // first 60 chars
  blockIndex: number;  // 0-based position in editor.document
  blockType: string;   // "heading" | "paragraph" | "bulletListItem" | etc.
  headingLevel?: number;
}

export interface DocOperation {
  op: "replace" | "insert_after" | "delete" | "prepend" | "append";
  anchor?: string;
  content?: string;
}

// ponytail: simple Levenshtein for fuzzy anchor matching (spec §7 level 4).
export function levenshteinDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  const dp = new Uint16Array(n + 1);
  for (let j = 0; j <= n; j++) dp[j] = j;
  for (let i = 1; i <= m; i++) {
    let prev = dp[0]!;
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const temp = dp[j]!;
      dp[j] = a[i - 1] === b[j - 1] ? prev : 1 + Math.min(prev, dp[j]!, dp[j - 1]!);
      prev = temp;
    }
  }
  return dp[n]!;
}

// ponytail: extract all text from any block type (paragraph, heading, list item,
// table cell, etc.) into a single string for anchor matching.
function getBlockText(block: any): string {
  if (!block) return "";
  // Table: collect text from all cells
  if (block.type === "table" && block.content?.type === "tableContent" && Array.isArray(block.content.rows)) {
    const parts: string[] = [];
    for (const row of block.content.rows) {
      for (const cell of row.cells ?? []) {
        if (Array.isArray(cell.content)) {
          for (const node of cell.content) {
            if (node.type === "text") parts.push(node.text || "");
          }
        }
      }
    }
    return parts.join(" ");
  }
  // Standard inline-content blocks (paragraph, heading, list item, etc.)
  if (Array.isArray(block.content)) {
    return block.content.filter((c: any) => c.type === "text").map((c: any) => c.text || "").join("");
  }
  return "";
}

// ponytail: shared anchor→blockId lookup used by matchAnchor / applyOperations / scrollToAnchor.
// 5-level matching per spec §7: exact → prefix → contains → fuzzy → null.
// ponytail: normalize anchor text for matching. Agent may output markdown formatting
// (### headings, **bold**, |table| pipes) that don't exist in the actual block text.
function normalizeAnchorText(s: string): string {
  return s
    .replace(/^#{1,6}\s+/, "")       // ### heading prefix
    .replace(/\*\*(.+?)\*\*/g, "$1")  // **bold**
    .replace(/\*(.+?)\*/g, "$1")      // *italic*
    .replace(/\|/g, " ")              // table pipes
    .replace(/\s+/g, " ")             // collapse whitespace
    .trim();
}

export function findBlockByAnchor(doc: any[], anchor: string): { blockId: string; blockIndex: number } | null {
  if (!anchor) return null;
  const trimmed = normalizeAnchorText(anchor);
  if (!trimmed) return null;

  // 1. Exact match (normalized both sides)
  for (let i = 0; i < doc.length; i++) {
    const fullText = normalizeAnchorText(getBlockText(doc[i]));
    if (!fullText) continue;
    if (fullText === trimmed) return { blockId: doc[i].id, blockIndex: i };
  }

  // 2. Prefix match (normalized)
  for (let i = 0; i < doc.length; i++) {
    const fullText = normalizeAnchorText(getBlockText(doc[i]));
    if (!fullText) continue;
    if (fullText.startsWith(trimmed)) return { blockId: doc[i].id, blockIndex: i };
  }

  // 3. Contains match (exactly one, normalized)
  let containsMatch: { blockId: string; blockIndex: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    const fullText = normalizeAnchorText(getBlockText(doc[i]));
    if (!fullText) continue;
    if (fullText.includes(trimmed)) {
      if (containsMatch) return null; // ambiguous
      containsMatch = { blockId: doc[i].id, blockIndex: i };
    }
  }
  if (containsMatch) return containsMatch;

  // 4. Fuzzy (Levenshtein < 30%) with substring sliding window
  if (trimmed.length < 5) return null;
  let best: { blockId: string; blockIndex: number; dist: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    let fullText = normalizeAnchorText(getBlockText(doc[i]));
    if (!fullText) continue;
    // Strip markdown heading prefix
    fullText = fullText.replace(/^#{1,6}\s+/, "").trim();
    if (!fullText || fullText.length < 3) continue;

    const fullDist = levenshteinDistance(trimmed, fullText.slice(0, 80));
    if (fullDist / trimmed.length < 0.3 && (!best || fullDist < best.dist)) {
      best = { blockId: doc[i].id, blockIndex: i, dist: fullDist };
    }

    if (fullText.length > trimmed.length + 5) {
      const windowLen = Math.max(trimmed.length, Math.min(trimmed.length * 2, fullText.length));
      for (let start = 0; start <= fullText.length - trimmed.length; start++) {
        const window = fullText.slice(start, start + windowLen);
        const dist = levenshteinDistance(trimmed, window);
        if (dist / trimmed.length < 0.3 && (!best || dist < best.dist)) {
          best = { blockId: doc[i].id, blockIndex: i, dist };
          if (dist === 0) break;
        }
      }
    }
  }
  return best ? { blockId: best.blockId, blockIndex: best.blockIndex } : null;
}

export interface PersonalBlockNoteEditorRef {
  getMarkdown: () => Promise<string>;
  getSelectedText: () => string;
  /** Get all block anchors for agent operation targeting. */
  getBlockAnchors: () => DocAnchor[];
  /** Match anchor text to a specific block. Returns null if no unique match. */
  matchAnchor: (text: string) => { blockId: string; blockIndex: number } | null;
  /** Apply document operations from the agent. */
  applyOperations: (ops: DocOperation[]) => void;
  /** Scroll to and highlight the block matching the anchor text. */
  scrollToAnchor: (text: string) => boolean;
  /** Save a snapshot of current blocks for undo. */
  snapshotBlocks: () => any[];
  /** Restore blocks from a saved snapshot. */
  restoreBlocks: (blocks: any[]) => void;
  /** Undo / redo the last editor transaction（Ctrl+Z/Y 的 UI 入口）。 */
  undo: () => void;
  redo: () => void;
  /** Find all top-level blocks whose text contains query. Returns { blockId, blockIndex, count }. */
  findText: (query: string) => Array<{ blockId: string; blockIndex: number; count: number }>;
  /** Replace query in one block's text nodes. Returns replaced count. */
  replaceInBlock: (blockId: string, query: string, replacement: string) => number;
  /** Scroll to and flash-highlight a block by id. */
  scrollToBlock: (blockId: string) => boolean;
}

interface PersonalBlockNoteEditorProps {
  initialContent: string;
  onChange: (markdown: string) => void;
  className?: string;
  hideSideMenu?: boolean;
}

const PersonalBlockNoteEditor = forwardRef<PersonalBlockNoteEditorRef, PersonalBlockNoteEditorProps>(
  ({ initialContent, onChange, className, hideSideMenu }, ref) => {
    const [seeded, setSeeded] = useState(false);
    const [headings, setHeadings] = useState<Array<{ id: string; level: number; text: string }>>([]);

    // ponytail: inject light-theme override for BlockNote code block wrapper
    useEffect(() => {
      const id = "personal-code-block-light";
      if (document.getElementById(id)) return;
      const style = document.createElement("style");
      style.id = id;
      style.textContent = `[data-content-type="codeBlock"] { background: #f6f8fa !important; border: 1px solid #d0d7de; border-radius: 6px; } [data-content-type="codeBlock"] pre { background: transparent !important; margin: 0; }`;
      document.head.appendChild(style);
      return () => { style.remove(); };
    }, []);

    const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
    const convertingRef = useRef(false);
    const onChangeRef = useRef(onChange);
    onChangeRef.current = onChange;

    const { locale } = useI18n();
    const isZh = locale.startsWith("zh");

    const dictionary = useMemo(
      () => (isZh ? { ...coreZh, ai: aiZh } : { ...coreEn, ai: aiEn }) as any,
      [isZh],
    );

    const aiTransport = useMemo(
      () => new DefaultChatTransport({ api: "/api/collab/ai-chat", credentials: "include" }),
      [],
    );

    const schema = useMemo(() => BlockNoteSchema.create({
      blockSpecs: { ...defaultBlockSpecs, ...mathBlockSpecs },
      inlineContentSpecs: { ...defaultInlineContentSpecs, ...latexInlineContentSpecs },
    }), []);

    const editor = useCreateBlockNote({
      schema,
      dictionary,
      extensions: [AIExtension({ transport: aiTransport }), highlightExtension],
    });

    // 数学公式块转换逻辑已抽到 utils/mathBlocks.ts（EAI-CUSTOM，含标题内联公式修复 $V_s$）。
    // TEXT_BLOCK_TYPES / convertInlineMathInContent / prepareBlocksForMarkdownExport / transformMathInBlocks 来自该模块。

    // Auto-save + heading extraction on change
    const rebuildHeadings = useCallback(() => {
      const h = (
        editor.document as unknown as Array<{
          id: string;
          type?: string;
          props?: Record<string, unknown>;
          content?: Array<{ text?: string }>;
        }>
      )
        .filter((b) => b.type === "heading")
        .map((b) => ({
          id: b.id,
          level: (b.props?.level as number) || 1,
          text: b.content?.map((c) => c.text || "").join("") || "",
        }));
      setHeadings(h);
    }, [editor]);

    // Seed initial content once
    useEffect(() => {
      if (seeded || !editor) return;
      if (initialContent?.trim()) {
        const parsed = editor.tryParseMarkdownToBlocks(initialContent.trim());
        const blocks = transformMathInBlocks(parsed);
        if (blocks.length > 0) {
          editor.replaceBlocks(editor.document.map((b) => b.id), blocks);
        }
      }
      setSeeded(true);
      // Rebuild headings after seed — onChange doesn't fire for initial content
      setTimeout(() => rebuildHeadings(), 100);
    }, [editor, initialContent, seeded, rebuildHeadings, transformMathInBlocks]);

    useEffect(() => {
      if (!seeded) return;

      const disposer = editor.onChange(() => {
        rebuildHeadings();

        clearTimeout(saveTimer.current);
        saveTimer.current = setTimeout(async () => {
          // Convert typed $...$ → inline latex (deferred to avoid onChange re-entry)
          const converting = convertingRef.current;
          if (converting) return;
          convertingRef.current = true;
          try {
            const doc = editor.document;
            for (const block of doc) {
              // Handle table blocks: scan each cell for $...$ inline math
              if (block.type === "table" && (block.content as any)?.type === "tableContent" && Array.isArray((block.content as any).rows)) {
                const tc = block.content as any;
                let tableChanged = false;
                const newRows = tc.rows.map((row: any) => {
                  if (!Array.isArray(row.cells)) return row;
                  const newCells = row.cells.map((cell: any) => {
                    if (!cell || !Array.isArray(cell.content)) return cell;
                    let changed = false;
                    const newContent = cell.content.map((node: any) => {
                      if (node.type !== "text" || !node.text) return node;
                      const text: string = node.text;
                      const parts = text.split(/(\$[^$\n]+\$)/g);
                      if (parts.every((p: string) => !/^\$[^$\n]+\$$/.test(p))) return node;
                      changed = true;
                      return parts.map((part: string) => {
                        const m = part.match(/^\$([^$\n]+)\$$/);
                        return m
                          ? { type: "latex", props: { latex: m[1]!.trim(), displayMode: false } }
                          : part ? { ...node, text: part } : null;
                      }).filter(Boolean);
                    }).flat();
                    if (changed) tableChanged = true;
                    return changed ? { ...cell, content: newContent } : cell;
                  });
                  return newCells;
                });
                if (tableChanged) {
                  editor.updateBlock(block, { type: "table", content: { ...tc, rows: newRows } } as any);
                }
                continue;
              }

              if (!TEXT_BLOCK_TYPES.has(block.type) || !Array.isArray(block.content)) continue;

              // ponytail: skip live $$...$$ → equation conversion — equation blocks
              // are leaf nodes (content: "none"); updateBlock type-change leaves stale
              // content slots. Use slash-menu or initial-load transformMathInBlocks instead.

              // Check each text node for inline $...$
              const { content: newContent, changed } = convertInlineMathInContent(block.content);
              if (changed) {
                editor.updateBlock(block, { type: block.type, content: newContent } as any);
              }
            }
          } catch (_e) { /* ignore */ }
          convertingRef.current = false;

          let md = "";
          try {
            const blocksForExport = prepareBlocksForMarkdownExport(editor.document);
            md = await editor.blocksToMarkdownLossy(blocksForExport);
          } catch (e: any) {
            console.warn("[PersonalBN] blocksToMarkdownLossy failed:", e.message);
          }
          onChangeRef.current(md);
        }, 1500);
      });

      return () => {
        disposer();
        clearTimeout(saveTimer.current);
      };
    }, [editor, seeded, rebuildHeadings]);

    useImperativeHandle(ref, () => ({
      getMarkdown: async () => editor.blocksToMarkdownLossy(prepareBlocksForMarkdownExport(editor.document)),
      getSelectedText: () => editor.getSelectedText(),

      getBlockAnchors: () => {
        return editor.document.map((b, i) => {
          const text = getBlockText(b);
          const anchor: DocAnchor = { text: text.slice(0, 60), blockIndex: i, blockType: b.type };
          if (b.type === "heading" && (b.props as any)?.level) {
            anchor.headingLevel = (b.props as any).level as number;
          }
          return anchor;
        });
      },

      matchAnchor: (text: string) => findBlockByAnchor(editor.document, text),

      applyOperations: (ops: DocOperation[]) => {
        for (const op of ops) {
          const parsed = editor.tryParseMarkdownToBlocks(op.content ?? "");
          if (parsed.length === 0 && op.op !== "delete") {
            console.warn("[applyOperations] skip: empty parsed content for op", op.op);
            continue;
          }

          switch (op.op) {
            case "replace":
            case "insert_after":
            case "delete": {
              if (!op.anchor) throw new Error(`操作缺少 anchor: ${op.op}`);
              const match = findBlockByAnchor(editor.document, op.anchor);
              if (!match) throw new Error(`找不到匹配的文本: "${op.anchor}"`);
              if (op.op === "replace") editor.replaceBlocks([match.blockId], parsed);
              else if (op.op === "insert_after") editor.insertBlocks(parsed, match.blockId, "after");
              else editor.removeBlocks([match.blockId]);
              break;
            }
            case "prepend": {
              const firstId = editor.document[0]?.id;
              if (!firstId) throw new Error("文档为空，无法在开头插入");
              editor.insertBlocks(parsed, firstId, "before");
              break;
            }
            case "append": {
              const last = editor.document[editor.document.length - 1];
              if (!last) throw new Error("文档为空，无法在末尾追加");
              editor.insertBlocks(parsed, last.id, "after");
              break;
            }
          }
        }
      },

      scrollToAnchor: (text: string) => {
        const match = findBlockByAnchor(editor.document, text);
        if (!match) return false;
        const el = document.querySelector(`[data-id="${match.blockId}"]`);
        if (!el) return false;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("ring-2", "ring-primary", "ring-offset-2");
        setTimeout(() => el.classList.remove("ring-2", "ring-primary", "ring-offset-2"), 2000);
        return true;
      },

      snapshotBlocks: () => JSON.parse(JSON.stringify(editor.document)),

      restoreBlocks: (blocks: any[]) => {
        editor.replaceBlocks(editor.document.map((b) => b.id), blocks);
      },

      undo: () => editor.undo(),
      redo: () => editor.redo(),

      findText: (query: string) => {
        const q = query.trim();
        if (!q) return [];
        const matches: Array<{ blockId: string; blockIndex: number; count: number }> = [];
        editor.document.forEach((b: any, blockIndex: number) => {
          const text = getBlockText(b);
          if (!text) return;
          const count = text.split(q).length - 1;
          if (count > 0) matches.push({ blockId: b.id, blockIndex, count });
        });
        return matches;
      },

      replaceInBlock: (blockId: string, query: string, replacement: string) => {
        const block = editor.document.find((b: any) => b.id === blockId);
        if (!block || !query || !Array.isArray(block.content)) return 0;
        const { content: newContent, replaced } = replaceTextInContent(block.content, query, replacement);
        if (replaced > 0) editor.updateBlock(block, { content: newContent } as any);
        return replaced;
      },

      scrollToBlock: (blockId: string) => {
        const el = document.querySelector(`[data-id="${blockId}"]`);
        if (!el) return false;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("ring-2", "ring-primary", "ring-offset-2");
        setTimeout(() => el.classList.remove("ring-2", "ring-primary", "ring-offset-2"), 2000);
        return true;
      },
    }));

    // AI menu items — same pattern as getCollabAIMenuItems
    const getAIMenuItems = useCallback(
      (_editor: typeof editor, status: string) => {
        const ai = _editor.getExtension(AIExtension);
        if (!ai) return [];

        if (status === "user-reviewing") {
          return [
            { key: "accept", title: "替换", onItemClick: () => ai.acceptChanges() },
            { key: "reject", title: "撤销", onItemClick: () => ai.rejectChanges() },
          ];
        }

        if (status === "error") {
          return [
            { key: "retry", title: "重试", onItemClick: async () => { await ai.retry(); } },
            { key: "cancel", title: "取消", onItemClick: () => ai.rejectChanges() },
          ];
        }

        if (status !== "user-input") return [];

        const hasSelection = !!_editor.getSelection();
        return hasSelection
          ? [
              { key: "ai-polish", title: "润色", onItemClick: (setPrompt: (p: string) => void) => setPrompt("润色选中文本，使其更加流畅、专业，保持原意不变。只输出润色后的文本。") },
              { key: "ai-expand", title: "扩写", onItemClick: (setPrompt: (p: string) => void) => setPrompt("扩写选中文本，增加更多细节、论据或说明，使内容更加丰富详实。只输出扩写后的文本。") },
              { key: "ai-condense", title: "精简", onItemClick: (setPrompt: (p: string) => void) => setPrompt("精简选中文本，去除冗余内容，保留核心信息，使表达更加简洁有力。只输出精简后的文本。") },
              { key: "ai-continue", title: "续写", onItemClick: (setPrompt: (p: string) => void) => setPrompt("基于选中文本内容继续撰写，保持风格和主题一致。只输出续写的部分。") },
            ]
          : [
              { key: "ai-continue", title: "续写", onItemClick: (setPrompt: (p: string) => void) => setPrompt("基于当前光标位置的上下文内容继续撰写。只输出续写的部分。") },
              { key: "ai-brainstorm", title: "头脑风暴", onItemClick: (setPrompt: (p: string) => void) => setPrompt("基于当前文档内容进行头脑风暴，提供3-5个相关的扩展思路或角度。只输出思路列表。") },
              { key: "ai-outline", title: "生成大纲", onItemClick: (setPrompt: (p: string) => void) => setPrompt("根据当前文档的上下文，生成一个合适的大纲结构。使用 Markdown 标题格式。") },
            ];
      },
      [],
    );

    const getSlashMenuItems = useCallback(
      async (query: string) => {
        const defaults = getDefaultReactSlashMenuItems(editor);
        const mathRaw = getMathSlashMenuItems(editor);
        return [...defaults, ...mathRaw];
      },
      [editor],
    );

    return (
      <div className={className} style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        {/* Left: TOC sidebar — matches OutlinePanel pattern */}
        {headings.length > 0 && (
          <div style={{
            width: 192, flexShrink: 0, display: "flex", flexDirection: "column",
            borderRight: "1px solid hsl(var(--border))", background: "hsl(var(--muted) / 0.5)",
          }}>
            <div style={{ padding: "16px 8px 0" }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: "hsl(var(--muted-foreground))",
                textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>目录</p>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "0 8px 16px" }}>
              {headings.map((h) => (
                <button
                  key={h.id}
                  onClick={() => {
                    const el = document.querySelector(`[data-id="${h.id}"]`);
                    el?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                  style={{
                    display: "block", width: "100%", textAlign: "left", lineHeight: 1.4,
                    padding: "4px 8px 4px 0", borderRadius: "0 4px 4px 0", fontSize: 13,
                    color: "hsl(var(--muted-foreground))", cursor: "pointer", overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap",
                    paddingLeft: h.level * 10,
                  }}
                >
                  {h.text}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Center: Editor — matches BlockNoteEditor layout */}
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          <div style={{ padding: "40px 32px 128px" }}>
            <BlockNoteView
              editor={editor}
              sideMenu={!hideSideMenu}
              slashMenu={false}
              formattingToolbar={false}
              linkToolbar
              tableHandles
            >
              <SuggestionMenuController
                getItems={getSlashMenuItems}
                triggerCharacter="/"
              />
              <FormattingToolbarController
                formattingToolbar={() => (
                  <FormattingToolbar>
                    {...getFormattingToolbarItems()}
                    <AIToolbarButton />
                  </FormattingToolbar>
                )}
              />
              <AIMenuController
                aiMenu={() => (
                  <AIMenu items={getAIMenuItems} />
                )}
              />
            </BlockNoteView>
          </div>
        </div>
      </div>
    );
  },
);

PersonalBlockNoteEditor.displayName = "PersonalBlockNoteEditor";
export default PersonalBlockNoteEditor;
