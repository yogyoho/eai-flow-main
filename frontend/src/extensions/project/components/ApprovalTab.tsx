"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Loader2, RotateCcw, Send, XCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import {
  MEMBER_ROLE_LABELS,
  type MemberRole,
  type ReportProject,
} from "@/extensions/project/types";
import { useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

// ── Types ──

interface ApprovalTabProps {
  can: (action: string) => boolean;
  role: string | null;
  projectId: string;
  project: ReportProject | null;
  onRefresh: () => void;
}

interface StepConfig {
  stepOrder: number;
  stepName: string;
  reviewerId: string;
}

// ── Approval Step Indicator ──

function StepIndicator({
  steps,
  currentStep,
}: {
  steps: { stepOrder: number; stepName: string; status: string; reviewerId: string | null }[];
  currentStep: number | null;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto px-5 py-4">
      {steps.map((step, idx) => {
        const isActive = step.stepOrder === currentStep;
        const isDone = step.status === "approved" || (currentStep !== null && step.stepOrder < currentStep);

        return (
          <div key={step.stepOrder} className="flex items-center">
            <div className="flex flex-col items-center gap-1 min-w-[72px]">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold",
                  isDone
                    ? "bg-[#22C55E] text-white"
                    : isActive
                      ? "bg-[#3B82F6] text-white ring-4 ring-[#3B82F6]/20"
                      : "bg-[#F1F5F9] text-[#94A3B8]",
                )}
              >
                {isDone ? <CheckCircle className="h-4 w-4" /> : step.stepOrder}
              </div>
              <span className="text-[11px] text-foreground font-medium text-center leading-tight">
                {step.stepName}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={cn(
                  "h-0.5 w-8 mx-1",
                  isDone ? "bg-[#22C55E]" : "bg-[#E2E8F0]",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Manager view: Submit approval (stage <= 4) ──

function SubmitApprovalView({
  project,
  members,
  onSubmitted,
}: {
  project: ReportProject;
  members: { userId: string; username: string; role: MemberRole }[];
  onSubmitted: () => void;
}) {
  const [showDialog, setShowDialog] = useState(false);
  const [steps, setSteps] = useState<StepConfig[]>([
    { stepOrder: 1, stepName: "初审", reviewerId: "" },
  ]);
  const [submitting, setSubmitting] = useState(false);

  const addStep = () => {
    setSteps((prev) => [
      ...prev,
      {
        stepOrder: prev.length + 1,
        stepName: `步骤 ${prev.length + 1}`,
        reviewerId: "",
      },
    ]);
  };

  const removeStep = (index: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, stepOrder: i + 1 })));
  };

  const updateStep = (index: number, field: "stepName" | "reviewerId", value: string) => {
    setSteps((prev) =>
      prev.map((s, i) => (i === index ? { ...s, [field]: value } : s)),
    );
  };

  const handleSubmit = async () => {
    if (steps.some((s) => !s.reviewerId)) {
      toast.error("请为每个步骤选择审核人");
      return;
    }
    setSubmitting(true);
    try {
      await projectApi.submitApproval(
        project.id,
        steps.map((s) => ({ stepOrder: s.stepOrder, stepName: s.stepName, reviewerId: s.reviewerId })),
      );
      toast.success("审核流程已提交");
      setShowDialog(false);
      onSubmitted();
    } catch {
      toast.error("提交审核失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-5">
      <div className="flex flex-col items-center gap-4 py-12">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#EFF6FF]">
          <Send className="h-6 w-6 text-[#3B82F6]" />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-foreground">审核流程未启动</p>
          <p className="mt-1 text-xs text-muted-foreground">
            当前项目处于协作编辑阶段，可以提交审核
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowDialog(true)}
          className="flex items-center gap-1.5 rounded-lg bg-[#3B82F6] px-4 py-2 text-sm font-medium text-white hover:bg-[#2563EB] transition-colors"
        >
          <Send className="h-4 w-4" />
          提交审核
        </button>
      </div>

      {/* Submit dialog */}
      {showDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background rounded-xl border border-border shadow-lg w-full max-w-md p-6">
            <h3 className="text-base font-semibold text-foreground mb-4">配置审核流程</h3>

            <div className="flex flex-col gap-3 max-h-[60vh] overflow-y-auto">
              {steps.map((step, idx) => (
                <div key={idx} className="flex items-center gap-2 rounded-lg border border-border p-3">
                  <span className="text-xs text-muted-foreground shrink-0 w-6">{step.stepOrder}.</span>
                  <input
                    type="text"
                    value={step.stepName}
                    onChange={(e) => updateStep(idx, "stepName", e.target.value)}
                    placeholder="步骤名称"
                    className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm outline-none focus:border-[#3B82F6]"
                  />
                  <select
                    value={step.reviewerId}
                    onChange={(e) => updateStep(idx, "reviewerId", e.target.value)}
                    className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm outline-none focus:border-[#3B82F6]"
                  >
                    <option value="">选择审核人</option>
                    {members.map((m) => (
                      <option key={m.userId} value={m.userId}>
                        {m.username} ({MEMBER_ROLE_LABELS[m.role]})
                      </option>
                    ))}
                  </select>
                  {steps.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeStep(idx)}
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                    >
                      <XCircle className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={addStep}
              className="mt-3 w-full rounded-lg border border-dashed border-[#E2E8F0] py-2 text-sm text-muted-foreground hover:text-foreground hover:border-[#CBD5E1] transition-colors"
            >
              + 添加步骤
            </button>

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowDialog(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-accent transition-colors"
                disabled={submitting}
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="flex items-center gap-1.5 rounded-lg bg-[#3B82F6] px-4 py-2 text-sm font-medium text-white hover:bg-[#2563EB] transition-colors disabled:opacity-50"
              >
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                确认提交
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Reviewer action section ──

function ReviewerActionSection({
  projectId,
  workflowId,
  stepName,
  onRefresh,
}: {
  projectId: string;
  workflowId: string;
  stepName: string;
  onRefresh: () => void;
}) {
  const [comment, setComment] = useState("");
  const [acting, setActing] = useState(false);

  const handleAction = useCallback(
    async (action: "approve" | "reject") => {
      setActing(true);
      try {
        await projectApi.doApprovalAction(projectId, workflowId, action, comment || undefined);
        toast.success(action === "approve" ? "已通过" : "已退回");
        onRefresh();
      } catch {
        toast.error(action === "approve" ? "通过失败" : "退回失败");
      } finally {
        setActing(false);
      }
    },
    [projectId, workflowId, comment, onRefresh],
  );

  return (
    <div className="mx-5 mt-4 rounded-lg border border-[#E2E8F0] bg-[#FAFBFC] p-4">
      <p className="text-sm font-medium text-foreground mb-3">
        当前步骤：{stepName}
      </p>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="审核意见（可选）"
        rows={3}
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-[#3B82F6] resize-none"
      />
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={() => handleAction("reject")}
          disabled={acting}
          className="flex items-center gap-1.5 rounded-lg border border-[#EF4444] px-4 py-2 text-sm text-[#EF4444] hover:bg-[#FEF2F2] transition-colors disabled:opacity-50"
        >
          {acting ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
          退回
        </button>
        <button
          type="button"
          onClick={() => handleAction("approve")}
          disabled={acting}
          className="flex items-center gap-1.5 rounded-lg bg-[#22C55E] px-4 py-2 text-sm text-white hover:bg-[#16A34A] transition-colors disabled:opacity-50"
        >
          {acting ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
          通过
        </button>
      </div>
    </div>
  );
}

// ── Main Component ──

export function ApprovalTab({
  can,
  role,
  projectId,
  project,
  onRefresh,
}: ApprovalTabProps) {
  const isManager = role === "manager";
  const canSubmitApproval = can("approval:submit");
  const canReview = can("approval:review");
  const { user: currentUser } = useAuth();

  // Fetch approval status when project is in stage 5
  const { data: approvalStatus, isLoading: approvalLoading } = useQuery({
    queryKey: ["approval-status", projectId],
    queryFn: () => projectApi.getApprovalStatus(projectId),
    enabled: project?.currentStage === 5 && !!projectId,
  });

  if (!project) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        加载中...
      </div>
    );
  }

  // ── Manager view: stage <= 4, can submit ──
  if (project.currentStage <= 4) {
    if (isManager && canSubmitApproval) {
      return (
        <SubmitApprovalView
          project={project}
          members={project.members ?? []}
          onSubmitted={onRefresh}
        />
      );
    }
    // Non-manager or no permission — read-only placeholder
    return (
      <div className="p-5 text-center text-sm text-muted-foreground py-12">
        审核流程尚未启动
      </div>
    );
  }

  // ── Stage 5+: Approval in progress ──
  if (approvalLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const steps = approvalStatus?.steps ?? [];
  const currentStep = approvalStatus?.currentStep ?? null;
  const currentWorkflow = steps.find((s) => s.stepOrder === currentStep);

  // Determine if current user is the reviewer for the current step
  const isCurrentReviewer =
    canReview &&
    currentWorkflow?.reviewerId != null &&
    currentWorkflow.reviewerId === currentUser?.id &&
    currentWorkflow?.status !== "approved";

  return (
    <div className="flex flex-col h-full">
      {/* Step indicator */}
      {steps.length > 0 && (
        <div className="border-b border-[#E2E8F0]">
          <StepIndicator steps={steps} currentStep={currentStep} />
        </div>
      )}

      {/* Manager: withdraw button */}
      {isManager && project.currentStage === 5 && (
        <div className="px-5 py-3 border-b border-[#E2E8F0]">
          <button
            type="button"
            onClick={async () => {
              try {
                await projectApi.update(projectId, { currentStage: 4 });
                toast.success("已撤回审核，回到协作编辑阶段");
                onRefresh();
              } catch {
                toast.error("撤回审核失败");
              }
            }}
            className="flex items-center gap-1.5 rounded-lg border border-[#D97706] px-3 py-1.5 text-sm text-[#D97706] hover:bg-[#FFFBEB] transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
            撤回审核
          </button>
        </div>
      )}

      {/* Approval history */}
      <div className="flex-1 overflow-y-auto p-5">
        {steps.length === 0 && (
          <div className="text-center text-sm text-muted-foreground py-8">
            暂无审核流程数据
          </div>
        )}

        <div className="flex flex-col gap-4">
          {steps.map((step) => (
            <div
              key={step.id}
              className={cn(
                "rounded-lg border p-4",
                step.stepOrder === currentStep
                  ? "border-[#3B82F6] bg-[#EFF6FF]/30"
                  : "border-border bg-background",
              )}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    步骤 {step.stepOrder}: {step.stepName}
                  </span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-medium",
                      step.status === "approved"
                        ? "bg-[#ECFDF5] text-[#22C55E]"
                        : step.status === "rejected"
                          ? "bg-[#FEF2F2] text-[#EF4444]"
                          : "bg-[#FFFBEB] text-[#D97706]",
                    )}
                  >
                    {step.status === "approved"
                      ? "已通过"
                      : step.status === "rejected"
                        ? "已退回"
                        : "待审核"}
                  </span>
                </div>
              </div>

              {/* Records */}
              {step.records.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  {step.records.map((record) => (
                    <div
                      key={record.id}
                      className="rounded-md bg-[#F9FAFB] px-3 py-2 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground">
                          {record.reviewerName}
                        </span>
                        <span
                          className={cn(
                            "font-medium",
                            record.action === "approve" ? "text-[#22C55E]" : "text-[#EF4444]",
                          )}
                        >
                          {record.action === "approve" ? "通过" : "退回"}
                        </span>
                        {record.createdAt && (
                          <span className="text-muted-foreground">
                            {new Date(record.createdAt).toLocaleString()}
                          </span>
                        )}
                      </div>
                      {record.comment && (
                        <p className="mt-1 text-muted-foreground">{record.comment}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Reviewer action section (only for current step reviewer) */}
      {isCurrentReviewer && currentWorkflow && (
        <ReviewerActionSection
          projectId={projectId}
          workflowId={currentWorkflow.id}
          stepName={currentWorkflow.stepName}
          onRefresh={onRefresh}
        />
      )}
    </div>
  );
}
