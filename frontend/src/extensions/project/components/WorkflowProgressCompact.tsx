"use client";

import {
  ArrowRight,
  Ban,
  Check,
  CheckCircle,
  ChevronRight,
  GitBranch,
  Loader2,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { workflowApi } from "@/extensions/workflow/api";
import type {
  WorkflowGraph,
  WorkflowStatusResponse,
  WorkflowNodeStatus,
} from "@/extensions/workflow/types";

const WorkflowProgressView = dynamic(
  () =>
    import("@/extensions/workflow/WorkflowProgressView").then((m) => ({
      default: m.WorkflowProgressView,
    })),
  { ssr: false },
);

interface WorkflowProgressCompactProps {
  projectId: string;
  workflowGraph: WorkflowGraph | null;
  /** Whether current user can advance phases */
  canAdvancePhase?: boolean;
  /** Called when a phase is completed/advanced */
  onPhaseCompleted?: () => void;
}

function getNodeDetail(node: WorkflowNodeStatus) {
  if (node.chapterTotal)
    return `${node.chapterCompleted ?? 0}/${node.chapterTotal}`;
  if (node.reviewTotal)
    return `${node.reviewApproved ?? 0}/${node.reviewTotal}`;
  return null;
}

export function WorkflowProgressCompact({
  projectId,
  workflowGraph,
  canAdvancePhase,
  onPhaseCompleted,
}: WorkflowProgressCompactProps) {
  const [status, setStatus] = useState<WorkflowStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [gateMessage, setGateMessage] = useState<string | null>(null);

  // Fetch once on mount — no polling in overview
  const fetchStatus = useCallback(() => {
    workflowApi
      .getWorkflowStatus(projectId)
      .then((data) => {
        setStatus(data);
        setFetchError(false);
      })
      .catch(() => {
        setFetchError(true);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [projectId]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const nodes = useMemo(() => status?.nodes ?? [], [status?.nodes]);
  const runningNode = nodes.find((n) => n.status === "running");
  const canAct = canAdvancePhase && runningNode != null;

  const handleAdvance = useCallback(async () => {
    if (!canAct) return;
    setAdvancing(true);
    setGateMessage(null);
    try {
      // Direct fetch avoids SSR/streaming issues with the authFetch wrapper.
      const csrf = /csrf_token=([^;]+)/.exec(document.cookie)?.[1] ?? "";
      const resp = await fetch(
        `/api/extensions/project/projects/${projectId}/phase-complete`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ comment: "通过UI提交" }),
        },
      );
      if (resp.ok) {
        toast.success("阶段已推进");
        setGateMessage(null);
        onPhaseCompleted?.();
        setTimeout(() => fetchStatus(), 1500);
      } else {
        const body = await resp
          .json()
          .catch(() => ({ detail: resp.statusText }));
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : `请求失败 (${resp.status})`;
        if (resp.status === 409) setGateMessage(detail);
        toast.error(detail.length > 80 ? detail.slice(0, 80) + "…" : detail);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "网络异常";
      toast.error(msg);
    } finally {
      setAdvancing(false);
    }
  }, [canAct, projectId, onPhaseCompleted, fetchStatus]);

  return (
    <>
      <div className="border-border bg-background flex flex-col overflow-hidden rounded-xl border shadow-sm transition-all hover:shadow-md">
        <div className="flex items-center justify-between px-5 pt-4 pb-0">
          <h3 className="text-foreground text-sm font-medium">流程进度</h3>
          <div className="flex items-center gap-2">
            {canAct && (
              <Button
                size="sm"
                disabled={advancing}
                onClick={() => {
                  void handleAdvance();
                }}
                className="h-7 rounded-md text-[12px]"
              >
                {advancing ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ArrowRight className="mr-1 h-3.5 w-3.5" />
                )}
                阶段推进
              </Button>
            )}
            {!loading && nodes.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="text-primary hover:bg-primary/10 h-7 rounded-md text-[12px]"
                onClick={() => setDetailOpen(true)}
              >
                查看详情
              </Button>
            )}
          </div>
        </div>

        <div className="px-5 pt-2 pb-4">
          {loading ? (
            <div className="flex items-center gap-2 py-2">
              <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" />
              <span className="text-muted-foreground text-[13px]">
                加载中...
              </span>
            </div>
          ) : fetchError ? (
            <div className="flex items-center gap-2 py-2">
              <GitBranch className="text-muted-foreground/40 h-4 w-4" />
              <span className="text-muted-foreground text-[13px]">
                无法获取流程状态
              </span>
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-4">
              <GitBranch className="text-muted-foreground/25 mb-2 h-7 w-7" />
              <p className="text-muted-foreground text-[13px]">
                项目暂未设置工作流程
              </p>
              <p className="text-muted-foreground/60 mt-0.5 text-[11px]">
                可在项目设置中关联工作流模板
              </p>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1.5 py-1">
                {nodes.map((node, i) => {
                  const detail = getNodeDetail(node);
                  return (
                    <div key={node.nodeId} className="flex items-center">
                      {node.status === "completed" ? (
                        <div className="bg-success/5 border-success/30 flex items-center gap-2 rounded-lg border p-2">
                          <div className="bg-success/10 text-success flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full text-[7px] font-bold">
                            <Check className="h-2 w-2" />
                          </div>
                          <div className="min-w-0">
                            <h4
                              className="truncate text-xs font-normal"
                              style={{
                                color: "var(--cyber-text-main, currentColor)",
                              }}
                            >
                              {node.label}
                            </h4>
                            {detail && (
                              <p className="text-success font-cyber mt-0.5 text-[9px] font-bold">
                                {detail}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : node.status === "running" ? (
                        <div className="bg-primary/10 border-primary/30 flex items-center gap-2 rounded-lg border p-2 shadow-[0_0_12px_rgba(7,70,255,0.12)]">
                          <span className="bg-primary inline-block h-2 w-2 shrink-0 animate-ping rounded-full" />
                          <div className="min-w-0">
                            <h4
                              className="flex items-center gap-1.5 truncate text-xs font-normal"
                              style={{
                                color: "var(--cyber-text-main, currentColor)",
                              }}
                            >
                              {node.label}
                            </h4>
                            {detail && (
                              <p className="text-primary font-cyber mt-0.5 text-[9px] font-bold">
                                {detail}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : node.status === "error" ? (
                        <div className="bg-destructive/5 border-destructive/30 flex items-center gap-2 rounded-lg border p-2">
                          <span className="bg-destructive h-3.5 w-3.5 shrink-0 rounded-full" />
                          <div className="min-w-0">
                            <h4
                              className="truncate text-xs font-normal"
                              style={{
                                color: "var(--cyber-text-main, currentColor)",
                              }}
                            >
                              {node.label}
                            </h4>
                            {detail && (
                              <p className="text-destructive font-cyber mt-0.5 text-[9px] font-bold">
                                {detail}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="bg-muted border-border flex items-center gap-2 rounded-lg border p-2">
                          <span className="bg-muted-foreground/30 h-3.5 w-3.5 shrink-0 rounded-full" />
                          <div className="min-w-0">
                            <h4
                              className="truncate text-xs font-normal"
                              style={{
                                color: "var(--cyber-text-main, currentColor)",
                              }}
                            >
                              {node.label}
                            </h4>
                            {detail && (
                              <p
                                className="font-cyber mt-0.5 text-[9px]"
                                style={{
                                  color:
                                    "var(--cyber-text-muted, var(--color-muted-foreground))",
                                }}
                              >
                                {detail}
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                      {i < nodes.length - 1 && (
                        <ChevronRight className="text-muted-foreground/30 mx-0.5 h-3 w-3 shrink-0" />
                      )}
                    </div>
                  );
                })}
              </div>
              {/* Chapter-completion gate feedback */}
              {gateMessage && (
                <div className="bg-warning/10 text-warning border-warning/20 mt-2 flex items-start gap-1.5 rounded-md border px-2.5 py-2 text-[12px]">
                  <Ban className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>{gateMessage}</span>
                </div>
              )}
              {/* Success feedback */}
              {!advancing && runningNode && !gateMessage && canAct && (
                <div className="text-muted-foreground mt-2 flex items-center gap-1.5 text-[12px]">
                  <CheckCircle className="text-success h-3.5 w-3.5" />
                  <span>
                    当前阶段「{runningNode.label}
                    」进行中，点击&quot;阶段推进&quot;完成本阶段
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Full-screen detail dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="h-[80vh] max-w-[90vw] gap-0 p-0">
          <DialogTitle className="sr-only">流程详情</DialogTitle>
          <WorkflowProgressView
            projectId={projectId}
            workflowGraph={workflowGraph}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
