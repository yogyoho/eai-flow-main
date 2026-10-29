"use client";

// EAI-CUSTOM (全文操作 M1): 面板任务区状态机 + 组件（spec §4.4）。
// 任务区独立于 thread 消息流：不伪造 assistant 消息、不污染 lead_agent 线程历史。

import { useCallback, useReducer, useRef, useState } from "react";

import { type DocAITransformEvent, docmgrApi } from "../api";

import type {
  DocOperation,
  PersonalBlockNoteEditorRef,
} from "./PersonalBlockNoteEditor";

// ── 状态机 ───────────────────────────────────────────────────────────

export type TaskSectionStatus =
  | "streaming"
  | "ready"
  | "unchanged"
  | "applied"
  | "skipped"
  | "failed";

export interface TaskSection {
  index: number;
  title: string;
  status: TaskSectionStatus;
  ops?: DocOperation[];
  error?: string;
}

export interface DocAITaskState {
  operation: string;
  running: boolean;
  sections: TaskSection[];
  summary?: string;
  failed: number[];
  skipped: number[];
  message?: string;
}

export type DocAITaskAction =
  | DocAITransformEvent
  | { type: "reset"; operation: string }
  | { type: "restart"; operation: string }
  | { type: "apply_section"; index: number }
  | { type: "reverted" }
  | { type: "cancel" }
  | { type: "dismiss" }
  | { type: "finish" };

export const initialTaskState = (operation: string): DocAITaskState => ({
  operation,
  running: true,
  sections: [],
  failed: [],
  skipped: [],
});

function upsertSection(
  sections: TaskSection[],
  next: TaskSection,
): TaskSection[] {
  const i = sections.findIndex((s) => s.index === next.index);
  if (i === -1) return [...sections, next].sort((a, b) => a.index - b.index);
  const copy = [...sections];
  copy[i] = { ...copy[i]!, ...next };
  return copy;
}

export function taskReducer(
  state: DocAITaskState | null,
  action: DocAITaskAction,
): DocAITaskState | null {
  if (action.type === "reset") return initialTaskState(action.operation);
  // EAI-CUSTOM (全文操作 M1, 终审 I-2a): retry（fresh=false）重开事件闸门——
  // cancel/finish 后 running 已是 false，不重置则下方守卫会吞掉重试的在途事件。
  if (action.type === "restart")
    return state
      ? { ...state, running: true, message: undefined }
      : initialTaskState(action.operation);
  if (action.type === "dismiss") return null;
  if (action.type === "finish")
    return state ? { ...state, running: false } : state;
  if (!state) return state;
  // EAI-CUSTOM (全文操作 M1, 终审 I-2a): cancel/finish 后拒收在途流事件——
  // 已 resolve 的 chunk 不得让已丢弃的节长回任务区。
  if (
    !state.running &&
    (action.type === "section_start" ||
      action.type === "ops" ||
      action.type === "section_error")
  ) {
    return state;
  }
  switch (action.type) {
    case "section_start":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title: action.title,
          status: action.skipped ? "skipped" : "streaming",
        }),
        skipped: action.skipped
          ? [...new Set([...state.skipped, action.index])]
          : state.skipped,
      };
    case "ops": {
      if (action.ops.length === 0) {
        return {
          ...state,
          sections: upsertSection(state.sections, {
            index: action.index,
            title:
              state.sections.find((s) => s.index === action.index)?.title ?? "",
            status: "unchanged",
          }),
        };
      }
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title:
            state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "ready",
          ops: action.ops as DocOperation[],
        }),
      };
    }
    case "section_error":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title:
            state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "failed",
          error: action.message,
        }),
        failed: [...new Set([...state.failed, action.index])],
      };
    case "summary":
      return { ...state, summary: action.content };
    case "done":
      return {
        ...state,
        running: false,
        failed: action.failed,
        skipped: action.skipped,
        message: action.message,
      };
    case "apply_section":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title:
            state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "applied",
        }),
      };
    case "reverted":
      return {
        ...state,
        sections: state.sections.map((s) =>
          s.status === "applied" ? { ...s, status: "ready" } : s,
        ),
      };
    case "cancel":
      return {
        ...state,
        running: false,
        // 取消 = 未确认 ops 丢弃（spec §4.4）：已应用/无变更/跳过保留，其余清除
        sections: state.sections.filter((s) =>
          ["applied", "unchanged", "skipped"].includes(s.status),
        ),
        message: "已取消：未确认的操作已丢弃",
      };
    default:
      return state;
  }
}

// ── 任务通道 hook ────────────────────────────────────────────────────

const CSRF_RE = /(?:^|;\s*)csrf_token=([^;]+)/;

function getErrMsg(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function useDocAITask(params: {
  editorRef: React.RefObject<PersonalBlockNoteEditorRef | null>;
  threadId: string;
  docRelPath: string;
  modelName: string | null;
}) {
  const [state, dispatch] = useReducer(taskReducer, null);
  const [busy, setBusy] = useState(false);
  const [undoBlocked, setUndoBlocked] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const snapshotRef = useRef<unknown[] | null>(null);
  const userEditedRef = useRef(false);
  const selfApplyRef = useRef(false);

  const markUserEdited = useCallback(() => {
    if (!selfApplyRef.current) userEditedRef.current = true;
  }, []);

  // 任务自己的 applyOperations 也会触发 onChange —— selfApplyRef 屏蔽，不算用户手改。
  const applyOpsSelf = useCallback(
    (ops: DocOperation[]) => {
      const ed = params.editorRef.current;
      if (!ed) throw new Error("编辑器未就绪");
      selfApplyRef.current = true;
      try {
        ed.applyOperations(ops);
      } finally {
        selfApplyRef.current = false;
      }
    },
    [params.editorRef],
  );

  const startTask = useCallback(
    async (operation: string, sections?: number[], fresh = true) => {
      const ed = params.editorRef.current;
      if (!ed || busy) return;
      // EAI-CUSTOM (全文操作 M1, 终审 I-2b): controller 前置到函数开头——
      // PUT 同步阶段点取消也要立刻掐断在途请求，不能等 aiTransformStream 才有 signal。
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      if (fresh) {
        userEditedRef.current = false;
        setUndoBlocked(false);
        snapshotRef.current = ed.snapshotBlocks();
        dispatch({ type: "reset", operation });
      } else {
        dispatch({ type: "restart", operation });
      }
      try {
        const raw = await ed.getMarkdown();
        if (controller.signal.aborted) return;
        const cleanContent = raw
          .replace(/<span[^>]*data-ai-\w+[^>]*>/g, "")
          .replace(/<\/span>/g, "");
        // bug-3302 同源修复：任务通道 PUT 同步必须检查 res.ok，失败即中止（半程文档不投喂模型）
        const token =
          typeof document !== "undefined"
            ? CSRF_RE.exec(document.cookie)?.[1]
            : null;
        const putRes = await fetch(
          `/api/extensions/docmgr/personal-docs/${encodeURIComponent(params.threadId)}/content`,
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              ...(token ? { "X-CSRF-Token": token } : {}),
            },
            credentials: "include",
            body: JSON.stringify({
              rel_path: params.docRelPath,
              content: cleanContent,
            }),
            signal: controller.signal,
          },
        );
        if (controller.signal.aborted) return;
        if (!putRes.ok) {
          throw new Error(`文档同步失败（${putRes.status}），已中止任务`);
        }
        try {
          await docmgrApi.createPersonalVersion(params.threadId, {
            rel_path: params.docRelPath,
            content: cleanContent,
            label: "AI 全文操作前快照",
          });
        } catch {
          /* 版本快照失败不阻塞任务 */
        }
        if (controller.signal.aborted) return;
        await docmgrApi.aiTransformStream<DocAITaskAction>(
          {
            thread_id: params.threadId,
            rel_path: params.docRelPath,
            operation,
            content: cleanContent,
            model_name: params.modelName ?? undefined,
            sections,
          },
          (event) => dispatch(event),
          controller.signal,
        );
      } catch (e) {
        if ((e as Error)?.name !== "AbortError") {
          dispatch({
            type: "done",
            total: 0,
            failed: [],
            skipped: [],
            message: getErrMsg(e, "任务失败"),
          });
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
        dispatch({ type: "finish" });
      }
    },
    [busy, params],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "cancel" });
  }, []);

  const applySection = useCallback(
    (index: number) => {
      const sec = state?.sections.find((s) => s.index === index);
      if (!sec?.ops) return;
      // EAI-CUSTOM (全文操作 M1, walkthrough F6): apply 异常（如锚点失配）就地转任务区
      // 反馈，不直抛 window——uncaught 会盖掉该节的失败可见性。
      try {
        applyOpsSelf(sec.ops);
      } catch (e) {
        dispatch({
          type: "done",
          total: 0,
          failed: state?.failed ?? [],
          skipped: state?.skipped ?? [],
          message: `应用失败：${getErrMsg(e, "未知错误")}`,
        });
        return;
      }
      dispatch({ type: "apply_section", index });
    },
    [state, applyOpsSelf],
  );

  const applyAll = useCallback(() => {
    if (!state) return;
    const failures: string[] = [];
    for (const sec of state.sections) {
      if (sec.status !== "ready" || !sec.ops) continue;
      try {
        applyOpsSelf(sec.ops);
        dispatch({ type: "apply_section", index: sec.index });
      } catch (e) {
        failures.push(
          `${sec.title || `第 ${sec.index + 1} 节`}: ${getErrMsg(e, "失败")}`,
        );
      }
    }
    if (failures.length > 0) {
      dispatch({
        type: "done",
        total: 0,
        failed: state.failed,
        skipped: state.skipped,
        message: `部分应用失败：${failures.join("；")}`,
      });
    }
  }, [state, applyOpsSelf]);

  const undoAll = useCallback(() => {
    const ed = params.editorRef.current;
    if (!ed || !snapshotRef.current) return;
    if (userEditedRef.current) {
      setUndoBlocked(true); // 任务开始后文档被改过（含其他 AI 操作）→ 禁整批回滚，指路版本历史
      return;
    }
    // EAI-CUSTOM (全文操作 M1, 终审 M-4): restoreBlocks 会触发 onChange，
    // selfApplyRef 屏蔽（同 applyOpsSelf）——否则整批回滚把 userEditedRef 置真，
    // 撤销一次后 undo 被永久禁用。
    selfApplyRef.current = true;
    try {
      ed.restoreBlocks(snapshotRef.current);
    } finally {
      selfApplyRef.current = false;
    }
    dispatch({ type: "reverted" });
  }, [params.editorRef, selfApplyRef]);

  const dismiss = useCallback(() => {
    if (busy) return;
    dispatch({ type: "dismiss" });
  }, [busy]);

  const retrySection = useCallback(
    (index: number) => {
      if (!state) return;
      // EAI-CUSTOM (全文操作 M1, 终审 M-2): 任一节已应用后禁用重试——应用后内容已变、
      // 节序号漂移，按旧下标重试会改写错节。
      if (state.sections.some((s) => s.status === "applied")) return;
      void startTask(state.operation, [index], false);
    },
    [state, startTask],
  );

  // EAI-CUSTOM (全文操作 M1, walkthrough F6): 插入摘要同走 catch 转反馈，不直抛。
  const insertSummary = useCallback(
    (ops: DocOperation[]) => {
      try {
        applyOpsSelf(ops);
      } catch (e) {
        dispatch({
          type: "done",
          total: 0,
          failed: state?.failed ?? [],
          skipped: state?.skipped ?? [],
          message: `插入失败：${getErrMsg(e, "未知错误")}`,
        });
      }
    },
    [state, applyOpsSelf],
  );

  return {
    state,
    busy,
    undoBlocked,
    markUserEdited,
    startTask,
    cancel,
    applySection,
    applyAll,
    undoAll,
    dismiss,
    retrySection,
    insertSummary,
  };
}

// ── 预设 chips + 任务区组件（Task 12 实现） ───────────────────────────

// ── 组件 ─────────────────────────────────────────────────────────────

export const PRESETS = [
  { id: "polish", label: "全文润色" },
  { id: "proofread", label: "全文校对" },
  { id: "terminology", label: "术语统一" },
  { id: "format", label: "格式规范" },
  { id: "toc", label: "生成目录" },
  { id: "summary", label: "全文摘要" },
] as const;

export function PresetChips({
  disabled,
  onPick,
}: {
  disabled: boolean;
  onPick: (operation: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {PRESETS.map((p) => (
        <button
          key={p.id}
          type="button"
          disabled={disabled}
          onClick={() => onPick(p.id)}
          title={`对全文执行「${p.label}」（逐节处理，可逐节确认）`}
          className="border-border/60 hover:border-primary/50 hover:bg-primary/5 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

export function SectionCard({
  section,
  onApply,
  onRetry,
}: {
  section: TaskSection;
  onApply: (index: number) => void;
  onRetry: (index: number) => void;
}) {
  const { index, title, status, ops, error } = section;
  const preview = ops?.[0]?.content?.slice(0, 160) ?? "";
  return (
    <div className="border-border/60 bg-background rounded-lg border text-xs">
      <div className="flex items-center justify-between px-3 py-1.5">
        <span className="text-foreground font-medium">
          {title || `第 ${index + 1} 节`}
        </span>
        <span className="text-muted-foreground">
          {status === "streaming" && "生成中…"}
          {status === "ready" && "待确认"}
          {status === "unchanged" && "本节无变更"}
          {status === "skipped" && "已跳过（含公式/表格/图片）"}
          {status === "applied" && "✓ 已应用"}
          {status === "failed" && "失败"}
        </span>
      </div>
      {status === "ready" && preview && (
        <div className="border-border/40 text-muted-foreground max-h-24 overflow-y-auto border-t px-3 py-1.5 whitespace-pre-wrap">
          {preview}
          {(ops?.[0]?.content?.length ?? 0) > 160 ? "…" : ""}
        </div>
      )}
      {status === "failed" && error && (
        <div className="border-border/40 text-destructive border-t px-3 py-1.5">
          {error}
        </div>
      )}
      {status === "ready" && (
        <div className="border-border/40 flex border-t">
          <button
            type="button"
            onClick={() => onApply(index)}
            className="text-primary hover:bg-primary/5 flex-1 py-1.5"
          >
            应用
          </button>
        </div>
      )}
      {status === "failed" && (
        <div className="border-border/40 flex border-t">
          <button
            type="button"
            onClick={() => onRetry(index)}
            className="text-primary hover:bg-primary/5 flex-1 py-1.5"
          >
            重试本节
          </button>
        </div>
      )}
    </div>
  );
}

export function DocAITaskArea({
  task,
  busy,
  undoBlocked,
  onApplySection,
  onApplyAll,
  onUndoAll,
  onRetrySection,
  onInsertSummary,
  onCancel,
  onDismiss,
}: {
  task: DocAITaskState;
  busy: boolean;
  undoBlocked: boolean;
  onApplySection: (index: number) => void;
  onApplyAll: () => void;
  onUndoAll: () => void;
  onRetrySection: (index: number) => void;
  onInsertSummary: (content: string) => void;
  onCancel: () => void;
  onDismiss: () => void;
}) {
  const appliedCount = task.sections.filter(
    (s) => s.status === "applied",
  ).length;
  const readyCount = task.sections.filter((s) => s.status === "ready").length;
  return (
    <div className="shrink-0 space-y-2 px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="text-foreground text-xs font-semibold">
          全文任务{busy ? "（进行中…）" : ""}
        </span>
        <div className="flex items-center gap-2">
          {busy && (
            <button
              type="button"
              onClick={onCancel}
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              取消
            </button>
          )}
          {!busy && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              关闭
            </button>
          )}
        </div>
      </div>
      {task.message && (
        <div className="bg-muted/30 text-muted-foreground rounded px-2 py-1.5 text-xs">
          {task.message}
        </div>
      )}
      {undoBlocked && (
        <div className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-400">
          任务开始后文档已被修改，整批回滚已禁用；请用「版本历史」恢复到「AI
          全文操作前快照」。
        </div>
      )}
      {task.summary && (
        <div className="border-border/60 rounded-lg border p-2 text-xs">
          <div className="text-foreground mb-1 font-medium">全文摘要</div>
          <div className="text-muted-foreground max-h-40 overflow-y-auto whitespace-pre-wrap">
            {task.summary}
          </div>
          <button
            type="button"
            onClick={() => onInsertSummary(task.summary!)}
            className="text-primary mt-1.5 hover:underline"
          >
            插入文末
          </button>
        </div>
      )}
      <div className="max-h-72 space-y-1.5 overflow-y-auto">
        {task.sections.map((s) => (
          <SectionCard
            key={s.index}
            section={s}
            onApply={onApplySection}
            onRetry={onRetrySection}
          />
        ))}
      </div>
      {!busy && readyCount > 0 && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onApplyAll}
            className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-xs"
          >
            全部应用（{readyCount}）
          </button>
          {appliedCount > 0 && !undoBlocked && (
            <button
              type="button"
              onClick={onUndoAll}
              className="border-border/60 rounded-md border px-3 py-1.5 text-xs"
            >
              撤销整批
            </button>
          )}
        </div>
      )}
      {!busy && appliedCount > 0 && readyCount === 0 && !undoBlocked && (
        <button
          type="button"
          onClick={onUndoAll}
          className="border-border/60 rounded-md border px-3 py-1.5 text-xs"
        >
          撤销整批（{appliedCount}）
        </button>
      )}
    </div>
  );
}
