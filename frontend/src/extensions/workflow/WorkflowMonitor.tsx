"use client";

import { workflowApi } from "./api";
import { PhaseStatusCard } from "./PhaseStatusCard";
import { useWorkflowStatus } from "./hooks/useWorkflowStatus";

interface WorkflowMonitorProps {
  projectId: string;
}

export function WorkflowMonitor({ projectId }: WorkflowMonitorProps) {
  const { status, loading, refresh } = useWorkflowStatus(projectId);

  if (loading) return <div className="p-4 text-sm text-muted-foreground">加载工作流状态...</div>;
  if (!status) return <div className="p-4 text-sm text-muted-foreground">未配置工作流</div>;

  const handleStart = async () => {
    if (!status.workflowId) return;
    await workflowApi.startWorkflow(projectId, status.workflowId);
    refresh();
  };

  const handleCancel = async () => {
    await workflowApi.cancelWorkflow(projectId);
    refresh();
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
    <div className="p-4 space-y-4">
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
              className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:opacity-90"
            >
              启动工作流
            </button>
          )}
          {status.status === "running" && (
            <button
              onClick={handleCancel}
              className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
            >
              取消
            </button>
          )}
        </div>
      </div>

      {/* Current phase */}
      {status.currentPhaseNode && (
        <div className="bg-blue-50 border border-blue-200 rounded p-2 text-xs">
          当前节点: <span className="font-medium">{status.currentPhaseNode}</span>
        </div>
      )}

      {/* Node timeline */}
      <div className="space-y-2">
        {status.nodes.map((node) => (
          <PhaseStatusCard key={node.nodeId} node={node} />
        ))}
      </div>

      {status.nodes.length === 0 && (
        <div className="text-xs text-muted-foreground text-center py-4">
          该项目未关联工作流定义
        </div>
      )}
    </div>
  );
}
