# Tiptap 数学渲染重构：markdown-it 插件方案 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 markdown-it 数学插件替代 encode/decode 正则层，根治 Tiptap 编辑器中数学公式的往返损坏。

**Architecture:** 在 Math.ts 的 `addStorage().markdown` 里通过 `parse.setup(md)` 注册一个极简 markdown-it 插件。插件在 markdown-it 状态机层 tokenize `$...$`/`$$...$$`，渲染成 mathInline/mathBlock 的 parseHTML 已匹配的 HTML 元素。删除 TiptapEditor.tsx 中的 encodeMath/decodeMath/sanitizeMarkdownForEditor 三层补丁。

**Tech Stack:** TypeScript, markdown-it 14.2.0 (transitive dep via tiptap-markdown), Tiptap 3.24, tiptap-markdown 0.9.0, Rstest (test runner)

---

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `frontend/src/extensions/docmgr/extensions/mathMarkdownIt.ts` | **新建** | markdown-it 数学插件（block+inline 规则 + renderer） |
| `frontend/src/extensions/docmgr/extensions/Math.ts` | **改** | 加 `parse.setup` 注册插件 |
| `frontend/src/extensions/docmgr/TiptapEditor.tsx` | **改** | 删 encode/decode/sanitize 调用 |
| `frontend/tests/unit/docmgr/mathMarkdownIt.test.ts` | **新建** | 插件单元测试 |

不改的文件：`MathNodeView.tsx`、`mathMarkdown.ts`（函数保留不删）、`core/streamdown/`。

---

## Task 1: 创建 markdown-it 数学插件

**Files:**
- Create: `frontend/src/extensions/docmgr/extensions/mathMarkdownIt.ts`
- Test: `frontend/tests/unit/docmgr/mathMarkdownIt.test.ts`

- [ ] **Step 1: 写单元测试（先写失败测试）**

Create `frontend/tests/unit/docmgr/mathMarkdownIt.test.ts`:

```typescript
import { expect, test } from "vitest";

import { mathMarkdownIt } from "@/extensions/docmgr/extensions/mathMarkdownIt";

// ponytail: markdown-it 是 tiptap-markdown 的传递依赖，pnpm 下可直接 import
// 如果 import 失败，在 package.json devDependencies 加 "markdown-it": "^14.0.0"
import MarkdownIt from "markdown-it";

function makeMd() {
  const md = new MarkdownIt({ html: true });
  md.use(mathMarkdownIt);
  return md;
}

test("行内 $...$ → <span data-math-inline>", () => {
  const html = makeMd().render("公式 $E=mc^2$ 测试");
  expect(html).toContain('data-math-inline');
  expect(html).toContain('data-latex="E=mc^2"');
});

test("块级 $$...$$ → <div data-math-block>", () => {
  const html = makeMd().render("$$\\frac{a}{b}$$");
  expect(html).toContain('data-math-block');
  expect(html).toContain('data-latex="\\frac{a}{b}"');
});

test("多行块级 $$...$$", () => {
  const html = makeMd().render("$$\n\\frac{a}{b}\n$$");
  expect(html).toContain('data-math-block');
  expect(html).toContain('data-latex="\\frac{a}{b}"');
});

test("不误伤货币符号 $5", () => {
  const html = makeMd().render("价格 $5 不算");
  expect(html).not.toContain('data-math-inline');
});

test("代码块里的 $ 不被误切", () => {
  const html = makeMd().render("```\n$5 + $3 = $8\n```");
  expect(html).not.toContain('data-math-inline');
});

test("行内代码里的 $ 不被误切", () => {
  const html = makeMd().render("用 `$x$` 表示变量");
  expect(html).not.toContain('data-math-inline');
});

test("latex 内容 HTML 转义", () => {
  const html = makeMd().render('$a < b \\text{且} c > d$');
  expect(html).toContain('data-latex="a &lt; b \\text{且} c &gt; d"');
});

test("中文紧邻 $ 不误判", () => {
  const html = makeMd().render("流量：$Q = Av$ 成立");
  expect(html).toContain('data-math-inline');
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run tests/unit/docmgr/mathMarkdownIt.test.ts`
Expected: FAIL — `Cannot find module '@/extensions/docmgr/extensions/mathMarkdownIt'`

- [ ] **Step 3: 创建 markdown-it 数学插件**

Create `frontend/src/extensions/docmgr/extensions/mathMarkdownIt.ts`:

```typescript
// ponytail: 极简 markdown-it 数学插件 —— 在状态机层 tokenize $...$/$$...$$,
// 渲染成 mathInline/mathBlock 节点 parseHTML 已匹配的 HTML 元素。
// 替代 encodeMath/decodeMath 正则方案，根治往返损坏。
// markdown-it 的 block/inline ruler 按字符扫描，天然跳过代码块/行内代码。

/** HTML 转义 latex 内容（与 encodeMath 的 escapeAttr 一致） */
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** markdown-it 实例的宽松类型（避免直接 import markdown-it 类型） */
interface MdInstance {
  block: { ruler: { before: (before: string, name: string, fn: Function, opts?: object) => void } };
  inline: { ruler: { after: (after: string, name: string, fn: Function, opts?: object) => void } };
  renderer: { rules: Record<string, (tokens: any[], idx: number) => string> };
}

/** markdown-it block ruler 状态的宽松类型 */
interface BlockState {
  src: string;
  bMarks: number[];
  eMarks: number[];
  tShift: number[];
  line: number;
  push(type: string, tag: string, nesting: number): { content: string; markup: string; map: [number, number]; block: boolean };
}

/** markdown-it inline ruler 状态的宽松类型 */
interface InlineState {
  src: string;
  pos: number;
  posMax: number;
  push(type: string, tag: string, nesting: number): { content: string; markup: string };
}

/**
 * 块级数学规则：识别 $$...$$（单行或跨行）
 * 注册在 paragraph 之前，确保 markdown-it 先处理数学再处理段落
 */
function mathBlockRule(state: BlockState, startLine: number, endLine: number, silent: boolean): boolean {
  const start = state.bMarks[startLine] + state.tShift[startLine];
  const max = state.eMarks[startLine];

  // 必须以 $$ 开头
  if (start + 2 > max) return false;
  if (state.src.charCodeAt(start) !== 0x24 /* $ */ || state.src.charCodeAt(start + 1) !== 0x24) return false;

  // $$ 后面的内容
  const afterDelim = state.src.slice(start + 2, max).trim();

  if (silent) return true;

  // 单行情况：$$ latex $$ 在同一行
  if (afterDelim.endsWith("$$") && afterDelim.length > 2) {
    const latex = afterDelim.slice(0, -2).trim();
    if (!latex) return false; // $$$$ → 空数学块，跳过
    const token = state.push("math_block", "div", 0);
    token.content = latex;
    token.markup = "$$";
    token.block = true;
    token.map = [startLine, startLine];
    state.line = startLine + 1;
    return true;
  }

  // 多行情况：$$ 开头，后续行是内容，某行单独 $$ 闭合
  let nextLine = startLine + 1;
  let foundClose = false;
  const lines: string[] = [];
  // 如果 $$ 后面还有内容（afterDelim 非空），它是第一行内容
  if (afterDelim) lines.push(afterDelim);

  while (nextLine < endLine) {
    const ls = state.bMarks[nextLine] + state.tShift[nextLine];
    const le = state.eMarks[nextLine];
    const lt = state.src.slice(ls, le).trim();
    if (lt === "$$") {
      foundClose = true;
      break;
    }
    lines.push(lt);
    nextLine++;
  }

  if (!foundClose) return false; // 未闭合 $$ → 不是数学块

  const latex = lines.join("\n").trim();
  const token = state.push("math_block", "div", 0);
  token.content = latex;
  token.markup = "$$";
  token.block = true;
  token.map = [startLine, nextLine];
  state.line = nextLine + 1;
  return true;
}

/**
 * 行内数学规则：识别 $...$（不跨行）
 * 注册在 escape 之后，确保转义字符先处理
 */
function mathInlineRule(state: InlineState, silent: boolean): boolean {
  // 必须是 $ 开头
  if (state.src.charCodeAt(state.pos) !== 0x24 /* $ */) return false;
  // 排除 $$（块级数学，由 block ruler 处理）
  if (state.src.charCodeAt(state.pos + 1) === 0x24) return false;

  // 前一个字符不能是数字或 $（避开货币 $5、$$ 残留）
  if (state.pos > 0) {
    const prev = state.src.charCodeAt(state.pos - 1);
    // 0x24=$, 0x30-0x39=数字
    if (prev === 0x24 || (prev >= 0x30 && prev <= 0x39)) return false;
  }

  // $ 后第一个字符必须非空白
  const startPos = state.pos + 1;
  if (startPos >= state.posMax) return false;
  if (/\s/.test(state.src[startPos])) return false;

  // 找闭合 $（不跨行）
  let end = -1;
  for (let i = startPos + 1; i < state.posMax; i++) {
    const ch = state.src[i];
    if (ch === "\n") return false; // 行内数学不跨行
    if (ch === "$") {
      // 闭合 $ 后不能跟数字（货币）
      if (i + 1 < state.posMax) {
        const next = state.src.charCodeAt(i + 1);
        if (next >= 0x30 && next <= 0x39) continue; // $5 跳过
      }
      // 闭合 $ 前必须非空白
      if (/\s/.test(state.src[i - 1])) return false;
      end = i;
      break;
    }
  }
  if (end === -1) return false;

  const latex = state.src.slice(startPos, end).trim();
  if (!latex) return false;

  if (silent) return true;

  const token = state.push("math_inline", "span", 0);
  token.content = latex;
  token.markup = "$";
  state.pos = end + 1;
  return true;
}

/**
 * markdown-it 数学插件入口
 * 用法: md.use(mathMarkdownIt)
 */
export function mathMarkdownIt(md: MdInstance): void {
  // 块级规则：在 paragraph 之前注册，确保 $$ 先于段落处理
  md.block.ruler.before("paragraph", "math_block", mathBlockRule, { alt: ["paragraph", "reference", "blockquote", "list"] });
  // 行内规则：在 escape 之后注册
  md.inline.ruler.after("escape", "math_inline", mathInlineRule);
  // 渲染规则
  md.renderer.rules["math_block"] = (tokens: any[], idx: number) => {
    const latex = escapeHtml(tokens[idx].content);
    return `<div data-math-block data-latex="${latex}"></div>\n`;
  };
  md.renderer.rules["math_inline"] = (tokens: any[], idx: number) => {
    const latex = escapeHtml(tokens[idx].content);
    return `<span data-math-inline data-latex="${latex}"></span>`;
  };
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run tests/unit/docmgr/mathMarkdownIt.test.ts`
Expected: PASS — all tests pass

如果 `import MarkdownIt from "markdown-it"` 失败（pnpm 未提升），在 `frontend/package.json` 的 `devDependencies` 加 `"markdown-it": "^14.0.0"`，然后 `pnpm install --lockfile-only`（宿主机 frontend 不需重建镜像）。

- [ ] **Step 5: 提交**

```bash
cd frontend
git add src/extensions/docmgr/extensions/mathMarkdownIt.ts tests/unit/docmgr/mathMarkdownIt.test.ts
git commit -m "feat(docmgr): markdown-it 数学插件 — 替代 encode/decode 正则层"
```

---

## Task 2: 将插件接入 Math.ts

**Files:**
- Modify: `frontend/src/extensions/docmgr/extensions/Math.ts`

- [ ] **Step 1: 加 import 和 parse.setup**

在 `Math.ts` 顶部加 import：

```typescript
import { mathMarkdownIt } from "./mathMarkdownIt";
```

在 `MathInline`（第 37-45 行）的 `addStorage()` 返回值中，`markdown` 对象里加 `parse.setup`：

```typescript
  addStorage() {
    return {
      markdown: {
        serialize(state: MdState, node: { attrs: { latex: string } }) {
          state.write(`$${node.attrs.latex}$`);
        },
        parse: {
          // ponytail: tiptap-markdown 的 MarkdownParser.parse() 在每次解析时
          // 调用 getMarkdownSpec(extension).parse.setup(md)，传入 markdown-it 实例。
          // 这里注册数学插件，让 markdown-it 在状态机层识别 $...$
          setup(md: any) {
            md.use(mathMarkdownIt);
          },
        },
      },
    };
  },
```

在 `MathBlock`（第 65-75 行）同样加 `parse.setup`（内容完全相同，因为插件注册是幂等的）：

```typescript
  addStorage() {
    return {
      markdown: {
        serialize(state: MdState, node: { attrs: { latex: string } }) {
          state.ensureNewLine();
          state.write(`$$${node.attrs.latex}$$`);
          state.closeBlock();
        },
        parse: {
          setup(md: any) {
            md.use(mathMarkdownIt);
          },
        },
      },
    };
  },
```

- [ ] **Step 2: 运行已有测试确认无回归**

Run: `cd frontend && npx vitest run tests/unit/docmgr/`
Expected: PASS — all existing tests still pass（mathMarkdown.test.ts 测的是 encode/decode 函数本身，不受影响）

- [ ] **Step 3: 提交**

```bash
git add src/extensions/docmgr/extensions/Math.ts
git commit -m "feat(docmgr): Math.ts 注册 markdown-it 数学插件 via parse.setup"
```

---

## Task 3: 删除 TiptapEditor.tsx 中的 encode/decode/sanitize 调用

**Files:**
- Modify: `frontend/src/extensions/docmgr/TiptapEditor.tsx`

- [ ] **Step 1: 删除 encode/decode/sanitize import（第 39 行）**

将：
```typescript
import { decodeMath, encodeMath, sanitizeMarkdownForEditor } from "./utils/mathMarkdown";
```
直接删除整行。

- [ ] **Step 2: content 改回原始 markdown（第 335 行）**

将：
```typescript
      content: encodeMath(sanitizeMarkdownForEditor(initialContent)),
```
改为：
```typescript
      content: initialContent,
```

- [ ] **Step 3: onUpdate 删除 decodeMath（第 367 行）**

将：
```typescript
        onChange(decodeMath(md));
```
改为：
```typescript
        onChange(md);
```

- [ ] **Step 4: 删除 setContent useEffect（第 378-384 行）**

删除整个 useEffect 块：
```typescript
    // 确保异步加载的内容也经过 sanitize(useEditor 的 content 选项仅用于初始创建)
    useEffect(() => {
      if (!editor || !initialContent) return;
      const html = encodeMath(sanitizeMarkdownForEditor(initialContent));
      // ponytail: setContent 用 emitUpdate:false 避免触发 onChange→存盘循环
      editor.commands.setContent(html, false);
    }, [editor, initialContent]);
```

- [ ] **Step 5: 删除 markdownItPlugins 配置（第 309 行附近）**

在 Markdown.configure 里删除：
```typescript
          // @ts-expect-error tiptap-markdown accepts markdown-it plugins at runtime.
          markdownItPlugins: [], // 使用默认的 markdown-it 表格支持
```

- [ ] **Step 6: 检查没有遗漏的 encodeMath/decodeMath/sanitize 引用**

Run: `cd frontend && grep -n "encodeMath\|decodeMath\|sanitizeMarkdown\|markdownItPlugins" src/extensions/docmgr/TiptapEditor.tsx`
Expected: 无输出（全部清除）

- [ ] **Step 7: typecheck**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep TiptapEditor`
Expected: 无 TiptapEditor 相关错误

- [ ] **Step 8: 提交**

```bash
git add src/extensions/docmgr/TiptapEditor.tsx
git commit -m "refactor(docmgr): 删除 encode/decode/sanitize 三层补丁 — 走 markdown-it 原生数学解析"
```

---

## Task 4: 端到端回归验证

**Files:** 无代码改动，纯验证

- [ ] **Step 1: 宿主机 frontend HMR 确认编译无错**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/`
Expected: 200

检查 frontend 日志无编译错误（`tail /app/logs/frontend.log` 或宿主机终端）。

- [ ] **Step 2: 打开测试文件验证公式渲染**

在浏览器 http://localhost:3000/docmgr 打开一个含数学公式的文档（如"公式渲染测试"或"循环水系统给排水计算书.md"），验证：
- 行内 `$E=mc^2$` 渲染为 KaTeX 公式（不是字面文本）
- 块级 `$$\frac{a}{b}$$` 渲染为居中公式
- 代码块里的 `$` 不被误切
- `**粗体**`、`### 标题`、`> 引用` 正常渲染（不被数学干扰）
- 表格正常渲染

- [ ] **Step 3: 验证保存往返无损**

在编辑器里随便点一下（触发 autosave），刷新页面重新打开同一文档，验证内容完整、公式仍然正常。

- [ ] **Step 4: 验证之前损坏的文件**

打开之前截断的"辽阳石化新装置给排水计算书.md"（已从 workspace/ 恢复），验证全部 797 行内容显示完整、数学渲染正常。

- [ ] **Step 5: 最终提交（如果有清理）**

```bash
git add -A && git status  # 检查无意外改动
```
如果干净则无需提交；如果 test 文件或 lockfile 有改动，一起提交。

---

## Self-Review

### Spec 覆盖

| Spec 要求 | 对应 Task |
|---|---|
| 新建 markdown-it 数学插件（tokenize + render） | Task 1 |
| Math.ts 加 parse.setup | Task 2 |
| TiptapEditor 删 encode/decode/sanitize | Task 3 |
| 不改 MathNodeView/parseHTML/chat | 无改动（确认） |
| mathMarkdown.ts 函数保留不删 | 无改动（确认） |
| 代码块不误切 | Task 1 测试覆盖 |
| 货币不误切 | Task 1 测试覆盖 |
| HTML 转义 latex | Task 1 插件实现 |
| 回退方案 | mathMarkdown.ts 保留可 revert |

### 类型一致性

- 插件函数名 `mathMarkdownIt` — Task 1 定义、Task 2 引用，一致
- `parse.setup(md)` — Task 2 实现，与 tiptap-markdown 源码 `getMarkdownSpec(extension).parse.setup.call(context, this.md)` 一致
- 渲染输出 HTML（`data-math-block`/`data-math-inline`/`data-latex`）与 Math.ts parseHTML 一致
