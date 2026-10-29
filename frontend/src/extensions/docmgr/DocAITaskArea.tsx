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
  if (action.type === "dismiss") return null;
  if (action.type === "finish")
    return state ? { ...state, running: false } : state;
  if (!state) return state;
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
      setBusy(true);
      if (fresh) {
        userEditedRef.current = false;
        setUndoBlocked(false);
        snapshotRef.current = ed.snapshotBlocks();
        dispatch({ type: "reset", operation });
      }
      try {
        const raw = await ed.getMarkdown();
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
          },
        );
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
        const controller = new AbortController();
        abortRef.current = controller;
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
      applyOpsSelf(sec.ops);
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
    ed.restoreBlocks(snapshotRef.current);
    dispatch({ type: "reverted" });
  }, [params.editorRef]);

  const dismiss = useCallback(() => {
    if (busy) return;
    dispatch({ type: "dismiss" });
  }, [busy]);

  const retrySection = useCallback(
    (index: number) => {
      if (!state) return;
      void startTask(state.operation, [index], false);
    },
    [state, startTask],
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
    insertSummary: applyOpsSelf,
  };
}

// ── 预设 chips + 任务区组件（Task 12 实现） ───────────────────────────
