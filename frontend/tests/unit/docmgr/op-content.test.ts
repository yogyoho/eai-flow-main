import { describe, expect, test } from "@rstest/core";

import { parseOperationContent } from "@/extensions/docmgr/PersonalBlockNoteEditor";

describe("parseOperationContent（op.content 统一走 details+math 管线）", () => {
  test("$$ 独立公式被转成 equation 块（不再裸 parse 成文本段）", () => {
    // stub 模拟真实 tryParse：按 \n\n 分段各成 paragraph（与真实 markdown 解析一致，
    // 亦同本文件测试 2 的 stub）。transformMathInBlocks 的 equation 识别锚定单块全文。
    const blocks = parseOperationContent(
      "前文。\n\n$$\nE = mc^2\n$$",
      (md) =>
        md.split("\n\n").map((t, i) => ({
          id: `raw${i}`,
          type: "paragraph",
          content: [{ type: "text", text: t }],
        })),
    ) as Array<{ type: string }>;
    expect(blocks.some((b) => b.type === "equation")).toBe(true);
  });

  test("无公式内容原样通过管线（块数不丢）", () => {
    const blocks = parseOperationContent("a\n\nb", (md) =>
      md.split("\n\n").map((t, i) => ({
        id: `b${i}`,
        type: "paragraph",
        content: [{ type: "text", text: t }],
      })),
    ) as Array<{ type: string }>;
    expect(blocks.length).toBe(2);
    expect(blocks.every((b) => b.type === "paragraph")).toBe(true);
  });

  test("details 切分走 buildBlocksWithDetails（<details> 区域被识别）", () => {
    const seen: string[] = [];
    const blocks = parseOperationContent(
      "前文。\n\n<details>\n<summary>s</summary>\n\n内容\n\n</details>",
      (md) => {
        seen.push(md);
        return [
          { id: "raw", type: "paragraph", content: [{ type: "text", text: md }] },
        ];
      },
    ) as Array<{ type: string }>;
    // detailsMarkdown 既有行为：<details> 区域不整段交给 tryParse——
    // 生成 detailsBlock 节点（collapsed 默认 true），仅把内部 markdown 递归交给 tryParse
    expect(seen.some((md) => md.includes("内容"))).toBe(true);
    expect(seen.every((md) => !md.includes("<details>"))).toBe(true);
    expect(blocks.some((b) => b.type === "detailsBlock")).toBe(true);
  });
});
