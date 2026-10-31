"use client";

/**
 * 人工复核工作台(二期 spec §五,原型 s6;EAI-CUSTOM 2026-10-31)。
 * need_human 队列逐条处置:左栏原文对照(DocLocateBody 内嵌,取当前项首条
 * 证据 {doc_id,page,text} → 定位窗口),右栏问题卡 + 处置表单
 * (确认问题 confirm / 误报 false_positive 必填四因 / 严重度调整 severity_change)。
 * 键盘快捷键:J/K 切换、Y 确认提交、N 选中误报(误报必填原因——快捷键只选中
 * 不代提交;输入框聚焦时全部禁用)。提交走既有 useBidFeedback(confirm 清
 * need_human 旗标、误报落库回流),本地 handled 集合立即推进队列,不依赖
 * 重取时序。零后端增量——反馈写路径一期已闭环。
 * 权限:挂 bid:page:workbench(同治理域,先例=metrics 挂 bid:page:rules)。
 */

import { ArrowLeft, ArrowRight, UserCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  type FeedbackAction,
  type LocateTarget,
} from "@/extensions/bid-review/api";
import { DocLocateBody } from "@/extensions/bid-review/components/DocLocateModal";
import { TaskTitleTag } from "@/extensions/bid-review/components/TaskTitleTag";
import {
  FP_REASONS,
  renderIssueMessage,
  sevPillBrx,
} from "@/extensions/bid-review/components/WorkbenchView";
import { useBidFeedback, useBidIssues } from "@/extensions/bid-review/hooks";
import { type IssueOut } from "@/extensions/bid-review/types";
import { cn } from "@/lib/utils";

/** 证据项 → 定位目标(首条;evidence 形如 {doc_id,page,section_path,text})。 */
function evidenceTarget(issue: IssueOut): LocateTarget | null {
  for (const ev of issue.evidence) {
    if (!ev || typeof ev !== "object") continue;
    const e = ev as Record<string, unknown>;
    if (typeof e.doc_id === "string" && e.doc_id) {
      const quote =
        typeof e.text === "string"
          ? e.text
          : typeof e.quote === "string"
            ? e.quote
            : "";
      return {
        docId: e.doc_id,
        page: typeof e.page === "number" ? e.page : null,
        quote,
      };
    }
  }
  return null;
}

export function ReviewQueueView({ taskId }: { taskId?: string | null }) {
  const issuesQuery = useBidIssues(taskId ?? null);
  const feedback = useBidFeedback();

  // 队列 = need_human 未处置项;提交成功即入 handled(本地即时推进,重取后
  // confirm 项的旗标翻转与 handled 语义一致,不重复计数)
  const [handled, setHandled] = useState<Set<string>>(() => new Set());
  const queue = useMemo(
    () =>
      (issuesQuery.data ?? []).filter(
        (i) => i.need_human && !handled.has(i.id),
      ),
    [issuesQuery.data, handled],
  );
  const [idx, setIdx] = useState(0);
  const safeIdx = queue.length === 0 ? 0 : Math.min(idx, queue.length - 1);
  const current = queue[safeIdx] ?? null;

  // 处置表单:确认问题 / 误报(四因必选,默认首因)/ 严重度调整(默认主要)
  const [action, setAction] = useState<FeedbackAction>("confirm");
  const [fpReason, setFpReason] = useState<string>(FP_REASONS[0] ?? "规则误判");
  const [newSeverity, setNewSeverity] = useState("major");
  const [note, setNote] = useState("");

  useEffect(() => {
    setAction("confirm");
    setNote("");
  }, [current?.id]);

  const submit = (a: FeedbackAction) => {
    if (!taskId || !current || feedback.isPending) return;
    // 误报原因后端无独立字段→折进 note(与 WorkbenchView 同口径)
    const noteFinal =
      a === "false_positive"
        ? `误报原因:${fpReason}${note ? `;${note}` : ""}`
        : note;
    feedback.mutate(
      {
        issueId: current.id,
        taskId,
        action: a,
        note: noteFinal,
        ...(a === "severity_change" ? { new_severity: newSeverity } : {}),
      },
      {
        onSuccess: () => {
          toast.success(
            a === "confirm"
              ? "已确认问题"
              : a === "false_positive"
                ? "已标误报(回流评测集)"
                : "已调整严重度",
          );
          setHandled((s) => new Set(s).add(current.id));
        },
        onError: (e) =>
          toast.error(e instanceof Error ? e.message : "提交失败"),
      },
    );
  };

  // 快捷键:输入类元素聚焦时禁用;N 只选中误报(必填原因,不代提交)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      if (
        t instanceof HTMLElement &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable)
      )
        return;
      if (queue.length === 0) return;
      if (e.key === "j" || e.key === "J")
        setIdx((v) => Math.min(v + 1, queue.length - 1));
      else if (e.key === "k" || e.key === "K")
        setIdx((v) => Math.max(v - 1, 0));
      else if ((e.key === "y" || e.key === "Y") && current) submit("confirm");
      else if (e.key === "n" || e.key === "N") setAction("false_positive");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!taskId) {
    return (
      <div className="screen on">
        <div className="page-head">
          <div className="ph-icon">
            <UserCheck className="ic" />
          </div>
          <div>
            <h2>人工复核工作台</h2>
            <div className="ph-sub">
              need_human 逐条处置——确认 / 误报回流 / 严重度调整
            </div>
          </div>
        </div>
        <div className="note-bar warnbar">
          <span>未指定任务——请从任务列表或审查工作台进入。</span>
        </div>
        <Link
          href="/bid-review"
          className="btn btn-sec"
          style={{ marginTop: 12 }}
        >
          返回任务列表
        </Link>
      </div>
    );
  }

  const target = current ? evidenceTarget(current) : null;
  const sev = current ? sevPillBrx(current.severity) : null;

  return (
    <div className="screen on">
      <div className="page-head">
        <div className="ph-icon">
          <UserCheck className="ic" />
        </div>
        <div>
          <h2>
            人工复核工作台
            <TaskTitleTag taskId={taskId} />
          </h2>
          <div className="ph-sub">
            待人工队列逐条处置——未判定 ≠ 通过 · 误报自动回流评测集
          </div>
        </div>
        <div className="ph-actions">
          <Link
            href={`/bid-review/workbench?task_id=${taskId}`}
            className="btn btn-sec btn-sm"
          >
            返回工作台
          </Link>
        </div>
      </div>

      {issuesQuery.isError ? (
        <div className="note-bar errbar">
          <span style={{ flex: 1 }}>
            问题列表加载失败:{issuesQuery.error.message}
          </span>
          <button
            type="button"
            className="btn btn-sec btn-sm"
            onClick={() => void issuesQuery.refetch()}
          >
            重试
          </button>
        </div>
      ) : null}

      {issuesQuery.isPending ? (
        <div className="note-bar">
          <span>问题列表加载中…</span>
        </div>
      ) : queue.length === 0 ? (
        <div className="note-bar">
          <span>
            待人工队列为空——引擎无法判定项已全部处置,或本任务暂无 need_human
            问题。
          </span>
        </div>
      ) : (
        <div className="split">
          {/* 左:原文对照(当前项首条证据 → DocLocateBody,与弹层同源) */}
          <div
            className="card"
            style={{
              display: "flex",
              flexDirection: "column",
              minHeight: 320,
              overflow: "hidden",
            }}
          >
            <div className="card-hd">
              <h3>原文对照</h3>
              <span className="hd-sub">
                {target
                  ? `${target.docId}${target.page != null ? ` · p.${target.page}` : " · 片段窗口"}`
                  : "无证据"}
              </span>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
              {target ? (
                <DocLocateBody taskId={taskId} target={target} />
              ) : (
                <span style={{ color: "var(--text-3)", fontSize: 13 }}>
                  该问题无原文证据(如缺字段类 need_human)——可到基准确认页核对
                  字段抽取结果。
                </span>
              )}
            </div>
          </div>

          {/* 右:队列 + 处置表单 */}
          <div className="card">
            <div className="card-hd">
              <h3>待复核队列</h3>
              <span className="hd-sub">
                当前 <b className="num">{safeIdx + 1}</b> /{" "}
                <span className="num">{queue.length}</span> · 未处置{" "}
                <span className="num">{queue.length}</span>
              </span>
            </div>
            <div className="toolbar">
              <button
                type="button"
                className="btn btn-sec btn-sm"
                disabled={safeIdx === 0}
                onClick={() => setIdx((v) => Math.max(v - 1, 0))}
              >
                <ArrowLeft size={14} /> 上一项 (K)
              </button>
              <button
                type="button"
                className="btn btn-sec btn-sm"
                disabled={safeIdx >= queue.length - 1}
                onClick={() => setIdx((v) => Math.min(v + 1, queue.length - 1))}
              >
                下一项 (J) <ArrowRight size={14} />
              </button>
              <span
                style={{
                  marginLeft: "auto",
                  fontSize: 12,
                  color: "var(--text-3)",
                }}
              >
                Y 确认 · N 选中误报
              </span>
            </div>

            {current ? (
              <div
                style={{
                  padding: "12px 16px 16px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div>
                  <span className="mono" style={{ fontSize: 12 }}>
                    {current.rule_id}
                  </span>
                  {sev ? (
                    <span
                      className={cn("pill", sev.cls)}
                      style={{ marginLeft: 8 }}
                    >
                      {sev.label}
                    </span>
                  ) : null}
                  <span className="pill pill-gray" style={{ marginLeft: 4 }}>
                    {current.layer}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 13 }} title={current.message}>
                  {renderIssueMessage(current.message)}
                </p>
                {current.fix ? (
                  <p
                    style={{
                      margin: 0,
                      fontSize: 13,
                      color: "var(--text-3)",
                    }}
                  >
                    建议:{current.fix}
                  </p>
                ) : null}

                <div
                  role="radiogroup"
                  aria-label="处置判定"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    fontSize: 13,
                  }}
                >
                  <label
                    style={{ display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <input
                      type="radio"
                      name="review-action"
                      checked={action === "confirm"}
                      onChange={() => setAction("confirm")}
                    />
                    确认问题(计入违规)
                  </label>
                  <label
                    style={{ display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <input
                      type="radio"
                      name="review-action"
                      checked={action === "false_positive"}
                      onChange={() => setAction("false_positive")}
                    />
                    误报(回流评测集)——原因必选:
                    <select
                      value={fpReason}
                      onChange={(e) => setFpReason(e.target.value)}
                      aria-label="误报原因"
                    >
                      {FP_REASONS.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label
                    style={{ display: "flex", alignItems: "center", gap: 6 }}
                  >
                    <input
                      type="radio"
                      name="review-action"
                      checked={action === "severity_change"}
                      onChange={() => setAction("severity_change")}
                    />
                    严重度调整为:
                    <select
                      value={newSeverity}
                      onChange={(e) => setNewSeverity(e.target.value)}
                      aria-label="调整后严重度"
                    >
                      <option value="fatal">致命</option>
                      <option value="major">主要</option>
                      <option value="minor">次要</option>
                      <option value="info">提示</option>
                    </select>
                  </label>
                </div>

                <textarea
                  className="inp"
                  rows={2}
                  placeholder="备注(可选)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  aria-label="备注"
                />

                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-pri"
                    disabled={feedback.isPending}
                    onClick={() => submit(action)}
                  >
                    {feedback.isPending
                      ? "提交中…"
                      : action === "confirm"
                        ? "提交并下一条"
                        : action === "false_positive"
                          ? "标误报并下一条"
                          : "调整严重度并下一条"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
