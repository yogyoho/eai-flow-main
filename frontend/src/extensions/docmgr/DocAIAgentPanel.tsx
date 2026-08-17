"use client";

import { useStream } from "@langchain/langgraph-sdk/react";
import { RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { getAPIClient } from "@/core/api";
import { useModels } from "@/core/models/hooks";
import { SafeStreamdown } from "@/core/streamdown/components";
import { cn } from "@/lib/utils";

import { docmgrApi } from "../api";

import type {
  PersonalBlockNoteEditorRef,
  DocOperation,
} from "./PersonalBlockNoteEditor";

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

// ponytail: persist user messages in localStorage so they survive page refresh.
// AI responses persist via LangGraph thread; user messages would be lost otherwise.
const USER_MSG_PREFIX = "docmgr-ai-usermessages:";

function loadUserMessages(threadId: string): string[] {
  try {
    const raw = localStorage.getItem(USER_MSG_PREFIX + threadId);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveUserMessages(threadId: string, msgs: string[]) {
  try {
    localStorage.setItem(USER_MSG_PREFIX + threadId, JSON.stringify(msgs));
  } catch {
    /* ignore */
  }
}

function clearUserMessages(threadId: string) {
  try {
    localStorage.removeItem(USER_MSG_PREFIX + threadId);
  } catch {
    /* ignore */
  }
}

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

**anchor 定位**：从下方锚点列表中选择与目标最匹配的文本，直接复制使用。每行一个可用锚点。

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
export function parseOperations(text: string): {
  analysis: string;
  operations: DocOperation[] | null;
  parseError: string | null;
} {
  const idx = text.indexOf("---OPERATIONS---");
  if (idx === -1) return { analysis: text, operations: null, parseError: null };

  const analysis = text.slice(0, idx).trim();
  let opsPart = text.slice(idx + "---OPERATIONS---".length).trim();

  if (!opsPart) return { analysis, operations: [], parseError: null };

  // ponytail: normalize common AI JSON formatting errors.
  // 0. Strip markdown code fences ```json ... ```
  opsPart = opsPart
    .replace(/^```(?:json)?\s*\n?/i, "")
    .replace(/\n?```\s*$/i, "");
  // 1. Wrap bare object in array: {"op":...} → [{"op":...}]
  if (opsPart.startsWith("{") && !opsPart.startsWith("[")) {
    opsPart = "[" + opsPart + "]";
  }
  // 2. Single quotes → double quotes (only outside string values)
  if (opsPart.includes("'") && !opsPart.includes('"')) {
    opsPart = opsPart.replace(/'/g, '"');
  }
  // 3. Strip trailing comma before ] or }
  opsPart = opsPart.replace(/,(\s*[}\]])/g, "$1");
  // 4. Try to extract JSON array if mixed with other text
  const arrayMatch = /\[[\s\S]*\]/.exec(opsPart);
  if (arrayMatch && arrayMatch[0].length > opsPart.length * 0.5) {
    opsPart = arrayMatch[0];
  }

  console.log("[DocAI] opsPart after normalize:", opsPart.slice(0, 500));

  try {
    const ops = JSON.parse(opsPart);
    if (!Array.isArray(ops))
      return { analysis, operations: null, parseError: "操作指令不是数组格式" };
    // Validate each operation has required fields
    for (const op of ops) {
      if (!op.op)
        return { analysis, operations: null, parseError: "操作缺少 op 字段" };
    }
    return { analysis, operations: ops as DocOperation[], parseError: null };
  } catch {
    return { analysis, operations: null, parseError: "操作指令 JSON 解析失败" };
  }
}

// ─── sub-components ─────────────────────────────────────────────────────

function WelcomePage() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="bg-primary/10 mb-4 flex h-12 w-12 items-center justify-center rounded-xl">
        <Sparkles className="text-primary h-6 w-6" />
      </div>
      <div className="text-foreground mb-6 text-base font-semibold">
        文档 AI 助手
      </div>

      <div className="text-muted-foreground w-full space-y-4 text-center text-sm">
        <div>
          <div className="text-foreground mb-1.5 font-medium">内容协作</div>
          <ul className="list-none space-y-1 p-0 text-xs">
            <li>&quot;给第3节加一段安全措施&quot;</li>
            <li>&quot;把设计参数表格改成文字描述&quot;</li>
            <li>&quot;在文档末尾补充结论&quot;</li>
          </ul>
        </div>
        <div>
          <div className="text-foreground mb-1.5 font-medium">文档审查</div>
          <ul className="list-none space-y-1 p-0 text-xs">
            <li>&quot;检查公式编号是否连续&quot;</li>
            <li>&quot;这段计算逻辑有没有问题&quot;</li>
            <li>&quot;全文的术语使用是否统一&quot;</li>
          </ul>
        </div>
        <div>
          <div className="text-foreground mb-1.5 font-medium">
            格式修正（自动应用）
          </div>
          <ul className="list-none space-y-1 p-0 text-xs">
            <li>&quot;统一中英文之间的空格&quot;</li>
            <li>&quot;修正标题层级&quot;</li>
          </ul>
        </div>
      </div>

      <div className="text-muted-foreground/70 mt-6 text-xs leading-relaxed">
        操作有预览，你可以逐条确认或拒绝。
        <br />
        格式修正类操作会自动应用，可一键撤销。
      </div>
    </div>
  );
}

/** Notification card for auto-applied operations with undo. */
function AutoNotifyCard({
  operations,
  onUndo,
}: {
  operations: DocOperation[];
  onUndo: () => void;
}) {
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  if (dismissed) return null;

  return (
    <div className="border-border bg-muted/30 rounded-lg border p-3 text-sm">
      <div className="mb-2 flex items-center gap-2">
        <div className="bg-primary/10 flex h-4 w-4 items-center justify-center rounded">
          <RefreshCw className="text-primary h-2.5 w-2.5" />
        </div>
        <span className="text-foreground font-medium">
          已自动应用 {operations.length} 项操作
        </span>
      </div>
      {expanded && (
        <ol className="text-muted-foreground mb-2 list-inside list-decimal space-y-0.5 text-xs">
          {operations.map((op, i) => {
            const content = op.content?.slice(0, 60) ?? "";
            const anchor = op.anchor?.slice(0, 40) ?? "";
            return (
              <li key={i}>
                {opLabel(op)}: {content ? content : anchor ? anchor : "-"}
              </li>
            );
          })}
        </ol>
      )}
      <div className="flex gap-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-muted-foreground hover:text-foreground text-xs"
        >
          {expanded ? "收起" : "展开查看详情"}
        </button>
        <button
          onClick={() => {
            onUndo();
            setDismissed(true);
          }}
          className="text-primary text-xs hover:underline"
        >
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
  onUndo,
}: {
  operation: DocOperation;
  onApply: () => void;
  onPreview: () => void;
  onSkip: () => void;
  onUndo?: () => void;
}) {
  const [status, setStatus] = useState<
    "pending" | "applied" | "skipped" | "failed"
  >("pending");
  const [errorMsg, setErrorMsg] = useState("");

  const handleApply = () => {
    try {
      onApply();
      setStatus("applied");
    } catch (e) {
      setStatus("failed");
      setErrorMsg(getErrorMessage(e, "操作失败"));
    }
  };

  const handleUndo = () => {
    onUndo?.();
    setStatus("pending");
  };

  if (status === "skipped") return null;

  const opLabel =
    operation.op === "delete"
      ? "删除"
      : operation.op === "insert_after"
        ? "插入"
        : operation.op === "prepend"
          ? "开头插入"
          : operation.op === "append"
            ? "末尾追加"
            : "替换";

  return (
    <div className="border-border bg-card overflow-hidden rounded-lg border text-sm">
      {/* Header */}
      <div className="bg-muted/30 border-border/60 flex items-center gap-2 border-b px-3 py-2">
        <span className="bg-primary/10 text-primary inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium">
          {opLabel}
        </span>
        <span className="text-muted-foreground flex-1 truncate text-xs">
          {operation.anchor?.slice(0, 40)
            ? operation.anchor.slice(0, 40)
            : operation.op === "prepend"
              ? "文档开头"
              : operation.op === "append"
                ? "文档末尾"
                : "-"}
        </span>
        {status === "applied" && (
          <span className="text-[11px] font-medium text-green-600">已应用</span>
        )}
        {status === "failed" && (
          <span className="text-[11px] font-medium text-red-500">失败</span>
        )}
      </div>
      {status === "failed" && errorMsg && (
        <div className="border-t border-red-100 bg-red-50/30 px-3 py-1.5 text-[11px] text-red-600 dark:border-red-900/20 dark:bg-red-950/10">
          {errorMsg}
        </div>
      )}

      {/* Content preview */}
      {operation.op !== "delete" && operation.content && (
        <div className="text-muted-foreground max-h-20 overflow-y-auto text-xs">
          <pre className="px-3 py-1.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
            {operation.content.slice(0, 200)}
          </pre>
        </div>
      )}

      {/* Actions */}
      {status === "pending" && (
        <div className="border-border/60 flex border-t">
          <button
            onClick={onPreview}
            className="text-muted-foreground hover:bg-muted/50 flex-1 py-2 text-xs transition-colors"
          >
            预览定位
          </button>
          <button
            onClick={handleApply}
            className="text-primary hover:bg-primary/5 border-border/60 flex-1 border-l py-2 text-xs font-medium transition-colors"
          >
            应用
          </button>
          <button
            onClick={() => {
              onSkip();
              setStatus("skipped");
            }}
            className="text-muted-foreground hover:bg-muted/50 border-border/60 flex-1 border-l py-2 text-xs transition-colors"
          >
            跳过
          </button>
        </div>
      )}
      {status === "applied" && (
        <div className="border-border/60 bg-muted/20 border-t px-3 py-1.5">
          <button
            onClick={handleUndo}
            className="text-muted-foreground hover:text-foreground text-xs transition-colors"
          >
            撤销
          </button>
        </div>
      )}
      {status === "failed" && (
        <div className="border-border/60 border-t bg-red-50/30 px-3 py-1.5 dark:bg-red-950/10">
          <button
            onClick={handleApply}
            className="text-primary text-xs hover:underline"
          >
            重试
          </button>
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
  // ponytail: hooks 必须无条件调用（原实现 useRef 在 auto 提前 return 之后 → Rules-of-Hooks 违规，
  // ask↔auto 切换会抛 "Rendered more hooks than during the previous render"）。
  const snapshotRef = useRef<unknown[] | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);

  // Auto mode: apply all immediately, show notification with undo.
  // ponytail: auto 应用失败不再静默中断——先快照（可整批撤销），applyOperations 抛错时捕获并展示。
  useEffect(() => {
    if (mode === "auto" && operations.length > 0) {
      snapshotRef.current = editorRef.current?.snapshotBlocks() ?? null;
      setAutoError(null);
      try {
        editorRef.current?.applyOperations(operations);
      } catch (e) {
        setAutoError(getErrorMessage(e, "操作失败，部分内容可能未应用"));
      }
    }
  }, [operations, editorRef, mode]);

  // Shared undo: restore the pre-apply snapshot (auto batch or ask-mode first apply).
  const handleUndo = () => {
    if (snapshotRef.current && editorRef.current) {
      editorRef.current.restoreBlocks(snapshotRef.current);
      snapshotRef.current = null;
    }
  };

  if (mode === "auto") {
    return (
      <div className="mt-3 space-y-2">
        {autoError && (
          <div className="rounded-lg border border-red-100 bg-red-50/30 px-3 py-2 text-xs text-red-600 dark:border-red-900/20 dark:bg-red-950/10">
            ⚠️ {autoError}
          </div>
        )}
        <AutoNotifyCard operations={operations} onUndo={handleUndo} />
      </div>
    );
  }

  // Ask mode: confirm cards
  const takeSnapshot = () => {
    snapshotRef.current ??= editorRef.current?.snapshotBlocks() ?? null;
  };

  return (
    <div className="mt-3 space-y-2">
      {operations.map((op, i) => (
        <ConfirmCard
          key={i}
          operation={op}
          onApply={() => {
            takeSnapshot();
            editorRef.current?.applyOperations([op]);
          }}
          onPreview={() => editorRef.current?.scrollToAnchor(op.anchor ?? "")}
          onSkip={() => {
            /* intentional no-op */
          }}
          onUndo={handleUndo}
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
  resetThread: () => Promise<void>;
  onClearHistory: () => void;
}

export default function DocAIAgentPanel({
  docRelPath,
  threadId,
  editorRef,
  onClose,
  subThreadId,
  ensureThread,
  isCreating,
  resetThread,
  onClearHistory,
}: DocAIAgentPanelProps) {
  const { models } = useModels();
  const [modelName, setModelName] = useState<string | null>(null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [mode, setMode] = useState<AIMode>("ask");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
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
    return { client, assistantId: "lead_agent", threadId: subThreadId };
  }, [client, subThreadId]);
  const streamState = useStream(streamConfig);

  const pendingRef = useRef<{
    message: string;
    modelName: string | null;
  } | null>(null);
  const [submitTick, setSubmitTick] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // ── model selector ────────────────────────────────────────────────
  useEffect(() => {
    if (!modelMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (
        modelMenuRef.current &&
        !modelMenuRef.current.contains(e.target as Node)
      )
        setModelMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelMenuOpen]);

  useEffect(() => {
    if (!modeMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (
        modeMenuRef.current &&
        !modeMenuRef.current.contains(e.target as Node)
      )
        setModeMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modeMenuOpen]);

  const selectedModelLabel = modelName
    ? (models.find((m) => m.name === modelName)?.display_name ?? modelName)
    : "默认模型";

  // ── submit ────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    const el = inputRef.current;
    if (!el) return;
    const trimmed = el.value.trim();
    if (!trimmed || isCreating || submitting) return;

    const message = trimmed;
    setUserMessages((prev) => [...prev, message]);
    el.value = "";
    el.style.height = "auto";
    setError(null);
    setSubmitting(true);

    try {
      // Sync current editor content to backend
      const rawMarkdown = (await editorRef.current?.getMarkdown()) ?? "";
      const cleanContent = rawMarkdown
        .replace(/<span[^>]*data-ai-\w+[^>]*>/g, "")
        .replace(/<\/span>/g, "");
      const token =
        typeof document !== "undefined"
          ? /(?:^|;\s*)csrf_token=([^;]+)/.exec(document.cookie)?.[1]
          : null;
      await fetch(
        `/api/extensions/docmgr/personal-docs/${encodeURIComponent(threadId)}/content`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { "X-CSRF-Token": token } : {}),
          },
          credentials: "include",
          body: JSON.stringify({ rel_path: docRelPath, content: cleanContent }),
        },
      );

      // C10: AI 消息提交前把当前内容存为版本快照（改稿后可回退）。失败不阻塞主流程。
      try {
        await docmgrApi.createPersonalVersion(threadId, {
          rel_path: docRelPath,
          content: cleanContent,
          label: "AI 编辑前快照",
        });
      } catch {
        /* 版本快照失败不影响 AI 对话 */
      }

      await ensureThread();
      pendingRef.current = { message, modelName };
      setSubmitTick((v) => v + 1);
    } catch (e) {
      // Restore input on failure so user can retry
      el.value = message;
      setError(getErrorMessage(e, "发送失败，请重试"));
    } finally {
      setSubmitting(false);
    }
  }, [
    isCreating,
    submitting,
    ensureThread,
    modelName,
    editorRef,
    threadId,
    docRelPath,
  ]);

  // ── send queued message when stream is ready ──────────────────────
  // Watch streamState.isLoading directly so the effect fires when loading completes.
  const streamLoading = !!streamState?.isLoading;
  useEffect(() => {
    if (!subThreadId || streamLoading || !pendingRef.current) return;

    const { message, modelName: mn } = pendingRef.current;
    pendingRef.current = null;

    void (async () => {
      try {
        const docContent = (await editorRef.current?.getMarkdown()) ?? "";
        const anchors = (editorRef.current?.getBlockAnchors() ?? [])
          .filter((a) => a.text)
          .map((a) => `"${a.text}"`)
          .join("\n");

        const prompt = buildPrompt({
          mode: modeRef.current,
          docContent,
          anchors,
          userMessage: message,
        });

        void streamState.submit(
          { messages: [{ type: "human", content: prompt }] },
          {
            configurable: { ...(mn ? { model_name: mn } : {}) },
            recursion_limit: 250,
          } as Parameters<typeof streamState.submit>[1],
        );
      } catch (e) {
        const msg = e instanceof Error ? e.message : "";
        const status =
          typeof e === "object" && e !== null && "status" in e
            ? (e as { status?: unknown }).status
            : undefined;
        const isMissing = status === 404 || /not found/i.test(msg);
        console.warn("[DocAI] submit effect failed:", msg);
        if (isMissing) {
          // 线程失效（网关重建/被删）→ 重建后自动重试一次
          try {
            await resetThread();
            pendingRef.current = { message, modelName: mn };
            setSubmitTick((v) => v + 1);
            return;
          } catch {
            /* 重建失败，走错误提示 */
          }
        }
        setError("发送失败: " + (msg || "未知错误"));
      }
    })();
  }, [
    subThreadId,
    streamLoading,
    submitTick,
    editorRef,
    streamState,
    resetThread,
  ]);

  // ── new chat ──────────────────────────────────────────────────────
  const handleNewChat = async () => {
    void streamState?.stop?.();
    if (subThreadId) clearUserMessages(subThreadId);
    setUserMessages([]);
    await resetThread(); // 原子操作：清除旧线程 + 创建新线程，subThreadId 永不为 null
    onClearHistory();
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
  // ponytail: persist user messages in localStorage so they survive
  // page refresh and panel close/reopen.
  const [userMessages, setUserMessages] = useState<string[]>(() => {
    return subThreadId ? loadUserMessages(subThreadId) : [];
  });

  // Sync state → localStorage
  useEffect(() => {
    if (subThreadId && userMessages.length > 0) {
      saveUserMessages(subThreadId, userMessages);
    }
  }, [subThreadId, userMessages]);

  const allMessages = useMemo(() => {
    return (streamState?.messages ?? []).filter((m) => {
      if (m.additional_kwargs?.hide_from_ui) return false;
      return m.type === "ai";
    });
  }, [streamState?.messages]);

  /** Parse a single AI message for operations. */
  const parseAIMessage = useCallback(
    (
      content: unknown,
    ): { text: string; ops: DocOperation[] | null; error: string | null } => {
      const raw =
        typeof content === "string"
          ? content
          : Array.isArray(content)
            ? content
                .map((b) => {
                  if (typeof b !== "object" || b === null || !("text" in b))
                    return "";
                  const t = (b as { text?: unknown }).text;
                  return typeof t === "string" ? t : "";
                })
                .join("")
            : "";
      if (!raw) return { text: "", ops: null, error: null };
      const parsed = parseOperations(raw);
      return {
        text: parsed.analysis,
        ops: parsed.operations,
        error: parsed.parseError,
      };
    },
    [],
  );

  return (
    <div className="bg-background flex h-full w-full flex-col">
      {/* Header */}
      <div className="border-border flex shrink-0 items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Sparkles className="text-primary h-4 w-4" />
          <span className="text-foreground text-sm font-semibold">AI 助手</span>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleNewChat}
            title="清除对话"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {subThreadId ? (
          userMessages.length === 0 && allMessages.length === 0 ? (
            <WelcomePage />
          ) : (
            <div className="space-y-4 p-4">
              {/* Interleaved Q&A: 问1 答1 问2 答2 ... */}
              {(() => {
                const aiMsgs = allMessages.filter((m) => m.type === "ai");
                const items: Array<
                  | { type: "human"; text: string; idx: number }
                  | { type: "ai"; msg: (typeof allMessages)[number] }
                > = [];
                let aiIdx = 0;
                for (
                  let i = 0;
                  i < Math.max(userMessages.length, aiMsgs.length);
                  i++
                ) {
                  if (i < userMessages.length)
                    items.push({
                      type: "human",
                      text: userMessages[i]!,
                      idx: i,
                    });
                  if (aiIdx < aiMsgs.length)
                    items.push({ type: "ai", msg: aiMsgs[aiIdx++]! });
                }
                return items.map((item) => {
                  if (item.type === "human") {
                    return (
                      <div
                        key={`user-${item.idx}`}
                        className="flex justify-end"
                      >
                        <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-md px-3.5 py-2 text-sm leading-relaxed break-words whitespace-pre-wrap">
                          {item.text}
                        </div>
                      </div>
                    );
                  }
                  const { text, ops, error } = parseAIMessage(item.msg.content);
                  return (
                    <div key={item.msg.id}>
                      <div className="text-foreground text-sm leading-relaxed break-words">
                        {text ? (
                          <SafeStreamdown>{text}</SafeStreamdown>
                        ) : (
                          <span className="text-muted-foreground flex items-center gap-2">
                            <span className="bg-primary h-1.5 w-1.5 animate-pulse rounded-full" />
                            思考中...
                          </span>
                        )}
                      </div>
                      {ops && ops.length > 0 && mode !== "plan" && (
                        <OperationCards
                          operations={ops}
                          editorRef={editorRef}
                          mode={mode}
                        />
                      )}
                      {error && (
                        <div className="text-muted-foreground bg-muted/30 mt-2 rounded p-2 text-xs">
                          ⚠️ {error}
                        </div>
                      )}
                    </div>
                  );
                });
              })()}

              {streamState?.isLoading && (
                <div className="text-muted-foreground flex items-center gap-2 px-1 text-sm">
                  <span className="bg-primary h-1.5 w-1.5 animate-pulse rounded-full" />
                  生成中...
                </div>
              )}
            </div>
          )
        ) : isCreating ? (
          <div className="text-muted-foreground flex h-full items-center justify-center">
            <span className="border-primary mr-2 h-4 w-4 animate-spin rounded-full border-2 border-t-transparent" />
            准备中...
          </div>
        ) : (
          <WelcomePage />
        )}
      </div>

      {/* Input area */}
      <div className="border-border shrink-0 border-t p-3">
        {error && (
          <div className="mb-2 flex items-center justify-between rounded-lg bg-red-50 px-3 py-2 text-xs text-red-500 dark:bg-red-950/20">
            <span>❌ {error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-2 text-red-400 hover:text-red-600"
            >
              ✕
            </button>
          </div>
        )}
        <div className="bg-muted/30 border-border rounded-2xl border px-3 py-2">
          <textarea
            ref={inputRef}
            onInput={autoResize}
            onKeyDown={handleKeyDown}
            placeholder="输入指令..."
            rows={1}
            disabled={isCreating || submitting}
            className="text-foreground placeholder:text-muted-foreground max-h-[120px] w-full min-w-0 resize-none border-none bg-transparent text-sm leading-relaxed outline-none"
          />
          <div className="mt-1.5 flex items-center justify-between">
            <div className="flex shrink-0 items-center gap-2">
              {/* Mode selector */}
              <div ref={modeMenuRef} className="relative shrink-0">
                <button
                  type="button"
                  onClick={() => setModeMenuOpen((v) => !v)}
                  className="text-muted-foreground hover:text-foreground hover:bg-muted flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[13px] transition-colors"
                >
                  <span>
                    {MODE_OPTIONS.find((m) => m.value === mode)?.label ?? "Ask"}
                  </span>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2.5 3.5L5 6L7.5 3.5"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                {modeMenuOpen && (
                  <div className="bg-background border-border absolute bottom-full left-0 z-50 mb-2 w-28 rounded-xl border py-1 shadow-lg">
                    {MODE_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => {
                          setMode(opt.value);
                          setModeMenuOpen(false);
                        }}
                        className={`hover:bg-muted w-full px-3 py-1.5 text-left text-xs ${mode === opt.value ? "bg-primary/5 text-primary" : ""}`}
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
                  className="text-muted-foreground hover:text-foreground hover:bg-muted flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[13px] transition-colors"
                >
                  <span className="max-w-[72px] truncate">
                    {selectedModelLabel}
                  </span>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path
                      d="M2.5 3.5L5 6L7.5 3.5"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                {modelMenuOpen && (
                  <div className="bg-background border-border absolute right-0 bottom-full z-50 mb-2 max-h-48 w-40 overflow-y-auto rounded-xl border py-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        setModelName(null);
                        setModelMenuOpen(false);
                      }}
                      className={cn(
                        "hover:bg-muted w-full px-3 py-1.5 text-left text-xs",
                        !modelName && "bg-primary/5 text-primary",
                      )}
                    >
                      默认模型
                    </button>
                    {models.map((m) => (
                      <button
                        key={m.name}
                        type="button"
                        onClick={() => {
                          setModelName(m.name);
                          setModelMenuOpen(false);
                        }}
                        className={cn(
                          "hover:bg-muted w-full px-3 py-1.5 text-left text-xs",
                          modelName === m.name && "bg-primary/5 text-primary",
                        )}
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
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors",
                !streamState?.isLoading && !isCreating && !submitting
                  ? "bg-primary text-primary-foreground hover:opacity-90"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {streamState?.isLoading || isCreating || submitting ? (
                <span className="border-muted-foreground h-3 w-3 animate-spin rounded-full border-2 border-t-transparent" />
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
