"use client";

import {
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getAPIClient } from "@/core/api";
import { useModels } from "@/core/models/hooks";
import { useStream } from "@langchain/langgraph-sdk/react";

import { SafeStreamdown } from "@/core/streamdown/components";
import type { PersonalBlockNoteEditorRef, DocAnchor, DocOperation } from "./PersonalBlockNoteEditor";

// ─── types ────────────────────────────────────────────────────────────────
type AIMode = "ask" | "auto" | "plan";
const MODE_OPTIONS: { value: AIMode; label: string }[] = [
  { value: "ask", label: "Ask" },
  { value: "auto", label: "Auto" },
  { value: "plan", label: "Plan" },
];

// ─── helpers ────────────────────────────────────────────────────────────

/** Build the system prompt — format depends on mode. */
export function buildPrompt(params: {
  mode: AIMode;
  docContent: string;
  anchors: string;
  userMessage: string;
}): string {
  if (params.mode === "plan") {
    return `你是文档分析助手。请阅读下方文档并根据用户指令提供分析、建议、思路或合规审查。

**重要**：只输出分析和建议，不要输出任何文档编辑操作。
用 Markdown 格式回复。

**文档全文**：
\`\`\`markdown
${params.docContent}
\`\`\`

**用户指令**：${params.userMessage}`;
  }

  // ask / auto mode: full prompt with operations format
  return `你是文档编辑助手，能直接修改文档。回复分两部分，用 \`---OPERATIONS---\` 分隔。

**规则（必须遵守）**：
1. 凡是要添加/修改/删除文档内容的，必须在 \`---OPERATIONS---\` 后输出 JSON 操作数组
2. 只有纯聊天/纯分析/纯问答才不需要操作块
3. 操作数组必须是合法 JSON

**操作类型与格式**：
{"op":"replace","anchor":"要匹配的文本","content":"新内容（markdown）"}
{"op":"insert_after","anchor":"在这段之后","content":"插入的内容"}
{"op":"delete","anchor":"删除这段"}
{"op":"prepend","content":"文档开头插入"}
{"op":"append","content":"文档末尾追加"}

**anchor 定位**：从下方锚点索引用最近似文本（取标题或段落前20字）。

**示例1 — 内容修改**：
\`\`\`
需要将第3节标题更新为更准确的描述。

---OPERATIONS---
[{"op":"replace","anchor":"实际参数","content":"## 设计参数分析"}]
\`\`\`

**示例2 — 末尾追加**：
\`\`\`
在文档末尾补充一段结论。

---OPERATIONS---
[{"op":"append","content":"## 结论\\n\\n本文基于GB/T 50746-2012完成循环水系统设计计算，各项指标满足规范要求。"}]
\`\`\`

**锚点索引**：
${params.anchors}

**文档全文**：
\`\`\`markdown
${params.docContent}
\`\`\`

**用户指令**：${params.userMessage}`;
}

/** Parse operations from agent output (spec §9). */
export function parseOperations(text: string): { analysis: string; operations: DocOperation[] | null; parseError: string | null } {
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

// ─── sub-components ─────────────────────────────────────────────────────

function WelcomePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center">
      <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4">
        <Sparkles className="w-6 h-6 text-primary" />
      </div>
      <div className="text-base font-semibold text-foreground mb-6">文档 AI 助手</div>

      <div className="w-full text-left space-y-4 text-sm text-muted-foreground">
        <div>
          <div className="font-medium text-foreground mb-1.5">内容协作</div>
          <ul className="space-y-1 text-xs">
            <li>"给第3节加一段安全措施"</li>
            <li>"把设计参数表格改成文字描述"</li>
            <li>"在文档末尾补充结论"</li>
          </ul>
        </div>
        <div>
          <div className="font-medium text-foreground mb-1.5">文档审查</div>
          <ul className="space-y-1 text-xs">
            <li>"检查公式编号是否连续"</li>
            <li>"这段计算逻辑有没有问题"</li>
            <li>"全文的术语使用是否统一"</li>
          </ul>
        </div>
        <div>
          <div className="font-medium text-foreground mb-1.5">格式修正（自动应用）</div>
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

/** Notification card for auto-applied operations with undo. */
function AutoNotifyCard({ operations, onUndo }: { operations: DocOperation[]; onUndo: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  if (dismissed) return null;

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-4 h-4 rounded bg-primary/10 flex items-center justify-center">
          <RefreshCw className="w-2.5 h-2.5 text-primary" />
        </div>
        <span className="font-medium text-foreground">已自动应用 {operations.length} 项操作</span>
      </div>
      {expanded && (
        <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-0.5 mb-2">
          {operations.map((op, i) => (
            <li key={i}>{opLabel(op)}: {op.content?.slice(0, 60) || op.anchor?.slice(0, 40) || "-"}</li>
          ))}
        </ol>
      )}
      <div className="flex gap-3">
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-muted-foreground hover:text-foreground">
          {expanded ? "收起" : "展开查看详情"}
        </button>
        <button onClick={() => { onUndo(); setDismissed(true); }} className="text-xs text-primary hover:underline">
          撤销全部
        </button>
      </div>
    </div>
  );
}

function opLabel(op: DocOperation): string {
  if (op.op === "delete") return "删除";
  if (op.op === "insert_after") return "插入";
  if (op.op === "prepend") return "开头插入";
  if (op.op === "append") return "末尾追加";
  return "替换";
}

/** Per-operation confirm card (spec §8). */
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

  const opLabel =
    operation.op === "delete" ? "删除"
    : operation.op === "insert_after" ? "插入"
    : operation.op === "prepend" ? "开头插入"
    : operation.op === "append" ? "末尾追加"
    : "替换";

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden text-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-muted/30 border-b border-border/60">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-primary/10 text-primary">
          {opLabel}
        </span>
        <span className="text-xs text-muted-foreground truncate flex-1">
          {operation.anchor?.slice(0, 40) || (operation.op === "prepend" ? "文档开头" : operation.op === "append" ? "文档末尾" : "-")}
        </span>
        {status === "applied" && <span className="text-[11px] font-medium text-green-600">已应用</span>}
        {status === "failed" && <span className="text-[11px] font-medium text-red-500">失败</span>}
      </div>

      {/* Content preview */}
      {operation.op !== "delete" && operation.content && (
        <div className="px-3 py-2 text-xs text-muted-foreground max-h-20 overflow-y-auto">
          <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed">{operation.content.slice(0, 200)}</pre>
        </div>
      )}

      {/* Actions */}
      {status === "pending" && (
        <div className="flex border-t border-border/60">
          <button onClick={onPreview} className="flex-1 text-xs py-2 text-muted-foreground hover:bg-muted/50 transition-colors">
            预览定位
          </button>
          <button onClick={handleApply} className="flex-1 text-xs py-2 font-medium text-primary hover:bg-primary/5 border-l border-border/60 transition-colors">
            应用
          </button>
          <button onClick={() => { onSkip(); setStatus("skipped"); }} className="flex-1 text-xs py-2 text-muted-foreground hover:bg-muted/50 border-l border-border/60 transition-colors">
            跳过
          </button>
        </div>
      )}
      {status === "applied" && (
        <div className="px-3 py-1.5 border-t border-border/60 bg-muted/20">
          <button onClick={() => {}} className="text-xs text-muted-foreground hover:text-foreground transition-colors">撤销</button>
        </div>
      )}
      {status === "failed" && (
        <div className="px-3 py-1.5 border-t border-border/60 bg-red-50/30 dark:bg-red-950/10">
          <button onClick={handleApply} className="text-xs text-primary hover:underline">重试</button>
        </div>
      )}
    </div>
  );
}

/** Render operations based on mode: auto-apply or confirm cards. */
function OperationCards({
  operations,
  editorRef,
  mode,
}: {
  operations: DocOperation[];
  editorRef: React.RefObject<PersonalBlockNoteEditorRef | null>;
  mode: AIMode;
}) {
  // Auto mode: apply all immediately, show notification
  useEffect(() => {
    if (mode === "auto" && operations.length > 0) {
      editorRef.current?.applyOperations(operations);
    }
  }, [operations, editorRef, mode]);

  if (mode === "auto") {
    return (
      <div className="space-y-2 mt-3">
        <AutoNotifyCard operations={operations} onUndo={() => { /* TBD */ }} />
      </div>
    );
  }

  // Ask mode: confirm cards
  return (
    <div className="space-y-2 mt-3">
      {operations.map((op, i) => (
        <ConfirmCard
          key={i}
          operation={op}
          onApply={() => editorRef.current?.applyOperations([op])}
          onPreview={() => editorRef.current?.scrollToAnchor(op.anchor ?? "")}
          onSkip={() => {}}
        />
      ))}
    </div>
  );
}

// ─── main component ─────────────────────────────────────────────────────

interface DocAIAgentPanelProps {
  docTitle: string;
  docRelPath: string;
  threadId: string;
  editorRef: React.RefObject<PersonalBlockNoteEditorRef | null>;
  onClose: () => void;
  subThreadId: string | null;
  ensureThread: () => Promise<string>;
  isCreating: boolean;
  resetThread: () => void;
}

export default function DocAIAgentPanel({
  docTitle,
  docRelPath,
  threadId,
  editorRef,
  onClose,
  subThreadId,
  ensureThread,
  isCreating,
  resetThread,
}: DocAIAgentPanelProps) {
  const { models } = useModels();
  const [modelName, setModelName] = useState<string | null>(null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [mode, setMode] = useState<AIMode>("ask");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [chatKey, setChatKey] = useState(0);
  const modelMenuRef = useRef<HTMLDivElement>(null);
  const modeMenuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const client = useMemo(() => getAPIClient(), []);

  // ── LangGraph stream ──────────────────────────────────────────────
  // ponytail: useStream struggles with null→threadId transitions.
  // Force remount by keying on subThreadId so the hook always starts fresh.
  const streamConfig = useMemo(() => {
    if (!subThreadId) return { client, assistantId: "lead_agent" };
    return { client, assistantId: "lead_agent", threadId: subThreadId, reconnectOnMount: true };
  }, [client, subThreadId]);
  const streamState = useStream(streamConfig);

  const pendingRef = useRef<{ message: string; modelName: string | null } | null>(null);
  const [submitTick, setSubmitTick] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // ── model selector ────────────────────────────────────────────────
  useEffect(() => {
    if (!modelMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target as Node))
        setModelMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelMenuOpen]);

  useEffect(() => {
    if (!modeMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(e.target as Node))
        setModeMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modeMenuOpen]);

  const selectedModelLabel = modelName
    ? models.find((m) => m.name === modelName)?.display_name ?? modelName
    : "默认模型";

  // ── submit ────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    const el = inputRef.current;
    if (!el) return;
    const trimmed = el.value.trim();
    if (!trimmed || isCreating || submitting) return;

    const message = trimmed;
    userMessagesRef.current.push(message);
    el.value = "";
    el.style.height = "auto";
    setError(null);
    setSubmitting(true);

    try {
      // Sync current editor content to backend
      const rawMarkdown = (await editorRef.current?.getMarkdown()) ?? "";
      const cleanContent = rawMarkdown.replace(/<span[^>]*data-ai-\w+[^>]*>/g, "").replace(/<\/span>/g, "");
      const token = typeof document !== "undefined" ? document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)?.[1] : null;
      await fetch(`/api/extensions/docmgr/personal-docs/${encodeURIComponent(threadId)}/content`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(token ? { "X-CSRF-Token": token } : {}) },
        credentials: "include",
        body: JSON.stringify({ rel_path: docRelPath, content: cleanContent }),
      });

      await ensureThread();
      pendingRef.current = { message, modelName };
      setSubmitTick((v) => v + 1);
    } catch (e: any) {
      // Restore input on failure so user can retry
      el.value = message;
      setError(e?.message || "发送失败，请重试");
    } finally {
      setSubmitting(false);
    }
  }, [isCreating, submitting, ensureThread, modelName, editorRef, threadId, docRelPath]);

  // ── send queued message when stream is ready ──────────────────────
  // Watch streamState.isLoading directly so the effect fires when loading completes.
  const streamLoading = !!(streamState && streamState.isLoading);
  useEffect(() => {
    if (!subThreadId || streamLoading || !pendingRef.current) return;

    const { message, modelName: mn } = pendingRef.current;
    pendingRef.current = null;

    (async () => {
      try {
        const docContent = (await editorRef.current?.getMarkdown()) ?? "";
        const anchors = (editorRef.current?.getBlockAnchors() ?? [])
          .map((a) => {
            const prefix = a.blockType === "heading" ? `H${a.headingLevel ?? 1}` : "P";
            return `[${a.blockIndex}] ${prefix} "${a.text}"`;
          })
          .join("\n");

        const prompt = buildPrompt({ mode: modeRef.current, docContent, anchors, userMessage: message });

        streamState.submit(
          { messages: [{ type: "human", content: prompt }] },
          { configurable: { ...(mn ? { model_name: mn } : {}) }, recursion_limit: 250 },
        );
      } catch (e: any) {
        console.warn("[DocAI] submit effect failed:", e?.message);
        setError("发送失败: " + (e?.message || "未知错误"));
      }
    })();
  }, [subThreadId, streamLoading, submitTick, editorRef, streamState]);

  // ── new chat ──────────────────────────────────────────────────────
  const handleNewChat = () => {
    streamState?.stop?.();
    resetThread();
    userMessagesRef.current = [];
    setChatKey((k) => k + 1);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const autoResize = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  // ── derived message state ─────────────────────────────────────────
  // ponytail: store original user messages in a ref array, pushed on submit.
  // Each human message bubble reads from this array by index (not by message ID)
  // since the actual human message content is the full system prompt.
  const userMessagesRef = useRef<string[]>([]);

  const allMessages = useMemo(() => {
    return (streamState?.messages ?? []).filter((m: any) => {
      if (m.additional_kwargs?.hide_from_ui) return false;
      return m.type === "human" || m.type === "ai";
    });
  }, [streamState?.messages]);

  /** Parse a single AI message for operations. */
  const parseAIMessage = useCallback((content: unknown): { text: string; ops: DocOperation[] | null; error: string | null } => {
    const raw = typeof content === "string"
      ? content
      : Array.isArray(content)
        ? content.map((b: any) => b.text || "").join("")
        : "";
    if (!raw) return { text: "", ops: null, error: null };
    const parsed = parseOperations(raw);
    return { text: parsed.analysis, ops: parsed.operations, error: parsed.parseError };
  }, []);

  return (
    <div className="w-full h-full flex flex-col bg-background">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-border flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">AI 助手</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNewChat} title="新对话">
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {subThreadId ? (
          <div className="p-4 space-y-4">
            {(() => { let hi = 0; return allMessages.map((m: any) => {
              if (m.type === "human") {
                const userText = userMessagesRef.current[hi++] ?? "";
                return (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] bg-primary text-primary-foreground rounded-2xl rounded-br-md px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words">
                      {userText || "..."}
                    </div>
                  </div>
                );
              }

              // AI message: parse content per-message for operations
              const { text, ops, error } = parseAIMessage(m.content);
              return (
                <div key={m.id}>
                  <div className="text-sm leading-relaxed break-words text-foreground">
                    {text ? (
                      <SafeStreamdown>{text}</SafeStreamdown>
                    ) : (
                      <span className="flex items-center gap-2 text-muted-foreground">
                        <span className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse" />
                        思考中...
                      </span>
                    )}
                  </div>
                  {ops && ops.length > 0 && mode !== "plan" && (
                    <OperationCards operations={ops} editorRef={editorRef} mode={mode} />
                  )}
                  {error && (
                    <div className="text-xs text-muted-foreground mt-2 p-2 bg-muted/30 rounded">
                      ⚠️ {error}
                    </div>
                  )}
                </div>
              );
            }); })()}

            {streamState?.isLoading && (
              <div className="flex items-center gap-2 text-muted-foreground text-sm px-1">
                <span className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse" />
                生成中...
              </div>
            )}
          </div>
        ) : (
          <WelcomePage />
        )}
      </div>

      {/* Input area */}
      <div className="p-3 border-t border-border shrink-0">
        {error && (
          <div className="mb-2 text-xs text-red-500 bg-red-50 dark:bg-red-950/20 rounded-lg px-3 py-2 flex items-center justify-between">
            <span>❌ {error}</span>
            <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-600">✕</button>
          </div>
        )}
        <div className="bg-muted/30 border border-border rounded-2xl px-3 py-2">
          <textarea
            ref={inputRef}
            onInput={autoResize}
            onKeyDown={handleKeyDown}
            placeholder="输入指令..."
            rows={1}
            disabled={isCreating || submitting}
            className="w-full border-none outline-none bg-transparent text-sm text-foreground min-w-0 placeholder:text-muted-foreground resize-none leading-relaxed max-h-[120px]"
          />
          <div className="flex items-center justify-between mt-1.5">
            <div className="flex items-center gap-2 shrink-0">
              {/* Mode selector */}
              <div ref={modeMenuRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setModeMenuOpen((v) => !v)}
                  className="flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground transition-colors rounded-md px-1.5 py-0.5 hover:bg-muted"
                >
                  <span>{MODE_OPTIONS.find(m => m.value === mode)?.label || "Ask"}</span>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2.5 3.5L5 6L7.5 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {modeMenuOpen && (
                  <div className="absolute bottom-full left-0 mb-2 w-28 bg-background rounded-xl shadow-lg border border-border py-1 z-50">
                    {MODE_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => { setMode(opt.value); setModeMenuOpen(false); }}
                        className={`w-full text-left px-3 py-1.5 text-xs hover:bg-muted ${mode === opt.value ? "bg-primary/5 text-primary" : ""}`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {/* Model selector */}
              <div ref={modelMenuRef} className="relative shrink-0">
              <button
                type="button"
                onClick={() => setModelMenuOpen((v) => !v)}
                className="flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground transition-colors rounded-md px-1.5 py-0.5 hover:bg-muted"
              >
                <span className="max-w-[72px] truncate">{selectedModelLabel}</span>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2.5 3.5L5 6L7.5 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              {modelMenuOpen && (
                <div className="absolute bottom-full right-0 mb-2 w-40 bg-background rounded-xl shadow-lg border border-border py-1 z-50 max-h-48 overflow-y-auto">
                  <button
                    type="button"
                    onClick={() => { setModelName(null); setModelMenuOpen(false); }}
                    className={cn("w-full text-left px-3 py-1.5 text-xs hover:bg-muted", !modelName && "bg-primary/5 text-primary")}
                  >
                    默认模型
                  </button>
                  {models.map((m) => (
                    <button
                      key={m.name}
                      type="button"
                      onClick={() => { setModelName(m.name); setModelMenuOpen(false); }}
                      className={cn("w-full text-left px-3 py-1.5 text-xs hover:bg-muted", modelName === m.name && "bg-primary/5 text-primary")}
                    >
                      {m.display_name ?? m.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            </div>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={isCreating || submitting}
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-colors",
                !streamState?.isLoading && !isCreating && !submitting
                  ? "bg-primary text-primary-foreground hover:opacity-90"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {streamState?.isLoading || isCreating || submitting ? (
                <span className="w-3 h-3 border-2 border-muted-foreground border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M2 7L12 2L7 12L5.5 7.5L2 7Z" fill="currentColor" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
