"use client";

// EAI-CUSTOM (全文操作 M2 Chunk 2): 审查任务区（FindingsCard + 宫格深度审查入口的执行位）。
// 自持 reducer/hook，独立于 DocAITaskArea 改写任务状态机；接 Chunk 1 /ai/review 事件流
//（section_start / finding / section_error / done）。审查只读不改文——「修复」把 finding.fix_op
//（replace_section）经既有 applyOperations 回灌；整批修复前 snapshotBlocks、可整批撤销
//（脏检查沿用 DocAITaskArea batch bar 既有模式）。审查与改写任务互斥，挂载位与任务区同槽。

import { Square, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { cn } from "@/lib/utils";

import { type DocAIFinding, type DocAIReviewEvent, docmgrApi } from "../api";

import type {
  DocOperation,
  PersonalBlockNoteEditorRef,
} from "./PersonalBlockNoteEditor";

// ── 审查类型预设 ─────────────────────────────────────────────────────

// review_type ∈ consistency|numbering|units（custom 仅 API 开放，不进 UI——Chunk 1 契约）。
export const REVIEW_PRESETS = [
  { id: "consistency", label: "术语一致性审查" },
  { id: "numbering", label: "编号连续性审查" },
  { id: "units", label: "公式单位审查" },
] as const;

export type ReviewType = (typeof REVIEW_PRESETS)[number]["id"];

export function reviewTypeLabel(id: string): string {
  return REVIEW_PRESETS.find((p) => p.id === id)?.label ?? id;
}

// ── 状态机 ───────────────────────────────────────────────────────────

export interface ReviewFindingEntry {
  finding: DocAIFinding;
  /** 来源节（后端 split_sections 桶下标），供失败兜底文案「第 n 节」。 */
  sectionIndex: number;
  /** fix_op 已回灌成功（可被整批撤销回退）。 */
  fixed: boolean;
}

export interface DocAIReviewState {
  reviewType: string;
  running: boolean;
  /** 后端期望总节数（section_start/done 携带，取 max 防重跑缩水）——工单进度分母。 */
  total?: number;
  /** 已审节（section_start 去重下标，含 skipped）——进度分子。 */
  audited: number[];
  /** 正在审的节（最后一个非 skipped section_start；done 后清空）——「正在审」计划行。 */
  current?: { index: number; title: string };
  /** findings 按事件序；节桶由 sectionIndex 承载。 */
  entries: ReviewFindingEntry[];
  failed: number[];
  skipped: number[];
  /** 忽略的 finding id（仅内存，restore 可撤销）。 */
  dismissedIds: string[];
  summary?: { error: number; warn: number; info: number };
  message?: string;
}

export type DocAIReviewAction =
  | DocAIReviewEvent
  | { type: "start"; reviewType: string }
  // EAI-CUSTOM (全文操作 M2, 同 DocAITaskArea 终审 I-2a 教训): retry 重开事件闸门——
  // done/finish 后 running 已是 false，不重开则守卫会吞掉重试的在途事件。
  | { type: "restart" }
  | { type: "finish" }
  // EAI-CUSTOM (全文操作 M2): 流异常中断的收官动作——与 done 不同，failed/skipped/
  // total/summary 原样保留（mid-stream section_error 已入册的失败节不得被清空）。
  | { type: "fail"; message: string }
  | { type: "dismiss"; id: string }
  | { type: "restore"; id: string }
  | { type: "fix_applied"; id: string }
  // 整批撤销（restoreBlocks）后所有「已修复」回退为待处理——快照回滚了文档内容。
  | { type: "fixes_reverted" }
  | { type: "reset" };

const EMPTY_SUMMARY = { error: 0, warn: 0, info: 0 };

export const initialReviewState = (reviewType: string): DocAIReviewState => ({
  reviewType,
  running: true,
  audited: [],
  entries: [],
  failed: [],
  skipped: [],
  dismissedIds: [],
});

const dedupePush = (xs: number[], v: number): number[] =>
  xs.includes(v) ? xs : [...xs, v];

export function reviewReducer(
  state: DocAIReviewState | null,
  action: DocAIReviewAction,
): DocAIReviewState | null {
  if (action.type === "reset") return null;
  if (action.type === "start") return initialReviewState(action.reviewType);
  if (action.type === "restart")
    return state ? { ...state, running: true, message: undefined } : state;
  if (action.type === "finish")
    return state ? { ...state, running: false } : state;
  if (action.type === "fail")
    return state
      ? {
          ...state,
          running: false,
          current: undefined,
          message: action.message,
        }
      : state;
  if (!state) return state;
  // EAI-CUSTOM (全文操作 M2, 同 taskReducer 终审 I-2a): done/finish 后拒收在途流事件——
  // 已 resolve 的 chunk 不得让已收官的任务区复活。
  if (
    !state.running &&
    (action.type === "section_start" ||
      action.type === "finding" ||
      action.type === "section_error")
  ) {
    return state;
  }
  switch (action.type) {
    case "section_start":
      return {
        ...state,
        // EAI-CUSTOM (全文操作 M2, 同 taskReducer 复审#2 教训): 分母取 max——
        // 重试/重跑只报小 total 时不得缩水旧分母。
        total: Math.max(state.total ?? 0, action.total),
        audited: dedupePush(state.audited, action.index),
        skipped: action.skipped
          ? dedupePush(state.skipped, action.index)
          : state.skipped,
        current: action.skipped
          ? state.current
          : { index: action.index, title: action.title },
      };
    case "finding": {
      // 按 id upsert（事件重放幂等），新条按事件序追加——节桶由 sectionIndex 字段承载。
      const i = state.entries.findIndex(
        (e) => e.finding.id === action.finding.id,
      );
      const entry: ReviewFindingEntry = {
        finding: action.finding,
        sectionIndex: action.index,
        fixed: false,
      };
      if (i === -1) return { ...state, entries: [...state.entries, entry] };
      const copy = [...state.entries];
      copy[i] = entry;
      return { ...state, entries: copy };
    }
    case "section_error":
      return { ...state, failed: dedupePush(state.failed, action.index) };
    case "done":
      return {
        ...state,
        running: false,
        total: Math.max(state.total ?? 0, action.total),
        current: undefined,
        failed: action.failed,
        skipped: action.skipped,
        // Chunk 1 移交提示：空表短路路径 done 无 summary 键 → 归一为全 0，读侧免判空。
        // 流异常中断走 fail 动作，不经此分支——真 summary 不会被错误路径抹掉。
        summary: action.summary ?? state.summary ?? EMPTY_SUMMARY,
        message: action.message,
      };
    case "dismiss":
      return state.dismissedIds.includes(action.id)
        ? state
        : { ...state, dismissedIds: [...state.dismissedIds, action.id] };
    case "restore":
      return {
        ...state,
        dismissedIds: state.dismissedIds.filter((id) => id !== action.id),
      };
    case "fix_applied":
      return {
        ...state,
        entries: state.entries.map((e) =>
          e.finding.id === action.id ? { ...e, fixed: true } : e,
        ),
      };
    case "fixes_reverted":
      return {
        ...state,
        entries: state.entries.map((e) =>
          e.fixed ? { ...e, fixed: false } : e,
        ),
      };
    default:
      return state;
  }
}

// ── 审查通道 hook ────────────────────────────────────────────────────

// 与 DocAITaskArea 同款 CSRF 读取（该模块私有常量，不跨文件导出）。
const CSRF_RE = /(?:^|;\s*)csrf_token=([^;]+)/;

function getErrMsg(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function useDocAIReview(params: {
  editorRef: React.RefObject<PersonalBlockNoteEditorRef | null>;
  threadId: string;
  docRelPath: string;
  modelName: string | null;
}) {
  const [state, dispatch] = useReducer(reviewReducer, null);
  const [busy, setBusy] = useState(false);
  const [undoBlocked, setUndoBlocked] = useState(false);
  const [hasSnapshot, setHasSnapshot] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const snapshotRef = useRef<unknown[] | null>(null);
  const userEditedRef = useRef(false);
  const selfApplyRef = useRef(false);

  const markUserEdited = useCallback(() => {
    if (!selfApplyRef.current) userEditedRef.current = true;
  }, []);

  // 编辑器异步挂载 → 轮询接线脏检查（同面板对 docTask.markUserEdited 的接线模式）。
  useEffect(() => {
    let off: (() => void) | null = null;
    let tries = 0;
    const timer = setInterval(() => {
      const ed = params.editorRef.current;
      if (ed?.onDocumentChange) {
        off = ed.onDocumentChange(markUserEdited);
        clearInterval(timer);
      } else if (++tries > 25) {
        clearInterval(timer);
      }
    }, 200);
    return () => {
      clearInterval(timer);
      off?.();
    };
  }, [params.editorRef, markUserEdited]);

  // 修复自己的 applyOperations 也会触发 onChange —— selfApplyRef 屏蔽，不算用户手改。
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

  const startReview = useCallback(
    async (reviewType: string) => {
      const ed = params.editorRef.current;
      if (!ed || busy) return;
      // controller 前置（同 startTask 终审 I-2b）：同步 PUT 阶段点取消也立即掐断在途请求。
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      userEditedRef.current = false;
      setUndoBlocked(false);
      snapshotRef.current = null;
      setHasSnapshot(false);
      dispatch({ type: "start", reviewType });
      try {
        const raw = await ed.getMarkdown();
        if (controller.signal.aborted) return;
        const cleanContent = raw
          .replace(/<span[^>]*data-ai-\w+[^>]*>/g, "")
          .replace(/<\/span>/g, "");
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
          throw new Error(`文档同步失败（${putRes.status}），已中止审查`);
        }
        try {
          await docmgrApi.createPersonalVersion(params.threadId, {
            rel_path: params.docRelPath,
            content: cleanContent,
            label: "AI 审查前快照",
          });
        } catch {
          /* 版本快照失败不阻塞审查 */
        }
        if (controller.signal.aborted) return;
        // 审查不收 sections——固定全文档（Chunk 1 契约：请求体无 sections 参数）。
        await docmgrApi.aiReviewStream<DocAIReviewAction>(
          {
            thread_id: params.threadId,
            rel_path: params.docRelPath,
            review_type: reviewType,
            content: cleanContent,
            model_name: params.modelName ?? undefined,
          },
          (event) => dispatch(event),
          controller.signal,
        );
      } catch (e) {
        if ((e as Error)?.name !== "AbortError") {
          // fail 而非 done：已入册的 failed/entries 保留，不合成空权威清单。
          dispatch({ type: "fail", message: getErrMsg(e, "审查失败") });
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
        // 流异常中断（无 done 事件）也保证收官，避免事件闸门永久封锁。
        dispatch({ type: "finish" });
      }
    },
    [busy, params],
  );

  const cancel = useCallback(() => {
    // 停止 = 掐断在途流；已收到的 findings 保留展示（finish 由 finally 统一落）。
    abortRef.current?.abort();
  }, []);

  const applyFix = useCallback(
    (finding: DocAIFinding) => {
      if (!finding.fix_op) return;
      // 锚点应用失败沿用任务区错误反馈路径（就地转 message，不直抛 window）。
      try {
        applyOpsSelf([finding.fix_op as DocOperation]);
      } catch (e) {
        dispatch({
          type: "fail",
          message: `修复失败：${getErrMsg(e, "未知错误")}`,
        });
        return;
      }
      dispatch({ type: "fix_applied", id: finding.id });
    },
    [applyOpsSelf],
  );

  const applyAllFixes = useCallback(() => {
    if (!state) return;
    const ed = params.editorRef.current;
    if (!ed) return;
    // 批量前快照（同 DocAITaskArea snapshotRef 手法）——整批撤销的回滚点。
    userEditedRef.current = false;
    snapshotRef.current = ed.snapshotBlocks();
    setHasSnapshot(true);
    const failures: string[] = [];
    for (const e of state.entries) {
      if (e.fixed || !e.finding.fix_op) continue;
      if (state.dismissedIds.includes(e.finding.id)) continue;
      try {
        applyOpsSelf([e.finding.fix_op as DocOperation]);
        dispatch({ type: "fix_applied", id: e.finding.id });
      } catch (err) {
        failures.push(
          `${e.finding.anchor || `第 ${e.sectionIndex + 1} 节`}: ${getErrMsg(err, "失败")}`,
        );
      }
    }
    if (failures.length > 0) {
      dispatch({
        type: "fail",
        message: `部分修复失败：${failures.join("；")}`,
      });
    }
  }, [state, applyOpsSelf, params.editorRef]);

  const undoAllFixes = useCallback(() => {
    const ed = params.editorRef.current;
    if (!ed || !snapshotRef.current) return;
    if (userEditedRef.current) {
      // 整批修复后文档被改过 → 禁整批撤销，指路版本历史（batch bar 既有模式）。
      setUndoBlocked(true);
      return;
    }
    // restoreBlocks 会触发 onChange，selfApplyRef 屏蔽（同 applyOpsSelf）。
    selfApplyRef.current = true;
    try {
      ed.restoreBlocks(snapshotRef.current);
    } finally {
      selfApplyRef.current = false;
    }
    snapshotRef.current = null;
    setHasSnapshot(false);
    dispatch({ type: "fixes_reverted" });
  }, [params.editorRef]);

  const dismissFinding = useCallback(
    (id: string) => dispatch({ type: "dismiss", id }),
    [],
  );

  const restoreFinding = useCallback(
    (id: string) => dispatch({ type: "restore", id }),
    [],
  );

  const reset = useCallback(() => {
    if (busy) return;
    dispatch({ type: "reset" });
  }, [busy]);

  return {
    state,
    busy,
    undoBlocked,
    hasSnapshot,
    markUserEdited,
    startReview,
    cancel,
    applyFix,
    applyAllFixes,
    undoAllFixes,
    dismissFinding,
    restoreFinding,
    reset,
  };
}

// ── 组件 ─────────────────────────────────────────────────────────────

// EAI-CUSTOM (全文操作 M2): pill 色档沿用 DocAITaskArea PILL_TONE 习语（模块私有，此处
// 按审查分组语义复刻三档：error=destructive、warn=amber-500、info=muted），不新增色系。
const PILL_TONE = {
  ok: "border-success/30 bg-success/10 text-success",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  err: "border-destructive/30 bg-destructive/10 text-destructive",
  gray: "border-border bg-muted/40 text-muted-foreground",
} as const;

const SEVERITY_GROUPS = [
  {
    severity: "error",
    label: "错误",
    head: "text-destructive",
    pill: PILL_TONE.err,
    accent: "border-l-destructive",
  },
  {
    severity: "warn",
    label: "警告",
    head: "text-amber-600 dark:text-amber-400",
    pill: PILL_TONE.warn,
    accent: "border-l-amber-500",
  },
  {
    severity: "info",
    label: "提示",
    head: "text-muted-foreground",
    pill: PILL_TONE.gray,
    accent: "border-l-muted-foreground",
  },
] as const;

/** 单条审查发现卡：excerpt（等宽、可截断）+ problem + suggestion + 定位/修复/忽略。 */
function FindingsCard({
  entry,
  onLocate,
  onApplyFix,
  onDismiss,
}: {
  entry: ReviewFindingEntry;
  onLocate: (anchor: string) => boolean;
  onApplyFix: (finding: DocAIFinding) => void;
  onDismiss: (id: string) => void;
}) {
  const { finding, fixed } = entry;
  // scrollToAnchor 返 false（或编辑器未就绪由回调返 false）→ 按钮转禁用态。
  const [locateFailed, setLocateFailed] = useState(false);
  return (
    <div
      className={cn(
        "border-border/60 bg-background rounded-lg border border-l-2 p-2",
        SEVERITY_GROUPS.find((g) => g.severity === finding.severity)!.accent,
      )}
    >
      {fixed ? (
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex h-5 shrink-0 items-center rounded-full border px-2 text-[11px] font-medium whitespace-nowrap",
              PILL_TONE.ok,
            )}
          >
            已修复
          </span>
          <span className="text-muted-foreground truncate text-[11px]">
            {finding.anchor}
          </span>
        </div>
      ) : (
        <>
          <div
            title={finding.excerpt}
            className="bg-muted/40 text-muted-foreground line-clamp-2 rounded px-2 py-1 font-mono text-[11px] break-all"
          >
            「{finding.excerpt}」
          </div>
          <div className="text-foreground mt-1.5 text-xs leading-relaxed">
            {finding.problem}
          </div>
          <div className="text-muted-foreground mt-1 text-xs leading-relaxed">
            建议：{finding.suggestion}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5">
            <button
              type="button"
              disabled={locateFailed}
              onClick={() => {
                if (!onLocate(finding.anchor)) setLocateFailed(true);
              }}
              title={locateFailed ? "定位失败：未匹配到锚点" : "滚动到相关章节"}
              className="border-border/60 text-primary hover:bg-primary/5 rounded border px-2 py-0.5 text-[11px] disabled:cursor-not-allowed disabled:opacity-40"
            >
              定位
            </button>
            {finding.fix_op && (
              <button
                type="button"
                onClick={() => onApplyFix(finding)}
                className="border-primary/40 text-primary hover:bg-primary/10 rounded border px-2 py-0.5 text-[11px] font-medium"
              >
                修复
              </button>
            )}
            <button
              type="button"
              onClick={() => onDismiss(finding.id)}
              className="text-muted-foreground hover:bg-muted hover:text-foreground ml-auto rounded px-2 py-0.5 text-[11px]"
            >
              忽略
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// EAI-CUSTOM (全文操作 M2): 审查版工单头——与 DocAITaskArea TicketHeader 同构
//（任务名+状态 pill+进度条+计划行），计划行用审查语义文案（已审 n 节/正在审/待查看
// findings n 条）。progress 分母口径同 TicketHeader：优先 done/section_start 携带的
// 后端 total，流式中退化为已见节数。
function ReviewTicketHeader({
  state,
  busy,
  onCancel,
  onReset,
}: {
  state: DocAIReviewState;
  busy: boolean;
  onCancel: () => void;
  onReset: () => void;
}) {
  const audited = state.audited.length;
  const total =
    state.total && state.total > 0 ? state.total : state.audited.length;
  const pct =
    total > 0 ? Math.min(100, Math.round((audited / total) * 100)) : 0;
  const visibleCount = state.entries.filter(
    (e) => !state.dismissedIds.includes(e.finding.id),
  ).length;
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="text-foreground text-xs font-semibold">
          {reviewTypeLabel(state.reviewType)}
        </span>
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
              aria-label="停止审查"
              title="停止审查"
              className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive rounded p-1 transition-colors"
            >
              <Square className="h-3 w-3" fill="currentColor" />
            </button>
          )}
          {!busy && (
            <button
              type="button"
              onClick={onReset}
              aria-label="关闭审查区"
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
        {audited > 0 && (
          <div className="text-success flex items-center gap-1.5">
            <span aria-hidden>✓</span>已审 {audited} 节
          </div>
        )}
        {busy && state.current && (
          <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
            <span
              aria-hidden
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-current"
            />
            正在审 §{state.current.index + 1} {state.current.title}
          </div>
        )}
        {visibleCount > 0 && (
          <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
            <span aria-hidden>○</span>待查看 findings {visibleCount} 条
          </div>
        )}
        {state.failed.length > 0 && (
          <div className="text-destructive flex items-center gap-1.5">
            <span aria-hidden>!</span>
            {state.failed.length} 节审查失败
          </div>
        )}
      </div>
    </div>
  );
}

export function DocAIReviewArea({
  state,
  busy,
  undoBlocked,
  hasSnapshot,
  onLocate,
  onApplyFix,
  onApplyAllFixes,
  onUndoAllFixes,
  onDismissFinding,
  onRestoreFinding,
  onCancel,
  onReset,
}: {
  state: DocAIReviewState;
  busy: boolean;
  undoBlocked: boolean;
  /** 整批修复已执行（快照在手）→ 显示「撤销整批」。 */
  hasSnapshot: boolean;
  /** 定位：编辑器 scrollToAnchor（false = 未匹配 → 按钮转禁用态）。 */
  onLocate: (anchor: string) => boolean;
  onApplyFix: (finding: DocAIFinding) => void;
  onApplyAllFixes: () => void;
  onUndoAllFixes: () => void;
  onDismissFinding: (id: string) => void;
  onRestoreFinding: (id: string) => void;
  onCancel: () => void;
  onReset: () => void;
}) {
  const visibleEntries = state.entries.filter(
    (e) => !state.dismissedIds.includes(e.finding.id),
  );
  // n = 带 fix_op、未修复、未忽略的条数（全部修复的实际作用域）。
  const fixableCount = state.entries.filter(
    (e) =>
      e.finding.fix_op &&
      !e.fixed &&
      !state.dismissedIds.includes(e.finding.id),
  ).length;
  return (
    <div className="shrink-0 px-3 pb-2">
      <div className="border-border/60 bg-muted/20 space-y-2 rounded-lg border p-2.5">
        <ReviewTicketHeader
          state={state}
          busy={busy}
          onCancel={onCancel}
          onReset={onReset}
        />
        {state.message && (
          <div className="bg-muted/30 text-muted-foreground rounded px-2 py-1.5 text-xs">
            {state.message}
          </div>
        )}
        {undoBlocked && (
          <div className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-400">
            整批修复后文档已被修改，整批撤销已禁用；请用「版本历史」恢复。
          </div>
        )}
        {visibleEntries.length > 0 && (
          <div className="max-h-72 space-y-2 overflow-y-auto">
            {SEVERITY_GROUPS.map((g) => {
              const items = visibleEntries.filter(
                (e) => e.finding.severity === g.severity,
              );
              if (items.length === 0) return null;
              return (
                <div
                  key={g.severity}
                  data-severity={g.severity}
                  className="space-y-1.5"
                >
                  <div className="flex items-center gap-1.5">
                    <span className={cn("text-[11px] font-semibold", g.head)}>
                      {g.label}
                    </span>
                    <span
                      className={cn(
                        "inline-flex h-4.5 shrink-0 items-center rounded-full border px-1.5 text-[10px] font-medium",
                        g.pill,
                      )}
                    >
                      {items.length}
                    </span>
                  </div>
                  {items.map((e) => (
                    <FindingsCard
                      key={e.finding.id}
                      entry={e}
                      onLocate={onLocate}
                      onApplyFix={onApplyFix}
                      onDismiss={onDismissFinding}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        )}
        {state.dismissedIds.length > 0 && (
          <div className="text-muted-foreground flex items-center gap-1.5 text-[11px]">
            <span>已忽略 {state.dismissedIds.length} 条</span>
            <button
              type="button"
              onClick={() => state.dismissedIds.forEach(onRestoreFinding)}
              className="text-primary hover:underline"
            >
              恢复忽略（{state.dismissedIds.length}）
            </button>
          </div>
        )}
        {!busy && (fixableCount > 0 || hasSnapshot) && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onApplyAllFixes}
                disabled={fixableCount === 0}
                className="bg-primary text-primary-foreground hover:bg-primary/90 flex-1 rounded-md py-1.5 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-40"
              >
                全部修复（{fixableCount}）
              </button>
              {hasSnapshot && (
                <button
                  type="button"
                  onClick={onUndoAllFixes}
                  disabled={undoBlocked}
                  className="border-border/60 text-muted-foreground hover:bg-muted hover:text-foreground rounded-md border px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
                >
                  撤销整批
                </button>
              )}
            </div>
            <div className="text-muted-foreground flex items-center gap-1 text-[11px]">
              <Undo2 aria-hidden className="h-3 w-3 shrink-0" />
              每次批量修复前自动快照当前文档，可一键整批撤销。
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
