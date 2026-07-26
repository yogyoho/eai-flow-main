import { Mark } from "@tiptap/core";

/**
 * AI 格式调整标记 — 蓝色下划线（轻微提示）。
 * 接受时移除 mark，拒绝时移除 mark 并撤销格式变更。
 */
export const AiFormat = Mark.create({
  name: "aiFormat",

  addAttributes() {
    return {
      opId: { default: null },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-ai-format]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      {
        "data-ai-format": "",
        "data-op-id": HTMLAttributes.opId,
        class: "ai-format",
        style:
          "text-decoration: underline; text-decoration-color: #3b82f6; text-underline-offset: 3px;",
      },
      0,
    ];
  },
});
