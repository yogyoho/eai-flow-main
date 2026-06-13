"use client";

import { Check, ChevronRight, GitBranch, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

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

export function WorkflowProgressCompact({ projectId, workflowGraph, canAdvancePhase: _canAdvance, onPhaseCompleted: _onPhaseCompleted }: WorkflowProgressCompactProps) {
  const [status, setStatus] = useState<WorkflowStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);

  // Fetch once on mount — no polling in overview
  useEffect(() => {
    let cancelled = false;
    workflowApi
      .getWorkflowStatus(projectId)
      .then((data) => { if (!cancelled) setStatus(data); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId]);

  const nodes = useMemo(() => status?.nodes ?? [], [status?.nodes]);

  return (
    <>
      <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
        <div className="flex items-center justify-between px-5 pt-4 pb-0">
          <h3 className="text-sm font-medium text-foreground">流程进度</h3>
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

        <div className="px-5 pb-4 pt-2">
          {loading ? (
            <div className="flex items-center gap-2 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="text-[13px] text-muted-foreground">加载中...</span>
            </div>
          ) : error ? (
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
