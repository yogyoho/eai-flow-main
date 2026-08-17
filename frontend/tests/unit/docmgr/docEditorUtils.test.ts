import { expect, test } from "@rstest/core";

import {
  computeDocStats,
  replaceTextInContent,
} from "@/extensions/docmgr/utils/docEditorUtils";

test("computeDocStats: 中英文混排字数统计", () => {
  const { words, chars } = computeDocStats("这是测试文档 hello world");
  // 汉字 6 + 英文 2 词 = 8 字;非空白字符 = 6 汉字 + "hello world"(10) = 16
  expect(words).toBe(8);
  expect(chars).toBe(16);
});

test("computeDocStats: 剥离 markdown 语法", () => {
  const md =
    "# 标题\n\n**加粗** text `code`\n\n- 列表项\n\n[链接](http://x) ![图](img.png)";
  const { words } = computeDocStats(md);
  // 汉字: 标题2 + 加粗2 + 列表项3 = 7;拉丁: text/code/x/img/png → text、code、链接链接里的x不算?链接已剥除
  expect(words).toBe(7 + 2); // text + code = 2 个拉丁词
});

test("computeDocStats: 空串与纯符号", () => {
  expect(computeDocStats("")).toEqual({ words: 0, chars: 0 });
  expect(computeDocStats("```code```")).toEqual({ words: 0, chars: 0 });
});

test("replaceTextInContent: 单节点替换", () => {
  const content = [{ type: "text", text: "总压损失 $V_s$ 计算", styles: {} }];
  const { content: out, replaced } = replaceTextInContent(
    content,
    "总压损失",
    "设计参数",
  );
  expect(replaced).toBe(1);
  expect(out[0]!.text).toBe("设计参数 $V_s$ 计算");
});

test("replaceTextInContent: 同一节点多处替换 + 保留 latex 节点", () => {
  const content = [
    { type: "text", text: "a b a b", styles: {} },
    { type: "latex", props: { latex: "x" } },
  ];
  const { content: out, replaced } = replaceTextInContent(content, "a", "A");
  expect(replaced).toBe(2);
  expect(out[0]!.text).toBe("A b A b");
  expect(out[1]!.type).toBe("latex"); // 非 text 节点原样保留
});

test("replaceTextInContent: 空 query 或未命中不替换", () => {
  const content = [{ type: "text", text: "abc", styles: {} }];
  expect(replaceTextInContent(content, "", "x").replaced).toBe(0);
  expect(replaceTextInContent(content, "zzz", "x").replaced).toBe(0);
});
