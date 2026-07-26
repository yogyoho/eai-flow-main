# 文档空间右侧 AI 助手重新定位 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 DocAIAgentPanel 从"4 pill 模式 + 轻量消息列表"重构为"无 pill 统一入口 + 复用对话页 MessageList + 结构化操作卡片 + anchor 匹配引擎"

**Architecture:** 分三层——编辑器层（PersonalBlockNoteEditor 暴露 anchor/match/apply API）、面板层（DocAIAgentPanel 负责 prompt 构建 + 流解析 + 操作卡片渲染）、消息层（复用对话页 MessageList 渲染分析文本）

**Tech Stack:** React 19, TypeScript, BlockNote 0.51, LangGraph SDK useStream, streamdown

---

## File Map

| 文件 | 职责 |
|------|------|
| `PersonalBlockNoteEditor.tsx` | 新增 3 个 API：`getBlockAnchors()` / `matchAnchor()` / `applyOperations()` / `scrollToAnchor()` |
| `DocAIAgentPanel.tsx` | 完全重构：删除 pill/StreamMessageList → 接入 MessageList + 欢迎页 + 操作卡片 + operations 解析 |
| `DocumentManagement.tsx` | Props 适配：删除 pill 相关传递，新增 MessageList 所需数据流 |

---

### Task 1: PersonalBlockNoteEditor — add `getBlockAnchors()`

**Files:**
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx`

- [ ] **Step 1: Add `Anchor` type and `getBlockAnchors` to the interface**

In `PersonalBlockNoteEditorRef` (line ~32), add:

```typescript
/** Anchor for agent operation targeting — text→block mapping. */
export interface DocAnchor {
  text: string;        // first 60 chars
  blockIndex: number;  // 0-based position in editor.document
  blockType: string;   // "heading" | "paragraph" | "bulletListItem" | etc.
  headingLevel?: number;
}

export interface DocOperation {
  op: "replace" | "insert_after" | "delete" | "prepend" | "append";
  anchor?: string;     // text to match; omitted for prepend/append
  content?: string;    // new markdown content; omitted for delete
  autoApply: boolean;
}

export interface PersonalBlockNoteEditorRef {
  // existing methods...
  getBlockAnchors: () => DocAnchor[];
  matchAnchor: (text: string) => { blockId: string; blockIndex: number } | null;
  applyOperations: (ops: DocOperation[]) => void;
  scrollToAnchor: (text: string) => boolean;
}
```

- [ ] **Step 2: Implement `getBlockAnchors()` in `useImperativeHandle`**

```typescript
getBlockAnchors: () => {
  return editor.document.map((b, i) => {
    let text = "";
    if (Array.isArray(b.content)) {
      text = b.content
        .filter((c: any) => c.type === "text")
        .map((c: any) => c.text || "")
        .join("");
    }
    const anchor: DocAnchor = {
      text: text.slice(0, 60),
      blockIndex: i,
      blockType: b.type,
    };
    if (b.type === "heading" && b.props?.level) {
      anchor.headingLevel = b.props.level as number;
    }
    return anchor;
  });
},
```

- [ ] **Step 3: Implement `matchAnchor()` in `useImperativeHandle`**

Match rules from spec §7 — exact, prefix, contains, fuzzy.

```typescript
matchAnchor: (text: string) => {
  const doc = editor.document;
  if (!text) return null;
  const trimmed = text.trim();

  // 1. Exact match
  for (let i = 0; i < doc.length; i++) {
    const b = doc[i];
    if (!Array.isArray(b.content)) continue;
    const fullText = b.content.filter((c: any) => c.type === "text").map((c: any) => c.text || "").join("");
    if (fullText.trim() === trimmed) return { blockId: b.id, blockIndex: i };
  }

  // 2. Prefix match
  for (let i = 0; i < doc.length; i++) {
    const b = doc[i];
    if (!Array.isArray(b.content)) continue;
    const fullText = b.content.filter((c: any) => c.type === "text").map((c: any) => c.text || "").join("");
    if (fullText.trim().startsWith(trimmed)) return { blockId: b.id, blockIndex: i };
  }

  // 3. Contains match (exactly one)
  let containsMatch: { blockId: string; blockIndex: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    const b = doc[i];
    if (!Array.isArray(b.content)) continue;
    const fullText = b.content.filter((c: any) => c.type === "text").map((c: any) => c.text || "").join("");
    if (fullText.includes(trimmed)) {
      if (containsMatch) return null; // ambiguous —  caller will handle multi-match
      containsMatch = { blockId: b.id, blockIndex: i };
    }
  }
  if (containsMatch) return containsMatch;

  // 4. Fuzzy (Levenshtein < 30%)
  // ponytail: simple Levenshtein, skip if text is very short
  if (trimmed.length < 5) return null;
  let best: { blockId: string; blockIndex: number; dist: number } | null = null;
  for (let i = 0; i < doc.length; i++) {
    const b = doc[i];
    if (!Array.isArray(b.content)) continue;
    const fullText = b.content.filter((c: any) => c.type === "text").map((c: any) => c.text || "").join("").slice(0, 80);
    const dist = levenshteinDistance(trimmed, fullText);
    if (dist / trimmed.length < 0.3 && (!best || dist < best.dist)) {
      best = { blockId: b.id, blockIndex: i, dist };
    }
  }
  return best ? { blockId: best.blockId, blockIndex: best.blockIndex } : null;
},
```

Add `levenshteinDistance` as a module-level helper (not inside the component — pure function):

```typescript
// ponytail: simple Levenshtein for fuzzy anchor matching.
function levenshteinDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  const dp = new Uint16Array(n + 1);
  for (let j = 0; j <= n; j++) dp[j] = j;
  for (let i = 1; i <= m; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const temp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? prev : 1 + Math.min(prev, dp[j], dp[j - 1]);
      prev = temp;
    }
  }
  return dp[n];
}
```

- [ ] **Step 4: Restart frontend and verify `getBlockAnchors()` works in console**

```bash
docker compose -p eai-docker restart frontend
```

Open browser dev console on a docmgr page with a document open, verify `getBlockAnchors()` returns expected anchor array.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx
git commit -m "feat(docmgr): add getBlockAnchors + matchAnchor to PersonalBlockNoteEditor"
```

---

### Task 2: PersonalBlockNoteEditor — add `applyOperations()` and `scrollToAnchor()`

**Files:**
- Modify: `frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx`

- [ ] **Step 1: Implement `scrollToAnchor()` in `useImperativeHandle`**

```typescript
scrollToAnchor: (text: string) => {
  const match = matchAnchorInternal(text);
  if (!match) return false;
  const el = document.querySelector(`[data-id="${match.blockId}"]`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  // highlight briefly
  el.classList.add("ring-2", "ring-primary", "ring-offset-2");
  setTimeout(() => el.classList.remove("ring-2", "ring-primary", "ring-offset-2"), 2000);
  return true;
},
```

(`matchAnchorInternal` is the same logic as `matchAnchor` but returns `{ blockId, blockIndex } | null` — extract the shared logic into a helper to avoid duplication.)

- [ ] **Step 2: Implement `applyOperations()` in `useImperativeHandle`**

```typescript
applyOperations: (ops: DocOperation[]) => {
  for (const op of ops) {
    const parsed = editor.tryParseMarkdownToBlocks(op.content ?? "");
    if (parsed.length === 0) continue;

    switch (op.op) {
      case "replace": {
        if (!op.anchor) continue;
        const match = matchAnchorInternal(op.anchor);
        if (!match) continue;
        editor.replaceBlocks([match.blockId], parsed);
        break;
      }
      case "insert_after": {
        if (!op.anchor) continue;
        const match = matchAnchorInternal(op.anchor);
        if (!match) continue;
        editor.insertBlocks(parsed, match.blockId, "after");
        break;
      }
      case "delete": {
        if (!op.anchor) continue;
        const match = matchAnchorInternal(op.anchor);
        if (!match) continue;
        editor.removeBlocks([match.blockId]);
        break;
      }
      case "prepend": {
        editor.insertBlocks(parsed, editor.document[0]?.id ?? "", "before");
        break;
      }
      case "append": {
        const lastBlock = editor.document[editor.document.length - 1];
        if (lastBlock) {
          editor.insertBlocks(parsed, lastBlock.id, "after");
        }
        break;
      }
    }
  }
},
```

- [ ] **Step 3: Extract shared match logic into module-level helper**

Move the match logic used by both `matchAnchor` and `scrollToAnchor` and `applyOperations` into a helper:

```typescript
function findBlockByAnchor(doc: any[], anchor: string): { blockId: string; blockIndex: number } | null {
  // same logic as matchAnchor above
  // ... (copy the implementation from Task 1 Step 3, returning {blockId, blockIndex})
}
```

Then call `findBlockByAnchor(editor.document, text)` from each of `matchAnchor`, `scrollToAnchor`, `applyOperations`.

- [ ] **Step 4: Restart frontend and smoke test**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/PersonalBlockNoteEditor.tsx
git commit -m "feat(docmgr): add applyOperations + scrollToAnchor to PersonalBlockNoteEditor"
```

---

### Task 3: DocAIAgentPanel — remove pills, add welcome page

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`

- [ ] **Step 1: Delete pill-related code**

Remove:
- `AIMode` type + `MODE_CONFIG`
- `mode` state + `modeRef`
- `handleModeSwitch` function
- Mode pills JSX (lines 210-231 in current file)
- `prompts[modeRef.current]` in submit effect (replace with unified prompt)

- [ ] **Step 2: Replace the mode pills section with nothing (removed)**

The header now has only: `[Sparkles icon] AI 助手` + `[新对话]` + `[X 关闭]`.

- [ ] **Step 3: Add welcome page component**

Replace the empty-state JSX (when `subThreadId` is null) with the welcome page:

```tsx
function WelcomePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center">
      <div className="text-4xl mb-4">🤖</div>
      <div className="text-base font-semibold text-foreground mb-6">文档 AI 助手</div>

      <div className="w-full text-left space-y-4 text-sm text-muted-foreground">
        <div>
          <div className="font-medium text-foreground mb-1.5">📝 内容协作</div>
          <ul className="space-y-1 text-xs">
            <li>"给第3节加一段安全措施"</li>
            <li>"把设计参数表格改成文字描述"</li>
            <li>"在文档末尾补充结论"</li>
          </ul>
        </div>
        <div>
          <div className="font-medium text-foreground mb-1.5">🔍 文档审查</div>
          <ul className="space-y-1 text-xs">
            <li>"检查公式编号是否连续"</li>
            <li>"这段计算逻辑有没有问题"</li>
            <li>"全文的术语使用是否统一"</li>
          </ul>
        </div>
        <div>
          <div className="font-medium text-foreground mb-1.5">✨ 格式修正（自动应用）</div>
          <ul className="space-y-1 text-xs">
            <li>"统一中英文之间的空格"</li>
            <li>"修正标题层级"</li>
          </ul>
        </div>
      </div>

      <div className="mt-6 text-xs text-muted-foreground/70 leading-relaxed">
        操作有预览，你可以逐条确认或拒绝。<br />
        格式修正类操作会自动应用，可一键撤销。
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire welcome page into the render tree**

```tsx
{/* Messages area */}
<div className="flex-1 overflow-y-auto">
  {subThreadId ? (
    <MessageList ... />
  ) : (
    <WelcomePage />
  )}
</div>
```

- [ ] **Step 5: Update `handleSubmit` — remove mode-dependent prompt, use unified prompt**

```typescript
const handleSubmit = useCallback(async () => {
  // ... (existing sync + ensureThread logic unchanged)

  await ensureThread();
  pendingRef.current = { message: trimmed, modelName };
  setSubmitTick((v) => v + 1);
}, [isCreating, ensureThread, modelName, editorRef, threadId, docRelPath]);
```

And in the submit effect, replace `prompts[modeRef.current]` with the unified system prompt from spec §5.

- [ ] **Step 6: Restart frontend and verify**

```bash
docker compose -p eai-docker restart frontend
```

Open docmgr → verify no pills, welcome page shows when no conversation.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAIAgentPanel.tsx
git commit -m "refactor(docmgr): remove mode pills, add welcome page to AI panel"
```

---

### Task 4: DocAIAgentPanel — build unified system prompt

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`

- [ ] **Step 1: Add `buildPrompt()` helper function**

```typescript
function buildPrompt(params: {
  docTitle: string;
  docContent: string;
  anchors: string;       // plain-text anchor index
  userMessage: string;
}): string {
  return `你是一个文档助手。当用户提出请求时，按以下规则输出：

**输出格式**：你的回复由两部分组成，用分隔符 \`---OPERATIONS---\` 隔开：

[你的分析/建议/回答文本，Markdown 格式]

---OPERATIONS---
[可选的 JSON 操作数组，如不需要操作则省略此行及之后所有内容]

**操作类型**：
• replace:   替换匹配文本所在的 block
• insert_after: 在匹配文本后插入新 block
• delete:    删除匹配的 block(s)
• prepend:   在文档开头插入
• append:    在文档末尾追加

**操作定位**：使用 \`anchor\` 字段匹配文本（标题文字或段落开头前20字），不要用 block ID。

**格式修正类操作**：如果修改纯属格式规范化（中英文空格、标点统一、标题层级、列表缩进），设置 \`autoApply: true\`。涉及内容增删改的，设置 \`autoApply: false\`。

**审查/分析类请求**：输出分析文本即可，不需要 operations 块。

示例输出：
\`\`\`
发现以下问题：

1. 第3节标题"实际参数"不够准确，建议改为"设计参数分析"
2. 中英文之间应加空格

---OPERATIONS---
[{"op":"replace","anchor":"实际参数","content":"## 设计参数分析","autoApply":false},{"op":"replace","anchor":"## 设计参数分析","content":"## 设计参数分析\\n\\n根据GB/T 50746-2012...","autoApply":true}]
\`\`\`

**文档锚点索引**（定位用，不要输出这些内容）：
${params.anchors}

**当前文档全文**：
\`\`\`markdown
${params.docContent}
\`\`\`

**用户指令**：${params.userMessage}`;
}
```

- [ ] **Step 2: Wire `buildPrompt` into the submit effect**

In the submit effect (where `pendingRef.current` is consumed):

```typescript
const fn = async () => {
  const docContent = (await editorRef.current?.getMarkdown()) ?? "";
  const anchors = (editorRef.current?.getBlockAnchors() ?? [])
    .map((a, i) => `[${i}] ${a.blockType === "heading" ? "H" + (a.headingLevel ?? 1) : "P"} "${a.text}"`)
    .join("\n");

  const prompt = buildPrompt({
    docTitle,
    docContent,
    anchors,
    userMessage: message,
  });

  streamState.submit(
    { messages: [{ type: "human", content: prompt }] },
    { configurable: { ...(mn ? { model_name: mn } : {}) }, recursion_limit: 250 },
  );
};
fn();
```

- [ ] **Step 3: Remove old `prompts` object and `modeRef.current` references**

Delete the `prompts` Record and any remaining mode-related code.

- [ ] **Step 4: Restart frontend and verify prompt**

```bash
docker compose -p eai-docker restart frontend
```

Send a test message in the AI panel, check browser network tab — the prompt should contain the unified system prompt with anchors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAIAgentPanel.tsx
git commit -m "feat(docmgr): unified system prompt with anchor index + operations format"
```

---

### Task 5: DocAIAgentPanel — replace StreamMessageList with chat MessageList

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`

- [ ] **Step 1: Import MessageList and related types**

```typescript
import { MessageList } from "@/components/workspace/messages/message-list";
// Also need thread state types for MessageList props
```

Before writing the import, check what props `MessageList` actually needs by reading its interface in `src/components/workspace/messages/message-list.tsx`.

- [ ] **Step 2: Build the messages array from streamState for MessageList**

`MessageList` expects `messages` in a specific format. The current `StreamMessageList` reads from `streamState.messages`. Build a compatible messages array:

```typescript
const displayMessages = useMemo(() => {
  if (!streamState?.messages) return [];
  return streamState.messages
    .filter((m: any) => {
      if (m.additional_kwargs?.hide_from_ui) return false;
      return m.type === "human" || m.type === "ai";
    });
}, [streamState?.messages]);
```

- [ ] **Step 3: Render MessageList instead of StreamMessageList**

```tsx
{subThreadId ? (
  <MessageList
    messages={displayMessages}
    isLoading={streamState?.isLoading ?? false}
    // Disable features not relevant in side panel:
    hideBranchActions
    hideGoalStatus
    hideThreadTitle
  />
) : (
  <WelcomePage />
)}
```

- [ ] **Step 4: Delete `StreamMessageList` and `toDisplayText`**

Remove these from the file.

- [ ] **Step 5: Restart frontend and verify**

```bash
docker compose -p eai-docker restart frontend
```

Send a message and verify the response renders with full Markdown (headings, lists, code blocks, formulas).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAIAgentPanel.tsx
git commit -m "feat(docmgr): replace StreamMessageList with shared MessageList in AI panel"
```

---

### Task 6: DocAIAgentPanel — add operation card rendering

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocAIAgentPanel.tsx`

- [ ] **Step 1: Add `parseOperations()` helper**

```typescript
function parseOperations(text: string): { analysis: string; operations: DocOperation[] | null; parseError: string | null } {
  const idx = text.indexOf("---OPERATIONS---");
  if (idx === -1) return { analysis: text, operations: null, parseError: null };

  const analysis = text.slice(0, idx).trim();
  const opsPart = text.slice(idx + "---OPERATIONS---".length).trim();

  if (!opsPart) return { analysis, operations: [], parseError: null };

  try {
    const ops = JSON.parse(opsPart);
    if (!Array.isArray(ops)) return { analysis, operations: null, parseError: "操作指令不是数组格式" };
    return { analysis, operations: ops as DocOperation[], parseError: null };
  } catch {
    return { analysis, operations: null, parseError: "操作指令 JSON 解析失败" };
  }
}
```

- [ ] **Step 2: Add `OperationCards` component**

Render autoApply operations as a merged notification card, and manual operations as individual confirm cards (per spec §8).

```tsx
function OperationCards({
  operations,
  onApply,
  onPreview,
}: {
  operations: DocOperation[];
  onApply: (op: DocOperation, index: number) => void;
  onPreview: (op: DocOperation) => void;
}) {
  const autoOps = operations.filter((o) => o.autoApply);
  const manualOps = operations.filter((o) => !o.autoApply);

  return (
    <div className="space-y-2 mt-3">
      {autoOps.length > 0 && (
        <AutoApplyCard operations={autoOps} onUndo={() => { /* TBD */ }} />
      )}
      {manualOps.map((op, i) => (
        <ConfirmCard
          key={i}
          operation={op}
          onApply={() => onApply(op, i)}
          onPreview={() => onPreview(op)}
          onSkip={() => {}}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Implement `AutoApplyCard`**

```tsx
function AutoApplyCard({ operations, onUndo }: { operations: DocOperation[]; onUndo: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-base">🔧</span>
        <span className="font-medium text-foreground">已自动应用 {operations.length} 项格式修正</span>
      </div>
      <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-0.5">
        {operations.map((op, i) => (
          <li key={i}>{op.content?.slice(0, 80) || op.op}</li>
        ))}
      </ol>
      <button
        onClick={() => { onUndo(); setDismissed(true); }}
        className="text-xs text-primary hover:underline mt-2"
      >
        撤销此次自动修正
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Implement `ConfirmCard`**

```tsx
function ConfirmCard({
  operation,
  onApply,
  onPreview,
  onSkip,
}: {
  operation: DocOperation;
  onApply: () => void;
  onPreview: () => void;
  onSkip: () => void;
}) {
  const [status, setStatus] = useState<"pending" | "applied" | "skipped" | "failed">("pending");

  const handleApply = () => {
    try {
      onApply();
      setStatus("applied");
    } catch {
      setStatus("failed");
    }
  };

  if (status === "skipped") return null;

  return (
    <div className="rounded-lg border border-border bg-card p-3 text-sm">
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-sm">✏️</span>
        <span className="font-medium text-foreground">
          {operation.op === "delete" ? "删除" : operation.op === "insert_after" ? "插入" : "替换"}: "
          {operation.anchor?.slice(0, 30) || "文档开头/末尾"}"
        </span>
        {status === "applied" && <span className="text-xs text-green-600 ml-auto">✅ 已应用</span>}
        {status === "failed" && <span className="text-xs text-red-500 ml-auto">❌ 失败</span>}
      </div>

      {operation.op !== "delete" && (
        <div className="text-xs text-muted-foreground bg-muted/50 rounded p-2 mb-2 max-h-20 overflow-y-auto">
          <pre className="whitespace-pre-wrap font-mono">{operation.content?.slice(0, 200)}</pre>
        </div>
      )}

      {status === "pending" && (
        <div className="flex gap-1.5">
          <button onClick={onPreview} className="text-xs px-2 py-1 rounded bg-muted hover:bg-muted/80">预览定位📍</button>
          <button onClick={handleApply} className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground hover:opacity-90">✅ 应用</button>
          <button onClick={() => { onSkip(); setStatus("skipped"); }} className="text-xs px-2 py-1 rounded bg-muted hover:bg-muted/80">✕ 跳过</button>
        </div>
      )}
      {status === "applied" && (
        <button onClick={() => { /* undo logic */ }} className="text-xs text-primary hover:underline">撤销</button>
      )}
      {status === "failed" && (
        <button onClick={handleApply} className="text-xs text-primary hover:underline">重试</button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Wire `parseOperations` and `OperationCards` into the message rendering**

In the area where AI messages are rendered (below `MessageList`), after each AI message, check if its content contains `---OPERATIONS---`:

```tsx
// Inside the message rendering area, after MessageList:
{lastAIMessageText && (() => {
  const { operations, parseError } = parseOperations(lastAIMessageText);
  if (parseError) {
    return <div className="text-xs text-muted-foreground p-2">⚠️ {parseError}</div>;
  }
  if (operations && operations.length > 0) {
    // First, auto-apply the autoApply operations
    const autoOps = operations.filter(o => o.autoApply);
    if (autoOps.length > 0) {
      editorRef.current?.applyOperations(autoOps);
    }
    return (
      <OperationCards
        operations={operations}
        onApply={(op) => editorRef.current?.applyOperations([op])}
        onPreview={(op) => editorRef.current?.scrollToAnchor(op.anchor ?? "")}
      />
    );
  }
  return null;
})()}
```

- [ ] **Step 6: Restart frontend and test operation cards**

```bash
docker compose -p eai-docker restart frontend
```

Send a message like "把第3节标题改为'测试标题'" and verify the operation card appears.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/extensions/docmgr/DocAIAgentPanel.tsx
git commit -m "feat(docmgr): add operation card rendering (autoApply + confirm) to AI panel"
```

---

### Task 7: DocumentManagement — simplify props

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

- [ ] **Step 1: Remove pill-related props from DocAIAgentPanel usage**

Find the `DocAIAgentPanel` JSX in `DocumentManagement.tsx` (around line 1378-1398). Remove any props related to modes.

- [ ] **Step 2: Pass `editorRef` and any new callbacks**

Ensure `editorRef` is already passed (it should be — check existing code). If `MessageList` needs additional context, pass it through.

- [ ] **Step 3: Verify props compatibility**

`DocAIAgentPanel` should receive:
- `docTitle`, `docRelPath`, `threadId` — existing, keep
- `editorRef` — existing, keep
- `onClose` — existing, keep
- `subThreadId`, `ensureThread`, `isCreating`, `resetThread` — existing, keep

No new props needed from `DocumentManagement` — the editor bridge is already there.

- [ ] **Step 4: Restart frontend and smoke test full flow**

```bash
docker compose -p eai-docker restart frontend
```

Open a document → open AI panel → send a message → verify response renders with MessageList → verify operation cards work.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "refactor(docmgr): simplify DocAIAgentPanel props after pill removal"
```

---

### Task 8: End-to-end verification

- [ ] **Step 1: Verify full flow — no conversation**

Open docmgr → open a document → open AI panel → should show welcome page with three sections and explanation text.

- [ ] **Step 2: Verify full flow — simple conversation**

Type "总结这篇文档的主要内容" → should stream response with full Markdown rendering (formulas, headings, lists).

- [ ] **Step 3: Verify full flow — content operation (manual confirm)**

Type "把第3节标题改为'新标题'" → should show analysis text + confirm card with preview/apply/skip buttons. Click preview → editor should scroll to anchor. Click apply → editor block should be replaced.

- [ ] **Step 4: Verify full flow — format operation (auto apply)**

Type "统一中英文之间的空格" → should auto-apply and show merged notification card with undo button.

- [ ] **Step 5: Verify full flow — review only (no operations)**

Type "检查这段逻辑有没有问题" → should show analysis text only, no operation cards.

- [ ] **Step 6: Verify error handling**

Force an error scenario — e.g., send a message that might produce malformed JSON after `---OPERATIONS---` → should show analysis text + "⚠️ 操作指令解析失败" card.

---

### Implementation Order

```
Task 1: PersonalBlockNoteEditor — matchAnchor + getBlockAnchors
    ↓
Task 2: PersonalBlockNoteEditor — applyOperations + scrollToAnchor
    ↓
Task 3: DocAIAgentPanel — remove pills + welcome page
    ↓
Task 4: DocAIAgentPanel — unified system prompt
    ↓
Task 5: DocAIAgentPanel — MessageList (replace StreamMessageList)
    ↓
Task 6: DocAIAgentPanel — operation cards (parse + render)
    ↓
Task 7: DocumentManagement — props cleanup
    ↓
Task 8: End-to-end verification
```

Tasks 1-2 are foundational (editor API). Tasks 3-6 build the panel incrementally. Task 7 is cleanup. Task 8 verifies everything.
