# Tiptap 数学渲染重构：markdown-it 插件方案

> 日期：2026-07-22  
> 状态：已批准  
> 关联 bug：bug-189/190/191/192/212（encode/decode 往返损坏链）

## 背景与问题

docmgr 的 Tiptap 编辑器需要渲染和编辑 markdown 文档中的 `$...$`/`$$...$$` 数学公式。当前方案用 `encodeMath`/`decodeMath` 正则把数学语法转成 HTML 占位标签（`<div data-math-block>`/`<span data-math-inline>`），让 tiptap-markdown 扛过去。

这个方案在多次保存往返中持续损坏内容：
- `$$` 块公式后换行丢失，与标题/正文挤到一行
- `\frac` 等数学命令被双反斜杠化
- `**粗体**` 被过度转义累积成 `\\\*\\\*`
- 表格行全部坍塌到一行
- `$$` 卷入非数学文本（引用/粗体）
- **最终导致内容截断**（outputs/ 副本从 797 行缩到 286 行）

根因：正则在原始字符串上做数学语法识别，无法正确处理代码块、转义字符、嵌套上下文。

## 方案

用 **markdown-it 数学插件** 替代 encode/decode 正则层。数学语法在 markdown-it 状态机里 tokenize（按字符扫描，天然区分代码块/普通文本/数学），渲染成 mathInline/mathBlock 节点的 parseHTML 已匹配的 HTML 元素。

### 数据流对比

**改前（5 层，脆弱）**：
```
加载: sanitizeMarkdownForEditor → encodeMath(正则) → tiptap-markdown 解析 HTML → 节点
保存: getMarkdown → decodeMath(正则) → 存盘
```

**改后（2 层，稳健）**：
```
加载: tiptap-markdown(含 markdown-it 数学插件) → 自动识别 $...$ → 节点
保存: getMarkdown → 存盘
```

### tiptap-markdown 的插件注入机制

tiptap-markdown v0.9.0 的 `MarkdownParser.parse()` 在每次解析时遍历所有扩展，调用 `getMarkdownSpec(extension)?.parse?.setup(this.md)`，把 markdown-it 实例传给扩展。扩展在 `setup` 里 `md.use(myPlugin)` 注册插件。

TaskList 扩展已经用这个机制注册 `taskListPlugin`（源码 605 行）。数学扩展用同样方式注册数学插件。

注意：`markdownItPlugins` 配置选项在 tiptap-markdown v0.9.0 源码中**不存在**（`@ts-expect-error` 抑制的死配置），正确的注入点是 `addStorage().markdown.parse.setup`。

## 改动清单（3 个文件）

### ① 新建 `frontend/src/extensions/docmgr/extensions/mathMarkdownIt.ts`（~60 行）

极简 markdown-it 插件，做两件事：

**tokenize**：
- block ruler 规则：识别 `$$...$$`（可跨行），产出 `math_block` token
- inline ruler 规则：识别 `$...$`（不跨行，首尾紧邻非空格，前置非 `$`/数字以避开货币），产出 `math_inline` token
- 两个规则都在扫描前检查是否在代码块/行内代码内（markdown-it 状态机天然支持）

**render**：
- `math_block` → `<div data-math-block data-latex="..."></div>`
- `math_inline` → `<span data-math-inline data-latex="..."></span>`
- latex 内容 HTML 转义（`&`/`"`/`<`）

### ② 改 `frontend/src/extensions/docmgr/extensions/Math.ts`（+4 行）

在 `MathInline` 和 `MathBlock` 的 `addStorage().markdown` 里加 `parse.setup`：

```ts
addStorage() {
  return {
    markdown: {
      serialize: { ... },  // 已有
      parse: {
        setup(md) { md.use(mathMarkdownIt); },  // 新增
      },
    },
  };
}
```

### ③ 改 `frontend/src/extensions/docmgr/TiptapEditor.tsx`（删 3 处）

- `content: encodeMath(sanitizeMarkdownForEditor(initialContent))` → `content: initialContent`
- `onUpdate` 里 `onChange(decodeMath(md))` → `onChange(md)`
- 删 `setContent` useEffect 里的 sanitize/encode
- 删 `import { encodeMath, decodeMath, sanitizeMarkdownForEditor }`
- 删无用的 `markdownItPlugins: []` 配置

### 不改的文件

- `MathNodeView.tsx`（KaTeX 渲染 + `normalizeLatexForKatex`）——不变
- `mathInline`/`mathBlock` 的 `parseHTML`/`renderHTML`——不变
- `core/streamdown/`（chat 渲染器）——完全独立，不受影响
- `mathMarkdown.ts` 中的 `encodeMath`/`decodeMath`/`sanitizeMarkdownForEditor` 函数保留（不删文件，只停止引用——避免影响其他可能引用的地方）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| markdown-it 数学 tokenize 误判货币 `$5` | 行内规则要求首尾紧邻非空格 + 前置非数字，和现有 encodeMath 启发式一致 |
| 插件在每次 parse() 被重复注册 | markdown-it `.use()` 幂等（覆盖同名规则），安全 |
| 数学内容含 `"` 破坏 HTML 属性 | render 时 HTML 转义 `&`/`"`/`<` |
| 代码块里的 `$` 被误切 | markdown-it 状态机自动跳过 code fence/inline code |

## 回退方案

改动集中在 3 个文件（1 新建 + 2 改），出问题可快速 revert 到 encode/decode 方案（代码保留不删）。
