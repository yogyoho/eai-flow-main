import { useMemo } from "react";
import type { ComponentProps } from "react";
import { type Streamdown } from "streamdown";

import {
  capMarkdownNesting,
  normalizeStreamdownMathMarkdown,
} from "./preprocess";

type StreamdownChildren = ComponentProps<typeof Streamdown>["children"];

export function getSafeStreamdownMarkdown(markdown: string): string {
  return normalizeStreamdownMathMarkdown(capMarkdownNesting(markdown));
}

export function getSafeStreamdownChildren(
  children: StreamdownChildren,
): StreamdownChildren {
  if (typeof children !== "string") {
    return children;
  }

  return getSafeStreamdownMarkdown(children);
}

// ponytail: enabled=false 时跳过 O(content) preprocess(capMarkdownNesting +
// normalizeStreamdownMathMarkdown→compactDisplayMathBlocks+normalizeLatexMathDelimiters)。
// 这些是 7月16 upstream sync(commit 3a54b68b)引入, 每 token 跑 4 个全文扫描是
// 流式卡顿根因(bug-174)。流式期用 raw children, 最终渲染(isLoading=false)跑完整
// preprocess 保证 LaTeX/表格/深嵌套正确。
export function useSafeStreamdownChildren(
  children: StreamdownChildren,
  enabled = true,
): StreamdownChildren {
  return useMemo(
    () => (enabled ? getSafeStreamdownChildren(children) : children),
    [children, enabled],
  );
}

export function useSafeStreamdownMarkdown(
  markdown: string,
  enabled = true,
): string {
  return useMemo(
    () => (enabled ? getSafeStreamdownMarkdown(markdown) : markdown),
    [markdown, enabled],
  );
}
