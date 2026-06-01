"use client";

import type { BlockNoteEditor } from "@blocknote/core";
import { AIExtension } from "@blocknote/xl-ai";
import type { AIMenuSuggestionItem } from "@blocknote/xl-ai";

export function getCollabAIMenuItems(
  editor: BlockNoteEditor,
  status: "user-input" | "thinking" | "ai-writing" | "error" | "user-reviewing" | "closed",
): AIMenuSuggestionItem[] {
  const ai = editor.getExtension(AIExtension);
  if (!ai) return [];

  if (status === "user-reviewing") {
    return [
      {
        key: "accept",
        title: "替换",
        icon: <>✓</>,
        onItemClick: () => {
          ai.acceptChanges();
        },
      },
      {
        key: "revert",
        title: "撤销",
        icon: <>↩</>,
        onItemClick: () => {
          ai.rejectChanges();
        },
      },
    ];
  }

  if (status === "error") {
    return [
      {
        key: "retry",
        title: "重试",
        icon: <>🔄</>,
        onItemClick: async () => {
          await ai.retry();
        },
      },
      {
        key: "cancel",
        title: "取消",
        icon: <>↩</>,
        onItemClick: () => {
          ai.rejectChanges();
        },
      },
    ];
  }

  if (status !== "user-input") return [];

  const hasSelection = !!editor.getSelection();
  const items: AIMenuSuggestionItem[] = [];

  if (hasSelection) {
    items.push(
      {
        key: "ai-polish",
        title: "润色",
        icon: <>✨</>,
        subtext: "优化文本表达，使其更加流畅专业",
        onItemClick: (setPrompt) => setPrompt("润色选中文本，使其更加流畅、专业，保持原意不变。只输出润色后的文本。"),
      },
      {
        key: "ai-expand",
        title: "扩写",
        icon: <>📝</>,
        subtext: "增加更多细节和论据，丰富内容",
        onItemClick: (setPrompt) => setPrompt("扩写选中文本，增加更多细节、论据或说明，使内容更加丰富详实。只输出扩写后的文本。"),
      },
      {
        key: "ai-condense",
        title: "精简",
        icon: <>✂️</>,
        subtext: "去除冗余，保留核心信息",
        onItemClick: (setPrompt) => setPrompt("精简选中文本，去除冗余内容，保留核心信息，使表达更加简洁有力。只输出精简后的文本。"),
      },
      {
        key: "ai-continue-selection",
        title: "续写",
        icon: <>➡️</>,
        subtext: "基于当前内容继续撰写",
        onItemClick: (setPrompt) => setPrompt("基于选中文本内容继续撰写，保持风格和主题一致。只输出续写的部分。"),
      },
    );
  } else {
    items.push(
      {
        key: "ai-continue",
        title: "续写",
        icon: <>➡️</>,
        subtext: "基于当前上下文继续撰写",
        onItemClick: (setPrompt) => setPrompt("基于当前光标位置的上下文内容继续撰写。只输出续写的部分。"),
      },
      {
        key: "ai-brainstorm",
        title: "头脑风暴",
        icon: <>💡</>,
        subtext: "生成相关思路和角度",
        onItemClick: (setPrompt) => setPrompt("基于当前文档内容进行头脑风暴，提供3-5个相关的扩展思路或角度，每条思路用「- 」开头。只输出思路列表。"),
      },
      {
        key: "ai-outline",
        title: "生成大纲",
        icon: <>📋</>,
        subtext: "根据上下文生成大纲结构",
        onItemClick: (setPrompt) => setPrompt("根据当前文档的上下文，生成一个合适的大纲结构。使用 Markdown 标题格式。"),
      },
    );
  }

  return items;
}
