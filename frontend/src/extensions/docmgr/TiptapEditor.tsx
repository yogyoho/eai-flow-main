"use client";

import { Extension } from "@tiptap/core";
import Highlight from "@tiptap/extension-highlight";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { Table } from "@tiptap/extension-table";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import { TableRow } from "@tiptap/extension-table-row";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  Pilcrow,
  List,
  ListOrdered,
  ListChecks,
  AlignLeft,
  AlignCenter,
  AlignRight,
  Quote,
  Code,
  Minus,
  Undo2,
  Redo2,
  Highlighter,
  Link2,
  Table as TableIcon,
} from "lucide-react";
import React, {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  forwardRef,
} from "react";
import { Markdown } from "tiptap-markdown";

import { cn } from "@/lib/utils";

import EditorDragHandle from "./components/EditorDragHandle";
import SlashMenu from "./components/SlashMenu";
import { MathBlock, MathInline } from "./extensions/Math";
import {
  SlashCommand,
  SlashCommandPluginKey,
  type SlashCommandPluginState,
} from "./extensions/SlashCommand";
import { useScrollSpy } from "./hooks/useScrollSpy";
import { AiDeletion } from "./tiptap/ai-deletion";
import { AiFormat } from "./tiptap/ai-format";
import { AiInsertion } from "./tiptap/ai-insertion";
import { AiReview } from "./tiptap/ai-review";
import { extractHeadings } from "./utils/headingIdManager";
import {
  getMarkdownPasteParseMode,
  shouldHandleMarkdownPaste,
} from "./utils/markdownPaste";
import { highlightSection } from "./utils/sectionHighlighter";

const aiHighlightKey = new PluginKey<DecorationSet>("aiHighlight");

/** 临时高亮 AI 操作选中的文字范围（仅装饰，不写入文档） */
const AiHighlight = Extension.create({
  addProseMirrorPlugins() {
    return [
      new Plugin<DecorationSet>({
        key: aiHighlightKey,
        state: {
          init: () => DecorationSet.empty,
          apply(tr, old) {
            const meta = tr.getMeta(aiHighlightKey);
            if (meta === "clear") return DecorationSet.empty;
            if (meta) {
              return DecorationSet.create(tr.doc, [
                Decoration.inline(meta.from, meta.to, {
                  style: "background-color: #fef9c3; border-radius: 2px;",
                }),
              ]);
            }
            if (tr.docChanged) return old.map(tr.mapping, tr.doc);
            return old;
          },
        },
        props: {
          decorations: (state) => aiHighlightKey.getState(state),
        },
      }),
    ];
  },
});

export interface TiptapEditorRef {
  getMarkdown: () => string;
  getSelectedText: () => string;
  replaceSelection: (text: string) => void;
  insertAtCursor: (text: string) => void;
  getCursorParagraph: () => string;
  highlightSelection: () => void;
  clearHighlight: () => void;
  focus: () => void;
  getEditor: () => Editor | null;
  scrollToSection: (sectionId: string) => boolean;
  getHeadings: () => HeadingItem[];
  // AI Agent 协作编辑 API
  /** 在指定文档位置插入文字，可选择打上 AI 协作 mark */
  insertAtPosition: (
    pos: number,
    text: string,
    opts?: { mark?: string; attrs?: Record<string, string> },
  ) => void;
  /** 为文档范围打上 AI 协作 mark（不修改内容） */
  markRange: (
    from: number,
    to: number,
    markName: string,
    attrs?: Record<string, string>,
  ) => void;
  /** 清除所有 AI 协作标记（不改变文字内容） */
  clearAllAIMarks: () => void;
  /** 接受全部 AI 变更：保留新增文字，删除标记为删除的文字 */
  acceptAllChanges: () => void;
  /** 拒绝全部 AI 变更：删除新增文字，恢复标记为删除的文字 */
  rejectAllChanges: () => void;
  /** 按 opId 接受单个变更 */
  acceptChange: (opId: string) => void;
  /** 按 opId 拒绝单个变更 */
  rejectChange: (opId: string) => void;
  /** 获取所有 AI 审核批注列表 */
  getReviewComments: () => Array<{
    opId: string;
    from: number;
    to: number;
    comment: string;
    severity: string;
    clauseRef: string;
  }>;
  /** EAI-CUSTOM: Replace entire editor content (used to sync after MCP tool writes file) */
  setContent: (markdown: string) => void;
}

interface TiptapEditorProps {
  initialContent: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
  className?: string;
  onReady?: (editor: Editor | null) => void;
}

interface HeadingItem {
  id: string;
  level: number;
  text: string;
  element: HTMLElement;
}

const SCROLL_OFFSET_TOP = 80;
const HIGHLIGHT_DURATION = 2000;

function TBtn({
  onClick,
  active,
  disabled,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onMouseDown={(e) => {
        e.preventDefault();
        onClick();
      }}
      className={cn(
        "rounded-md p-1.5 transition-colors",
        active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:text-foreground hover:bg-muted",
        disabled && "cursor-not-allowed opacity-30",
      )}
    >
      {children}
    </button>
  );
}

function TDivider() {
  return <div className="bg-border mx-0.5 h-4 w-px shrink-0" />;
}

export function EditorToolbar({ editor }: { editor: Editor | null }) {
  if (!editor) return null;

  const setLink = () => {
    const prev = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt("输入链接地址", prev ?? "https://");
    if (url === null) return;
    if (url === "") {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };

  const insertTable = (rows: number, cols: number) => {
    editor
      .chain()
      .focus()
      .insertTable({ rows, cols, withHeaderRow: true })
      .run();
  };

  return (
    <div className="bg-background/95 border-border flex flex-wrap items-center gap-0.5 rounded-xl border px-3 py-2 shadow-lg backdrop-blur-sm">
      <TBtn
        title="撤销 (Ctrl+Z)"
        onClick={() => editor.chain().focus().undo().run()}
        disabled={!editor.can().undo()}
      >
        <Undo2 className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="重做 (Ctrl+Y)"
        onClick={() => editor.chain().focus().redo().run()}
        disabled={!editor.can().redo()}
      >
        <Redo2 className="h-3.5 w-3.5" />
      </TBtn>
      <TDivider />
      <TBtn
        title="正文"
        active={editor.isActive("paragraph")}
        onClick={() => editor.chain().focus().setParagraph().run()}
      >
        <Pilcrow className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="标题 1"
        active={editor.isActive("heading", { level: 1 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
      >
        <Heading1 className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="标题 2"
        active={editor.isActive("heading", { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
      >
        <Heading2 className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="标题 3"
        active={editor.isActive("heading", { level: 3 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
      >
        <Heading3 className="h-3.5 w-3.5" />
      </TBtn>
      <TDivider />
      <TBtn
        title="加粗 (Ctrl+B)"
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="斜体 (Ctrl+I)"
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="下划线 (Ctrl+U)"
        active={editor.isActive("underline")}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="删除线"
        active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <Strikethrough className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="高亮"
        active={editor.isActive("highlight")}
        onClick={() => editor.chain().focus().toggleHighlight().run()}
      >
        <Highlighter className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="行内代码"
        active={editor.isActive("code")}
        onClick={() => editor.chain().focus().toggleCode().run()}
      >
        <Code className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn title="链接" active={editor.isActive("link")} onClick={setLink}>
        <Link2 className="h-3.5 w-3.5" />
      </TBtn>
      <TDivider />
      <TBtn
        title="无序列表"
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <List className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="有序列表"
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <ListOrdered className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="任务列表"
        active={editor.isActive("taskList")}
        onClick={() => editor.chain().focus().toggleTaskList().run()}
      >
        <ListChecks className="h-3.5 w-3.5" />
      </TBtn>
      <TDivider />
      <TBtn
        title="左对齐"
        active={editor.isActive({ textAlign: "left" })}
        onClick={() => editor.chain().focus().setTextAlign("left").run()}
      >
        <AlignLeft className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="居中"
        active={editor.isActive({ textAlign: "center" })}
        onClick={() => editor.chain().focus().setTextAlign("center").run()}
      >
        <AlignCenter className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="右对齐"
        active={editor.isActive({ textAlign: "right" })}
        onClick={() => editor.chain().focus().setTextAlign("right").run()}
      >
        <AlignRight className="h-3.5 w-3.5" />
      </TBtn>
      <TDivider />
      <TBtn
        title="引用块"
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <Quote className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="代码块"
        active={editor.isActive("codeBlock")}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
      >
        <Code className="h-3.5 w-3.5" />
      </TBtn>
      <TBtn
        title="分割线"
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
      >
        <Minus className="h-3.5 w-3.5" />
      </TBtn>
      <TDivider />
      <TBtn
        title="插入表格"
        active={editor.isActive("table")}
        onClick={() => insertTable(3, 3)}
      >
        <TableIcon className="h-3.5 w-3.5" />
      </TBtn>
    </div>
  );
}

function TableOfContents({
  headings,
  activeId,
  onSectionClick,
}: {
  headings: HeadingItem[];
  activeId: string | null;
  onSectionClick: (sectionId: string) => void;
}) {
  if (headings.length === 0) return null;

  return (
    <nav className="relative space-y-0.5">
      {headings.map((h) => (
        <div key={h.id} className="group relative">
          <div
            className={cn(
              "bg-primary absolute top-0 bottom-0 left-0 w-0.5 rounded-full transition-all duration-200",
              activeId === h.id
                ? "opacity-100"
                : "opacity-0 group-hover:opacity-30",
            )}
          />
          <button
            onClick={() => onSectionClick(h.id)}
            title={h.text}
            className={cn(
              "w-full rounded-r py-1 pr-2 text-left text-[13px] leading-snug transition-colors",
              h.level === 1 && "pl-3 font-medium",
              h.level === 2 && "pl-5",
              h.level === 3 && "pl-7",
              h.level === 4 && "pl-9",
              h.level === 5 && "pl-11",
              h.level >= 6 && "pl-13",
              activeId === h.id
                ? "text-primary bg-primary/10"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60",
            )}
          >
            {h.text}
          </button>
        </div>
      ))}
    </nav>
  );
}

const TiptapEditor = forwardRef<TiptapEditorRef, TiptapEditorProps>(
  (
    {
      initialContent,
      onChange,
      placeholder = "开始输入内容...",
      className,
      onReady,
    },
    ref,
  ) => {
    const scrollRef = useRef<HTMLDivElement>(null);
    const editorInstanceRef = useRef<Editor | null>(null);
    const [headings, setHeadings] = useState<HeadingItem[]>([]);
    const [clickedId, setClickedId] = useState<string | null>(null);
    const [slashMenuVisible, setSlashMenuVisible] = useState(false);
    const [slashMenuQuery, setSlashMenuQuery] = useState("");
    const [slashMenuPosition, setSlashMenuPosition] = useState({
      top: 0,
      left: 0,
    });

    const activeId = useScrollSpy({
      containerRef: scrollRef,
      headings: headings.map((h) => ({ id: h.id, element: h.element })),
      offsetTop: SCROLL_OFFSET_TOP,
      debounceMs: 50,
    });

    const currentActiveId = clickedId ?? activeId;

    const editor = useEditor({
      extensions: [
        StarterKit,
        Underline,
        TextAlign.configure({ types: ["heading", "paragraph"] }),
        Highlight.configure({ multicolor: false }),
        TaskList,
        TaskItem.configure({ nested: true }),
        Link.configure({
          openOnClick: false,
          HTMLAttributes: {
            class: "text-primary underline underline-offset-2 cursor-pointer",
          },
        }),
        Placeholder.configure({ placeholder }),
        Table.configure({ resizable: true }),
        TableRow,
        TableHeader,
        TableCell,
        Markdown.configure({
          html: true,
          transformPastedText: true,
          transformCopiedText: false,
        }),
        MathInline,
        MathBlock,
        SlashCommand.configure({
          onActivate: (state: SlashCommandPluginState) => {
            const editorInstance = editorInstanceRef.current;
            if (!editorInstance) return;
            if (state.active) {
              const { view } = editorInstance;
              const { from } = view.state.selection;
              const coords = view.coordsAtPos(from);
              setSlashMenuPosition({
                top: coords.bottom + 8,
                left: coords.left,
              });
              setSlashMenuQuery(state.query);
              setSlashMenuVisible(true);
            } else {
              setSlashMenuVisible(false);
              setSlashMenuQuery("");
            }
          },
        }),
        AiHighlight,
        AiInsertion,
        AiDeletion,
        AiReview,
        AiFormat,
      ],
      content: initialContent,
      editorProps: {
        attributes: {
          class:
            "prose prose-foreground max-w-none focus:outline-none min-h-full pb-32 text-[15px] leading-7",
        },
        handlePaste: (view, event) => {
          const text = event.clipboardData?.getData("text/plain") ?? "";
          const html = event.clipboardData?.getData("text/html") ?? "";

          if (!shouldHandleMarkdownPaste({ text, html, shiftKey: false })) {
            return false;
          }

          const editorInstance = editorInstanceRef.current;
          const markdownStorage = (
            editorInstance?.storage as
              | {
                  markdown?: {
                    parser?: {
                      parse: (
                        content: string,
                        options?: { inline?: boolean },
                      ) => string;
                    };
                  };
                }
              | undefined
          )?.markdown as
            | {
                parser?: {
                  parse: (
                    content: string,
                    options?: { inline?: boolean },
                  ) => string;
                };
              }
            | undefined;
          const parser = markdownStorage?.parser;
          if (!parser) return false;

          event.preventDefault();

          const parsed = parser.parse(text, getMarkdownPasteParseMode(text));
          editorInstance?.chain().focus().insertContent(parsed).run();
          return true;
        },
      },
      onUpdate: ({ editor: e }) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const md = (e.storage as any).markdown.getMarkdown() as string;
        onChange(md);
        rebuildHeadings(e);
      },
      immediatelyRender: false,
    });

    useEffect(() => {
      editorInstanceRef.current = editor;
      onReady?.(editor);
    }, [editor, onReady]);

    const rebuildHeadings = useCallback((e: Editor) => {
      const headingNodes = extractHeadings(e);
      const seen = new Map<string, (typeof headingNodes)[0]>();
      for (const h of headingNodes) {
        if (!seen.has(h.id)) seen.set(h.id, h);
      }
      setHeadings(
        Array.from(seen.values()).map((h) => ({
          id: h.id,
          level: h.level,
          text: h.text,
          element: h.element,
        })),
      );
    }, []);

    useEffect(() => {
      if (editor) rebuildHeadings(editor);
    }, [editor, rebuildHeadings]);

    useEffect(() => {
      if (activeId && clickedId && activeId !== clickedId) {
        setClickedId(null);
      }
    }, [activeId, clickedId]);

    const scrollToSection = useCallback(
      (sectionId: string): boolean => {
        const container = scrollRef.current;
        if (!container || !editor) return false;

        setClickedId(sectionId);
        const editorDom = editor.view.dom;

        let targetEl = container.querySelector(`#${CSS.escape(sectionId)}`)!;
        if (!targetEl) {
          targetEl = editorDom.querySelector(`#${CSS.escape(sectionId)}`)!;
        }

        if (!targetEl) {
          const headingInList = headings.find((h) => h.id === sectionId);
          if (headingInList) {
            const storedEl = headingInList.element;
            if (storedEl && storedEl.offsetParent !== null) {
              targetEl = storedEl;
            } else {
              const allHeadings = editorDom.querySelectorAll(
                "h1, h2, h3, h4, h5, h6",
              );
              for (const h of allHeadings) {
                const htmlH = h as HTMLElement;
                if (
                  htmlH.id === sectionId ||
                  htmlH.textContent?.includes(headingInList.text.slice(0, 20))
                ) {
                  targetEl = htmlH;
                  break;
                }
              }
            }
          }
        }

        if (!targetEl) return false;
        if (!targetEl.id) targetEl.id = sectionId;
        targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        highlightSection(targetEl as HTMLElement, HIGHLIGHT_DURATION);
        return true;
      },
      [editor, headings],
    );

    const getHeadings = useCallback(() => headings, [headings]);

    const handleSectionClick = useCallback(
      (sectionId: string) => {
        scrollToSection(sectionId);
      },
      [scrollToSection],
    );

    useImperativeHandle(ref, () => ({
      getMarkdown: () => {
        if (!editor) return "";
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        return (editor.storage as any).markdown.getMarkdown() as string;
      },
      getSelectedText: () => {
        if (!editor) return "";
        const { from, to } = editor.state.selection;
        return editor.state.doc.textBetween(from, to, " ");
      },
      replaceSelection: (text: string) => {
        if (!editor) return;
        editor.chain().focus().deleteSelection().insertContent(text).run();
      },
      insertAtCursor: (text: string) => {
        if (!editor) return;
        const { from } = editor.state.selection;
        editor.chain().focus().setTextSelection(from).insertContent(text).run();
      },
      getCursorParagraph: () => {
        if (!editor) return "";
        const { $from } = editor.state.selection;
        for (let depth = $from.depth; depth > 0; depth--) {
          const node = $from.node(depth);
          if (node.isTextblock) {
            return node.textContent;
          }
        }
        return "";
      },
      highlightSelection: () => {
        if (!editor) return;
        const { from, to } = editor.state.selection;
        if (from === to) return;
        editor.view.dispatch(
          editor.state.tr.setMeta(aiHighlightKey, { from, to }),
        );
      },
      clearHighlight: () => {
        if (!editor) return;
        editor.view.dispatch(editor.state.tr.setMeta(aiHighlightKey, "clear"));
      },
      focus: () => {
        editor?.commands.focus();
      },
      getEditor: () => editor,
      scrollToSection,
      getHeadings,
      // ── AI Agent 协作编辑 API ──────────────────────────────────
      insertAtPosition: (pos, text, opts) => {
        if (!editor) return;
        const resolvedPos = Math.min(pos, editor.state.doc.content.size);
        editor
          .chain()
          .focus()
          .setTextSelection(resolvedPos)
          .insertContent(text)
          .run();
        // 如果指定了 mark，给刚插入的文字打上标记
        if (opts?.mark) {
          const insertedFrom = resolvedPos;
          const insertedTo = resolvedPos + text.length;
          editor
            .chain()
            .setTextSelection({ from: insertedFrom, to: insertedTo })
            .setMark(opts.mark, opts.attrs ?? {})
            .run();
        }
      },
      markRange: (from, to, markName, attrs) => {
        if (!editor) return;
        const docSize = editor.state.doc.content.size;
        const safeFrom = Math.max(0, Math.min(from, docSize));
        const safeTo = Math.max(0, Math.min(to, docSize));
        if (safeFrom === safeTo) return;
        editor
          .chain()
          .focus()
          .setTextSelection({ from: safeFrom, to: safeTo })
          .setMark(markName, attrs ?? {})
          .setTextSelection(safeTo) // 取消选中
          .run();
      },
      clearAllAIMarks: () => {
        if (!editor) return;
        const { state } = editor;
        const { doc } = state;
        const tr = state.tr;
        const marksToClear = [
          "aiInsertion",
          "aiDeletion",
          "aiReview",
          "aiFormat",
        ];
        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          const hasAIMark = node.marks.some((m) =>
            marksToClear.includes(m.type.name),
          );
          if (hasAIMark) {
            for (const mark of node.marks) {
              if (marksToClear.includes(mark.type.name)) {
                tr.removeMark(pos, pos + node.nodeSize, mark.type);
              }
            }
          }
        });
        editor.view.dispatch(tr);
      },
      acceptAllChanges: () => {
        if (!editor) return;
        const { state } = editor;
        const { doc } = state;
        const tr = state.tr;
        // Collect deletion ranges before modifying the doc
        const deletions: Array<{ from: number; to: number }> = [];
        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (mark.type.name === "aiDeletion") {
              deletions.push({ from: pos, to: pos + node.nodeSize });
            }
          }
        });

        // Clear all AI marks (accept = confirm changes), then delete marked text
        const allAITypes = new Set([
          "aiInsertion",
          "aiDeletion",
          "aiReview",
          "aiFormat",
        ]);
        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (allAITypes.has(mark.type.name)) {
              tr.removeMark(pos, pos + node.nodeSize, mark.type);
            }
          }
        });

        // 从后往前删除 deletion 文字，保持位置正确
        for (const { from, to } of deletions.sort((a, b) => b.from - a.from)) {
          tr.delete(from, to);
        }

        editor.view.dispatch(tr);
      },
      rejectAllChanges: () => {
        if (!editor) return;
        const { state } = editor;
        const { doc } = state;
        const tr = state.tr;

        const insertions: Array<{ from: number; to: number }> = [];

        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (mark.type.name === "aiInsertion") {
              insertions.push({ from: pos, to: pos + node.nodeSize });
            }
          }
        });

        // 清除所有 AI marks
        const allAITypes = new Set([
          "aiInsertion",
          "aiDeletion",
          "aiReview",
          "aiFormat",
        ]);
        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (allAITypes.has(mark.type.name)) {
              tr.removeMark(pos, pos + node.nodeSize, mark.type);
            }
          }
        });

        // 从后往前删除 insertion 文字
        for (const { from, to } of insertions.sort((a, b) => b.from - a.from)) {
          tr.delete(from, to);
        }

        editor.view.dispatch(tr);
      },
      acceptChange: (opId) => {
        if (!editor) return;
        const { state } = editor;
        const { doc } = state;
        const tr = state.tr;

        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (mark.attrs.opId === opId) {
              if (mark.type.name === "aiDeletion") {
                tr.delete(pos, pos + node.nodeSize);
              } else {
                tr.removeMark(pos, pos + node.nodeSize, mark.type);
              }
            }
          }
        });
        editor.view.dispatch(tr);
      },
      rejectChange: (opId) => {
        if (!editor) return;
        const { state } = editor;
        const { doc } = state;
        const tr = state.tr;

        doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (mark.attrs.opId === opId) {
              // aiInsertion = new text added by AI → delete on reject
              // aiFormat = existing text restyled by AI → just clear mark, keep text
              if (mark.type.name === "aiInsertion") {
                tr.delete(pos, pos + node.nodeSize);
              } else {
                tr.removeMark(pos, pos + node.nodeSize, mark.type);
              }
            }
          }
        });
        editor.view.dispatch(tr);
      },
      getReviewComments: () => {
        if (!editor) return [];
        const comments: Array<{
          opId: string;
          from: number;
          to: number;
          comment: string;
          severity: string;
          clauseRef: string;
        }> = [];
        editor.state.doc.descendants((node, pos) => {
          if (!node.isInline || !node.marks.length) return;
          for (const mark of node.marks) {
            if (mark.type.name === "aiReview") {
              comments.push({
                opId: mark.attrs.opId as string,
                from: pos,
                to: pos + node.nodeSize,
                comment: (mark.attrs.comment as string) || "",
                severity: (mark.attrs.severity as string) || "info",
                clauseRef: (mark.attrs.clauseRef as string) || "",
              });
            }
          }
        });
        return comments;
      },
      // EAI-CUSTOM: Replace editor content (sync after MCP tool writes file)
      setContent: (markdown: string) => {
        if (!editor) return;
        editor.commands.setContent(markdown);
      },
    }));

    const handleSlashCommand = useCallback(
      (item: { command: (editor: Editor) => void }) => {
        if (!editor) return;
        const pluginState = SlashCommandPluginKey.getState(editor.state) as
          | SlashCommandPluginState
          | undefined;
        // Delete the "/" and query text
        const tr = editor.state.tr.setMeta(
          SlashCommandPluginKey as Parameters<
            typeof editor.state.tr.setMeta
          >[0],
          {
            active: false,
            query: "",
            range: null,
          },
        );
        editor.view.dispatch(tr);

        const { state } = editor;
        if (pluginState?.range) {
          editor
            .chain()
            .focus()
            .deleteRange({
              from: pluginState.range.from,
              to: state.selection.from,
            })
            .run();
        }

        // Execute the command
        item.command(editor);
        setSlashMenuVisible(false);
        setSlashMenuQuery("");
      },
      [editor],
    );

    return (
      <div
        className={cn(
          "bg-background relative flex h-full overflow-hidden",
          className,
        )}
      >
        {headings.length > 0 && (
          <div className="border-border bg-muted/50 hidden w-48 shrink-0 flex-col border-r lg:flex">
            <div className="shrink-0 px-3 pt-4">
              <p className="text-muted-foreground mb-3 text-[11px] font-semibold tracking-wider uppercase">
                目录
              </p>
            </div>
            <div className="scrollbar-hide flex-1 overflow-y-auto px-3">
              <div className="pb-4">
                <TableOfContents
                  headings={headings}
                  activeId={currentActiveId}
                  onSectionClick={handleSectionClick}
                />
              </div>
            </div>
          </div>
        )}
        <div
          ref={scrollRef}
          className="scrollbar-hide relative flex-1 overflow-y-auto"
        >
          <div
            className="relative mx-auto px-8 pt-10 pb-32"
            style={{ maxWidth: 780 }}
          >
            <EditorDragHandle editor={editor} scrollContainerRef={scrollRef} />
            <EditorContent editor={editor} />
          </div>
        </div>
        <div className="pointer-events-none absolute bottom-6 left-1/2 z-10 -translate-x-1/2">
          <div className="pointer-events-auto">
            <EditorToolbar editor={editor} />
          </div>
        </div>
        <SlashMenu
          editor={editor}
          visible={slashMenuVisible}
          position={slashMenuPosition}
          query={slashMenuQuery}
          onClose={() => {
            setSlashMenuVisible(false);
            setSlashMenuQuery("");
          }}
          onCommand={handleSlashCommand}
        />
      </div>
    );
  },
);

TiptapEditor.displayName = "TiptapEditor";
export default TiptapEditor;
