# 文档空间 Tiptap 编辑器数学公式渲染 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在文档空间 docmgr 的 Tiptap 编辑器里把 `$...$` / `$$...$$` 渲染成 KaTeX 公式,点击可改源码,保存往返一致。

**Architecture:** 在 Tiptap 新增两个原子节点 `MathInline` / `MathBlock`,NodeView 用 KaTeX 渲染。Markdown 往返走"边界 `encodeMath`/`decodeMath` 纯函数 + HTML 占位标签桥接",不依赖 tiptap-markdown 的 token 映射(`html:true` 已开,标签被保留)。

**Tech Stack:** Tiptap v3 (`@tiptap/core ^3.22.4`, `@tiptap/react ^3.20.4`), `tiptap-markdown ^0.9.0`, `katex ^0.16.28`(CSS 已全局引入), React 19, vitest。

**Spec:** `docs/superpowers/specs/2026-07-20-docmgr-math-render-design.md`

---

## 文件结构

| 文件 | 责任 |
|------|------|
| `frontend/src/extensions/docmgr/utils/mathMarkdown.ts` | 纯函数 `encodeMath` / `decodeMath` + 自检。markdown ⇄ HTML 占位标签互转 |
| `frontend/src/extensions/docmgr/components/MathNodeView.tsx` | React NodeView:KaTeX 渲染 + 点击 prompt 改源码 |
| `frontend/src/extensions/docmgr/extensions/Math.ts` | `MathInline` + `MathBlock` 两个 Tiptap 原子节点 |
| `frontend/src/extensions/docmgr/TiptapEditor.tsx` | 注册节点;入站 `encodeMath`、出站 `decodeMath` |
| `frontend/tests/unit/extensions/docmgr/mathMarkdown.test.ts` | encode/decode 纯函数单测 |

---

## Task 1: `mathMarkdown` 纯函数 + 单测(TDD)

**Files:**
- Create: `frontend/src/extensions/docmgr/utils/mathMarkdown.ts`
- Test: `frontend/tests/unit/extensions/docmgr/mathMarkdown.test.ts`

- [ ] **Step 1: 写失败测试**

Create `frontend/tests/unit/extensions/docmgr/mathMarkdown.test.ts`:

```ts
import { expect, test } from "vitest";

import { decodeMath, encodeMath } from "@/extensions/docmgr/utils/mathMarkdown";

test("encodeMath: inline $...$ → span 占位", () => {
  expect(encodeMath("$E=mc^2$")).toBe(
    '<span data-math-inline data-latex="E=mc^2"></span>',
  );
});

test("encodeMath: block $$...$$ → div 占位", () => {
  expect(encodeMath("$$\\frac{a}{b}$$")).toBe(
    '<div data-math-block data-latex="\\frac{a}{b}"></div>',
  );
});

test("encodeMath: 不误伤货币符号", () => {
  expect(encodeMath("价格 $5 不算")).toBe("价格 $5 不算");
  expect(encodeMath("$10 和 $20")).toBe("$10 和 $20");
});

test("encodeMath: 段中行内公式保留前缀", () => {
  expect(encodeMath("a $x$ b")).toBe(
    'a <span data-math-inline data-latex="x"></span> b',
  );
});

test("decodeMath: 容忍属性重排与空值", () => {
  expect(decodeMath('<span data-math-inline data-latex="x"></span>')).toBe("$x$");
  expect(decodeMath('<span data-math-inline="" data-latex="x"></span>')).toBe("$x$");
  expect(decodeMath('<span data-latex="x" data-math-inline=""></span>')).toBe("$x$");
  expect(decodeMath('<div data-math-block data-latex="\\frac{a}{b}"></div>')).toBe(
    "$$\\frac{a}{b}$$",
  );
});

test("往返一致 decode(encode(x)) === x", () => {
  const samples = [
    "$E=mc^2$",
    "$$\\frac{a}{b}$$",
    "a $x$ b",
    "$a_1$ 然后 $b^2$",
    "$a & b$",
  ];
  for (const s of samples) {
    expect(decodeMath(encodeMath(s))).toBe(s);
  }
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd frontend && pnpm vitest run tests/unit/extensions/docmgr/mathMarkdown.test.ts
```
Expected: FAIL — `Failed to resolve import "@/extensions/docmgr/utils/mathMarkdown"`(文件不存在)。

- [ ] **Step 3: 实现 `mathMarkdown.ts`**

Create `frontend/src/extensions/docmgr/utils/mathMarkdown.ts`:

```ts
// ponytail: 边界预处理/后处理 —— markdown 数学语法 ($...$ / $$...$$) ⇄ HTML 占位标签。
// 让 tiptap-markdown(html:true 已开)携带公式节点往返,不依赖其 token 映射(文档少、v3 不稳)。
// 已知 ceiling: 行内 $...$ 正则是启发式(首尾紧邻非空格),极端嵌套可能误判 —— 靠单测覆盖常见用例。

const ESC: Array<[RegExp, string]> = [
  [/&/g, "&amp;"],
  [/"/g, "&quot;"],
  [/</g, "&lt;"],
];
const UNESC: Array<[RegExp, string]> = [
  [/&lt;/g, "<"],
  [/&quot;/g, '"'],
  [/&amp;/g, "&"],
];

function escapeAttr(s: string): string {
  let r = s;
  for (const [re, rep] of ESC) r = r.replace(re, rep);
  return r;
}

function unescapeAttr(s: string): string {
  let r = s;
  for (const [re, rep] of UNESC) r = r.replace(re, rep);
  return r;
}

export function encodeMath(md: string): string {
  // 先块级 $$...$$(可跨行),再行内 $...$(不跨行;首尾须紧邻非空格,避开货币与 $$ 残留)
  return md
    .replace(
      /\$\$([\s\S]+?)\$\$/g,
      (_m, latex: string) =>
        `<div data-math-block data-latex="${escapeAttr(latex)}"></div>`,
    )
    .replace(
      /(^|[^$\n\\])\$([^\s$][^\n$]*?[^\s$]|[^\s$])\$(?=$|[^$\n])/g,
      (_m, pre: string, latex: string) =>
        `${pre}<span data-math-inline data-latex="${escapeAttr(latex)}"></span>`,
    );
}

export function decodeMath(md: string): string {
  // 容忍 data-math-x 与 data-math-x="" 、属性两种顺序(正序 + 反序各一轮)
  const block = (l: string) => `$$${unescapeAttr(l)}$$`;
  const inline = (l: string) => `$${unescapeAttr(l)}$`;
  return md
    .replace(
      /<div\b[^>]*\bdata-math-block\b(?:="")?[^>]*\bdata-latex="([^"]*)"[^>]*><\/div>/g,
      (_m, l: string) => block(l),
    )
    .replace(
      /<div\b[^>]*\bdata-latex="([^"]*)"[^>]*\bdata-math-block\b(?:="")?[^>]*><\/div>/g,
      (_m, l: string) => block(l),
    )
    .replace(
      /<span\b[^>]*\bdata-math-inline\b(?:="")?[^>]*\bdata-latex="([^"]*)"[^>]*><\/span>/g,
      (_m, l: string) => inline(l),
    )
    .replace(
      /<span\b[^>]*\bdata-latex="([^"]*)"[^>]*\bdata-math-inline\b(?:="")?[^>]*><\/span>/g,
      (_m, l: string) => inline(l),
    );
}
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
cd frontend && pnpm vitest run tests/unit/extensions/docmgr/mathMarkdown.test.ts
```
Expected: PASS — 6 tests passed。

- [ ] **Step 5: 跑类型检查**

Run:
```bash
cd frontend && pnpm typecheck
```
Expected: 无新增报错。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/docmgr/utils/mathMarkdown.ts frontend/tests/unit/extensions/docmgr/mathMarkdown.test.ts
git commit -m "feat(docmgr): add math markdown encode/decode helpers (math render)"
```

---

## Task 2: `MathNodeView` React 组件

**Files:**
- Create: `frontend/src/extensions/docmgr/components/MathNodeView.tsx`

无单测(纯 UI 渲染组件,靠 Task 4/5 手动 QA)。`katex.render` 在 `throwOnError:false` 下保证不抛。

- [ ] **Step 1: 创建组件**

Create `frontend/src/extensions/docmgr/components/MathNodeView.tsx`:

```tsx
"use client";

import { NodeViewWrapper } from "@tiptap/react";
import katex from "katex";
import { useEffect, useRef } from "react";

// ponytail: atom node 的 NodeView —— 只读渲染公式,点击 prompt 改源码。
// 不做公式内光标编辑(避免选区/撤销地狱)。prompt 是最省事的入口,体验不足再升 popover。
const KATEX_OPTS = { output: "html", throwOnError: false, strict: false } as const;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface MathNodeViewProps {
  node: any;
  updateAttributes: (attrs: Record<string, unknown>) => void;
}

export function MathNodeView({ node, updateAttributes }: MathNodeViewProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const latex: string = node.attrs.latex ?? "";
  const isBlock = node.type.name === "mathBlock";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    try {
      katex.render(latex, el, { ...KATEX_OPTS, displayMode: isBlock });
    } catch {
      el.textContent = latex; // throwOnError:false 下一般不会到这;防御
    }
  }, [latex, isBlock]);

  const onEdit = () => {
    const next = window.prompt("编辑公式 LaTeX 源码", latex);
    if (next !== null) updateAttributes({ latex: next });
  };

  return (
    <NodeViewWrapper
      as={isBlock ? "div" : "span"}
      style={
        isBlock
          ? { textAlign: "center", margin: "1em 0" }
          : { display: "inline", verticalAlign: "baseline" }
      }
    >
      <span
        ref={ref}
        onClick={onEdit}
        title="点击编辑公式源码"
        style={{ cursor: "pointer" }}
      />
    </NodeViewWrapper>
  );
}
```

- [ ] **Step 2: 跑类型检查**

Run:
```bash
cd frontend && pnpm typecheck
```
Expected: 无新增报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/components/MathNodeView.tsx
git commit -m "feat(docmgr): add KaTeX NodeView for math nodes"
```

---

## Task 3: `MathInline` + `MathBlock` Tiptap 节点

**Files:**
- Create: `frontend/src/extensions/docmgr/extensions/Math.ts`

- [ ] **Step 1: 创建节点定义**

Create `frontend/src/extensions/docmgr/extensions/Math.ts`:

```ts
import { Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { MathNodeView } from "../components/MathNodeView";

const latexAttr = {
  default: "",
  parseHTML: (el: HTMLElement) => el.getAttribute("data-latex") ?? "",
};

export const MathInline = Node.create({
  name: "mathInline",
  group: "inline",
  inline: true,
  atom: true,
  addAttributes() {
    return { latex: latexAttr };
  },
  parseHTML() {
    return [{ tag: "span[data-math-inline]" }];
  },
  renderHTML({ node }) {
    return ["span", { "data-math-inline": "", "data-latex": node.attrs.latex }];
  },
  addNodeView() {
    return ReactNodeViewRenderer(MathNodeView);
  },
});

export const MathBlock = Node.create({
  name: "mathBlock",
  group: "block",
  atom: true,
  defining: true,
  addAttributes() {
    return { latex: latexAttr };
  },
  parseHTML() {
    return [{ tag: "div[data-math-block]" }];
  },
  renderHTML({ node }) {
    return ["div", { "data-math-block": "", "data-latex": node.attrs.latex }];
  },
  addNodeView() {
    return ReactNodeViewRenderer(MathNodeView);
  },
});
```

- [ ] **Step 2: 跑类型检查**

Run:
```bash
cd frontend && pnpm typecheck
```
Expected: 无新增报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/extensions/Math.ts
git commit -m "feat(docmgr): add MathInline/MathBlock Tiptap nodes"
```

---

## Task 4: `TiptapEditor` 接入

**Files:**
- Modify: `frontend/src/extensions/docmgr/TiptapEditor.tsx`

- [ ] **Step 1: 加 import**

在 `TiptapEditor.tsx` 现有 sibling import 区(第 29–35 行 `./components/...`、`./extensions/SlashCommand`、`./utils/...` 附近)加:

```ts
import { MathBlock, MathInline } from "./extensions/Math";
import { decodeMath, encodeMath } from "./utils/mathMarkdown";
```

- [ ] **Step 2: 注册节点到 extensions 数组**

在 `useEditor({ extensions: [ ... ] })` 里,`Markdown.configure({...})` 之后、`SlashCommand.configure(...)` 之前插入:

```ts
        MathInline,
        MathBlock,
```

- [ ] **Step 3: 入站 encode**

把 `content: initialContent,`(第 288 行附近)改为:

```ts
      content: encodeMath(initialContent),
```

- [ ] **Step 4: 出站 decode(onUpdate)**

把 `onUpdate` 里的:
```ts
        const md = (e.storage as any).markdown.getMarkdown() as string;
        onChange(md);
```
改为:
```ts
        const md = (e.storage as any).markdown.getMarkdown() as string;
        onChange(decodeMath(md));
```

- [ ] **Step 5: 出站 decode(getMarkdown imperative handle)**

把 `useImperativeHandle` 里的:
```ts
        return (editor.storage as any).markdown.getMarkdown() as string;
```
改为:
```ts
        return decodeMath((editor.storage as any).markdown.getMarkdown() as string);
```

- [ ] **Step 6: 跑类型检查 + lint**

Run:
```bash
cd frontend && pnpm typecheck && pnpm lint
```
Expected: 无新增报错。

- [ ] **Step 7: 重建前端镜像(代码变更需容器重启,见 CLAUDE.md)**

```bash
make rebuild-frontend
```
(若已停用 Docker 开发流,改为 `cd frontend && pnpm dev`。)

- [ ] **Step 8: 手动 QA — 渲染**

浏览器打开 `localhost:2026` → 文档空间 → 我的文档 → 选一个含 `$E=mc^2$` 和 `$$\frac{a}{b}$$` 的 md 文件。
Expected:
- 行内公式渲染成 `E=mc²`(KaTeX)
- 块级公式居中渲染成分式
- 点击公式 → 弹出 prompt,改源码后实时重渲染

- [ ] **Step 9: Commit**

```bash
git add frontend/src/extensions/docmgr/TiptapEditor.tsx
git commit -m "feat(docmgr): wire math render into Tiptap editor (encode/decode)"
```

---

## Task 5: R1 往返一致性验证

**风险 R1(spec):** `tiptap-markdown` 在 `html:true` 下序列化自定义 atom node 时,需确认 `data-latex` 标签被保留,否则 `decodeMath` 拿不到 latex。

- [ ] **Step 1: 浏览器 console 验证往返**

在编辑器里输入 `$x^2$`,在 DevTools console 执行(用 React DevTools 拿 editor 实例,或临时在 `onUpdate` 里 `console.log(md)`):
```js
// 期望 onUpdate 打印的 md 含 "$x^2$",而非丢失或变成乱码
```
Expected: `onChange` 收到的 md 是 `$x^2$`。保存后重开文件,公式仍渲染。

- [ ] **Step 2: 判定**

- 若往返正确 → R1 通过,跳过 Task 5b,本计划完成。
- 若 `getMarkdown()` 输出里**没有** `data-latex`(latex 丢失)→ 执行 Task 5b 降级。

- [ ] **Step 3: 记录结果**

把验证结论补到 `.wolf/memory.md`(OpenWolf 簿记)。

---

## Task 5b(条件 — 仅 R1 失败时): 改用 tiptap-markdown 自定义序列化

**触发条件:** Task 5 Step 2 判定 R1 失败(getMarkdown 丢失 latex)。

**Files:**
- Modify: `frontend/src/extensions/docmgr/extensions/Math.ts`

- [ ] **Step 1: 给两个节点加 markdown 序列化 option**

在 `MathInline` 与 `MathBlock` 的 `Node.create({...})` 里,`addAttributes` 之前加:

```ts
  addOptions() {
    return {
      // ponytail: 降级路径 —— tiptap-markdown 运行时读取 node options.markdown 做序列化,
      // 绕过 renderHTML 标签在 getMarkdown 中丢失的问题。
      // @ts-expect-error tiptap-markdown runtime contract (markdown serializer)
      markdown: {
        serialize(state: { write: (s: string) => void; ensureNewLine: () => void; closeBlock: () => void }, node: { attrs: { latex: string } }) {
          const delim = "$$";
          state.ensureNewLine();
          state.write(`${delim}${node.attrs.latex}${delim}`);
          state.closeBlock();
        },
      },
    };
  },
```

对 `MathInline`,serialize 改为:
```ts
      // @ts-expect-error tiptap-markdown runtime contract
      markdown: {
        serialize(state: { write: (s: string) => void }, node: { attrs: { latex: string } }) {
          state.write(`$${node.attrs.latex}$`);
        },
      },
```

- [ ] **Step 2: 重测往返**

重复 Task 5 Step 1。Expected: `onChange` md 含 `$x^2$` / `$$...$$`。

- [ ] **Step 3: 若仍失败**

若 `addOptions.markdown` 也不生效(tiptap-markdown 0.9 不识别),最后手段:在 `TiptapEditor` 的 `getMarkdown`/`onUpdate` 里遍历 `editor.state.doc` 提取 math 节点 latex,用唯一占位文本替换节点后序列化,再还原(实现时定方案,记录到 `.wolf/buglog.json`)。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/docmgr/extensions/Math.ts
git commit -m "fix(docmgr): fallback math serialization via tiptap-markdown option (R1)"
```

---

## 完成标准

- [ ] Task 1 单测全绿
- [ ] 打开含公式 md → 行内 + 块级公式正确渲染
- [ ] 点击公式可改源码并重渲染
- [ ] 保存 → 重开,公式源码与渲染往返一致(R1 通过或已降级)
- [ ] 货币符号 `$5` 不被误渲染
- [ ] `pnpm typecheck` + `pnpm lint` 无新增报错
