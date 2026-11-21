/**
 * 规则日志查看组件
 */

import { X } from "lucide-react";
import React from "react";

import { Button } from "@/components/ui/button";
import type {
  RuleExecutionLog,
  RuleExecutionStatistics,
} from "@/extensions/knowledge-factory/complianceRulesApi";
import { cn } from "@/lib/utils";

interface RuleLogsViewerProps {
  logs: RuleExecutionLog[];
  statistics?: RuleExecutionStatistics;
  loading?: boolean;
  onClose?: () => void;
}

export function RuleLogsViewer({
  logs,
  statistics,
  loading = false,
  onClose,
}: RuleLogsViewerProps) {
  return (
    <div className="bg-background border-border w-full shrink-0 overflow-hidden rounded-t-xl border-t shadow-sm">
      <div className="bg-muted flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-foreground m-0 text-sm font-semibold">执行日志</h3>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* 统计信息 */}
      {statistics && (
        <div className="bg-muted flex flex-wrap gap-4 border-b px-4 py-3">
          <div className="flex min-w-[60px] flex-col items-center">
            <span className="text-muted-foreground text-xs">总执行次数</span>
            <span className="text-foreground text-lg font-bold">
              {statistics.totalExecutions}
            </span>
          </div>
          <div className="flex min-w-[60px] flex-col items-center">
            <span className="text-muted-foreground text-xs">通过</span>
            <span className="text-success text-lg font-bold">
              {statistics.passCount}
            </span>
          </div>
          <div className="flex min-w-[60px] flex-col items-center">
            <span className="text-muted-foreground text-xs">失败</span>
            <span className="text-destructive text-lg font-bold">
              {statistics.failCount}
            </span>
          </div>
          <div className="flex min-w-[60px] flex-col items-center">
            <span className="text-muted-foreground text-xs">警告</span>
            <span className="text-warning text-lg font-bold">
              {statistics.warningCount}
            </span>
          </div>
          <div className="flex min-w-[60px] flex-col items-center">
            <span className="text-muted-foreground text-xs">最近执行</span>
            <span className="text-foreground text-lg font-bold">
              {statistics.lastExecutedAt
                ? new Date(statistics.lastExecutedAt).toLocaleString()
                : "无"}
            </span>
          </div>
        </div>
      )}

      {/* 日志列表 */}
      <div className="max-h-[400px] overflow-y-auto">
        {loading ? (
          <div className="text-muted-foreground p-8 text-center">加载中...</div>
        ) : logs.length === 0 ? (
          <div className="text-muted-foreground p-8 text-center">
            暂无执行日志
          </div>
        ) : (
          <div className="p-2">
            {logs.map((log) => (
              <LogItem key={log.id} log={log} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LogItem({ log }: { log: RuleExecutionLog }) {
  const resultClass = getResultClass(log.checkResult);
  const resultText = getResultText(log.checkResult);

  return (
    <div
      className={cn(
        "mb-2 rounded-md p-3 last:mb-0",
        resultClass === "pass" && "bg-success/10 border-success border-l-2",
        resultClass === "fail" &&
          "bg-destructive/10 border-destructive border-l-2",
        resultClass === "warning" && "bg-warning/10 border-warning border-l-2",
        resultClass === "error" && "bg-warning/10 border-warning border-l-2",
        !resultClass && "bg-muted",
      )}
    >
      <div className="mb-1.5 flex items-center justify-between">
        <span
          className={cn(
            "rounded px-2 py-0.5 text-xs font-medium",
            resultClass === "pass" && "bg-success/10 text-success",
            resultClass === "fail" && "bg-destructive/10 text-destructive",
            resultClass === "warning" && "bg-warning/10 text-warning",
            resultClass === "error" && "bg-warning/10 text-warning",
            !resultClass && "bg-muted text-muted-foreground",
          )}
        >
          {resultText}
        </span>
        <span className="text-muted-foreground/60 text-xs">
          {new Date(log.executedAt).toLocaleString()}
        </span>
      </div>
      {log.checkDetails && (
        <div className="text-sm">
          {(log.checkDetails as { message?: string })?.message && (
            <p className="text-foreground mb-1">
              {(log.checkDetails as { message?: string })?.message}
            </p>
          )}
          {(log.checkDetails as { fieldName?: string })?.fieldName && (
            <span className="text-muted-foreground block text-xs">
              字段:{" "}
              {String((log.checkDetails as { fieldName?: string })?.fieldName)}
            </span>
          )}
          {(log.checkDetails as { suggestion?: string })?.suggestion && (
            <span className="text-success block text-xs">
              建议:{" "}
              {String(
                (log.checkDetails as { suggestion?: string })?.suggestion,
              )}
            </span>
          )}
        </div>
      )}
      {log.errorInfo && (
        <div className="text-destructive mt-1 text-xs">{log.errorInfo}</div>
      )}
    </div>
  );
}

function getResultClass(result: string): string {
  switch (result) {
    case "pass":
      return "pass";
    case "fail":
      return "fail";
    case "warning":
      return "warning";
    case "error":
      return "error";
    default:
      return "";
  }
}

function getResultText(result: string): string {
  switch (result) {
    case "pass":
      return "通过";
    case "fail":
      return "失败";
    case "warning":
      return "警告";
    case "error":
      return "错误";
    case "skip":
      return "跳过";
    default:
      return result;
  }
}
