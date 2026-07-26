import { Mark } from "@tiptap/core";

/**
 * AI 新增文字标记 — 绿色下划线。
 * 接受时移除 mark，拒绝时删除标记文字。
 */
export const AiInsertion = Mark.create({
  name: "aiInsertion",

  addAttributes() {
    return {
      /** 操作 ID，用于逐条接受/拒绝 */
      opId: { default: null },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-ai-insertion]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      {
        "data-ai-insertion": "",
        "data-op-id": HTMLAttributes.opId,
        class: "ai-insertion",
        style:
          "text-decoration: underline; text-decoration-color: #22c55e; text-underline-offset: 3px;",
      },
      0,
    ];
  },
});
