import { expect, test } from "@rstest/core";

import {
  buildBlocksWithDetails,
  extractDetailsSegments,
  serializeWithDetails,
} from "@/extensions/docmgr/utils/detailsMarkdown";

const CALC_MD = `## 6 循环水装置工艺计算

* 计算过程
  * 公式：$Q_{e} = Q \\times KZF$`;

test("extractDetailsSegments: 无 details 时原样单段返回", () => {
  const segs = extractDetailsSegments(CALC_MD);
  expect(segs).toHaveLength(1);
  expect(segs[0]!.kind).toBe("md");
  expect(segs[0]!.text).toContain("循环水装置工艺计算");
});

test("extractDetailsSegments: details+summary+inner 正确切分", () => {
  const md = "前文\n<details><summary>计算过程</summary>\n* 公式：$Q$\n</details>\n后文";
  const segs = extractDetailsSegments(md);
  expect(segs.map((s) => s.kind)).toEqual(["md", "details", "md"]);
  expect(segs[1]!.summary).toBe("计算过程");
  expect(segs[1]!.inner).toBe("* 公式：$Q$");
  expect(segs[0]!.text).toContain("前文");
  expect(segs[2]!.text).toContain("后文");
});

test("extractDetailsSegments: 多个 details 与带属性的标签", () => {
  const md =
    "<details open><summary>A</summary>A内</details>中<details><summary>B</summary>B内</details>";
  const segs = extractDetailsSegments(md);
  expect(segs.filter((s) => s.kind === "details")).toHaveLength(2);
  expect(segs[0]!.summary).toBe("A");
  expect(segs[2]!.summary).toBe("B");
  expect(segs[1]!.text).toBe("中");
});

test("buildBlocksWithDetails: 生成 detailsBlock 节点（summary/children/嵌套 parse）", () => {
  // stub parse：把 markdown 文本包成单个 paragraph 块
  const parse = (md: string) => [
    {
      type: "paragraph",
      content: [{ type: "text", text: md.trim(), styles: {} }],
    },
  ];
  const md = "前文\n<details><summary>计算过程</summary>\n* 公式：$Q$\n</details>";
  const blocks = buildBlocksWithDetails(md, parse);
  expect(blocks).toHaveLength(2);
  expect(blocks[0]!.type).toBe("paragraph");
  const details = blocks[1]!;
  expect(details.type).toBe("detailsBlock");
  expect(details.props!.collapsed).toBe(true); // <details> 默认收起（对齐工件区）
  expect(details.content).toEqual([
    { type: "text", text: "计算过程", styles: {} },
  ]);
  expect(details.children![0]!.content).toEqual([
    { type: "text", text: "* 公式：$Q$", styles: {} },
  ]);
});

test("buildBlocksWithDetails: 递归处理 details 内嵌 details", () => {
  const parse = (md: string) => [
    {
      type: "paragraph",
      content: [{ type: "text", text: md.trim(), styles: {} }],
    },
  ];
  const md =
    "<details><summary>外</summary><details><summary>内</summary>里</details></details>";
  const blocks = buildBlocksWithDetails(md, parse);
  const outer = blocks[0]!;
  expect(outer.type).toBe("detailsBlock");
  expect(outer.children![0]!.type).toBe("detailsBlock");
  expect(outer.children![0]!.children![0]!.content).toEqual([
    { type: "text", text: "里", styles: {} },
  ]);
});

test("serializeWithDetails: details 回写 <details> 标签，普通块按序交给 mdFn", () => {
  const mdFn = (bs: Array<Record<string, unknown>>) =>
    bs.map((b) => `MD(${(b.content as Array<{ text: string }>)[0]!.text})`).join("\n\n");
  const blocks = [
    {
      type: "paragraph",
      content: [{ type: "text", text: "前文", styles: {} }],
    },
    {
      type: "detailsBlock",
      props: { collapsed: true },
      content: [{ type: "text", text: "计算过程", styles: {} }],
      children: [
        {
          type: "paragraph",
          content: [{ type: "text", text: "子内容", styles: {} }],
        },
      ],
    },
    {
      type: "paragraph",
      content: [{ type: "text", text: "后文", styles: {} }],
    },
  ];
  const md = serializeWithDetails(blocks as never, mdFn as never);
  expect(md).toBe(
    "MD(前文)\n\n<details><summary>计算过程</summary>\n\nMD(子内容)\n\n</details>\n\nMD(后文)",
  );
});
