/**
 * 检查结果展示组件
 */

import { X, CheckCircle2, Loader2 } from "lucide-react";
import React from "react";

import { Button } from "@/components/ui/button";
import type {
  ValidationIssue,
  ComplianceCheckResponse,
} from "@/extensions/knowledge-factory/types";
import { SEVERITY_LEVELS } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface CheckResultPanelProps {
  result: ComplianceCheckResponse;
  onIssueClick?: (issue: ValidationIssue) => void;
  onClose?: () => void;
  showDetails?: boolean;
}

export function CheckResultPanel({
  result,
  onIssueClick,
  onClose,
  showDetails = true,
}: CheckResultPanelProps) {
  // 按严重级别分组问题
  const criticalIssues = result.issues.filter(
    (i) => i.severity === "critical" && i.checkResult === "fail",
  );
  const warningIssues = result.issues.filter(
    (i) => i.severity === "warning" && i.checkResult === "fail",
  );
  const passedIssues = result.issues.filter((i) => i.checkResult === "pass");

  return (
    <div className="bg-background overflow-hidden rounded-lg shadow-md">
      {/* 头部 */}
      <div className="bg-muted flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-foreground m-0 text-sm font-semibold">
          合规性检查结果
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs">
            {result.durationMs.toFixed(0)}ms
          </span>
          {onClose && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* 统计摘要 */}
      <div className="border-b px-4 py-4">
        <div
          className={cn(
            "mb-3 inline-block rounded px-3 py-1 text-sm font-semibold",
            result.success
              ? "bg-success/10 text-success"
              : "bg-destructive/10 text-destructive",
          )}
        >
          {result.success ? "全部通过" : "存在违规"}
        </div>
        <div className="flex gap-4">
          <div className="flex flex-col items-center">
            <span className="text-foreground text-xl font-bold">
              {result.totalRules}
            </span>
            <span className="text-muted-foreground text-xs">总规则</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-success text-xl font-bold">
              {result.passed}
            </span>
            <span className="text-muted-foreground text-xs">通过</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-destructive text-xl font-bold">
              {result.failed}
            </span>
            <span className="text-muted-foreground text-xs">失败</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-warning text-xl font-bold">
              {result.warnings}
            </span>
            <span className="text-muted-foreground text-xs">警告</span>
          </div>
        </div>
        {result.hasCriticalIssues && (
          <div className="bg-destructive/10 text-destructive mt-3 rounded px-3 py-2 text-sm font-medium">
            存在严重违规问题，需要立即处理
          </div>
        )}
      </div>

      {/* 问题列表 */}
      {showDetails && (
        <div className="max-h-[400px] overflow-y-auto">
          {/* 严重问题 */}
          {criticalIssues.length > 0 && (
            <div className="border-b px-4 py-3">
              <h4 className="text-destructive mb-2 text-sm font-semibold">
                严重问题 ({criticalIssues.length})
              </h4>
              <div>
                {criticalIssues.map((issue, idx) => (
                  <IssueItem
                    key={idx}
                    issue={issue}
                    onClick={() => onIssueClick?.(issue)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 警告问题 */}
          {warningIssues.length > 0 && (
            <div className="border-b px-4 py-3">
              <h4 className="text-warning mb-2 text-sm font-semibold">
                警告问题 ({warningIssues.length})
              </h4>
              <div>
                {warningIssues.map((issue, idx) => (
                  <IssueItem
                    key={idx}
                    issue={issue}
                    onClick={() => onIssueClick?.(issue)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 通过的检查 */}
          {passedIssues.length > 0 && result.failed > 0 && (
            <div className="border-b px-4 py-3">
              <h4 className="text-success mb-2 text-sm font-semibold">
                通过的检查 ({passedIssues.length})
              </h4>
              <div className="max-h-[150px] overflow-y-auto">
                {passedIssues.map((issue, idx) => (
                  <div
                    key={idx}
                    className="text-success flex items-center gap-2 py-1.5 text-sm"
                  >
                    <CheckCircle2 className="h-4 w-4 font-bold" />
                    <span>{issue.ruleName}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface IssueItemProps {
  issue: ValidationIssue;
  onClick?: () => void;
}

function IssueItem({ issue, onClick }: IssueItemProps) {
  const severityInfo = SEVERITY_LEVELS.find((s) => s.value === issue.severity);
  const severityColor = severityInfo?.color ?? "var(--muted-foreground)";

  return (
    <div
      className="bg-muted hover:bg-muted/80 mb-2 cursor-pointer rounded-md p-3 transition-colors last:mb-0"
      onClick={onClick}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: severityColor }}
        />
        <span className="text-foreground flex-1 font-medium">
          {issue.ruleName}
        </span>
        <span className="bg-destructive/10 text-destructive rounded px-1.5 py-0.5 text-xs font-medium">
          违规
        </span>
      </div>
      <p className="text-foreground mb-1.5 text-sm leading-relaxed">
        {issue.message}
      </p>
      {issue.fieldName && (
        <div className="text-muted-foreground mb-1 text-xs">
          <span className="font-medium">涉及字段：</span>
          <span>{issue.fieldName}</span>
        </div>
      )}
      {issue.sourceValue && issue.targetValue && (
        <div className="mb-1 flex items-center gap-2 text-xs">
          <span className="text-destructive">源值：{issue.sourceValue}</span>
          <span className="text-muted-foreground">→</span>
          <span className="text-success">目标值：{issue.targetValue}</span>
        </div>
      )}
      {issue.suggestion && (
        <div className="text-success mb-1 text-xs italic">
          <span className="font-medium not-italic">修复建议：</span>
          <span>{issue.suggestion}</span>
        </div>
      )}
    </div>
  );
}

// ============== 检查状态组件 ==============

interface CheckStatusProps {
  checking: boolean;
  lastResult?: ComplianceCheckResponse;
  onCheck?: () => void;
  onViewResult?: () => void;
}

export function CheckStatus({
  checking,
  lastResult,
  onCheck,
  onViewResult,
}: CheckStatusProps) {
  return (
    <div className="flex items-center">
      {checking ? (
        <div className="text-muted-foreground flex items-center gap-2">
          <Loader2 className="text-primary h-4 w-4 animate-spin" />
          <span>检查中...</span>
        </div>
      ) : lastResult ? (
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full text-sm font-bold",
              lastResult.success
                ? "bg-success/10 text-success"
                : "bg-destructive/10 text-destructive",
            )}
          >
            {lastResult.success ? "✓" : "!"}
          </div>
          <span className="text-foreground text-sm">
            {lastResult.success
              ? `检查通过 (${lastResult.passed}项)`
              : `${lastResult.failed}项违规，${lastResult.warnings}项警告`}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={onCheck}>
              重新检查
            </Button>
            <Button size="sm" variant="ghost" onClick={onViewResult}>
              查看详情
            </Button>
          </div>
        </div>
      ) : (
        <div className="text-muted-foreground flex items-center gap-3">
          <span>尚未执行合规性检查</span>
          <Button size="sm" onClick={onCheck}>
            开始检查
          </Button>
        </div>
      )}
    </div>
  );
}

// ============== 行内校验组件 ==============

interface InlineCheckProps {
  issues: ValidationIssue[];
  fieldName?: string;
  onDismiss?: () => void;
}

export function InlineCheck({
  issues,
  fieldName,
  onDismiss,
}: InlineCheckProps) {
  if (issues.length === 0) return null;

  const critical = issues.filter((i) => i.severity === "critical");
  const isCritical = critical.length > 0;

  return (
    <div
      className={cn(
        "mb-2 rounded-md p-3",
        isCritical
          ? "bg-destructive/10 border-destructive/20 border"
          : "bg-warning/10 border-warning/20 border",
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            "text-lg",
            isCritical ? "text-destructive" : "text-warning",
          )}
        >
          {isCritical ? "!" : "⚠"}
        </span>
        <span className="text-foreground flex-1 font-medium">
          {fieldName ? `字段 "${fieldName}" 校验问题` : "校验问题"}
        </span>
        {onDismiss && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
      <ul className="m-0 list-none p-0">
        {issues.map((issue, idx) => (
          <li key={idx} className="py-1 text-sm">
            <span className="text-foreground">{issue.message}</span>
            {issue.suggestion && (
              <span className="text-success mt-0.5 block text-xs">
                {issue.suggestion}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
