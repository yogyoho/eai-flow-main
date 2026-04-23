const BLOCK_MARKDOWN_PATTERNS = [
  /^#{1,6}\s+/m,
  /^\s*[-*+]\s+/m,
  /^\s*\d+\.\s+/m,
  /^\s*>\s+/m,
  /^\s*```/m,
  /^\s*---+\s*$/m,
  /^\|.+\|\s*$/m,
];

const INLINE_MARKDOWN_PATTERNS = [
  /\*\*[^*\n]+\*\*/,
  /__[^_\n]+__/,
  /`[^`\n]+`/,
  /\[[^\]]+\]\([^)]+\)/,
  /!\[[^\]]*\]\([^)]+\)/,
  /\*[^*\n]+\*/,
  /_[^_\n]+_/,
  /~~[^~\n]+~~/,
];

const STRUCTURED_HTML_TAG_PATTERN =
  /<(h[1-6]|p|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|pre|code|hr|img|a)\b/i;

export function isLikelyMarkdown(text: string): boolean {
  if (!text.trim()) return false;

  return [...BLOCK_MARKDOWN_PATTERNS, ...INLINE_MARKDOWN_PATTERNS].some((pattern) =>
    pattern.test(text)
  );
}

export function hasStructuredHtml(html: string): boolean {
  if (!html.trim()) return false;
  return STRUCTURED_HTML_TAG_PATTERN.test(html);
}

export function shouldHandleMarkdownPaste(params: {
  text: string;
  html: string;
  shiftKey: boolean;
}): boolean {
  const { text, html, shiftKey } = params;

  if (shiftKey) return false;
  if (!text.trim()) return false;
  if (hasStructuredHtml(html)) return false;

  return isLikelyMarkdown(text);
}

export function getMarkdownPasteParseMode(text: string): { inline: boolean } {
  const hasBlockMarkdown = BLOCK_MARKDOWN_PATTERNS.some((pattern) => pattern.test(text));
  return { inline: !hasBlockMarkdown };
}
