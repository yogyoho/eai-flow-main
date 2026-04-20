/**
 * 规则日志查看组件
 */

import React from "react";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import type { RuleExecutionLog, RuleExecutionStatistics } from "@/extensions/knowledge-factory/complianceRulesApi";
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
    <div className="shrink-0 w-full bg-background rounded-t-xl overflow-hidden border-t border-border shadow-sm">
      <div className="flex justify-between items-center px-4 py-3 bg-muted border-b">
        <h3 className="text-sm font-semibold text-foreground m-0">执行日志</h3>
        {onClose && (
          <Button variant="ghost" size="icon" className="w-7 h-7" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* 统计信息 */}
      {statistics && (
        <div className="flex gap-4 flex-wrap px-4 py-3 bg-muted border-b">
          <div className="flex flex-col items-center min-w-[60px]">
            <span className="text-xs text-muted-foreground">总执行次数</span>
            <span className="text-lg font-bold text-foreground">{statistics.totalExecutions}</span>
          </div>
          <div className="flex flex-col items-center min-w-[60px]">
            <span className="text-xs text-muted-foreground">通过</span>
            <span className="text-lg font-bold text-success">{statistics.passCount}</span>
          </div>
          <div className="flex flex-col items-center min-w-[60px]">
            <span className="text-xs text-muted-foreground">失败</span>
            <span className="text-lg font-bold text-destructive">{statistics.failCount}</span>
          </div>
          <div className="flex flex-col items-center min-w-[60px]">
            <span className="text-xs text-muted-foreground">警告</span>
            <span className="text-lg font-bold text-warning">{statistics.warningCount}</span>
          </div>
          <div className="flex flex-col items-center min-w-[60px]">
            <span className="text-xs text-muted-foreground">最近执行</span>
            <span className="text-lg font-bold text-foreground">
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
          <div className="p-8 text-center text-muted-foreground">加载中...</div>
        ) : logs.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">暂无执行日志</div>
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
    <div className={cn(
      "p-3 rounded-md mb-2 last:mb-0",
      resultClass === "pass" && "bg-success/10 border-l-2 border-success",
      resultClass === "fail" && "bg-destructive/10 border-l-2 border-destructive",
      resultClass === "warning" && "bg-warning/10 border-l-2 border-warning",
      resultClass === "error" && "bg-warning/10 border-l-2 border-warning",
      !resultClass && "bg-muted"
    )}>
      <div className="flex justify-between items-center mb-1.5">
        <span className={cn(
          "px-2 py-0.5 rounded text-xs font-medium",
          resultClass === "pass" && "bg-success/10 text-success",
          resultClass === "fail" && "bg-destructive/10 text-destructive",
          resultClass === "warning" && "bg-warning/10 text-warning",
          resultClass === "error" && "bg-warning/10 text-warning",
          !resultClass && "bg-muted text-muted-foreground"
        )}>{resultText}</span>
        <span className="text-xs text-muted-foreground/60">
          {new Date(log.executedAt).toLocaleString()}
        </span>
      </div>
      {log.checkDetails && (
        <div className="text-sm">
          {(log.checkDetails as { message?: string })?.message && (
            <p className="text-foreground mb-1">{(log.checkDetails as { message?: string })?.message}</p>
          )}
          {(log.checkDetails as { fieldName?: string })?.fieldName && (
            <span className="block text-xs text-muted-foreground">
              字段: {String((log.checkDetails as { fieldName?: string })?.fieldName)}
            </span>
          )}
          {(log.checkDetails as { suggestion?: string })?.suggestion && (
            <span className="block text-xs text-success">
              建议: {String((log.checkDetails as { suggestion?: string })?.suggestion)}
            </span>
          )}
        </div>
      )}
      {log.errorInfo && (
        <div className="text-xs text-destructive mt-1">{log.errorInfo}</div>
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
