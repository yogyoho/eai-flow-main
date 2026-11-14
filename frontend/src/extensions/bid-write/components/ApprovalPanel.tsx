"use client";

import {
  CheckCircle2,
  Clock3,
  LockKeyhole,
  Send,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/extensions/bid-write/api";
import { Badge } from "@/extensions/bid-write/components/primitives";
import type { AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";
import { AST_SCHEMA_VERSION } from "@/extensions/bid-write/editor/schema.gen";
import { formatDate } from "@/extensions/bid-write/helpers";
import {
  useSubmitTaskApproval,
  useTaskApproval,
  useTaskApprovalAction,
} from "@/extensions/bid-write/hooks";

const REVISION_LABELS: Record<string, string> = {
  submitted: "审批中",
  approved: "已批准",
  rejected: "已驳回",
  superseded: "已被替代",
};

const REVIEW_LABELS: Record<string, string> = {
  pending: "待审批",
  approved: "通过",
  rejected: "驳回",
  cancelled: "已取消",
};

interface ApprovalPanelProps {
  taskId: string | null;
  ast: AstJsonNode | null;
  cloudReady: boolean;
  onLockedChange?: (locked: boolean) => void;
  onNotice?: (message: string) => void;
}

export function ApprovalPanel({
  taskId,
  ast,
  cloudReady,
  onLockedChange,
  onNotice,
}: ApprovalPanelProps) {
  const query = useTaskApproval(taskId);
  const submit = useSubmitTaskApproval(taskId);
  const action = useTaskApprovalAction(taskId);
  const [reviewerIds, setReviewerIds] = useState("");
  const [gateMode, setGateMode] = useState("all");
  const [definitionId, setDefinitionId] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const data = query.data;
  const revision = data?.revision ?? null;
  const approval = data?.approval ?? null;
  const status = revision?.status ?? "";
  const locked = status === "approved";
  const pending = status === "submitted";
  const canSubmit = Boolean(
    taskId &&
      ast &&
      cloudReady &&
      data?.is_owner &&
      !pending &&
      !locked &&
      !busy,
  );

  useEffect(() => {
    onLockedChange?.(locked);
  }, [locked, onLockedChange]);

  const snapshot = useMemo(() => {
    const raw = revision?.assertion_snapshot as
      | { status?: string; summary?: { d0?: number; d1?: number; d2?: number } }
      | undefined;
    return raw ?? null;
  }, [revision?.assertion_snapshot]);

  const notify = (message: string) => onNotice?.(message);

  const handleSubmit = async () => {
    if (!taskId || !ast) return;
    const ids = reviewerIds
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (ids.length === 0 && !definitionId.trim()) {
      notify("内置审批流至少需要 1 名审批人；选择审批流定义时可省略。");
      return;
    }
    setBusy(true);
    try {
      await submit.mutateAsync({
        ast,
        schema_version: AST_SCHEMA_VERSION,
        workflow_definition_id: definitionId.trim() || undefined,
        reviewer_ids: ids.length > 0 ? ids : undefined,
        gate_mode: gateMode,
        comment: comment.trim() || undefined,
      });
      setComment("");
      notify(`已提交审批：修订冻结 ${ids.length} 名审批人。`);
    } catch (error) {
      notify(error instanceof ApiError ? error.message : "提交审批失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const handleAction = async (next: "approved" | "rejected") => {
    if (!approval) return;
    setBusy(true);
    try {
      await action.mutateAsync({
        instance_id: approval.instance_id,
        action: next,
        comment: comment.trim() || undefined,
      });
      setComment("");
      notify(next === "approved" ? "审批已通过。" : "审批已驳回。");
    } catch (error) {
      notify(error instanceof ApiError ? error.message : "审批动作失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  if (!taskId) return null;

  return (
    <div className="bw-approval">
      <div className="bw-approval-h">
        <b>审批</b>
        {revision ? (
          <Badge
            tone={
              status === "approved"
                ? "ok"
                : status === "rejected"
                  ? "bad"
                  : status === "submitted"
                    ? "warn"
                    : "gray"
            }
            dot={status === "submitted"}
          >
            {REVISION_LABELS[status] ?? status}
          </Badge>
        ) : (
          <Badge tone="gray">未提交</Badge>
        )}
        {revision ? (
          <span className="bw-approval-meta">
            修订 #{revision.revision_no} · hash{" "}
            <span className="mono">{revision.doc_hash.slice(0, 12)}</span>
            {revision.hash_ok ? null : " · 哈希不匹配"}
          </span>
        ) : null}
      </div>

      {query.error ? (
        <p className="bw-muted">审批状态读取失败：{query.error.message}</p>
      ) : null}

      {snapshot ? (
        <p className="bw-muted">
          提交时断言快照：
          {snapshot.status === "ok" ? (
            <>
              D0 {snapshot.summary?.d0 ?? 0} · D1 {snapshot.summary?.d1 ?? 0} ·
              D2 {snapshot.summary?.d2 ?? 0}
            </>
          ) : (
            "执行器不可用（已如实记录，未伪造通过）"
          )}
        </p>
      ) : null}

      {approval ? (
        <div className="bw-approval-flow">
          <div className="bw-inline-facts bw-facts-col">
            <span>
              审批流{" "}
              <b>
                {approval.workflow_source === "definition"
                  ? approval.definition_id
                  : "内置单节点"}
              </b>
            </span>
            <span>
              当前节点 <b>{approval.current_node_label || "已结束"}</b> ·
              模式 <b>{approval.gate_mode || "all"}</b>
            </span>
            <span>
              发起 {formatDate(approval.created_at)}
              {approval.decided_at
                ? ` · 完成 ${formatDate(approval.decided_at)}`
                : ""}
            </span>
          </div>
          <div className="bw-approval-reviews">
            {approval.reviews.map((review) => (
              <div className="bw-approval-review" key={review.id}>
                <span className="mono">{review.reviewer_id}</span>
                <span>{review.node_label || review.node_id}</span>
                <Badge
                  tone={
                    review.status === "approved"
                      ? "ok"
                      : review.status === "rejected"
                        ? "bad"
                        : review.status === "cancelled"
                          ? "gray"
                          : "warn"
                  }
                >
                  {REVIEW_LABELS[review.status] ?? review.status}
                </Badge>
                {review.comment ? (
                  <span className="bw-approval-comment">{review.comment}</span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {locked ? (
        <p className="bw-approval-lock">
          <LockKeyhole size={14} aria-hidden="true" />
          该修订已批准，正文锁定；修改需从新修订流程重开。
        </p>
      ) : null}

      {pending && approval ? (
        approval.can_act ? (
          <div className="bw-approval-action">
            <div className="bw-approval-h">
              <b>待你审批</b>
              <Clock3 size={13} aria-hidden="true" />
            </div>
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="审批意见（驳回建议填写原因）"
              rows={2}
            />
            <div className="bw-approval-btns">
              <button
                type="button"
                className="btn btn-sm pri"
                disabled={busy}
                onClick={() => void handleAction("approved")}
              >
                <CheckCircle2 size={13} aria-hidden="true" />
                批准
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={busy}
                onClick={() => void handleAction("rejected")}
              >
                <XCircle size={13} aria-hidden="true" />
                驳回
              </button>
            </div>
          </div>
        ) : (
          <p className="bw-muted">等待指定审批人处理；当前用户不可执行审批动作。</p>
        )
      ) : null}

      {!pending && !locked && data?.is_owner ? (
        <div className="bw-approval-submit">
          {!cloudReady ? (
            <p className="bw-muted">演示文档不能提交审批；请先保存云端正文。</p>
          ) : (
            <>
              <div className="bw-approval-form">
                <label>
                  审批人用户 ID
                  <input
                    value={reviewerIds}
                    onChange={(event) => setReviewerIds(event.target.value)}
                    placeholder="u-1001, u-1002"
                  />
                </label>
                <label>
                  签核模式
                  <select
                    value={gateMode}
                    onChange={(event) => setGateMode(event.target.value)}
                  >
                    <option value="all">会签（全部通过）</option>
                    <option value="any">或签（任一通过）</option>
                    <option value="ratio">比例签（默认 50%）</option>
                    <option value="sequential">顺序签</option>
                  </select>
                </label>
                <label>
                  审批流定义 ID（可选）
                  <input
                    value={definitionId}
                    onChange={(event) => setDefinitionId(event.target.value)}
                    placeholder="workflow_definitions.id；空=内置单节点"
                  />
                </label>
              </div>
              <div className="bw-approval-btns">
                <button
                  type="button"
                  className="btn btn-sm pri"
                  disabled={!canSubmit}
                  onClick={() => void handleSubmit()}
                >
                  <Send size={13} aria-hidden="true" />
                  {busy ? "提交中…" : status === "rejected" ? "重新提交审批" : "提交审批"}
                </button>
                {revision?.status === "rejected" ? (
                  <span className="bw-muted">驳回后可继续编辑，再提交生成新修订。</span>
                ) : null}
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
