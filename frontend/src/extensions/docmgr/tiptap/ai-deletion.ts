import { Mark } from "@tiptap/core";

/**
 * AI 标记删除文字 — 红色删除线 + 变灰。
 * 接受时真删除文字，拒绝时移除 mark 恢复。
 */
export const AiDeletion = Mark.create({
  name: "aiDeletion",

  addAttributes() {
    return {
      opId: { default: null },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-ai-deletion]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      {
        "data-ai-deletion": "",
        "data-op-id": HTMLAttributes.opId,
        class: "ai-deletion",
        style:
          "text-decoration: line-through; text-decoration-color: #ef4444; color: #9ca3af;",
      },
      0,
    ];
  },
});
