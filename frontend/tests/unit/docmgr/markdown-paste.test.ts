import { expect, test } from "vitest";

import {
  getMarkdownPasteParseMode,
  hasStructuredHtml,
  isLikelyMarkdown,
  shouldHandleMarkdownPaste,
} from "@/extensions/docmgr/utils/markdownPaste";

test("isLikelyMarkdown detects common block markdown", () => {
  expect(isLikelyMarkdown("# Title\n\n- item")).toBe(true);
  expect(isLikelyMarkdown("```ts\nconst a = 1\n```")).toBe(true);
});

test("isLikelyMarkdown detects common inline markdown", () => {
  expect(isLikelyMarkdown("This is **bold** text")).toBe(true);
  expect(isLikelyMarkdown("[OpenAI](https://openai.com)")).toBe(true);
});

test("hasStructuredHtml detects actual rich text blocks", () => {
  expect(hasStructuredHtml("<h3>Title</h3><ul><li>Item</li></ul>")).toBe(true);
  expect(hasStructuredHtml('<meta charset="utf-8"><span>### Title</span>')).toBe(false);
});

test("shouldHandleMarkdownPaste intercepts markdown even when clipboard has non-structured html", () => {
  expect(
    shouldHandleMarkdownPaste({
      text: "# Title",
      html: "",
      shiftKey: false,
    })
  ).toBe(true);

  expect(
    shouldHandleMarkdownPaste({
      text: "# Title",
      html: '<meta charset="utf-8"><span># Title</span>',
      shiftKey: false,
    })
  ).toBe(true);

  expect(
    shouldHandleMarkdownPaste({
      text: "# Title",
      html: "<h1>Title</h1>",
      shiftKey: false,
    })
  ).toBe(false);

  expect(
    shouldHandleMarkdownPaste({
      text: "# Title",
      html: "",
      shiftKey: true,
    })
  ).toBe(false);
});

test("getMarkdownPasteParseMode uses block mode for multiline structures", () => {
  expect(getMarkdownPasteParseMode("# Title\n\n- item")).toEqual({ inline: false });
  expect(getMarkdownPasteParseMode("This is **bold** text")).toEqual({ inline: true });
});
