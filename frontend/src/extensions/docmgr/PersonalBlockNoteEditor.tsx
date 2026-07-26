"use client";

// EAI-CUSTOM: Personal document BlockNote editor with AI extension + math formula support (no collaboration).
// Pattern matches BlockNoteEditor.tsx for toolbar/TOC/AI menu setup.

import type { BlockSchema, InlineContentSchema } from "@blocknote/core";
import { BlockNoteSchema, defaultBlockSpecs, defaultInlineContentSpecs } from "@blocknote/core";
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

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

// Schema with math blocks
const schema = BlockNoteSchema.create({
  blockSpecs: { ...defaultBlockSpecs, ...mathBlockSpecs },
  inlineContentSpecs: { ...defaultInlineContentSpecs, ...latexInlineContentSpecs },
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
  anchor?: string;     // text to match; omitted for prepend/append
  content?: string;    // new markdown content; omitted for delete
  autoApply: boolean;
}

// ponytail: simple Levenshtein for fuzzy anchor matching (spec §7 level 4).
export function levenshteinDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  const dp = new Uint16Array(n + 1);
  for (let j = 0; j <= n; j++) dp[j] = j;
  for (let i = 1; i <= m; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const temp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? prev : 1 + Math.min(prev, dp[j], dp[j - 1]);
      prev = temp;
    }
  }
  return dp[n];
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
export function findBlockByAnchor(doc: any[], anchor: string): { blockId: string; blockIndex: number } | null {
  if (!anchor) return null;
  const trimmed = anchor.trim();
  if (!trimmed) return null;

  // 1. Exact match
  for (let i = 0; i < doc.length; i++) {
    const fullText = getBlockText(doc[i]);
    if (!fullText) continue;
    if (fullText.trim() === trimmed) return { blockId: doc[i].id, blockIndex: i };
  }

  // 2. Prefix match
  for (let i = 0; i < doc.length; i++) {
    const fullText = getBlockText(doc[i]);
    if (!fullText) continue;
    if (fullText.trim().startsWith(trimmed)) return { blockId: doc[i].id, blockIndex: i };
  }

  // 3. Contains match (exactly one)
  let containsMatch: { blockId: string; blockIndex: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    const fullText = getBlockText(doc[i]);
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
    let fullText = getBlockText(doc[i]);
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
}

interface PersonalBlockNoteEditorProps {
  initialContent: string;
  onChange: (markdown: string) => void;
  className?: string;
}

const PersonalBlockNoteEditor = forwardRef<PersonalBlockNoteEditorRef, PersonalBlockNoteEditorProps>(
  ({ initialContent, onChange, className }, ref) => {
    const [seeded, setSeeded] = useState(false);
    const [headings, setHeadings] = useState<Array<{ id: string; level: number; text: string }>>([]);
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

    const editor = useCreateBlockNote({
      schema,
      dictionary,
      extensions: [AIExtension({ transport: aiTransport })],
    });

    // Block types that carry inline content (text nodes that may contain $...$).
    const TEXT_BLOCK_TYPES = new Set(["paragraph", "bulletListItem", "numberedListItem", "checkListItem"]);

    // ponytail: shared inline $...$ → latex content conversion.
    // Returns { content, changed }. Does NOT mutate; caller applies updateBlock.
    const convertInlineMathInContent = useCallback(
      (content: any[]): { content: any[]; changed: boolean } => {
        let changed = false;
        const newContent: any[] = [];
        for (const node of content) {
          if (node.type !== "text" || !node.text) {
            newContent.push(node);
            continue;
          }
          const text: string = node.text;
          const parts = text.split(/(\$[^$\n]+\$)/g);
          if (parts.every((p: string) => !/^\$[^$\n]+\$$/.test(p))) {
            newContent.push(node);
            continue;
          }
          changed = true;
          for (const part of parts) {
            const m = part.match(/^\$([^$\n]+)\$$/);
            if (m) {
              newContent.push({ type: "latex", props: { latex: m[1].trim(), displayMode: false } });
            } else if (part) {
              newContent.push({ ...node, text: part });
            }
          }
        }
        return { content: newContent, changed };
      },
      [],
    );

    // ── Math markdown round-trip helpers ──────────────────────────────
    // ponytail: @defensestation/blocknote-math defines no toMarkdown for equation/latex
    // (only toExternalHTML). blocksToMarkdownLossy silently skips "content: none" types,
    // so formulas vanish from saved markdown → broken on re-entry.
    // Fix: before calling blocksToMarkdownLossy, create a copy of the blocks with
    // equation→paragraph ($$...$$) and latex→text ($...$) so the export is correct.
    // Does NOT mutate editor state — operates on a shallow copy.
    const prepareBlocksForMarkdownExport = useCallback(
      (blocks: any[]): any[] => {
        return blocks.map((block: any) => {
          // equation block → paragraph with $$latex$$
          if (block.type === "equation") {
            const latex: string = block.props?.latex ?? "";
            return {
              type: "paragraph",
              props: {},
              content: [{ type: "text", text: `$$${latex}$$`, styles: {} }],
              children: block.children ?? [],
              id: block.id,
            };
          }
          // table: scan cells for latex inline content → $latex$
          if (
            block.type === "table" &&
            block.content?.type === "tableContent" &&
            Array.isArray(block.content?.rows)
          ) {
            const tc = block.content;
            const newRows = tc.rows.map((row: any) => ({
              ...row,
              cells: (row.cells ?? []).map((cell: any) => {
                if (!cell || !Array.isArray(cell.content)) return cell;
                let changed = false;
                const newContent = cell.content.map((node: any) => {
                  if (node.type === "latex") {
                    changed = true;
                    return {
                      type: "text",
                      text: `$${node.props?.latex ?? ""}$`,
                      styles: {},
                    };
                  }
                  return node;
                });
                return changed ? { ...cell, content: newContent } : cell;
              }),
            }));
            return { ...block, content: { ...tc, rows: newRows } };
          }
          // paragraph / heading: scan for latex inline content → $latex$
          if (Array.isArray(block.content)) {
            let changed = false;
            const newContent = block.content.map((node: any) => {
              if (node.type === "latex") {
                changed = true;
                return {
                  type: "text",
                  text: `$${node.props?.latex ?? ""}$`,
                  styles: {},
                };
              }
              return node;
            });
            return changed ? { ...block, content: newContent } : block;
          }
          return block;
        });
      },
      [],
    );

    // Transform BlockNote-parsed blocks: convert $$...$$ paragraphs into equation blocks,
    // and convert $...$ inline text into latex inline content.
    // BlockNote's built-in markdown parser doesn't know about custom math block types.
    const transformMathInBlocks = useCallback(
      (blocks: any[]) => {
        const result: any[] = [];
        for (const block of blocks) {
          if (TEXT_BLOCK_TYPES.has(block.type) && Array.isArray(block.content)) {
            const fullText = block.content
              .filter((c: any) => c.type === "text")
              .map((c: any) => c.text || "")
              .reduce((acc: string, c: string) => acc + c, "");

            // Check if the ENTIRE paragraph is a $$...$$ block equation
            const blockMatch = fullText.match(/^\$\$([\s\S]*?)\$\$$/);
            if (blockMatch && block.content.every((c: any) => c.type === "text" || !c.text?.trim())) {
              result.push({ type: "equation", props: { latex: blockMatch[1].trim() } });
              continue;
            }

            // Handle inline $...$ within text blocks (paragraph, list items)
            const { content: newContent, changed } = convertInlineMathInContent(block.content);
            result.push(changed ? { ...block, content: newContent } : block);
            continue;
          }
          // Handle table blocks: scan cells for $...$ inline math
          if (block.type === "table" && block.content?.type === "tableContent" && Array.isArray(block.content?.rows)) {
            const tc = block.content;
            const newRows = tc.rows.map((row: any) => ({
              ...row,
              cells: (row.cells || []).map((cell: any) => {
                // cell = { type: "tableCell", content: [...], props: {...} }
                if (!cell || !Array.isArray(cell.content)) return cell;
                let changed = false;
                const newContent = cell.content
                  .map((node: any) => {
                    if (node.type !== "text" || !node.text) return [node];
                    const text: string = node.text;
                    const parts = text.split(/(\$[^$]+\$)/g);
                    if (parts.every((p: string) => !/^\$[^$]+\$$/.test(p))) return [node];
                    changed = true;
                    return parts.map((part: string) => {
                      const m = part.match(/^\$([^$]+)\$$/);
                      return m
                        ? { type: "latex", props: { latex: m[1].trim(), displayMode: false } }
                        : part ? { ...node, text: part } : null;
                    }).filter(Boolean);
                  })
                  .flat();
                return changed ? { ...cell, content: newContent } : cell;
              }),
            }));
            result.push({ ...block, content: { ...tc, rows: newRows } });
            continue;
          }
          result.push(block);
        }

        // ── Second pass: merge multi-paragraph $$...$$ into equation blocks ──
        // ponytail: AI-generated markdown often has $$ on its own line with
        // blank lines around the content, producing three separate paragraphs
        // ($$ / content / $$). The single-paragraph regex above can't match
        // across blocks. Scan consecutive paragraphs, merge $$...$$ spans.
        const merged: any[] = [];
        let i = 0;
        while (i < result.length) {
          const block = result[i];
          if (
            block.type === "paragraph" &&
            Array.isArray(block.content) &&
            block.content.length === 1 &&
            block.content[0]?.type === "text"
          ) {
            const trimmed = (block.content[0].text || "").trim();
            if (trimmed === "$$") {
              // Opening $$ found — collect content until closing $$
              const contentParts: string[] = [];
              let j = i + 1;
              let found = false;
              while (j < result.length) {
                const nb = result[j];
                if (
                  nb.type === "paragraph" &&
                  Array.isArray(nb.content) &&
                  nb.content.length === 1 &&
                  nb.content[0]?.type === "text"
                ) {
                  const nt = (nb.content[0].text || "").trim();
                  if (nt === "$$") {
                    found = true;
                    break;
                  }
                }
                // Collect block text as part of the equation content
                if (nb.type === "paragraph" && Array.isArray(nb.content)) {
                  contentParts.push(
                    nb.content
                      .filter((c: any) => c.type === "text")
                      .map((c: any) => c.text || "")
                      .join(""),
                  );
                } else if (nb.type === "equation") {
                  contentParts.push(`$$${nb.props?.latex ?? ""}$$`);
                }
                j++;
              }
              if (found && contentParts.length > 0) {
                const latex = contentParts.join("\n").trim();
                if (latex) {
                  merged.push({ type: "equation", props: { latex } });
                  i = j + 1;
                  continue;
                }
              }
            }
          }
          merged.push(block);
          i++;
        }
        return merged;
      },
      [],
    );

    // Auto-save + heading extraction on change
    const rebuildHeadings = useCallback(() => {
      const h = editor.document
        .filter((b: { type?: string }) => b.type === "heading")
        .map((b: { id: string; props?: Record<string, unknown>; content?: Array<{ text?: string }> }) => ({
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
                          ? { type: "latex", props: { latex: m[1].trim(), displayMode: false } }
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
        // Debug: log to verify items are generated
        if (mathRaw.length) console.log('[PersonalBN] math items:', mathRaw.map((m: any) => m.title));
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
            <div style={{ padding: "16px 12px 0" }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: "hsl(var(--muted-foreground))",
                textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>目录</p>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "0 12px 16px" }}>
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
                    paddingLeft: 4 + h.level * 12,
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
          <div style={{ maxWidth: 780, margin: "0 auto", padding: "40px 32px 128px" }}>
            <BlockNoteView
              editor={editor}
              sideMenu
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
