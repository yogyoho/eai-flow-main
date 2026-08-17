"use client";

import { workflowApi } from "./api";
import { useWorkflowStatus } from "./hooks/useWorkflowStatus";
import { PhaseStatusCard } from "./PhaseStatusCard";

interface WorkflowMonitorProps {
  projectId: string;
}

export function WorkflowMonitor({ projectId }: WorkflowMonitorProps) {
  const { status, loading, refresh } = useWorkflowStatus(projectId);

  if (loading)
    return (
      <div className="text-muted-foreground p-4 text-sm">加载工作流状态...</div>
    );
  if (!status)
    return (
      <div className="text-muted-foreground p-4 text-sm">未配置工作流</div>
    );

  const handleStart = async () => {
    if (!status.workflowId) return;
    await workflowApi.startWorkflow(projectId, status.workflowId);
    await refresh();
  };

  const handleCancel = async () => {
    await workflowApi.cancelWorkflow(projectId);
    await refresh();
  };

  const statusColor =
    status.status === "running"
      ? "text-blue-600"
      : status.status === "completed"
        ? "text-green-600"
        : status.status === "failed"
          ? "text-red-600"
          : "text-muted-foreground";

  return (
    <div className="space-y-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">工作流监控</div>
          <div className={`text-xs ${statusColor}`}>
            {status.status === "idle" && "未启动"}
            {status.status === "running" && "执行中"}
            {status.status === "completed" && "已完成"}
            {status.status === "failed" && "失败"}
          </div>
        </div>
        <div className="flex gap-2">
          {status.status === "idle" && status.workflowId && (
            <button
              onClick={handleStart}
              className="bg-primary text-primary-foreground rounded px-3 py-1 text-xs hover:opacity-90"
            >
              启动工作流
            </button>
          )}
          {status.status === "running" && (
            <button
              onClick={handleCancel}
              className="rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-700"
            >
              取消
            </button>
          )}
        </div>
      </div>

      {/* Current phase */}
      {status.currentPhaseNode && (
        <div className="rounded border border-blue-200 bg-blue-50 p-2 text-xs">
          当前节点:{" "}
          <span className="font-medium">{status.currentPhaseNode}</span>
        </div>
      )}

      {/* Node timeline */}
      <div className="space-y-2">
        {status.nodes.map((node) => (
          <PhaseStatusCard key={node.nodeId} node={node} />
        ))}
      </div>

      {status.nodes.length === 0 && (
        <div className="text-muted-foreground py-4 text-center text-xs">
          该项目未关联工作流定义
        </div>
      )}
    </div>
  );
}
