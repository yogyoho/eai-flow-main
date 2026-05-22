"use client";

import { Loader2, Send, Clock } from "lucide-react";
import { useState, useEffect, useMemo } from "react";

import { cn } from "@/lib/utils";

import { approvalApi } from "./api";
import { ApprovalAction } from "./components/ApprovalAction";
import { ApprovalTimeline } from "./components/ApprovalTimeline";
import type { ApprovalStep, ApprovalRecord } from "./types";

interface ApprovalPanelProps {
  projectId: string;
  reportType: string;
  currentUserId?: string;
  projectStatus?: string;
}

export function ApprovalPanel({
  projectId,
  reportType,
  currentUserId,
  projectStatus,
}: ApprovalPanelProps) {
  const authenticated = Boolean(currentUserId);
  const [steps, setSteps] = useState<ApprovalStep[]>([]);
  const [records, setRecords] = useState<ApprovalRecord[]>([]);
  const [currentStepId, setCurrentStepId] = useState<string>();
  const [currentReviewerId, setCurrentReviewerId] = useState<string>();
  const [currentReviewerName, setCurrentReviewerName] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    loadData();
  }, [projectId, reportType]);

  const loadData = async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [workflow, recordList] = await Promise.all([
        approvalApi.getWorkflow(reportType),
        approvalApi.getRecords(projectId),
      ]);

      if (workflow) {
        setSteps(workflow.steps);
      }

      setRecords(recordList);

      // Determine current step: find the first step without an approve record
      if (workflow) {
        const sortedSteps = [...workflow.steps].sort((a, b) => a.order - b.order);
        for (const step of sortedSteps) {
          const hasApproval = recordList.some(
            (r) => r.stepId === step.id && r.action === "approve"
          );
          if (!hasApproval) {
            setCurrentStepId(step.id);
            setCurrentReviewerId(step.requiredRole);
            setCurrentReviewerName(step.requiredRole);
            break;
          }
        }
      }
    } catch (err) {
      setError("加载审批数据失败");
    } finally {
      setLoading(false);
    }
  };

  const isCurrentReviewer = useMemo(() => {
    if (!authenticated || !currentReviewerId) return false;
    return currentUserId === currentReviewerId;
  }, [authenticated, currentUserId, currentReviewerId]);

  const handleSubmitForApproval = async () => {
    setSubmitting(true);
    setError(undefined);
    try {
      await approvalApi.submitForApproval({ projectId });
      await loadData();
    } catch {
      setError("提交审批失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAction = async (action: "approve" | "reject" | "comment", comment: string) => {
    if (!currentStepId) return;
    setActionLoading(true);
    setError(undefined);
    try {
      await approvalApi.act({
        projectId,
        stepId: currentStepId,
        action,
        comment,
      });
      await loadData();
    } catch {
      setError("操作失败");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && steps.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (steps.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        暂无可用的审批流程
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      {/* Left panel - Timeline (2/3 width on desktop) */}
      <div className="min-w-0 flex-[2]">
        <h3 className="mb-4 text-sm font-semibold">审批流程</h3>
        <ApprovalTimeline
          steps={steps}
          records={records}
          currentStepId={currentStepId}
        />
      </div>

      {/* Right panel - Action (1/3 width on desktop) */}
      <div className="shrink-0 space-y-4 lg:w-80">
        {/* Submit for approval button (if project is in writing status) */}
        {projectStatus === "writing" && (
          <button
            onClick={handleSubmitForApproval}
            disabled={submitting}
            className={cn(
              "flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium",
              "bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/80",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            提交审批
          </button>
        )}

        {/* Current step action panel */}
        {currentStepId && (
          <div className="rounded-xl border border-border bg-background p-6">
            {!authenticated ? (
              <div className="flex flex-col items-center gap-3 py-4 text-center">
                <Clock className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  请先登录后再进行审批操作
                </p>
              </div>
            ) : isCurrentReviewer ? (
              <>
                <h4 className="mb-4 text-sm font-semibold">审批操作</h4>
                <ApprovalAction
                  onAction={handleAction}
                  loading={actionLoading}
                />
              </>
            ) : (
              <div className="flex flex-col items-center gap-3 py-4 text-center">
                <Clock className="h-8 w-8 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">
                    当前等待 {currentReviewerName ?? "审批人"} 审批
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    请耐心等待审批完成
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Error display */}
        {error && steps.length > 0 && (
          <p className="text-center text-xs text-destructive">{error}</p>
        )}
      </div>
    </div>
  );
}
