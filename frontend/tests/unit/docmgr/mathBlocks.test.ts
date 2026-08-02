import { expect, test } from "vitest";

import {
  convertInlineMathInContent,
  prepareBlocksForMarkdownExport,
  transformMathInBlocks,
} from "@/extensions/docmgr/utils/mathBlocks";

// ── Bug 回归: 标题内联公式 $V_s$ 不渲染 ──────────────────────────────────
test("transformMathInBlocks: 标题内联 $V_s$ → latex 内联节点（原 bug）", () => {
  const blocks = [
    {
      id: "h1",
      type: "heading",
      props: { level: 2 },
      content: [{ type: "text", text: "总压损失 $V_s$ 计算", styles: {} }],
    },
  ];
  const result = transformMathInBlocks(blocks);
  expect(result).toHaveLength(1);
  expect(result[0].type).toBe("heading"); // 标题结构保留
  expect(result[0].props.level).toBe(2);
  expect(result[0].content).toEqual([
    { type: "text", text: "总压损失 ", styles: {} },
    { type: "latex", props: { latex: "V_s", displayMode: false } },
    { type: "text", text: " 计算", styles: {} },
  ]);
});

test("transformMathInBlocks: 段落内联公式仍正常", () => {
  const blocks = [
    {
      id: "p1",
      type: "paragraph",
      content: [{ type: "text", text: "流速 $v$ 取 1.5 m/s", styles: {} }],
    },
  ];
  const result = transformMathInBlocks(blocks);
  expect(result[0].content).toEqual([
    { type: "text", text: "流速 ", styles: {} },
    { type: "latex", props: { latex: "v", displayMode: false } },
    { type: "text", text: " 取 1.5 m/s", styles: {} },
  ]);
});

// ── 回归陷阱: 整段 $$...$$ 只对 paragraph 类转 equation,标题不能被替换 ───
test("transformMathInBlocks: 段落整段 $$...$$ → equation 块", () => {
  const blocks = [
    {
      id: "p1",
      type: "paragraph",
      content: [{ type: "text", text: "$$E = mc^2$$", styles: {} }],
    },
  ];
  const result = transformMathInBlocks(blocks);
  expect(result[0]).toEqual({ type: "equation", props: { latex: "E = mc^2" } });
});

test("transformMathInBlocks: 标题整段 $$...$$ 不得变成 equation 块（保留标题层级）", () => {
  const blocks = [
    {
      id: "h1",
      type: "heading",
      props: { level: 3 },
      content: [{ type: "text", text: "$$E = mc^2$$", styles: {} }],
    },
  ];
  const result = transformMathInBlocks(blocks);
  expect(result).toHaveLength(1);
  expect(result[0].type).toBe("heading");
  expect(result[0].props.level).toBe(3);
  // 退化为行内 latex（不丢标题,也不留字面 $$）
  expect(result[0].content.some((c: any) => c.type === "latex")).toBe(true);
});

// ── 表格内联公式 ─────────────────────────────────────────────────────────
test("transformMathInBlocks: 表格单元格 $...$ → latex", () => {
  const blocks = [
    {
      id: "t1",
      type: "table",
      content: {
        type: "tableContent",
        rows: [
          {
            cells: [
              {
                type: "tableCell",
                content: [{ type: "text", text: "Q=$V_s$", styles: {} }],
              },
            ],
          },
        ],
      },
    },
  ];
  const result = transformMathInBlocks(blocks);
  const cell = result[0].content.rows[0].cells[0];
  expect(cell.content).toEqual([
    { type: "text", text: "Q=", styles: {} },
    { type: "latex", props: { latex: "V_s", displayMode: false } },
  ]);
});

// ── 导出回写 ─────────────────────────────────────────────────────────────
test("prepareBlocksForMarkdownExport: 标题 latex 内联 → $latex$ 文本", () => {
  const blocks = [
    {
      id: "h1",
      type: "heading",
      props: { level: 2 },
      content: [
        { type: "text", text: "总压损失 ", styles: {} },
        { type: "latex", props: { latex: "V_s", displayMode: false } },
        { type: "text", text: " 计算", styles: {} },
      ],
    },
  ];
  const result = prepareBlocksForMarkdownExport(blocks);
  expect(result[0].type).toBe("heading");
  // latex 节点被替换为 $latex$ 文本节点;相邻文本不合并,序列化时拼接(块内多 text 节点 = 同段连续文本)
  expect(result[0].content).toEqual([
    { type: "text", text: "总压损失 ", styles: {} },
    { type: "text", text: "$V_s$", styles: {} },
    { type: "text", text: " 计算", styles: {} },
  ]);
  // 拼接后即期望的 markdown 文本
  expect(result[0].content.map((c: any) => c.text).join("")).toBe(
    "总压损失 $V_s$ 计算",
  );
});

test("prepareBlocksForMarkdownExport: equation 块 → 段落 $$latex$$", () => {
  const blocks = [
    { id: "e1", type: "equation", props: { latex: "E = mc^2" }, children: [] },
  ];
  const result = prepareBlocksForMarkdownExport(blocks);
  expect(result[0]).toMatchObject({
    type: "paragraph",
    content: [{ type: "text", text: "$$E = mc^2$$", styles: {} }],
  });
});

// ── 多段落 $$ 合并 ───────────────────────────────────────────────────────
test("transformMathInBlocks: 三段落 $$/内容/$$ 合并成 equation 块", () => {
  const blocks = [
    {
      id: "p1",
      type: "paragraph",
      content: [{ type: "text", text: "$$", styles: {} }],
    },
    {
      id: "p2",
      type: "paragraph",
      content: [{ type: "text", text: "\\frac{a}{b}", styles: {} }],
    },
    {
      id: "p3",
      type: "paragraph",
      content: [{ type: "text", text: "$$", styles: {} }],
    },
  ];
  const result = transformMathInBlocks(blocks);
  expect(result).toEqual([
    { type: "equation", props: { latex: "\\frac{a}{b}" } },
  ]);
});

// ── 实时输入路径(同一函数) ───────────────────────────────────────────────
test("convertInlineMathInContent: 纯内联转换不吞普通文本", () => {
  const { content, changed } = convertInlineMathInContent([
    { type: "text", text: "前 $x_1$ 后", styles: {} },
  ]);
  expect(changed).toBe(true);
  expect(content).toEqual([
    { type: "text", text: "前 ", styles: {} },
    { type: "latex", props: { latex: "x_1", displayMode: false } },
    { type: "text", text: " 后", styles: {} },
  ]);
});

test("convertInlineMathInContent: 无公式 → changed=false 原样返回", () => {
  const nodes = [{ type: "text", text: "价格 $5 不算", styles: {} }];
  const { content, changed } = convertInlineMathInContent(nodes);
  expect(changed).toBe(false);
  expect(content).toEqual(nodes); // 内容不变(返回新数组但节点为原引用,不改原对象)
});
