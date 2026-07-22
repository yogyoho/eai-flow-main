# 对话页面流式卡顿分析与解决方案

> 日期：2026-07-22  
> 状态：分析完成，修复方案待实施  
> 基线：BASE=`a180c923`（7月16前，不卡顿）vs HEAD（卡顿）

## 一、根因

### 卡顿是 7月16 upstream sync 引入的回归

用户确认：**7月16日前的版本不卡顿，之后的版本卡顿**。对比 BASE（7月16前）vs HEAD：

- 渲染依赖**完全相同**（streamdown 1.4.0 / react-markdown 10.1.0 / katex / remark-math / use-stick-to-bottom / langgraph-sdk 版本一字不差）
- word-split（rehypeSplitWordsIntoSpans）**BASE 已有**
- **唯一差异**：7月16 upstream sync（commit `3a54b68b`）引入了 `SafeMessageResponse` 中间层 + preprocess 链

### 每 token 的 O(content) 全文扫描对比

**BASE（不卡）—— 每 token ~1 个 O(content)：**
```
content → preprocessStreamdownMarkdown（mermaid only，early return）
       → MessageResponse（直接）
       → ClipboardSafeStreamdown → capMarkdownNesting（1 个 O(content)，防 marked 崩溃）
```

**HEAD（卡）—— 每 token 5 个 O(content)：**
```
content → preprocessStreamdownMarkdown（mermaid only）
       → SafeMessageResponse → useSafeStreamdownChildren
           → capMarkdownNesting              ← O(content) #1（新增）
           → normalizeStreamdownMathMarkdown ← O(content) #2（新增）
              → compactDisplayMathBlocks     ← O(content) #3（新增）
              → normalizeLatexMathDelimiters ← O(content) #4（新增）
       → MessageResponse → ClipboardSafeStreamdown
           → capMarkdownNesting              ← O(content) #5（重复）
```

给排水报告 15-30K 字符 × 每 token 5 个 30K 全文扫描 = **浏览器主线程压满 → 页面不动/输入框无响应**。

### preprocess 函数位置

| 函数 | 文件 | 作用 |
|------|------|------|
| `useSafeStreamdownChildren` | `core/streamdown/safe-children.ts:26` | 入口：调 getSafeStreamdownChildren |
| `getSafeStreamdownChildren` | `core/streamdown/safe-children.ts:16` | 调 normalizeStreamdownMathMarkdown + capMarkdownNesting |
| `normalizeStreamdownMathMarkdown` | `core/streamdown/preprocess.ts:319` | 调 compactDisplayMathBlocks + normalizeLatexMathDelimiters |
| `normalizeLatexMathDelimiters` | `core/streamdown/preprocess.ts` | LaTeX `$...$`/`$$...$$` delimiter 归一化 |
| `compactDisplayMathBlocks` | `core/streamdown/preprocess.ts` | 合并跨行 `$$...$$` 块 |
| `capMarkdownNesting` | `core/streamdown/preprocess.ts` | 限制 markdown 嵌套深度（防 marked 崩溃） |
| `capMarkdownNesting`（重复） | `ai-elements/streamdown.tsx:68` | ClipboardSafeStreamdown 内，与 safe-children 重复 |
| `rehypeNormalizeMath` | `core/streamdown/latexNormalize.ts` | rehype plugin，per math node 调 normalizeLatexForKatex |

---

## 二、解决方案（按优先级）

### 方案 A：流式期跳过 preprocess（最直接，已验证）

**原理**：preprocess 是为最终正确性（LaTeX delimiter / 表格 / 深嵌套防崩溃），流式期不必每 token 跑——最终渲染跑一次即可。

**改动（3 文件，~15 行）**：

1. **`core/streamdown/safe-children.ts`** — `useSafeStreamdownChildren`/`useSafeStreamdownMarkdown` 加 `enabled` 参数：
```typescript
export function useSafeStreamdownChildren(
  children: StreamdownChildren,
  enabled = true,
): StreamdownChildren {
  return useMemo(
    () => (enabled ? getSafeStreamdownChildren(children) : children),
    [children, enabled],
  );
}
```

2. **`core/streamdown/components.tsx`** — `SafeMessageResponse` 加 `safeEnabled` prop：
```typescript
export function SafeMessageResponse({
  children,
  safeEnabled = true,
  ...props
}: MessageResponseProps & { safeEnabled?: boolean }) {
  const safeChildren = useSafeStreamdownChildren(children, safeEnabled);
  return <MessageResponse {...props}>{safeChildren}</MessageResponse>;
}
```

3. **`components/workspace/messages/markdown-content.tsx`** — 传 `safeEnabled={!isLoading}`：
```tsx
<SafeMessageResponse
  ...
  parseIncompleteMarkdown={isLoading}
  safeEnabled={!isLoading}  // 流式期跳过 preprocess
>
```

**效果**：每 token 5→1 个 O(content)（只剩 streamdown.tsx 的 capMarkdownNesting 防崩溃）。

**tradeoff**：流式期 LaTeX delimiter/深嵌套可能短暂未归一化（视觉上公式可能用 `$...$` 而非渲染态）。最终渲染（isLoading=false）跑完整 preprocess，最终正确。

**历史 commit**：`d1904007`（已退回，可重新 apply）

---

### 方案 B：port 上游 PR #2411 memo chain（减少 re-render）

**原理**：MessageListItem 无 memo → 流式时历史消息随活跃条 re-render。PR #2411 加 memo + MessageResponse equality 扩展 + rehypeFadeInBlocks（块级 fade 替代 per-word span）。

**上游 PR**：https://github.com/bytedance/deer-flow/pull/2411（open，将合并）

**改动**（7 文件）：
- `MessageListItem` 包 `memo()`（message-list-item.tsx）
- `MarkdownContent` 包 `memo()`（markdown-content.tsx）
- `MessageResponse` memo equality 扩展（+className/remarkPlugins/rehypePlugins/components）（ai-elements/message.tsx）
- `rehypeSplitWordsIntoSpans` → `rehypeFadeInBlocks`（块级 fade，DOM 节点降 ~100x）（rehype/index.ts）
- 4 调用点重命名（message-list/list-item/group/subtask-card）

**效果**：每 token render count ~20→1（PR #2411 Profiler 实测）。DOM 节点降 ~100x（块级 vs per-word）。

**注意**：PR #2411 stacked on PR #2410（Shiki worker），两者都改 message-list-item.tsx。port 时注意冲突。

**历史 commit**：`d547d3b3` + `16659a02`（已退回，可重新 apply）

---

### 方案 C：port 上游 PR #2410 Shiki Web Worker（代码高亮异步）

**原理**：Shiki 语法高亮的 TextMate tokenizer 是 CPU 密集。几百行代码块高亮一次 = 几百毫秒主线程阻塞。移到 Web Worker 不阻塞主线程。

**上游 PR**：https://github.com/bytedance/deer-flow/pull/2410（open，将合并）

**改动**（3 文件）：
- `core/shiki/worker.ts`（新 77 行）：Shiki codeToHtml 移入 Worker
- `core/shiki/client.ts`（新 104 行）：单例 Worker + Promise + generation counter
- `ai-elements/code-block.tsx`：删主线程 highlightCode，改用 highlightInWorker

**效果**：含代码块的流式响应帧率 ≥50fps（PR 描述实测）。

**对给排水计算书效果**：边际（代码块少，主瓶颈是 LaTeX preprocess + KaTeX）。

---

### 方案 D：useDeferredValue 节流 streamdown re-tokenize

**原理**：streamdown 1.4.0 无节流（没有 useDeferredValue/useTransition/rAF），每 token 都全量 tokenize。useDeferredValue 把 content 更新降为 non-urgent，React 空闲时推进。

**改动**（1 文件）：
```typescript
// markdown-content.tsx
import { useDeferredValue } from "react";
const deferredContent = useDeferredValue(content);
const normalizedContent = useMemo(
  () => preprocessStreamdownMarkdown(deferredContent),
  [deferredContent],
);
```

**效果**：减少 tokenize + preprocess 频率（每帧最多 1 次，非每 token）。但每次仍跑完整 preprocess（与方案 A 叠加更有效）。

**tradeoff**：显示内容稍滞后 LLM 输出（几十 ms，通常无感）。

**历史 commit**：`64cd0d5a`（已退回，可重新 apply）

---

### 方案 E：SSE values 缓冲（传输层优化）

**原理**：useStream 的 trackStreamMode 把 `values` 加回 streamMode 请求，后端 worker.py 每 node 发全量消息历史快照。sse_consumer buffer values，只 end 前补发最终。

**改动**（1 文件 services.py + 回归测试）：
- `app/gateway/services.py` sse_consumer：buffer values events（pending_values_entry），END_SENTINEL 前补发
- 回环境变量 `GATEWAY_SSE_DROP_VALUES` 控制（默认 true）

**效果**：减少 SSE payload + 前端 mergeMessages 不每 event 处理全量。

**对前端渲染卡的影响**：边际（与 preprocess 链不同层，减少 mergeMessages 输入但不减少 preprocess 的 O(content)）。

**历史 commit**：`c3ff376f`（已退回，可重新 apply）

---

## 三、推荐实施顺序

| 步骤 | 方案 | 预期效果 | 偏离上游 |
|------|------|----------|---------|
| 1 | **方案 A**（preprocess 跳过） | **砍 5→1 个 O(content)/token**，直接解根因 | 3 文件 ~15 行（safeEnabled 开关） |
| 2 | **方案 B**（PR #2411 memo） | render count ~20→1 + DOM 降 ~100x | 上游 PR（将合并），不算偏离 |
| 3 | **方案 C**（PR #2410 Shiki worker） | 代码块高亮不阻塞主线程 | 上游 PR（将合并） |
| 4 | 方案 D（useDeferredValue） | 节流 tokenize 频率 | 1 文件（偏离） |
| 5 | 方案 E（SSE buffer） | 减少 payload | 1 文件（偏离） |

**建议**：先实施 **A**（根因解，最小改动），测试效果。如果不够，叠加 **B**（上游 PR #2411）。C/D/E 视情况追加。

---

## 四、验证方法

1. **流式卡顿**：触发给排水计算书报告生成（15-30K 字符 + LaTeX + 表格），确认流式期页面/输入框流畅
2. **最终渲染**：确认结束后 LaTeX 公式 / 表格 / 深嵌套都正确（最终渲染跑完整 preprocess）
3. **React DevTools Profiler**（可选）：确认每 token 只活跃条 re-render（方案 B 后 render count ~1）

---

## 五、上游对齐说明

- 方案 A（preprocess 跳过）：本地补丁。preprocess 链是 upstream sync（3a54b68b）引入。等上游优化后可对齐。
- 方案 B/C（PR #2411/#2410）：上游 open PR，将合并。port 后等上游合并即可对齐。
- 方案 D/E：本地补丁。等上游优化后可移除。

所有方案都可通过 `GATEWAY_SSE_DROP_VALUES`（方案 E）或 `safeEnabled`（方案 A）开关回退到上游行为。

---

## 六、附录：为什么其他修复不够

| 修复 | 解决的瓶颈 | 为何单独不够 |
|------|-----------|-------------|
| SSE buffer（E） | 传输层（values payload） | 与渲染层 preprocess 无关 |
| memo chain（B） | re-render 次数（历史消息） | 活跃条每次 render 的 preprocess 仍在 |
| useDeferredValue（D） | tokenize 频率（节流） | 频率降低但每次仍跑 5 个 O(content) |
| **preprocess 跳过（A）** | **preprocess 链本身** | **直接砍 7月16回归根因** |

卡顿是 **7月16后引入的 preprocess 链**（每 token 多了 4 个 O(content) 全文扫描）。方案 A 直接跳过这条链（流式期），其他方案解决的是传输/re-render/频率等次要瓶颈。
