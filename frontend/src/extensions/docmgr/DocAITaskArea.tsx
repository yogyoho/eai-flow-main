"use client";

// EAI-CUSTOM (全文操作 M1): 面板任务区状态机 + 组件（spec §4.4）。
// 任务区独立于 thread 消息流：不伪造 assistant 消息、不污染 lead_agent 线程历史。
// EAI-CUSTOM (全文操作 v2): 任务区工单化——ticket 头（进度条+计划行）+ 逐节 diff 卡
//（接受/拒绝/恢复建议）+ 行级 LCS diff（sectionDiff.ts）。

import { ChevronDown, Square, Undo2, X } from "lucide-react";
import { useCallback, useMemo, useReducer, useRef, useState } from "react";

import { cn } from "@/lib/utils";

import { type DocAITransformEvent, docmgrApi } from "../api";

import type {
  DocOperation,
  PersonalBlockNoteEditorRef,
} from "./PersonalBlockNoteEditor";
import { diffLines, type DiffLine } from "./sectionDiff";

// ── 状态机 ───────────────────────────────────────────────────────────

export type TaskSectionStatus =
  | "streaming"
  | "ready"
  | "unchanged"
  | "applied"
  | "rejected"
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
  /** EAI-CUSTOM (全文操作 v2): 后端期望总节数（done 事件携带；错误路径 total:0 不采纳）——工单进度条分母。 */
  total?: number;
}

export type DocAITaskAction =
  | DocAITransformEvent
  | { type: "reset"; operation: string }
  | { type: "restart"; operation: string }
  | { type: "apply_section"; index: number }
  | { type: "reject_section"; index: number }
  | { type: "restore_section"; index: number }
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
        // EAI-CUSTOM (全文操作 v2): 记录期望总节数供进度条；错误路径复用 done 只为
        // 携带 message（total:0），此时不覆盖。
        total: action.total > 0 ? action.total : state.total,
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
    // EAI-CUSTOM (全文操作 v2): 拒绝 = 用户否决本节建议。ops 保留（「恢复建议」可
    // 反悔回 ready），不计入 failed，不从列表清除。用户动作，同 apply_section 不设
    // running 守卫。
    case "reject_section":
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title:
            state.sections.find((s) => s.index === action.index)?.title ?? "",
          status: "rejected",
        }),
      };
    // EAI-CUSTOM (全文操作 v2): 恢复建议 = 反悔拒绝，仅 rejected → ready 单向。
    case "restore_section": {
      const target = state.sections.find((s) => s.index === action.index);
      if (target?.status !== "rejected") return state;
      return {
        ...state,
        sections: upsertSection(state.sections, {
          index: action.index,
          title: target.title,
          status: "ready",
        }),
      };
    }
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
        // 取消 = 未确认 ops 丢弃（spec §4.4）：已应用/无变更/跳过保留，其余清除。
        // v2 决策：rejected 同属未确认，取消即丢弃（与 ready/streaming/failed 一致）。
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

  // EAI-CUSTOM (全文操作 v2): 拒绝/恢复均为用户即时动作，不设 running 守卫（同 apply_section）。
  const rejectSection = useCallback((index: number) => {
    dispatch({ type: "reject_section", index });
  }, []);

  const restoreSection = useCallback((index: number) => {
    dispatch({ type: "restore_section", index });
  }, []);

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
    rejectSection,
    restoreSection,
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

// ── v2 工单组件（工单头 + 逐节 diff 卡，替换 M1 的 SectionCard） ─────

// EAI-CUSTOM (全文操作 v2): pill 色档沿用仓库 Pill 习语（contract-price bits 同款
// token：success/warn/destructive/muted），不新增色系。
type PillTone = "ok" | "warn" | "err" | "gray";

const PILL_TONE: Record<PillTone, string> = {
  ok: "border-success/30 bg-success/10 text-success",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  err: "border-destructive/30 bg-destructive/10 text-destructive",
  gray: "border-border bg-muted/40 text-muted-foreground",
};

function statusPill(status: TaskSectionStatus): {
  tone: PillTone;
  label: string;
  pulse?: boolean;
} {
  switch (status) {
    case "streaming":
      return { tone: "warn", label: "生成中", pulse: true };
    case "ready":
      return { tone: "warn", label: "待确认" };
    case "applied":
      return { tone: "ok", label: "已接受" };
    case "rejected":
      return { tone: "gray", label: "已拒绝" };
    case "unchanged":
      return { tone: "gray", label: "无变更" };
    case "skipped":
      return { tone: "gray", label: "已跳过" };
    case "failed":
      return { tone: "err", label: "失败" };
  }
}

function StatusPill({ status }: { status: TaskSectionStatus }) {
  const pill = statusPill(status);
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] font-medium whitespace-nowrap",
        PILL_TONE[pill.tone],
      )}
    >
      {pill.pulse && (
        <span
          aria-hidden
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"
        />
      )}
      {pill.label}
    </span>
  );
}

// 行 diff 色档：del=destructive 删除线；ins=emerald（仓库既有「新增」色习语，见
// ApprovalsQueue/StatCard 先例）；ctx=muted。前缀 − / + / 空格。
const DIFF_LINE_CLASS: Record<DiffLine["type"], string> = {
  del: "bg-destructive/10 text-destructive line-through",
  ins: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  ctx: "text-muted-foreground",
};

const DIFF_LINE_PREFIX: Record<DiffLine["type"], string> = {
  del: "−",
  ins: "+",
  ctx: " ",
};

export function DiffCard({
  section,
  oldText,
  onApply,
  onReject,
  onRetry,
  onRestore,
}: {
  section: TaskSection;
  /** 旧节文本（父层经 getSectionText 解析锚点后取得）；空/缺省时 ready 态退化为新内容预览。 */
  oldText?: string;
  onApply: (index: number) => void;
  onReject: (index: number) => void;
  onRetry: (index: number) => void;
  onRestore?: (index: number) => void;
}) {
  const { index, title, status, ops, error } = section;
  // 展开态以挂载时 status 播种（ready 展开、其余收起），用户可自由开合。
  const [open, setOpen] = useState(status === "ready");
  const newContent = ops?.[0]?.content ?? "";
  const lines = useMemo(
    () =>
      status === "ready" && oldText ? diffLines(oldText, newContent) : null,
    [status, oldText, newContent],
  );
  return (
    <div className="border-border/60 bg-background overflow-hidden rounded-lg border text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="hover:bg-muted/40 flex w-full items-center gap-2 px-3 py-2 text-left transition-colors"
      >
        <StatusPill status={status} />
        <span className="text-foreground min-w-0 flex-1 truncate font-medium">
          {title || `第 ${index + 1} 节`}
        </span>
        <ChevronDown
          className={cn(
            "text-muted-foreground h-3.5 w-3.5 shrink-0 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="border-border/40 space-y-2 border-t px-3 py-2">
          {status === "ready" &&
            (lines ? (
              <div className="border-border/40 max-h-52 overflow-y-auto rounded border">
                {lines.map((l, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex gap-1.5 px-2 py-px font-mono text-[11.5px] leading-relaxed break-all whitespace-pre-wrap",
                      DIFF_LINE_CLASS[l.type],
                    )}
                  >
                    <span
                      aria-hidden
                      className="w-2 shrink-0 text-center select-none"
                    >
                      {DIFF_LINE_PREFIX[l.type]}
                    </span>
                    <span className="min-w-0">{l.text || " "}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-muted-foreground max-h-52 overflow-y-auto whitespace-pre-wrap">
                {newContent || "（空内容）"}
              </div>
            ))}
          {status === "skipped" && (
            <div className="text-muted-foreground">
              含公式/表格/图片，AI 未改动本节
            </div>
          )}
          {status === "unchanged" && (
            <div className="text-muted-foreground">本节内容未变化</div>
          )}
          {status === "failed" && (
            <>
              <div className="text-destructive whitespace-pre-wrap">
                {error}
              </div>
              <button
                type="button"
                onClick={() => onRetry(index)}
                className="border-border/60 text-primary hover:bg-primary/5 rounded border px-2 py-1"
              >
                重试本节
              </button>
            </>
          )}
          {status === "rejected" && onRestore && (
            <button
              type="button"
              onClick={() => onRestore(index)}
              className="border-border/60 text-muted-foreground hover:bg-muted rounded border px-2 py-1"
            >
              恢复建议
            </button>
          )}
        </div>
      )}
      {status === "ready" && (
        <div className="border-border/40 flex border-t">
          <button
            type="button"
            onClick={() => onApply(index)}
            className="bg-primary text-primary-foreground hover:bg-primary/90 flex-1 py-1.5 font-medium"
          >
            接受
          </button>
          <button
            type="button"
            onClick={() => onReject(index)}
            className="border-border/60 text-muted-foreground hover:bg-muted flex-1 border-l py-1.5"
          >
            拒绝
          </button>
        </div>
      )}
    </div>
  );
}

// EAI-CUSTOM (全文操作 v2): 工单头——任务名 + 状态 pill + 进度条 + 计划行（纯 state 派生）。
const TERMINAL_STATUSES: readonly TaskSectionStatus[] = [
  "applied",
  "unchanged",
  "skipped",
  "failed",
  "rejected",
];

function TicketHeader({
  task,
  busy,
  onCancel,
  onDismiss,
}: {
  task: DocAITaskState;
  busy: boolean;
  onCancel: () => void;
  onDismiss: () => void;
}) {
  const terminal = task.sections.filter((s) =>
    TERMINAL_STATUSES.includes(s.status),
  ).length;
  const ready = task.sections.filter((s) => s.status === "ready").length;
  // 期望总数：优先 done 事件携带的后端口径；流式中退化为已见卡片数。
  const total =
    task.total && task.total > 0 ? task.total : task.sections.length;
  const pct =
    total > 0 ? Math.min(100, Math.round((terminal / total) * 100)) : 0;
  // 「正在处理」取最后一个 streaming 节（后端逐节推进，同刻至多一个在途）。
  const streamingSec = [...task.sections]
    .reverse()
    .find((s) => s.status === "streaming");
  const opLabel =
    PRESETS.find((p) => p.id === task.operation)?.label ?? task.operation;
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="text-foreground text-xs font-semibold">{opLabel}</span>
        {busy ? (
          <span className="inline-flex h-5 items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 text-[11px] font-medium whitespace-nowrap text-amber-600 dark:text-amber-400">
            <span
              aria-hidden
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"
            />
            执行中
          </span>
        ) : (
          <span className="border-border bg-muted/40 text-muted-foreground inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-medium whitespace-nowrap">
            已完成
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {busy && (
            <button
              type="button"
              onClick={onCancel}
              aria-label="停止任务"
              title="停止任务"
              className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive rounded p-1 transition-colors"
            >
              <Square className="h-3 w-3" fill="currentColor" />
            </button>
          )}
          {!busy && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="关闭任务区"
              title="关闭"
              className="text-muted-foreground hover:bg-muted hover:text-foreground rounded p-1 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
      <div className="bg-muted mt-2 h-1 overflow-hidden rounded-full">
        <div
          className="bg-primary h-full rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1.5 space-y-1 text-[11px]">
        <div className="text-success flex items-center gap-1.5">
          <span aria-hidden>✓</span>已完成处理 {terminal} 节
        </div>
        {streamingSec && (
          <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
            <span
              aria-hidden
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"
            />
            正在处理 {streamingSec.title || `第 ${streamingSec.index + 1} 节`}
          </div>
        )}
        {ready > 0 && (
          <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
            <span aria-hidden>○</span>待确认 {ready} 节
          </div>
        )}
      </div>
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
  onRejectSection,
  onRestoreSection,
  getSectionText,
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
  /** EAI-CUSTOM (全文操作 v2): 拒绝 / 恢复建议回调（hook 的 rejectSection / restoreSection）。 */
  onRejectSection?: (index: number) => void;
  onRestoreSection?: (index: number) => void;
  /** EAI-CUSTOM (全文操作 v2): 锚点文本 → 旧节纯文本（DocAIAgentPanel 持编辑器 ref 负责解析）。 */
  getSectionText?: (anchor: string) => string;
}) {
  const appliedCount = task.sections.filter(
    (s) => s.status === "applied",
  ).length;
  const readyCount = task.sections.filter((s) => s.status === "ready").length;
  // diff 旧文本：仅 ready 节需要（applied 后文档已变、rejected 不展示 diff）；
  // op.anchor 是锚点文本，由面板侧 matchAnchor 解析为块下标后取整节文本。
  const oldTextFor = (s: TaskSection): string | undefined => {
    if (s.status !== "ready" || !getSectionText) return undefined;
    const anchor = s.ops?.[0]?.anchor;
    return anchor ? getSectionText(anchor) : undefined;
  };
  return (
    <div className="shrink-0 px-3 pb-2">
      <div className="border-border/60 bg-muted/20 space-y-2 rounded-lg border p-2.5">
        <TicketHeader
          task={task}
          busy={busy}
          onCancel={onCancel}
          onDismiss={onDismiss}
        />
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
            <DiffCard
              key={s.index}
              section={s}
              oldText={oldTextFor(s)}
              onApply={onApplySection}
              onReject={onRejectSection ?? (() => undefined)}
              onRetry={onRetrySection}
              onRestore={onRestoreSection}
            />
          ))}
        </div>
        {!busy && (readyCount > 0 || appliedCount > 0) && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onApplyAll}
                disabled={readyCount === 0}
                className="bg-primary text-primary-foreground hover:bg-primary/90 flex-1 rounded-md py-1.5 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-40"
              >
                接受全部（{readyCount}）
              </button>
              <button
                type="button"
                onClick={onUndoAll}
                disabled={appliedCount === 0 || undoBlocked}
                className="border-border/60 text-muted-foreground hover:bg-muted hover:text-foreground rounded-md border px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
              >
                撤销整批
              </button>
            </div>
            <div className="text-muted-foreground flex items-center gap-1 text-[11px]">
              <Undo2 aria-hidden className="h-3 w-3 shrink-0" />
              每次批量应用前自动建版本快照，可一键整批撤销。
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
