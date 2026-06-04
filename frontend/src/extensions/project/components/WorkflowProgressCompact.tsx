"use client";

import { Check, ChevronRight, Loader2 } from "lucide-react";
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

export function WorkflowProgressCompact({ projectId, workflowGraph }: WorkflowProgressCompactProps) {
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

  // Don't render if loading, errored, or no nodes
  if (loading || error || nodes.length === 0) return null;

  return (
    <>
      <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md">
        <div className="flex items-center justify-between px-5 pt-4 pb-0">
          <h3 className="text-sm font-medium text-foreground">流程进度</h3>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-[12px] text-primary rounded-md hover:bg-primary/10"
            onClick={() => setDetailOpen(true)}
          >
            查看详情
          </Button>
        </div>
        <div className="flex items-center flex-wrap gap-1 px-5 pb-4 pt-2">
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
