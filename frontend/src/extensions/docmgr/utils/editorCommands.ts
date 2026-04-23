import type { Editor } from "@tiptap/react";

export interface CommandItem {
  title: string;
  description: string;
  icon: string;
  command: (editor: Editor) => void;
}

export interface CommandGroup {
  title: string;
  items: CommandItem[];
}

export const editorCommands: CommandGroup[] = [
  {
    title: "基础块",
    items: [
      {
        title: "文本",
        description: "普通文本段落",
        icon: "T",
        command: (editor) =>
          editor.chain().focus().setParagraph().run(),
      },
      {
        title: "标题 1",
        description: "大标题",
        icon: "H1",
        command: (editor) =>
          editor.chain().focus().toggleHeading({ level: 1 }).run(),
      },
      {
        title: "标题 2",
        description: "中标题",
        icon: "H2",
        command: (editor) =>
          editor.chain().focus().toggleHeading({ level: 2 }).run(),
      },
      {
        title: "标题 3",
        description: "小标题",
        icon: "H3",
        command: (editor) =>
          editor.chain().focus().toggleHeading({ level: 3 }).run(),
      },
    ],
  },
  {
    title: "列表",
    items: [
      {
        title: "无序列表",
        description: "项目符号列表",
        icon: "•",
        command: (editor) =>
          editor.chain().focus().toggleBulletList().run(),
      },
      {
        title: "有序列表",
        description: "数字编号列表",
        icon: "1.",
        command: (editor) =>
          editor.chain().focus().toggleOrderedList().run(),
      },
      {
        title: "任务列表",
        description: "带复选框的任务",
        icon: "☑",
        command: (editor) =>
          editor.chain().focus().toggleTaskList().run(),
      },
    ],
  },
  {
    title: "高级",
    items: [
      {
        title: "引用块",
        description: "引用文本",
        icon: '"',
        command: (editor) =>
          editor.chain().focus().toggleBlockquote().run(),
      },
      {
        title: "代码块",
        description: "格式化代码",
        icon: "</>",
        command: (editor) =>
          editor.chain().focus().toggleCodeBlock().run(),
      },
      {
        title: "分割线",
        description: "水平分隔线",
        icon: "—",
        command: (editor) =>
          editor.chain().focus().setHorizontalRule().run(),
      },
      {
        title: "表格",
        description: "插入表格",
        icon: "⊞",
        command: (editor) =>
          editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
      },
    ],
  },
  {
    title: "媒体",
    items: [
      {
        title: "链接",
        description: "插入超链接",
        icon: "🔗",
        command: (editor) => {
          const url = window.prompt("输入链接地址");
          if (url) {
            editor.chain().focus().setLink({ href: url }).run();
          }
        },
      },
    ],
  },
];

export function normalizeSlashQuery(query: string): string {
  return query.replace(/^\//, "").trimStart();
}

export function filterCommands(query: string): CommandItem[] {
  const normalizedQuery = normalizeSlashQuery(query);

  if (!normalizedQuery) {
    return editorCommands.flatMap((group) => group.items);
  }

  const lower = normalizedQuery.toLowerCase();
  return editorCommands
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) =>
          item.title.toLowerCase().includes(lower) ||
          item.description.toLowerCase().includes(lower)
      ),
    }))
    .filter((group) => group.items.length > 0)
    .flatMap((group) => group.items);
}
