# 文档空间 Tiptap 编辑器数学公式渲染

- **日期**: 2026-07-20
- **状态**: 设计已批准,待实现
- **方案**: A — 编辑器内 WYSIWYG 直接渲染
- **关联模块**: 文档空间扩展 `frontend/src/extensions/docmgr/`

## 背景

文档空间"我的文档"里打开 `.md` 文件,进入 Tiptap 编辑器页面(`frontend/src/extensions/docmgr/TiptapEditor.tsx`)。当前 LaTeX 数学公式(`$...$` 行内、`$$...$$` 块级)以**原始文本**显示,未渲染。

聊天消息侧的 streamdown 已支持 KaTeX(`frontend/src/core/streamdown/plugins.ts`),但 docmgr 的 Tiptap 编辑器未接入。前置条件已全部就绪:

- KaTeX 全套依赖已装:`katex ^0.16.28`、`rehype-katex ^7`、`remark-math ^6`
- `katex.min.css` 已在 `frontend/src/app/layout.tsx:2` 全局引入
- Tiptap v3(`@tiptap/core ^3.22.4`、`@tiptap/react ^3.20.4`)+ `tiptap-markdown ^0.9.0`,`Markdown.configure({ html: true })` 已开

## 目标

1. 打开 md 文件,在 WYSIWYG 编辑器中**直接看到渲染后的公式**(行内 `$...$` + 块级 `$$...$$`)
2. 点击公式可编辑 LaTeX 源码,实时重渲染
3. **保存往返一致**:`getMarkdown()` 输出的 `$$...$$` / `$...$` 与原文等价,重开文件仍能正确渲染

## 非目标(YAGNI)

- 不做"插入公式"工具栏按钮(需求仅渲染已有公式;需要插入时再加)
- 不做公式内部光标编辑(atom node + 点击改源码,避免选区/撤销地狱)
- 不引入新的 npm 依赖

## 架构

在 Tiptap 新增两个**原子节点** `MathInline` / `MathBlock`,NodeView 用 KaTeX 渲染。Markdown 往返采用 **"边界预处理/后处理 + HTML 标签桥接"**,不依赖 `tiptap-markdown` 的 token→node 映射机制(那部分文档稀少、v3 行为不稳、易踩坑)。

## 数据流

**加载(打开 md 文件):**

```
md 原文 ($...$ / $$...$$)
 → encodeMath(md)                              [utils/mathMarkdown.ts]
 → $L$   ⇒ <span data-math-inline data-latex="L">
   $$L$$ ⇒ <div  data-math-block  data-latex="L">
 → TiptapEditor initialContent
 → tiptap-markdown 解析(html:true 已开,保留这些标签)
 → MathInline/MathBlock.parseHTML 命中 → ProseMirror 数学节点
 → NodeView 用 katex.render(latex) 渲染
```

**编辑(点击公式):**

```
点击节点 → NodeView 用 window.prompt 弹出当前 LaTeX → 用户改 →
node.attrs.latex 更新 → KaTeX 重新渲染
```

**保存(onChange / getMarkdown):**

```
ProseMirror doc → tiptap-markdown getMarkdown()
 → 数学节点 renderHTML 仍输出带 data-latex 的标签(html:true 下被保留)
 → decodeMath(md)  标签 ⇒ $L$ / $$L$$
 → 存盘 / onChange 回调
```

## 组件清单

| 文件 | 动作 | 职责 |
|------|------|------|
| `extensions/Math.ts` | 新增 | 导出 `MathInline` + `MathBlock`:`atom: true`;`addAttributes` 暴露 `latex`;`parseHTML` 识别 `[data-math-inline]` / `[data-math-block]`,从 `data-latex` 读源码;`renderHTML` 输出带 `data-latex` 的 span/div(供 markdown 序列化往返);`addNodeView` 接 `ReactNodeViewRenderer` |
| `components/MathNodeView.tsx` | 新增 | React NodeView:`useEffect` 内 `katex.render(latex, dom, katexOptions)`;点击 → `window.prompt` 改源码(更新 `node.attrs.latex`);block 节点 `text-align: center` 居中 |
| `utils/mathMarkdown.ts` | 新增 | 纯函数 `encodeMath(md)` / `decodeMath(md)` + 一个 `__main__`/`demo()` 自检(`decode(encode(x)) === x`) |
| `TiptapEditor.tsx` | 改 | import + 注册 `MathInline`、`MathBlock`;`content: encodeMath(initialContent)`;`getMarkdown()` 与 `onUpdate` 输出前套 `decodeMath` |

`katexOptions` 复用 streamdown 现有配置:`{ output: "html", throwOnError: false, strict: false }`。

## 关键决策

1. **边界预处理而非 markdown-it 插件** —— `tiptap-markdown` 的自定义 token 映射文档稀少、v3 不稳。HTML 标签桥接(配合已有 `html:true`)+ 纯函数 encode/decode 完全可控、可单测。LaTeX 中的 `_`、`*`、`\` 等放在 HTML 标签的**属性值**里,不会被 markdown 二次解释。
2. **atom node + 点击改源码** —— 不让光标进入公式内部,点击 `prompt` 改源码。务实折中,避免 ProseMirror 在原子节点内部的光标/选区/撤销复杂度。
3. **`katexOptions` 复用 streamdown** —— `throwOnError:false, strict:false`,语法错的公式显示原 LaTeX 红字,不阻塞编辑器。
4. **不加"插入公式"按钮** —— YAGNI,仅满足渲染需求。
5. **CSS 已就绪** —— `katex.min.css` 已全局引入,无需新增样式。

## 错误处理

- LaTeX 语法错 → `throwOnError:false` → KaTeX 渲染红色原 LaTeX 文本,编辑器不崩
- encode/decode **必须可逆**:单测断言 `decode(encode(x)) === x` 覆盖各类样本
- **不误伤货币符号 `$5`**:行内 `$...$` 正则约束 —— 开 `$` 后紧跟非空格、闭 `$` 前紧跟非空格、内容不含换行、不与 `$$` 重叠(先处理块级 `$$...$$`,再处理剩余行内 `$...$`)

## 测试

- `tests/unit/extensions/docmgr/mathMarkdown.test.ts`(Rstest):纯函数,覆盖
  - 纯行内 `$E=mc^2$`
  - 纯块级 `$$\frac{a}{b}$$`
  - 行内 + 块级混合
  - 货币符号 `$5`、`价格 $10 和 $20` 不被误匹配
  - LaTeX 内含 `_`、`*`、`\` 的往返一致性
  - `decode(encode(x)) === x` 对上述全部样本成立
- 手动 QA:打开含公式的 md 文件 → 渲染正确 → 点击改源码 → 保存 → 重开文件 → 公式与源码往返一致

## 风险与缓解

- **R1 — `getMarkdown()` 是否保留 `data-latex` 标签**:`tiptap-markdown` 在 `html:true` 下序列化自定义 atom node 的行为需在实现时验证。若标签被吞,降级方案 A:把 `latex` 编码进 HTML 注释 `<!--math:inline:L-->`;降级方案 B:改走 markdown-it 插件路线(成本更高,留作后备)。
- **R2 — 行内 `$` 与货币歧义**:用上述正则约束;测试用例覆盖货币场景。

## 不涉及

- 后端:纯前端改动,不触碰 `backend/app/extensions/docmgr/`
- 聊天消息渲染:streamdown 已支持,不动
- `FilePreviewModal`:仍是纯文本预览,不在本次范围
