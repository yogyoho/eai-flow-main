# 文档空间（我的文档）— 右侧 AI 助手 P0 完善 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为「我的文档」Tiptap 编辑器的右侧 AI 助手补齐 4 项核心能力：流式输出、无选中快捷操作、插入到光标、对话持久化。

**Architecture:** 后端新增 SSE 流式端点（`astream` 替代 `ainvoke`）；前端 `AIEditPanel` 渐进增强——新增流式读取、段落上下文获取、插入模式、对话缓存。`TiptapEditorRef` 接口扩增 `insertAtCursor` 和 `getCursorParagraph` 两个方法。

**Tech Stack:** Python/FastAPI (后端 SSE), TypeScript/React (前端), Tiptap/ProseMirror (编辑器)

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `backend/app/extensions/docmgr/routers.py` | 新增 `POST /documents/ai-edit/stream` SSE 端点 | 修改 |
| `frontend/src/extensions/docmgr/TiptapEditor.tsx` | 扩增 `TiptapEditorRef`：`insertAtCursor` + `getCursorParagraph` | 修改 |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | `AIEditPanel` 流式+快捷操作+插入+缓存；`DocumentEditor` 透传新 props | 修改 |
| `frontend/src/extensions/api/index.ts` | 新增 `docmgrApi.aiEditStream()` | 修改 |

---

### Task 1: 后端 — 新增 SSE 流式端点

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py`

- [ ] **Step 1: 在 `routers.py` 顶部新增 `StreamingResponse` import**

```python
# 在现有 imports 下方添加
from fastapi.responses import StreamingResponse
```

修改位置：第 9 行 `from fastapi import APIRouter, Depends, HTTPException, Query, status` 之后。

- [ ] **Step 2: 新增 `AIEditStreamRequest` schema 和流式端点函数**

在 `AI_EDIT_TIMEOUT_SECONDS = 120`（第 496 行）之后，`_extract_ai_response_text` 函数之前，添加：

```python
class AIEditStreamRequest(BaseModel):
    """AI edit stream request schema."""

    text: str = Field(..., min_length=1, description="The text to process")
    operation: str = Field(..., description="polish | expand | condense | brainstorm")
    model_name: str | None = Field(None, description="Optional model override")


@router.post("/documents/ai-edit/stream")
async def ai_edit_text_stream(
    request: AIEditStreamRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Stream AI operation result as SSE text/event-stream."""
    prompt_template = OPERATION_PROMPTS.get(request.operation)
    if not prompt_template:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operation: {request.operation}. Must be one of: {list(OPERATION_PROMPTS.keys())}",
        )

    prompt = prompt_template.format(text=request.text)

    from deerflow.models import create_chat_model

    model = create_chat_model(name=request.model_name, thinking_enabled=False)

    async def generate():
        try:
            async for chunk in model.astream(prompt):
                text = _extract_ai_response_text(chunk.content).strip()
                if text:
                    yield f"data: {json.dumps({'token': text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.exception("AI edit stream failed: operation=%s err=%s", request.operation, exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
        },
    )
```

还需要在文件顶部添加 `import json`（如果尚未导入）。

- [ ] **Step 3: 重启 Gateway 验证端点可用**

```bash
docker compose -p eai-docker restart gateway
```

验证：
```bash
curl -X POST http://localhost:2026/api/docmgr/documents/ai-edit/stream \
  -H "Content-Type: application/json" \
  -d '{"text":"你好世界","operation":"polish"}' \
  --no-buffer
```

预期：看到 SSE 流式输出 `data: {"token": "你好，世界"}\n\ndata: [DONE]\n\n`

- [ ] **Step 4: 提交**

```bash
git add backend/app/extensions/docmgr/routers.py
git commit -m "feat(docmgr): add SSE streaming endpoint for AI edit"
```

---

### Task 2: 前端 API — 新增流式请求方法

**Files:**
- Modify: `frontend/src/extensions/api/index.ts`

- [ ] **Step 1: 在 `docmgrApi` 对象中新增 `aiEditStream` 方法**

在 `aiEdit` 方法（约第 456-464 行）之后添加：

```typescript
aiEditStream: (
  data: {
    text: string;
    operation: "polish" | "expand" | "condense" | "brainstorm";
    model_name?: string;
  },
  onToken: (token: string) => void,
  signal?: AbortSignal,
): Promise<string> =>
  new Promise((resolve, reject) => {
    const fullUrl = `${BASE_URL}/docmgr/documents/ai-edit/stream`;
    fetch(fullUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal,
      credentials: "include",
    })
      .then(async (response) => {
        if (!response.ok) {
          const err = await response.text().catch(() => "Unknown error");
          reject(new Error(`AI stream failed: ${response.status} ${err}`));
          return;
        }
        const reader = response.body?.getReader();
        if (!reader) { reject(new Error("No response body")); return; }
        const decoder = new TextDecoder();
        let buffer = "";
        let fullText = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;
            const data = trimmed.slice(6);
            if (data === "[DONE]") continue;
            try {
              const parsed = JSON.parse(data);
              if (parsed.token) {
                fullText += parsed.token;
                onToken(parsed.token);
              }
              if (parsed.error) {
                reject(new Error(parsed.error));
                return;
              }
            } catch { /* skip malformed lines */ }
          }
        }
        resolve(fullText);
      })
      .catch(reject);
  }),
```

确认 `BASE_URL` 变量已在文件顶部定义。在该文件中搜索 `const BASE_URL` 确认。

- [ ] **Step 2: 提交**

```bash
git add frontend/src/extensions/api/index.ts
git commit -m "feat(docmgr): add aiEditStream method for SSE streaming"
```

---

### Task 3: TiptapEditor — 扩增 ref 接口

**Files:**
- Modify: `frontend/src/extensions/docmgr/TiptapEditor.tsx`

- [ ] **Step 1: 在 `TiptapEditorRef` interface 中新增两个方法**

修改第 39-47 行的 `TiptapEditorRef` interface：

```typescript
export interface TiptapEditorRef {
  getMarkdown: () => string;
  getSelectedText: () => string;
  replaceSelection: (text: string) => void;
  insertAtCursor: (text: string) => void;
  getCursorParagraph: () => string;
  focus: () => void;
  getEditor: () => Editor | null;
  scrollToSection: (sectionId: string) => boolean;
  getHeadings: () => HeadingItem[];
}
```

新增两行：`insertAtCursor: (text: string) => void;` 和 `getCursorParagraph: () => string;`

- [ ] **Step 2: 在 `useImperativeHandle` 中实现这两个方法**

修改第 411-430 行的 `useImperativeHandle`：

```typescript
useImperativeHandle(ref, () => ({
  getMarkdown: () => {
    if (!editor) return "";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return decodeMath((editor.storage as any).markdown.getMarkdown() as string);
  },
  getSelectedText: () => {
    if (!editor) return "";
    const { from, to } = editor.state.selection;
    return editor.state.doc.textBetween(from, to, " ");
  },
  replaceSelection: (text: string) => {
    if (!editor) return;
    editor.chain().focus().deleteSelection().insertContent(text).run();
  },
  insertAtCursor: (text: string) => {
    if (!editor) return;
    const { from } = editor.state.selection;
    editor.chain().focus().setTextSelection(from).insertContent(text).run();
  },
  getCursorParagraph: () => {
    if (!editor) return "";
    const { $from } = editor.state.selection;
    // Walk up from cursor to find the nearest text block (paragraph/heading/listItem/...)
    for (let depth = $from.depth; depth > 0; depth--) {
      const node = $from.node(depth);
      if (node.isTextblock) {
        return node.textContent;
      }
    }
    return "";
  },
  focus: () => { editor?.commands.focus(); },
  getEditor: () => editor,
  scrollToSection,
  getHeadings,
}));
```

关键变更：
- `replaceSelection`: 新增 `.deleteSelection()` 确保先清除选中再插入（ProseMirror 的 `insertContent` 本身在选中非空时会替换，但显式调用更清晰）
- `insertAtCursor`: 先把 selection 收缩到光标位置（`setTextSelection(from)`），再插入——确保永远不替换选中文字
- `getCursorParagraph`: 从光标位置向上遍历找到所在的 paragraph/heading node 并返回其文本

- [ ] **Step 3: 提交**

```bash
git add frontend/src/extensions/docmgr/TiptapEditor.tsx
git commit -m "feat(docmgr): add insertAtCursor and getCursorParagraph to TiptapEditorRef"
```

---

### Task 4: AIEditPanel — 流式输出 + 无选中快捷操作 + 插入按钮 + 对话缓存

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

- [ ] **Step 1: 更新 `DocumentEditor` 中 `AIEditPanel` 的 props 传递**

修改第 1372-1383 行的 AIEditPanel 渲染：

```tsx
<AnimatePresence>
  {showAI && (
    <motion.div initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: 360 }}
      exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.2 }}
      className="border-l border-border overflow-hidden shrink-0">
      <AIEditPanel
        docKey={docId ?? personalFile?.rel_path ?? "personal"}
        onClose={() => setShowAI(false)}
        getSelectedText={() => editorRef.current?.getSelectedText() ?? ""}
        getFullText={() => editorRef.current?.getMarkdown() ?? ""}
        getCursorParagraph={() => editorRef.current?.getCursorParagraph() ?? ""}
        onResult={(text) => editorRef.current?.replaceSelection(text)}
        onInsert={(text) => editorRef.current?.insertAtCursor(text)}
      />
    </motion.div>
  )}
</AnimatePresence>
```

- [ ] **Step 2: 更新 `AIEditPanel` 的 props interface 和函数签名**

修改第 1411-1416 行：

```typescript
function AIEditPanel({ docKey, onClose, getSelectedText, getFullText, getCursorParagraph, onResult, onInsert }: {
  docKey: string;
  onClose: () => void;
  getSelectedText: () => string;
  getFullText: () => string;
  getCursorParagraph: () => string;
  onResult: (text: string) => void;
  onInsert: (text: string) => void;
}) {
```

- [ ] **Step 3: 新增对话缓存机制**

在 `AIEditPanel` 函数体内，第 1417 行 `const [messages, setMessages]` 之前添加：

```typescript
// 对话持久化缓存：按 docKey 缓存最近 50 条消息
const chatCache = useRef<Map<string, ChatMessage[]>>(new Map());
const prevDocKey = useRef<string>(docKey);

// 切换文档时保存/恢复对话
if (prevDocKey.current !== docKey) {
  // 保存当前对话
  if (messages.length > 0) {
    chatCache.current.set(prevDocKey.current, messages.slice(-50));
  }
  // 恢复目标文档对话（或空数组）
  setMessages(chatCache.current.get(docKey) ?? []);
  prevDocKey.current = docKey;
}
```

- [ ] **Step 4: 新增流式发送逻辑，替换原有 `sendMessage`**

替换第 1467-1489 行的 `sendMessage` 函数：

```typescript
const sendMessage = async (text: string, operation?: AIOperation, displayContent?: string) => {
  const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: displayContent ?? text, operation };
  setMessages((prev) => [...prev, userMsg]);
  setInput("");
  resetInputHeight();
  setRunning(true);
  scrollToBottom();

  const assistantId = crypto.randomUUID();
  const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", content: "" };
  setMessages((prev) => [...prev, assistantMsg]);

  try {
    await docmgrApi.aiEditStream(
      { text, operation: operation ?? activeOp, model_name: modelName ?? undefined },
      (token) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + token } : m)),
        );
        scrollToBottom();
      },
    );
  } catch (e) {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId
          ? { ...m, content: `⚠️ ${e instanceof Error ? e.message : "AI 处理失败"}` }
          : m,
      ),
    );
  } finally {
    setRunning(false);
    scrollToBottom();
  }
};
```

- [ ] **Step 5: 无选中快捷操作 — 移除 disabled + 增加作用范围提示**

修改第 1556-1578 行的快捷操作 pills 区域，将整段替换为：

```tsx
{/* Quick action pills */}
<div className="px-4 py-2 border-b border-border/60 shrink-0">
  <div className="flex gap-1.5 flex-wrap">
    {AI_OPS.map(({ key, label, icon }) => (
      <button
        key={key}
        type="button"
        onClick={() => handleQuickAction(key)}
        className={cn(
          "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[13px] font-medium transition-all border",
          activeOp === key
            ? "bg-primary text-primary-foreground border-primary"
            : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        {icon}{label}
      </button>
    ))}
  </div>
  <p className="text-[11px] text-muted-foreground mt-1.5">
    {hasSelection ? "将对选中文字执行操作" : "将对全文执行操作（可选中文字后精确操作）"}
  </p>
</div>
```

- [ ] **Step 6: 更新 `handleQuickAction` 支持无选中场景**

替换第 1499-1508 行：

```typescript
const handleQuickAction = (op: AIOperation) => {
  setActiveOp(op);
  const selected = getSelectedText();
  if (selected.trim()) {
    void sendMessage(selected, op);
  } else {
    // 无选中时：润色/扩写/缩写作用于光标所在段落；头脑风暴作用于全文
    if (op === "brainstorm") {
      void sendMessage(getFullText(), op);
    } else {
      const paragraph = getCursorParagraph();
      void sendMessage(paragraph || getFullText(), op);
    }
  }
};
```

- [ ] **Step 7: 更新建议提示词 touch 全文逻辑**

替换第 1510-1515 行的 `handleSuggestedPrompt`：

```typescript
const handleSuggestedPrompt = (prompt: string) => {
  const selected = getSelectedText();
  const fullText = getFullText();
  const apiText = selected.trim()
    ? `${prompt}\n\n【选中文字】：\n${selected}`
    : `${prompt}\n\n【文档全文】：\n${fullText}`;
  void sendMessage(apiText, undefined, prompt);
};
```

- [ ] **Step 8: 在 assistant 消息操作按钮中新增"插入"按钮**

在第 1623-1639 行的操作按钮区域，替换为：

```tsx
{!msg.content.startsWith("⚠️") && (
  <div className="mt-1.5 flex gap-1.5">
    <button
      type="button"
      onClick={() => handleReplace(msg.content)}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-primary/30 text-primary text-[11px] hover:bg-primary/10 transition-colors"
    >
      <Wand2 className="w-3 h-3" />替换
    </button>
    <button
      type="button"
      onClick={() => onInsert(msg.content)}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border text-muted-foreground text-[11px] hover:bg-muted transition-colors"
    >
      <Plus className="w-3 h-3" />插入
    </button>
    <button
      type="button"
      onClick={() => handleCopy(msg.content)}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border text-muted-foreground text-[11px] hover:bg-muted transition-colors"
    >
      <Copy className="w-3 h-3" />复制
    </button>
  </div>
)}
```

需要在文件顶部 imports 中添加 `Plus` 图标（从 `lucide-react`）：

```typescript
import { ..., Plus, ... } from "lucide-react";
```

查找 `DocumentManagement.tsx` 中已有的 lucide-react import，将 `Plus` 加入已有 import 列表。

- [ ] **Step 9: 流式输出期间显示闪烁光标**

在第 1644-1648 行的运行指示器，替换为：

```tsx
{running && (
  <div className="flex items-center gap-2 text-xs text-muted-foreground">
    <Loader2 className="w-3.5 h-3.5 animate-spin" />
    <span>生成中</span>
    <span className="inline-block w-0.5 h-3.5 bg-primary animate-pulse rounded-full" />
  </div>
)}
```

- [ ] **Step 10: 提交**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): streaming output, no-selection quick actions, insert at cursor, chat persistence"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 重启前端容器**

```bash
docker compose -p eai-docker restart frontend
```

- [ ] **Step 2: 验证流式输出**

1. 打开 `http://localhost:2026`，进入「我的文档」，打开或新建一个文档
2. 点击右上角「AI 助手」打开右侧面板
3. 输入 "帮我写一段关于AI的介绍"，按 Enter 发送
4. 预期：回复逐字流式输出，光标闪烁，完成后显示 [替换][插入][复制] 按钮

- [ ] **Step 3: 验证无选中快捷操作**

1. 确保编辑器无文字选中
2. 点击快捷操作 pill「润色」
3. 预期：不置灰，可点击，提示文字显示"将对全文执行操作"，AI 正常响应

- [ ] **Step 4: 验证插入到光标**

1. 将光标放在编辑器某段落中间
2. 在 AI 面板发送一条指令
3. 完成后点击「插入」按钮
4. 预期：AI 生成内容插入到光标位置，不覆盖选中文字

- [ ] **Step 5: 验证对话持久化**

1. 在文档 A 与 AI 对话几条
2. 返回文档列表，打开文档 B，与 AI 对话
3. 返回文档列表，重新打开文档 A
4. 预期：文档 A 的 AI 对话历史还在

- [ ] **Step 6: 提交验证结果**

```bash
# 如果验证通过
git add -A
git commit -m "chore: P0 verification passed — streaming, no-selection, insert, persistence"
```
