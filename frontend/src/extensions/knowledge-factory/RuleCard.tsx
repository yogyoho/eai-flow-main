/**
 * 规则卡片组件
 */

import { AlertCircle, Terminal, FileText } from "lucide-react";
import React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ComplianceRule } from "@/extensions/knowledge-factory/types";
import {
  SEVERITY_LEVELS,
  RULE_TYPES,
  INDUSTRIES,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface RuleCardProps {
  rule: ComplianceRule;
  selected?: boolean;
  selectionMode?: boolean;
  checked?: boolean;
  onSelect?: () => void;
  onToggleSelect?: () => void;
  readOnly?: boolean;
  onToggleEnabled?: (enabled: boolean) => Promise<void>;
  onViewLogs?: () => void;
  onTestRule?: () => void;
}

export function RuleCard({
  rule,
  selected = false,
  selectionMode = false,
  checked = false,
  onSelect,
  onToggleSelect,
  readOnly = false,
  onToggleEnabled,
  onViewLogs,
  onTestRule,
}: RuleCardProps) {
  // 获取严重级别颜色和标签
  const severityInfo = SEVERITY_LEVELS.find((s) => s.value === rule.severity);
  const severityLabel =
    rule.severityName || severityInfo?.label || rule.severity; // eslint-disable-line @typescript-eslint/prefer-nullish-coalescing -- *Name 字段是 API 层归一化出的 ""（非 nullish），空串必须回退到派生 label

  // 获取规则类型标签
  const typeInfo = RULE_TYPES.find((t) => t.value === rule.type);
  // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- 同上：typeName 为 "" 时需回退
  const typeLabel = rule.typeName || typeInfo?.label || rule.type;

  // 获取行业标签
  const industryInfo = INDUSTRIES.find((i) => i.value === rule.industry);
  const industryLabel =
    rule.industryName || industryInfo?.label || rule.industry; // eslint-disable-line @typescript-eslint/prefer-nullish-coalescing -- 同上：industryName 为 "" 时需回退

  // 处理启用/禁用切换
  const handleToggleEnabled = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onToggleEnabled) {
      await onToggleEnabled(!rule.enabled);
    }
  };

  // 处理复选框点击
  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleSelect?.();
  };

  // 严重级别徽章颜色
  const severityBadgeClass =
    rule.severity === "critical"
      ? "bg-destructive/10 text-destructive border-destructive/20"
      : rule.severity === "warning"
        ? "bg-warning/10 text-warning border-warning/20"
        : "bg-muted text-muted-foreground border-transparent";

  return (
    <Card
      className={cn(
        "hover:border-primary/30 relative cursor-pointer overflow-hidden transition-all hover:shadow-md",
        selected && "border-primary ring-primary/20 ring-2",
        !rule.enabled && "opacity-60",
        selectionMode && checked && "border-primary/40 bg-primary/5",
      )}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          onSelect?.();
        }
      }}
    >
      {/* 选择模式复选框 */}
      {selectionMode && (
        <div
          className="absolute top-3 left-3 z-10"
          onClick={handleCheckboxClick}
        >
          <input
            type="checkbox"
            checked={checked}
            onChange={() => {
              /* intentional no-op: click is handled by wrapper div */
            }}
            className="h-4 w-4"
          />
        </div>
      )}

      <div className="p-5">
        {/* 头部：规则ID和严重级别 */}
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            {/* 严重级别图标 */}
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                rule.severity === "critical"
                  ? "bg-destructive/10 text-destructive"
                  : rule.severity === "warning"
                    ? "bg-warning/10 text-warning"
                    : "bg-muted text-muted-foreground",
              )}
            >
              <AlertCircle className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground font-mono text-xs">
                  {rule.ruleId}
                </span>
                <Badge
                  variant="outline"
                  className={cn("text-xs font-medium", severityBadgeClass)}
                >
                  {severityLabel}
                </Badge>
              </div>

              {/* 规则名称 */}
              <h3 className="text-foreground mt-1 line-clamp-1 font-semibold">
                {rule.name}
              </h3>
            </div>
          </div>
        </div>

        {/* 规则描述 */}
        {rule.description && (
          <p className="text-muted-foreground mb-3 line-clamp-2 text-sm">
            {rule.description}
          </p>
        )}

        {/* 标签区域 */}
        <div className="mb-3 flex flex-wrap gap-2">
          <Badge variant="secondary" className="text-xs">
            {typeLabel}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {industryLabel}
          </Badge>
          {rule.nationalLevel && (
            <Badge
              variant="outline"
              className="border-warning/20 bg-warning/10 text-warning text-xs"
            >
              国家标准
            </Badge>
          )}
        </div>

        {/* 报告类型 */}
        {(rule.reportTypes?.length ?? 0) > 0 && (
          <div className="text-muted-foreground mb-3 flex items-center gap-2 text-xs">
            <span className="shrink-0 font-medium">适用报告:</span>
            <div className="flex flex-wrap gap-1">
              {(rule.reportTypes ?? []).slice(0, 2).map((rt, idx) => (
                <span
                  key={idx}
                  className="bg-muted rounded px-1.5 py-0.5 text-xs"
                >
                  {rt}
                </span>
              ))}
              {(rule.reportTypes ?? []).length > 2 && (
                <span className="text-muted-foreground/60">
                  +{(rule.reportTypes ?? []).length - 2}
                </span>
              )}
            </div>
          </div>
        )}

        {/* 源章节 */}
        {(rule.sourceSections?.length ?? 0) > 0 && (
          <div className="text-muted-foreground mb-4 text-xs">
            <span className="font-medium">来源: </span>
            {(rule.sourceSections ?? []).slice(0, 3).join("、")}
            {(rule.sourceSections?.length ?? 0) > 3 && "..."}
          </div>
        )}

        {/* 底部操作 */}
        <div className="border-border flex items-center justify-between border-t pt-4">
          {/* 启用/禁用开关 */}
          {!readOnly && onToggleEnabled && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleToggleEnabled}
              className={cn(
                "h-7 text-xs",
                rule.enabled
                  ? "border-success/20 bg-success/10 text-success hover:bg-success/10"
                  : "border-border bg-muted text-muted-foreground hover:bg-accent",
              )}
            >
              {rule.enabled ? "已启用" : "已禁用"}
            </Button>
          )}
          {readOnly && (
            <span
              className={cn(
                "text-xs font-medium",
                rule.enabled ? "text-success" : "text-muted-foreground",
              )}
            >
              {rule.enabled ? "启用" : "禁用"}
            </span>
          )}

          {/* 扩展操作按钮 */}
          <div className="flex gap-2">
            {onViewLogs && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onViewLogs();
                }}
                className="h-7 text-xs"
              >
                <FileText className="mr-1 h-3 w-3" />
                日志
              </Button>
            )}
            {onTestRule && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onTestRule();
                }}
                className="h-7 text-xs"
              >
                <Terminal className="mr-1 h-3 w-3" />
                测试
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
