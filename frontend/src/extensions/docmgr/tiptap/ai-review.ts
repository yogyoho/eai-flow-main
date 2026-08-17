import { Mark } from "@tiptap/core";

/**
 * AI 审核批注标记 — 橙色波浪虚线。
 * 属性: comment (审核意见), severity (info|warning|error), clauseRef (规程条款引用)。
 * 点击 → 前端通过 data 属性 + document click 事件弹出 Popover 显示详情。
 */
export const AiReview = Mark.create({
  name: "aiReview",

  addAttributes() {
    return {
      opId: { default: null },
      /** 审核意见 */
      comment: { default: "" },
      /** info | warning | error */
      severity: { default: "info" },
      /** 规程条款引用，如 "煤矿安全规程第135条" */
      clauseRef: { default: "" },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-ai-review]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const severity = HTMLAttributes.severity ?? "info";
    // 空字符串/缺省时回退默认文案（等价于原 `comment || "查看审核意见"`，避免 ?? 改变空串行为）
    const comment = HTMLAttributes.comment;
    const commentTitle =
      comment !== "" && comment !== null && comment !== undefined
        ? comment
        : "查看审核意见";
    const severityColor =
      severity === "error"
        ? "#ef4444"
        : severity === "warning"
          ? "#f59e0b"
          : "#3b82f6";
    return [
      "span",
      {
        "data-ai-review": "",
        "data-op-id": HTMLAttributes.opId,
        "data-comment": HTMLAttributes.comment,
        "data-severity": severity,
        "data-clause-ref": HTMLAttributes.clauseRef,
        class: `ai-review severity-${severity}`,
        style: `text-decoration: underline; text-decoration-style: wavy; text-decoration-color: ${severityColor}; text-underline-offset: 4px; cursor: pointer;`,
        title: commentTitle,
      },
      0,
    ];
  },
});
