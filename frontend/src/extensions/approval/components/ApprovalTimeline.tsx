"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { MessageSquare } from "lucide-react";
import { ApprovalStepCard } from "./ApprovalStepCard";
import type { ApprovalStep, ApprovalRecord } from "../types";

interface ApprovalTimelineProps {
  steps: ApprovalStep[];
  records: ApprovalRecord[];
  currentStepId?: string;
}

const formatDate = (dateStr: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateStr));

const actionLabels: Record<string, string> = {
  approve: "通过",
  reject: "退回",
  comment: "评论",
};

export function ApprovalTimeline({
  steps,
  records,
  currentStepId,
}: ApprovalTimelineProps) {
  const recordsByStep = useMemo(() => {
    const map = new Map<string, ApprovalRecord[]>();
    for (const record of records) {
      const existing = map.get(record.stepId) ?? [];
      existing.push(record);
      map.set(record.stepId, existing);
    }
    return map;
  }, [records]);

  const sortedSteps = useMemo(
    () => [...steps].sort((a, b) => a.order - b.order),
    [steps]
  );

  const getStepStatus = (
    step: ApprovalStep
  ): "pending" | "current" | "completed" | "rejected" => {
    if (step.id === currentStepId) return "current";
    const stepRecords = recordsByStep.get(step.id) ?? [];
    if (stepRecords.some((r) => r.action === "reject")) return "rejected";
    if (stepRecords.some((r) => r.action === "approve")) return "completed";
    return "pending";
  };

  const getLatestReviewer = (step: ApprovalStep): string | undefined => {
    const stepRecords = recordsByStep.get(step.id);
    if (!stepRecords || stepRecords.length === 0) return undefined;
    const latest = stepRecords[stepRecords.length - 1];
    return latest?.reviewerName;
  };

  return (
    <div className="space-y-0">
      {sortedSteps.map((step, index) => {
        const status = getStepStatus(step);
        const reviewerName = getLatestReviewer(step);
        const stepRecords = recordsByStep.get(step.id) ?? [];
        const isLast = index === sortedSteps.length - 1;

        return (
          <div key={step.id} className="relative flex gap-4">
            {/* Vertical line */}
            {!isLast && (
              <div
                className={cn(
                  "absolute left-[15px] top-10 h-[calc(100%-16px)] w-0.5",
                  status === "completed"
                    ? "bg-green-500/40"
                    : status === "rejected"
                      ? "bg-destructive/40"
                      : "bg-border"
                )}
              />
            )}

            {/* Step card + records */}
            <div className="flex-1 space-y-2 pb-6">
              <ApprovalStepCard
                step={step}
                status={status}
                reviewerName={reviewerName}
              />

              {/* Approval records */}
              {stepRecords.length > 0 && (
                <div className="ml-11 space-y-1.5">
                  {stepRecords.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-start gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs"
                    >
                      <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{record.reviewerName}</span>
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                              record.action === "approve" &&
                                "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400",
                              record.action === "reject" &&
                                "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400",
                              record.action === "comment" &&
                                "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400"
                            )}
                          >
                            {actionLabels[record.action]}
                          </span>
                          <span className="text-muted-foreground">
                            {formatDate(record.actedAt)}
                          </span>
                        </div>
                        {record.comment && (
                          <p className="mt-1 text-muted-foreground leading-relaxed">
                            {record.comment}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
