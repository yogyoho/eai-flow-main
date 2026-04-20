"use client";

import Highlight from "@tiptap/extension-highlight";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold, Italic, Underline as UnderlineIcon, Strikethrough,
  Heading1, Heading2, Heading3,
  List, ListOrdered, ListChecks,
  AlignLeft, AlignCenter, AlignRight,
  Quote, Code, Minus, Undo2, Redo2,
  Highlighter, Link2,
} from "lucide-react";
import React, { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import { Markdown } from "tiptap-markdown";

import { cn } from "@/lib/utils";
import { extractHeadings } from "./utils/headingIdManager";
import { highlightSection } from "./utils/sectionHighlighter";
import { useScrollSpy } from "./hooks/useScrollSpy";

export interface TiptapEditorRef {
  getMarkdown: () => string;
  getSelectedText: () => string;
  replaceSelection: (text: string) => void;
  focus: () => void;
  getEditor: () => Editor | null;
  scrollToSection: (sectionId: string) => boolean;
  getHeadings: () => HeadingItem[];
}

interface TiptapEditorProps {
  initialContent: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
  className?: string;
  onReady?: (editor: import("@tiptap/react").Editor | null) => void;
}

interface HeadingItem {
  id: string;
  level: number;
  text: string;
  element: HTMLElement;
}

const SCROLL_OFFSET_TOP = 80;
const HIGHLIGHT_DURATION = 2000;

function TBtn({ onClick, active, disabled, title, children }: {
  onClick: () => void; active?: boolean; disabled?: boolean;
  title: string; children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      className={cn(
        "p-1.5 rounded-md transition-colors",
        active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground hover:bg-muted",
        disabled && "opacity-30 cursor-not-allowed"
      )}
    >
      {children}
    </button>
  );
}

function TDivider() {
  return <div className="w-px h-4 bg-border mx-0.5 shrink-0" />;
}

export function EditorToolbar({ editor }: { editor: Editor | null }) {
  if (!editor) return null;

  const setLink = () => {
    const prev = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt("输入链接地址", prev ?? "https://");
    if (url === null) return;
    if (url === "") { editor.chain().focus().extendMarkRange("link").unsetLink().run(); return; }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };

  return (
    <div className="flex items-center flex-wrap gap-0.5 px-3 py-2 bg-background/95 backdrop-blur-sm border border-border rounded-xl shadow-lg">
      <TBtn title="撤销 (Ctrl+Z)" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()}>
        <Undo2 className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="重做 (Ctrl+Y)" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()}>
        <Redo2 className="w-3.5 h-3.5" />
      </TBtn>
      <TDivider />
      <TBtn title="标题 1" active={editor.isActive("heading", { level: 1 })} onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}>
        <Heading1 className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="标题 2" active={editor.isActive("heading", { level: 2 })} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>
        <Heading2 className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="标题 3" active={editor.isActive("heading", { level: 3 })} onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}>
        <Heading3 className="w-3.5 h-3.5" />
      </TBtn>
      <TDivider />
      <TBtn title="加粗 (Ctrl+B)" active={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
        <Bold className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="斜体 (Ctrl+I)" active={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
        <Italic className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="下划线 (Ctrl+U)" active={editor.isActive("underline")} onClick={() => editor.chain().focus().toggleUnderline().run()}>
        <UnderlineIcon className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="删除线" active={editor.isActive("strike")} onClick={() => editor.chain().focus().toggleStrike().run()}>
        <Strikethrough className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="高亮" active={editor.isActive("highlight")} onClick={() => editor.chain().focus().toggleHighlight().run()}>
        <Highlighter className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="行内代码" active={editor.isActive("code")} onClick={() => editor.chain().focus().toggleCode().run()}>
        <Code className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="链接" active={editor.isActive("link")} onClick={setLink}>
        <Link2 className="w-3.5 h-3.5" />
      </TBtn>
      <TDivider />
      <TBtn title="无序列表" active={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
        <List className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="有序列表" active={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        <ListOrdered className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="任务列表" active={editor.isActive("taskList")} onClick={() => editor.chain().focus().toggleTaskList().run()}>
        <ListChecks className="w-3.5 h-3.5" />
      </TBtn>
      <TDivider />
      <TBtn title="左对齐" active={editor.isActive({ textAlign: "left" })} onClick={() => editor.chain().focus().setTextAlign("left").run()}>
        <AlignLeft className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="居中" active={editor.isActive({ textAlign: "center" })} onClick={() => editor.chain().focus().setTextAlign("center").run()}>
        <AlignCenter className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="右对齐" active={editor.isActive({ textAlign: "right" })} onClick={() => editor.chain().focus().setTextAlign("right").run()}>
        <AlignRight className="w-3.5 h-3.5" />
      </TBtn>
      <TDivider />
      <TBtn title="引用块" active={editor.isActive("blockquote")} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
        <Quote className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="代码块" active={editor.isActive("codeBlock")} onClick={() => editor.chain().focus().toggleCodeBlock().run()}>
        <Code className="w-3.5 h-3.5" />
      </TBtn>
      <TBtn title="分割线" onClick={() => editor.chain().focus().setHorizontalRule().run()}>
        <Minus className="w-3.5 h-3.5" />
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
        <div key={h.id} className="relative group">
          <div
            className={cn(
              "absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-full transition-all duration-200",
              activeId === h.id ? "opacity-100" : "opacity-0 group-hover:opacity-30"
            )}
          />
          <button
            onClick={() => onSectionClick(h.id)}
            title={h.text}
            className={cn(
              "w-full text-left leading-snug py-1 pl-3 pr-2 rounded-r transition-colors text-[13px]",
              h.level === 2 && "pl-5",
              h.level === 3 && "pl-7",
              activeId === h.id
                ? "text-primary font-medium bg-primary/10"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
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
  ({ initialContent, onChange, placeholder = "开始输入内容...", className, onReady }, ref) => {
    const scrollRef = useRef<HTMLDivElement>(null);
    const [headings, setHeadings] = useState<HeadingItem[]>([]);
    const [clickedId, setClickedId] = useState<string | null>(null);

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
          HTMLAttributes: { class: "text-primary underline underline-offset-2 cursor-pointer" },
        }),
        Placeholder.configure({ placeholder }),
        Markdown.configure({ html: true, transformPastedText: true, transformCopiedText: false }),
      ],
      content: initialContent,
      editorProps: {
        attributes: {
          class: "prose prose-foreground max-w-none focus:outline-none min-h-full pb-32 text-[15px] leading-7",
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
      onReady?.(editor);
    }, [editor, onReady]);

    const rebuildHeadings = useCallback((e: Editor) => {
      const headingNodes = extractHeadings(e);
      const seen = new Map<string, typeof headingNodes[0]>();
      for (const h of headingNodes) {
        if (!seen.has(h.id)) seen.set(h.id, h);
      }
      setHeadings(Array.from(seen.values()).map((h) => ({
        id: h.id,
        level: h.level,
        text: h.text,
        element: h.element,
      })));
    }, []);

    useEffect(() => {
      if (editor) rebuildHeadings(editor);
    }, [editor, rebuildHeadings]);

    useEffect(() => {
      if (activeId && clickedId && activeId !== clickedId) {
        setClickedId(null);
      }
    }, [activeId, clickedId]);

    const scrollToSection = useCallback((sectionId: string): boolean => {
      const container = scrollRef.current;
      if (!container || !editor) return false;

      setClickedId(sectionId);
      const editorDom = editor.view.dom;

      let targetEl = container.querySelector(`#${CSS.escape(sectionId)}`) as HTMLElement;
      if (!targetEl) {
        targetEl = editorDom.querySelector(`#${CSS.escape(sectionId)}`) as HTMLElement;
      }

      if (!targetEl) {
        const headingInList = headings.find((h) => h.id === sectionId);
        if (headingInList) {
          const storedEl = headingInList.element;
          if (storedEl && storedEl.offsetParent !== null) {
            targetEl = storedEl;
          } else {
            const allHeadings = editorDom.querySelectorAll("h1, h2, h3, h4, h5, h6");
            for (const h of allHeadings) {
              const htmlH = h as HTMLElement;
              if (htmlH.id === sectionId || htmlH.textContent?.includes(headingInList.text.slice(0, 20))) {
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
      highlightSection(targetEl, HIGHLIGHT_DURATION);
      return true;
    }, [editor, headings]);

    const getHeadings = useCallback(() => headings, [headings]);

    const handleSectionClick = useCallback((sectionId: string) => {
      scrollToSection(sectionId);
    }, [scrollToSection]);

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
        editor.chain().focus().insertContent(text).run();
      },
      focus: () => { editor?.commands.focus(); },
      getEditor: () => editor,
      scrollToSection,
      getHeadings,
    }));

    return (
      <div className={cn("flex h-full overflow-hidden bg-background relative", className)}>
        {headings.length > 0 && (
          <div className="hidden lg:flex w-48 shrink-0 flex-col border-r border-border bg-muted/50">
            <div className="shrink-0 pt-4 px-3">
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-3">目录</p>
            </div>
            <div className="flex-1 overflow-y-auto scrollbar-hide px-3">
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
          className="flex-1 overflow-y-auto scrollbar-hide relative"
        >
          <div className="mx-auto px-8 pt-10 pb-32" style={{ maxWidth: 780 }}>
            <EditorContent editor={editor} />
          </div>
        </div>
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <div className="pointer-events-auto">
            <EditorToolbar editor={editor} />
          </div>
        </div>
      </div>
    );
  }
);

TiptapEditor.displayName = "TiptapEditor";
export default TiptapEditor;
