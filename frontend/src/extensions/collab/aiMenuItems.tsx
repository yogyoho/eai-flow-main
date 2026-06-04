"use client";

import type { BlockNoteEditor } from "@blocknote/core";
import { AIExtension } from "@blocknote/xl-ai";
import type { AIMenuSuggestionItem } from "@blocknote/xl-ai";
import { Check, X, RefreshCw, Sparkles, FileText, Scissors, ArrowRight, Lightbulb, List } from "lucide-react";

/**
 * @function 根据编辑器的当前状态返回相应的 AI 菜单项列表，用于协作编辑中的 AI 辅助功能
 * @description 根据BlockNote编辑器实例和当前AI操作状态，返回适合的菜单项列表。当用户正在审核AI生成的文本时，提供接受和撤销选项；
 *               当发生错误时，提供重试和取消选项；当用户输入文本等待AI处理时，根据是否有选中文本提供不同的AI操作选项，
 *               如润色、扩写、精简、续写等。其他状态下不提供菜单项。
 * @param editor BlockNote编辑器实例
 * @param status 当前 AI 操作状态，包括：
 * - user-input: 用户输入文本，等待 AI 处理
 * - thinking: AI 正在思考中，用户不能进行其他操作
 * - ai-writing: AI 正在生成文本，用户不能进行其他操作
 * - error: 发生错误，用户可以重试或取消操作
 * - user-reviewing: 用户正在审核 AI 生成的文本
 * - closed: 操作已关闭，用户不能进行其他操作
 * @returns AIMenuSuggestionItem - AI 菜单项数组，根据不同状态返回不同的菜单选项
 * @logic
 * - 如果状态是 user-reviewing，显示"替换"和"撤销"选项，用于接受或拒绝 AI 生成的修改
 * - 如果状态是 error，显示"重试"和"取消"选项，用于重新尝试或取消操作
 * - 如果状态是 user-input，根据是否有选中文本显示不同的 AI 功能菜单
 *    - 有选中文本时：润色、扩写、精简、续写
 *    - 无选中文本时：续写、头脑风暴、生成大纲
 * - 其他状态，返回空数组，不提供菜单项 
 */
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
        icon: <Check size={16} />,
        onItemClick: () => {
          ai.acceptChanges();
        },
      },
      {
        key: "revert",
        title: "撤销",
        icon: <X size={16} />,
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
        icon: <RefreshCw size={16} />,
        onItemClick: async () => {
          await ai.retry();
        },
      },
      {
        key: "cancel",
        title: "取消",
        icon: <X size={16} />,
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
        icon: <Sparkles size={16} />,
        subtext: "优化文本表达，使其更加流畅专业",
        onItemClick: (setPrompt) => setPrompt("润色选中文本，使其更加流畅、专业，保持原意不变。只输出润色后的文本。"),
      },
      {
        key: "ai-expand",
        title: "扩写",
        icon: <FileText size={16} />,
        subtext: "增加更多细节和论据，丰富内容",
        onItemClick: (setPrompt) => setPrompt("扩写选中文本，增加更多细节、论据或说明，使内容更加丰富详实。只输出扩写后的文本。"),
      },
      {
        key: "ai-condense",
        title: "精简",
        icon: <Scissors size={16} />,
        subtext: "去除冗余，保留核心信息",
        onItemClick: (setPrompt) => setPrompt("精简选中文本，去除冗余内容，保留核心信息，使表达更加简洁有力。只输出精简后的文本。"),
      },
      {
        key: "ai-continue-selection",
        title: "续写",
        icon: <ArrowRight size={16} />,
        subtext: "基于当前内容继续撰写",
        onItemClick: (setPrompt) => setPrompt("基于选中文本内容继续撰写，保持风格和主题一致。只输出续写的部分。"),
      },
    );
  } else {
    items.push(
      {
        key: "ai-continue",
        title: "续写",
        icon: <ArrowRight size={16} />,
        subtext: "基于当前上下文继续撰写",
        onItemClick: (setPrompt) => setPrompt("基于当前光标位置的上下文内容继续撰写。只输出续写的部分。"),
      },
      {
        key: "ai-brainstorm",
        title: "头脑风暴",
        icon: <Lightbulb size={16} />,
        subtext: "生成相关思路和角度",
        onItemClick: (setPrompt) => setPrompt("基于当前文档内容进行头脑风暴，提供3-5个相关的扩展思路或角度，每条思路用「- 」开头。只输出思路列表。"),
      },
      {
        key: "ai-outline",
        title: "生成大纲",
        icon: <List size={16} />,
        subtext: "根据上下文生成大纲结构",
        onItemClick: (setPrompt) => setPrompt("根据当前文档的上下文，生成一个合适的大纲结构。使用 Markdown 标题格式。"),
      },
    );
  }

  return items;
}