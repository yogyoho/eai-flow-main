"use client";

import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Filter,
  Loader2,
  MessageSquare,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { projectApi } from "@/extensions/project/api";
import type { ApprovalStatusResponse } from "@/extensions/project/types";
import type { ProjectIdentity } from "@/extensions/project/tabRegistry";
import { workflowApi } from "@/extensions/workflow/api";
import type { PhaseReview, ReviewStatus } from "@/extensions/workflow/types";

interface ReviewTabProps {
  project: { id: string; name: string; chapters: any[] };
  projectId: string;
  onRefresh: () => void;
  identity: ProjectIdentity | null;
}

type StatusFilter = "all" | "pending" | "approved" | "rejected";

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  pending: { label: "待审核", color: "bg-amber-50 text-amber-700 border-amber-200", icon: Clock },
  approved: { label: "已通过", color: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: CheckCircle2 },
  rejected: { label: "已拒绝", color: "bg-red-50 text-red-700 border-red-200", icon: XCircle },
};

export function ReviewTab({ project, projectId, onRefresh, identity }: ReviewTabProps) {
  const [myReviews, setMyReviews] = useState<PhaseReview[]>([]);
  const [allReviews, setAllReviews] = useState<PhaseReview[]>([]);
  const [approvalStatus, setApprovalStatus] = useState<ApprovalStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<"mine" | "all">("mine");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [reviews, approval] = await Promise.all([
        workflowApi.getMyReviews(projectId).catch(() => []),
        projectApi.getApprovalStatus(projectId).catch(() => null),
      ]);
      setMyReviews(reviews);
      setApprovalStatus(approval);
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const activeReviews = tab === "mine" ? myReviews : allReviews;
  const filtered = statusFilter === "all" ? activeReviews : activeReviews.filter((r) => r.status === statusFilter);
  const selected = filtered.find((r) => r.id === selectedId) ?? filtered[0] ?? null;

  const handleAction = async (action: "approved" | "rejected") => {
    if (!selected) return;
    setSubmitting(true);
    try {
      await workflowApi.submitReviewAction(projectId, selected.id, {
        action,
        comment: comment || undefined,
      });
      setComment("");
      await loadData();
    } catch {
      /* toast */
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header Bar */}
      <div className="flex items-center gap-3 border-b border-border/60 px-5 py-3 shrink-0">
        {/* Sub-tabs */}
        <div className="flex items-center rounded-lg bg-muted/50 p-0.5">
          <button
            type="button"
            onClick={() => setTab("mine")}
            className={`rounded-md px-3 py-1 text-[12px] font-medium transition-colors ${
              tab === "mine" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            我的审核
          </button>
          <button
            type="button"
            onClick={() => setTab("all")}
            className={`rounded-md px-3 py-1 text-[12px] font-medium transition-colors ${
              tab === "all" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            全部审核
          </button>
        </div>
        <div className="flex-1" />
        {/* Status filter */}
        <div className="flex items-center gap-1">
          <Filter className="h-3.5 w-3.5 text-muted-foreground mr-1" />
          {(["all", "pending", "approved", "rejected"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatusFilter(s)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors ${
                statusFilter === s
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {s === "all" ? "全部" : STATUS_CONFIG[s]?.label ?? s}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex flex-1 min-h-0">
        {/* Review Queue */}
        <div className="w-[340px] shrink-0 border-r border-border/40">
          <ScrollArea className="h-full">
            <div className="p-3 space-y-2">
              {filtered.length > 0 ? (
                filtered.map((review) => {
                  const cfg = STATUS_CONFIG[review.status] ?? STATUS_CONFIG.pending!;
                  const Icon = cfg.icon;
                  return (
                    <button
                      key={review.id}
                      type="button"
                      onClick={() => setSelectedId(review.id)}
                      className={`w-full text-left rounded-lg border p-3 transition-all ${
                        selected?.id === review.id
                          ? "border-primary/40 bg-primary/5 ring-1 ring-primary/20"
                          : "border-border/40 hover:bg-accent/40"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-foreground truncate">
                          {review.chapterId ? `章节 ${review.chapterId.slice(0, 8)}...` : "项目级审核"}
                        </span>
                        <Badge variant="outline" className={`text-[10px] ${cfg.color}`}>
                          <Icon className="h-3 w-3 mr-0.5" />
                          {cfg.label}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        审核人: {review.reviewerId?.slice(0, 8) ?? "..."}
                      </p>
                      {review.reviewType && (
                        <p className="text-[10px] text-muted-foreground/60 mt-0.5">{review.reviewType}</p>
                      )}
                    </button>
                  );
                })
              ) : (
                <div className="flex flex-col items-center justify-center py-16">
                  <CheckCircle2 className="h-8 w-8 text-muted-foreground/25 mb-2" />
                  <p className="text-sm text-muted-foreground">
                    {tab === "mine" ? "暂无待审核项" : "暂无审核数据"}
                  </p>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Detail Panel */}
        <div className="flex-1 min-w-0">
          {selected ? (
            <div className="flex h-full flex-col">
              <div className="p-5 space-y-4">
                <h3 className="text-sm font-semibold text-foreground">审核详情</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex">
                    <span className="w-20 text-muted-foreground shrink-0">审核 ID</span>
                    <span className="text-foreground font-mono text-xs">{selected.id.slice(0, 16)}...</span>
                  </div>
                  <div className="flex">
                    <span className="w-20 text-muted-foreground shrink-0">审核状态</span>
                    <Badge variant="outline" className={(STATUS_CONFIG[selected.status] ?? STATUS_CONFIG.pending!)?.color ?? ""}>
                      {(STATUS_CONFIG[selected.status] ?? STATUS_CONFIG.pending!)?.label ?? selected.status}
                    </Badge>
                  </div>
                  {selected.reviewType && (
                    <div className="flex">
                      <span className="w-20 text-muted-foreground shrink-0">审核类型</span>
                      <span className="text-foreground">{selected.reviewType}</span>
                    </div>
                  )}
                  {selected.comment && (
                    <div className="flex">
                      <span className="w-20 text-muted-foreground shrink-0">审核意见</span>
                      <span className="text-foreground">{selected.comment}</span>
                    </div>
                  )}
                </div>
                <Separator />
                {/* Action area for pending reviews */}
                {selected.status === "pending" && (
                  <div className="space-y-3">
                    <Textarea
                      placeholder="输入审核意见（可选）..."
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      className="min-h-[80px] text-sm resize-none"
                    />
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        className="h-8 bg-emerald-600 hover:bg-emerald-700 text-white"
                        disabled={submitting}
                        onClick={() => handleAction("approved")}
                      >
                        <ThumbsUp className="h-3.5 w-3.5 mr-1.5" />
                        通过
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        className="h-8"
                        disabled={submitting}
                        onClick={() => handleAction("rejected")}
                      >
                        <ThumbsDown className="h-3.5 w-3.5 mr-1.5" />
                        拒绝
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* Approval Status */}
              {approvalStatus && approvalStatus.steps?.length > 0 && (
                <div className="border-t border-border/40 px-5 py-4">
                  <h4 className="text-xs font-medium text-muted-foreground mb-3">审批流程</h4>
                  <div className="flex items-center gap-1">
                    {approvalStatus.steps.map((step, i) => (
                      <div key={step.id} className="flex items-center">
                        <div
                          className={`flex h-7 items-center rounded-full px-3 text-[11px] font-medium ${
                            step.status === "approved"
                              ? "bg-emerald-100 text-emerald-700"
                              : step.status === "rejected"
                                ? "bg-red-100 text-red-700"
                                : i === (approvalStatus.currentStep ?? 0)
                                  ? "bg-primary/10 text-primary"
                                  : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {step.stepName}
                        </div>
                        {i < approvalStatus.steps.length - 1 && (
                          <div className="h-px w-4 bg-border/60" />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <MessageSquare className="h-8 w-8 text-muted-foreground/25 mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">选择左侧审核项查看详情</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
