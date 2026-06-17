"use client";

import { ArrowRight, Ban, Check, CheckCircle, ChevronRight, GitBranch, Loader2 } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { projectApi } from "@/extensions/project/api";
import { workflowApi } from "@/extensions/workflow/api";
import type { WorkflowGraph, WorkflowStatusResponse, WorkflowNodeStatus } from "@/extensions/workflow/types";

const WorkflowProgressView = dynamic(
  () => import("@/extensions/workflow/WorkflowProgressView").then((m) => ({ default: m.WorkflowProgressView })),
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
  if (node.chapterTotal) return `${node.chapterCompleted ?? 0}/${node.chapterTotal}`;
  if (node.reviewTotal) return `${node.reviewApproved ?? 0}/${node.reviewTotal}`;
  return null;
}

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700",
  running: "bg-primary/10 text-primary ring-1 ring-primary/30",
  pending: "bg-muted text-muted-foreground",
  error: "bg-red-100 text-red-700",
};

export function WorkflowProgressCompact({ projectId, workflowGraph, canAdvancePhase, onPhaseCompleted }: WorkflowProgressCompactProps) {
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
      .then((data) => { setStatus(data); setFetchError(false); })
      .catch(() => { setFetchError(true); })
      .finally(() => { setLoading(false); });
  }, [projectId]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const nodes = useMemo(() => status?.nodes ?? [], [status?.nodes]);
  const runningNode = nodes.find((n) => n.status === "running");
  const canAct = canAdvancePhase && runningNode != null;

  const handleAdvance = useCallback(async () => {
    if (!canAct) return;
    setAdvancing(true);
    setGateMessage(null);
    try {
      // Direct fetch avoids SSR/streaming issues with the authFetch wrapper.
      const csrf = (/csrf_token=([^;]+)/.exec(document.cookie))?.[1] ?? "";
      const resp = await fetch(`/api/extensions/project/projects/${projectId}/phase-complete`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ comment: "通过UI提交" }),
      });
      if (resp.ok) {
        toast.success("阶段已推进");
        setGateMessage(null);
        onPhaseCompleted?.();
        setTimeout(() => fetchStatus(), 1500);
      } else {
        const body = await resp.json().catch(() => ({ detail: resp.statusText }));
        const detail = typeof body.detail === "string" ? body.detail : `请求失败 (${resp.status})`;
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
      <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
        <div className="flex items-center justify-between px-5 pt-4 pb-0">
          <h3 className="text-sm font-medium text-foreground">流程进度</h3>
          <div className="flex items-center gap-2">
            {canAct && (
              <Button
                size="sm"
                disabled={advancing}
                onClick={handleAdvance}
                className="h-7 text-[12px] rounded-md"
              >
                {advancing ? (
                  <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                ) : (
                  <ArrowRight className="h-3.5 w-3.5 mr-1" />
                )}
                阶段推进
              </Button>
            )}
            {!loading && nodes.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-[12px] text-primary rounded-md hover:bg-primary/10"
                onClick={() => setDetailOpen(true)}
              >
                查看详情
              </Button>
            )}
          </div>
        </div>

        <div className="px-5 pb-4 pt-2">
          {loading ? (
            <div className="flex items-center gap-2 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="text-[13px] text-muted-foreground">加载中...</span>
            </div>
          ) : fetchError ? (
            <div className="flex items-center gap-2 py-2">
              <GitBranch className="h-4 w-4 text-muted-foreground/40" />
              <span className="text-[13px] text-muted-foreground">无法获取流程状态</span>
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-4">
              <GitBranch className="h-7 w-7 text-muted-foreground/25 mb-2" />
              <p className="text-[13px] text-muted-foreground">项目暂未设置工作流程</p>
              <p className="text-[11px] text-muted-foreground/60 mt-0.5">可在项目设置中关联工作流模板</p>
            </div>
          ) : (
            <>
              <div className="flex items-center flex-wrap gap-1">
                {nodes.map((node, i) => (
                  <div key={node.nodeId} className="flex items-center">
                    <span
                      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-medium ${
                        STATUS_STYLES[node.status] ?? STATUS_STYLES.pending!
                      }`}
                    >
                      {node.status === "completed" && <Check className="h-3 w-3 mr-1" />}
                      {node.status === "running" && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                      {node.label}
                      {getNodeDetail(node) && (
                        <span className="ml-1.5 text-[10px] opacity-70">({getNodeDetail(node)})</span>
                      )}
                    </span>
                    {i < nodes.length - 1 && (
                      <ChevronRight className="h-3 w-3 text-muted-foreground/40 mx-0.5" />
                    )}
                  </div>
                ))}
              </div>
              {/* Chapter-completion gate feedback */}
              {gateMessage && (
                <div className="mt-2 flex items-start gap-1.5 rounded-md bg-amber-50 px-2.5 py-2 text-[12px] text-amber-700 border border-amber-200">
                  <Ban className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>{gateMessage}</span>
                </div>
              )}
              {/* Success feedback */}
              {!advancing && runningNode && !gateMessage && canAct && (
                <div className="mt-2 flex items-center gap-1.5 text-[12px] text-muted-foreground">
                  <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                  <span>当前阶段「{runningNode.label}」进行中，点击"阶段推进"完成本阶段</span>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Full-screen detail dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-[90vw] h-[80vh] p-0 gap-0">
          <DialogTitle className="sr-only">流程详情</DialogTitle>
          <WorkflowProgressView projectId={projectId} workflowGraph={workflowGraph} />
        </DialogContent>
      </Dialog>
    </>
  );
}
