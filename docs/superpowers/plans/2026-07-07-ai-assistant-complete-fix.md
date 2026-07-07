# AI 助手完备化（P0+P1+P2）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把文档编辑器 AI 助手从单次无状态文本工具升级为流式多轮文档助手，修复全部 P0/P1/P2 缺陷。

**Architecture:** 前端负责多轮上下文（messages + localStorage），后端无状态流式（`model.astream` + SSE）。替换前 diff 预览。brainstorm 不替换。

**Tech Stack:** FastAPI StreamingResponse（SSE）/ LangChain `model.astream` / React + fetch ReadableStream / localStorage

**Spec:** `docs/superpowers/specs/2026-07-07-ai-assistant-complete-fix-design.md`

---

## 文件结构

| 文件 | 责任 | 改动 |
|---|---|---|
| `backend/app/extensions/docmgr/routers.py` | 新增 SSE 流式 endpoint + 错误细化 | 修改 |
| `frontend/src/extensions/api/index.ts` | 新增 `aiEditStream`（fetch stream） | 修改 |
| `frontend/src/extensions/docmgr/DocumentManagement.tsx` | AIEditPanel 重构（多轮/流式/持久/diff/长度/brainstorm/ref） | 修改 |
| `frontend/src/extensions/docmgr/DiffPreviewDialog.tsx` | diff 预览组件 | 新建 |

---

### Task 1: 后端 SSE 流式 endpoint + 错误细化

**Files:**
- Modify: `backend/app/extensions/docmgr/routers.py:421-505`（AI Operations 段）

- [ ] **Step 1: 添加 StreamingResponse + LangChain messages import**

在 `routers.py` 顶部 import 区（已有 `from fastapi import ...`），确认或追加：

```python
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
```

- [ ] **Step 2: 添加 AIEditStreamRequest schema + 流式生成器**

在 `AIEditResponse` class 之后（约 line 435），追加：

```python
class AIEditStreamRequest(BaseModel):
    """Streaming AI edit request — carries full conversation history."""

    messages: list[dict] = Field(..., min_length=1, description="[{role: system|user|assistant, content}]")
    operation: str = Field(..., description="polish | expand | condense | brainstorm")
    model_name: str | None = Field(None, description="Optional model override")


def _to_langchain_messages(raw: list[dict], operation: str) -> list:
    """Convert [{role, content}] to LangChain messages, prepending operation system prompt."""
    sys_prompt = OPERATION_PROMPTS.get(operation, "")
    msgs: list = []
    if sys_prompt:
        msgs.append(SystemMessage(content=sys_prompt))
    for m in raw:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            msgs.append(SystemMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(HumanMessage(content=content))
    return msgs


async def _ai_edit_stream_generator(messages: list, model_name: str | None):
    """Yield SSE tokens from model.astream. Error frames use event: error."""
    try:
        from deerflow.models import create_chat_model

        model = create_chat_model(name=model_name, thinking_enabled=False)
        async for chunk in model.astream(messages):
            token = _extract_ai_response_text(chunk.content)
            if token:
                yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"
    except TimeoutError:
        yield "event: error\ndata: timeout\n\n"
    except Exception as exc:
        # 区分 context window 超限 vs 模型不可用 vs 其他
        msg = str(exc).lower()
        if "context" in msg or "too long" in msg or "maximum" in msg:
            yield "event: error\ndata: context_length\n\n"
        elif "connection" in msg or "unavailable" in msg or "refused" in msg:
            yield "event: error\ndata: model_unavailable\n\n"
        else:
            logger.exception("AI edit stream failed: %s", exc)
            yield "event: error\ndata: internal\n\n"
```

- [ ] **Step 3: 添加 POST /documents/ai-edit-stream endpoint**

在现有 `ai_edit_text` endpoint 之后（约 line 506），追加：

```python
@router.post("/documents/ai-edit-stream")
async def ai_edit_stream(
    request: AIEditStreamRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Streaming AI edit — SSE token stream with multi-turn context."""
    if request.operation not in OPERATION_PROMPTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operation: {request.operation}. Must be one of: {list(OPERATION_PROMPTS.keys())}",
        )
    messages = _to_langchain_messages(request.messages, request.operation)
    return StreamingResponse(
        _ai_edit_stream_generator(messages, request.model_name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: 细化原 ai-edit 的错误码（P2-6）**

把 `ai_edit_text`（line 494-505）的 except 块改为分类：

```python
    except TimeoutError:
        logger.warning("AI edit timed out: operation=%s model=%s", request.operation, model_name)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="AI 处理超时，请缩短文本或换更快的模型")
    except Exception as exc:
        msg = str(exc).lower()
        logger.exception("AI edit failed: operation=%s model=%s err=%s", request.operation, model_name, exc)
        if "context" in msg or "too long" in msg or "maximum" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档过长，超出模型上下文限制，请缩短或分段处理")
        if "connection" in msg or "unavailable" in msg or "refused" in msg:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI 模型暂不可用，请稍后重试")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI 处理失败，请重试")
```

- [ ] **Step 5: 重启 gateway + 冒烟测试**

```bash
docker compose -p eai-docker restart gateway
# 等 ready
docker exec deer-flow-gateway bash -lc 'for i in $(seq 1 30); do tail -80 /app/logs/gateway.log | grep -q "Application startup complete" && echo ready && break; sleep 1; done'
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/extensions/docmgr/routers.py
git commit -m "feat(docmgr): streaming AI edit endpoint (SSE) + multi-turn messages + error classification"
```

---

### Task 2: 前端 aiEditStream API（fetch + ReadableStream）

**Files:**
- Modify: `frontend/src/extensions/api/index.ts:456-464`（aiEdit 附近）

- [ ] **Step 1: 添加 aiEditStream 函数**

在 `aiEdit` 函数之后（约 line 465），追加：

```typescript
  /** 流式 AI 编辑（SSE）。onToken 收到每个 token，onDone 收到完整结果，onError 收到错误类型。返回 AbortController。 */
  aiEditStream: (
    data: {
      messages: Array<{ role: "system" | "user" | "assistant"; content: string }>;
      operation: "polish" | "expand" | "condense" | "brainstorm";
      model_name?: string;
    },
    handlers: { onToken: (t: string) => void; onDone: (full: string) => void; onError: (kind: string) => void },
  ): AbortController => {
    const controller = new AbortController();
    const csrf = document.cookie.match(/csrf_token=([^;]+)/)?.[1] || "";
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/docmgr/documents/ai-edit-stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify(data),
          credentials: "include",
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          handlers.onError("http_" + res.status);
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let full = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          let event = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              event = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              const payload = line.slice(6);
              if (event === "error") {
                handlers.onError(payload.trim());
                return;
              }
              if (payload.trim() === "[DONE]") {
                handlers.onDone(full);
                return;
              }
              full += payload;
              handlers.onToken(payload);
            } else if (line === "") {
              event = ""; // 帧边界重置 event
            }
          }
        }
        handlers.onDone(full);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        handlers.onError("network");
      }
    })();
    return controller;
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/extensions/api/index.ts
git commit -m "feat(docmgr): aiEditStream client (fetch ReadableStream + SSE parse + AbortController)"
```

---

### Task 3: AIEditPanel 多轮上下文 + localStorage + ref 拦截

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`（AIEditPanel，约 1406-1700）

- [ ] **Step 1: AIEditPanel 接收 docKey prop（用于 localStorage 隔离）**

修改 `AIEditPanel` 的签名（约 line 1406）和 `DocumentEditor` 里调用处（约 line 1372）。

`AIEditPanel` 签名加 `docKey: string`：

```tsx
function AIEditPanel({ onClose, getSelectedText, getFullText, onResult, docKey }: {
  onClose: () => void;
  getSelectedText: () => string;
  getFullText: () => string;
  onResult: (text: string) => void;
  docKey: string;
}) {
```

`DocumentEditor` 里传 docKey（约 line 1372）：

```tsx
<AIEditPanel onClose={() => setShowAI(false)}
  getSelectedText={() => editorRef.current?.getSelectedText() ?? ""}
  getFullText={() => editorRef.current?.getMarkdown() ?? ""}
  onResult={(text) => editorRef.current?.replaceSelection(text)}
  docKey={docId || (personalFile ? `personal-${personalFile.thread_id}-${personalFile.rel_path}` : "default")} />
```

- [ ] **Step 2: messages 从 localStorage 初始化 + 持久化 + runningRef**

在 AIEditPanel 内（`const [messages, setMessages] = useState...` 附近，约 line 1412），替换为：

```tsx
  const STORAGE_KEY = `ai-chat-${docKey}`;
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });
  const [input, setInput] = useState("");
  const [activeOp, setActiveOp] = useState<AIOperation>(() => {
    try { return (JSON.parse(localStorage.getItem(STORAGE_KEY + "-meta") || "{}").activeOp) || "polish"; }
    catch { return "polish"; }
  });
  const [modelName, setModelName] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);  // 同步拦截并发
  const abortRef = useRef<AbortController | null>(null);
  const streamingMsgId = useRef<string | null>(null);

  // messages 持久化
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(messages)); } catch {}
  }, [messages, STORAGE_KEY]);
  // activeOp 持久化
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY + "-meta", JSON.stringify({ activeOp })); } catch {}
  }, [activeOp, STORAGE_KEY]);
```

- [ ] **Step 3: handleNewChat 清空 localStorage**

修改 `handleNewChat`（约 line 1520）：

```tsx
  const handleNewChat = () => {
    if (runningRef.current) {
      abortRef.current?.abort();
      runningRef.current = false;
      setRunning(false);
    }
    setMessages([]);
    setInput("");
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  };
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): AIEditPanel multi-turn messages + localStorage persistence + runningRef"
```

---

### Task 4: AIEditPanel 流式渲染（接 aiEditStream）+ 多轮上下文

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`（AIEditPanel sendMessage）

- [ ] **Step 1: buildApiMessages helper**

在 AIEditPanel 内 `sendMessage` 之前（约 line 1462），加：

```tsx
  const buildApiMessages = (currentUserText: string): Array<{ role: "system" | "user" | "assistant"; content: string }> => {
    // 历史轮次（最多保留最近 10 轮，防 token 爆）
    const history = messages.slice(-20).map(m => ({
      role: m.role,
      content: m.content,
    }));
    return [...history, { role: "user" as const, content: currentUserText }];
  };
```

- [ ] **Step 2: sendMessage 改用流式 + ref 拦截**

替换 `sendMessage`（约 line 1462-1484）：

```tsx
  const sendMessage = async (text: string, operation: AIOperation, displayContent?: string) => {
    if (runningRef.current) return;  // 同步拦截并发
    runningRef.current = true;
    setRunning(true);

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: displayContent ?? text, operation };
    const assistantId = crypto.randomUUID();
    streamingMsgId.current = assistantId;
    setMessages(prev => [...prev, userMsg, { id: assistantId, role: "assistant", content: "", operation }]);
    setInput("");
    resetInputHeight();
    scrollToBottom();

    const apiMessages = buildApiMessages(text);
    abortRef.current = docmgrApi.aiEditStream(
      { messages: apiMessages, operation, model_name: modelName ?? undefined },
      {
        onToken: (t) => {
          setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: m.content + t } : m));
          scrollToBottom();
        },
        onDone: () => {
          runningRef.current = false;
          setRunning(false);
          streamingMsgId.current = null;
        },
        onError: (kind) => {
          const errMap: Record<string, string> = {
            timeout: "⏱️ AI 处理超时，请缩短文本或换更快的模型",
            context_length: "📄 文档过长，超出模型上下文限制，请缩短或分段",
            model_unavailable: "🔌 AI 模型暂不可用，请稍后重试",
            internal: "⚠️ AI 处理失败，请重试",
            network: "🌐 网络错误，请检查连接",
          };
          setMessages(prev => prev.map(m => m.id === assistantId
            ? { ...m, content: errMap[kind] || `⚠️ 处理失败（${kind}）` }
            : m));
          runningRef.current = false;
          setRunning(false);
          streamingMsgId.current = null;
        },
      },
    );
  };
```

- [ ] **Step 3: 流式中的 assistant 气泡显示 spinner（content 为空时）**

修改 assistant 消息渲染（约 line 1614），在 content 为空且 running 时显示 spinner。把 `{running && (...)}`（约 line 1639）那段移除，改为在 assistant 气泡内处理：

找到 assistant 气泡的 `<ReactMarkdown>`（约 line 1616），在其后加：

```tsx
                    {msg.content === "" && msg.id === streamingMsgId.current && (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
                    )}
```

并删除独立的 `{running && (<div className="flex items-center gap-2..."><Loader2/>...</div>)}` 块。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): streaming AI responses + multi-turn context in AIEditPanel"
```

---

### Task 5: brainstorm 语义修正 + 全文长度保护

**Files:**
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`（AIEditPanel）

- [ ] **Step 1: brainstorm 消息不显示「替换」按钮 + 标记思路参考**

修改 assistant 消息的替换/复制按钮区（约 line 1618-1635），加 brainstorm 判断。把：

```tsx
                      {!msg.content.startsWith("⚠️") && (
                        <div className="mt-1.5 flex gap-1.5">
                          <button ... onClick={() => handleReplace(msg.content)} ...>替换</button>
                          <button ... onClick={() => handleCopy(msg.content)} ...>复制</button>
                        </div>
                      )}
```

改为：

```tsx
                      {msg.content && !msg.content.startsWith("⚠️") && !msg.content.startsWith("⏱️") && !msg.content.startsWith("📄") && !msg.content.startsWith("🔌") && !msg.content.startsWith("🌐") && (
                        <div className="mt-1.5 flex gap-1.5 items-center">
                          {msg.operation === "brainstorm" ? (
                            <>
                              <span className="text-[10px] text-amber-500">💡 思路参考（不替换原文）</span>
                              <button type="button" onClick={() => handleCopy(msg.content)}
                                className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border text-muted-foreground text-[11px] hover:bg-muted transition-colors">
                                <Copy className="w-3 h-3" />复制
                              </button>
                            </>
                          ) : (
                            <>
                              <button type="button" onClick={() => setDiffPreview({ original: getSelectedText(), aiText: msg.content })}
                                className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-primary/30 text-primary text-[11px] hover:bg-primary/10 transition-colors">
                                <Wand2 className="w-3 h-3" />对比替换
                              </button>
                              <button type="button" onClick={() => handleCopy(msg.content)}
                                className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-border text-muted-foreground text-[11px] hover:bg-muted transition-colors">
                                <Copy className="w-3 h-3" />复制
                              </button>
                            </>
                          )}
                        </div>
                      )}
```

- [ ] **Step 2: 添加 diffPreview state + 长度检查**

在 AIEditPanel 内（state 区），加：

```tsx
  const [diffPreview, setDiffPreview] = useState<{ original: string; aiText: string } | null>(null);
  const FULLTEXT_WARN_THRESHOLD = 20000;
```

修改 `handleSubmit`（约 line 1486），加全文长度检查：

```tsx
  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || runningRef.current) return;
    const selected = getSelectedText();
    const text = selected.trim() ? `${trimmed}\n\n【选中文字】：\n${selected}` : trimmed;
    // 全文操作长度保护：无选中且指令可能用全文时检查
    if (!selected.trim() && getFullText().length > FULLTEXT_WARN_THRESHOLD) {
      if (!confirm(`文档较长（${getFullText().length} 字），AI 可能截断或超时，是否继续？`)) return;
    }
    void sendMessage(text, activeOp);
  };
```

同样修改 `handleSuggestedPrompt`（约 line 1505），在 `sendMessage` 前加长度检查：

```tsx
  const handleSuggestedPrompt = (prompt: string) => {
    const fullText = getFullText();
    const selected = getSelectedText();
    if (!selected.trim() && fullText.length > FULLTEXT_WARN_THRESHOLD) {
      if (!confirm(`文档较长（${fullText.length} 字），AI 可能截断或超时，是否继续？`)) return;
    }
    const apiText = `${prompt}\n\n${selected.trim() ? `【选中文字】：\n${selected}` : `【文档全文】：\n${fullText}`}`;
    void sendMessage(apiText, activeOp, prompt);
  };
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): brainstorm no-replace + fulltext length guard + diff preview trigger"
```

---

### Task 6: DiffPreviewDialog 组件 + 替换流程

**Files:**
- Create: `frontend/src/extensions/docmgr/DiffPreviewDialog.tsx`
- Modify: `frontend/src/extensions/docmgr/DocumentManagement.tsx`

- [ ] **Step 1: 创建 DiffPreviewDialog 组件**

```tsx
"use client";

import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";

/** 简易行级 diff（避免引入 diff 库）：逐行对比，标记 +/- */
function lineDiff(original: string, ai: string) {
  const oldLines = original.split("\n");
  const newLines = ai.split("\n");
  const max = Math.max(oldLines.length, newLines.length);
  const rows: { type: "same" | "add" | "del"; old?: string; new?: string }[] = [];
  for (let i = 0; i < max; i++) {
    const o = oldLines[i];
    const n = newLines[i];
    if (o === n) rows.push({ type: "same", old: o, new: n });
    else {
      if (o !== undefined) rows.push({ type: "del", old: o });
      if (n !== undefined) rows.push({ type: "add", new: n });
    }
  }
  return rows;
}

export function DiffPreviewDialog({
  open,
  original,
  aiText,
  onAccept,
  onCancel,
}: {
  open: boolean;
  original: string;
  aiText: string;
  onAccept: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  const rows = lineDiff(original, aiText);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onCancel}>
      <div className="bg-background rounded-xl border border-border shadow-2xl w-[80vw] max-w-4xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-border flex items-center justify-between shrink-0">
          <span className="text-sm font-semibold">对比替换预览</span>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onCancel}><X className="w-4 h-4" /></Button>
        </div>
        <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-relaxed">
          {original.trim() === "" && (
            <p className="text-muted-foreground mb-3 text-center">⚠️ 编辑器中未选中文字，将替换为 AI 输出（全文替换）</p>
          )}
          {rows.map((r, i) => (
            <div key={i} className={
              r.type === "add" ? "bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400" :
              r.type === "del" ? "bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 line-through opacity-70" :
              "text-muted-foreground"
            }>
              <span className="inline-block w-6 text-muted-foreground/40">{r.type === "add" ? "+" : r.type === "del" ? "-" : " "}</span>
              {r.type === "del" ? r.old : r.new}
            </div>
          ))}
        </div>
        <div className="px-5 py-3 border-t border-border flex justify-end gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
          <Button size="sm" onClick={onAccept}><Check className="w-4 h-4 mr-1" />接受替换</Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: AIEditPanel 引入 DiffPreviewDialog + 接受替换**

在 `DocumentManagement.tsx` 顶部 import：

```tsx
import { DiffPreviewDialog } from "./DiffPreviewDialog";
```

在 AIEditPanel 的 return（消息区之后，闭合 div 前），加：

```tsx
      <DiffPreviewDialog
        open={!!diffPreview}
        original={diffPreview?.original ?? ""}
        aiText={diffPreview?.aiText ?? ""}
        onAccept={() => {
          if (diffPreview) onResult(diffPreview.aiText);
          setDiffPreview(null);
        }}
        onCancel={() => setDiffPreview(null)}
      />
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/extensions/docmgr/DiffPreviewDialog.tsx frontend/src/extensions/docmgr/DocumentManagement.tsx
git commit -m "feat(docmgr): DiffPreviewDialog — review diff before replacing selection"
```

---

### Task 7: 集成验证

- [ ] **Step 1: 重启 gateway + frontend**

```bash
docker compose -p eai-docker restart gateway frontend
# 等两个 ready
docker exec deer-flow-gateway bash -lc 'for i in $(seq 1 30); do tail -80 /app/logs/gateway.log | grep -q "Application startup complete" && echo "gateway ready" && break; sleep 1; done'
for i in $(seq 1 40); do code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/docmgr 2>/dev/null); [ "$code" = "200" ] && sleep 6 && echo "frontend ready" && break; sleep 3; done
```

- [ ] **Step 2: 浏览器验证流式 + 多轮**

打开 http://localhost:2026/docmgr → 选线程 → 点 md 文件进编辑器 → 点「AI 助手」→ 选中文字点「润色」→ 确认：
- token 逐字流式流出（不卡 spinner）
- 追问「再正式一点」→ AI 记得上一轮（多轮上下文）
- 刷新页面 → 对话历史保留（localStorage）

- [ ] **Step 3: 验证 diff 替换 + brainstorm**

- 点「对比替换」→ 弹 diff modal → 接受才替换
- 选「头脑风暴」→ 结果只有「复制」，无「替换」，标记「💡 思路参考」

- [ ] **Step 4: 验证长度保护**

- 不选中文字，输入「优化文档结构」（文档 >20K 字）→ 弹长度警告 → 取消则不发

- [ ] **Step 5: 验证并发 + 错误**

- 快速连点两次「润色」→ 只发一次（ref 拦截）
- 断网或停 gateway → 友好错误提示（具体原因）

- [ ] **Step 6: 最终 Commit**

```bash
git add -A
git commit -m "feat(docmgr): complete AI assistant — streaming + multi-turn + diff + safety (P0+P1+P2)"
```
