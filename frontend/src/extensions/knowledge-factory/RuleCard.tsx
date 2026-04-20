/**
 * 规则卡片组件
 */

import {
  AlertCircle,
  ChevronRight,
  Terminal,
  FileText,
} from "lucide-react";
import React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ComplianceRule } from "@/extensions/knowledge-factory/types";
import { SEVERITY_LEVELS, RULE_TYPES, INDUSTRIES } from "@/extensions/knowledge-factory/types";
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
  const severityColor = severityInfo?.color || "#6b7280";
  const severityLabel = rule.severityName || severityInfo?.label || rule.severity;

  // 获取规则类型标签
  const typeInfo = RULE_TYPES.find((t) => t.value === rule.type);
  const typeLabel = rule.typeName || typeInfo?.label || rule.type;

  // 获取行业标签
  const industryInfo = INDUSTRIES.find((i) => i.value === rule.industry);
  const industryLabel = rule.industryName || industryInfo?.label || rule.industry;

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
      ? "bg-amber-50 text-amber-600 border-amber-200"
      : "bg-muted text-muted-foreground border-transparent";

  return (
    <Card
      className={cn(
        "relative cursor-pointer overflow-hidden transition-all hover:border-primary/30 hover:shadow-md",
        selected && "border-primary ring-2 ring-primary/20",
        !rule.enabled && "opacity-60",
        selectionMode && checked && "border-primary/40 bg-primary/5"
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
          className="absolute left-3 top-3 z-10"
          onClick={handleCheckboxClick}
        >
          <input
            type="checkbox"
            checked={checked}
            onChange={() => {}}
            className="h-4 w-4"
          />
        </div>
      )}

      <div className="p-5">
        {/* 头部：规则ID和严重级别 */}
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            {/* 严重级别图标 */}
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                rule.severity === "critical"
                  ? "bg-destructive/10 text-destructive"
                  : rule.severity === "warning"
                  ? "bg-amber-50 text-amber-600"
                  : "bg-muted text-muted-foreground"
              )}
            >
              <AlertCircle className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs text-muted-foreground">
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
              <h3 className="mt-1 font-semibold text-foreground line-clamp-1">
                {rule.name}
              </h3>
            </div>
          </div>
        </div>

        {/* 规则描述 */}
        {rule.description && (
          <p className="mb-3 text-sm text-muted-foreground line-clamp-2">
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
            <Badge variant="outline" className="text-xs border-amber-200 bg-amber-50 text-amber-600">
              国家标准
            </Badge>
          )}
        </div>

        {/* 报告类型 */}
        {(rule.reportTypes?.length ?? 0) > 0 && (
          <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="shrink-0 font-medium">适用报告:</span>
            <div className="flex flex-wrap gap-1">
              {(rule.reportTypes ?? []).slice(0, 2).map((rt, idx) => (
                <span
                  key={idx}
                  className="rounded bg-muted px-1.5 py-0.5 text-xs"
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
          <div className="mb-4 text-xs text-muted-foreground">
            <span className="font-medium">来源: </span>
            {(rule.sourceSections ?? []).slice(0, 3).join("、")}
            {(rule.sourceSections?.length ?? 0) > 3 && "..."}
          </div>
        )}

        {/* 底部操作 */}
        <div className="flex items-center justify-between border-t border-border pt-4">
          {/* 启用/禁用开关 */}
          {!readOnly && onToggleEnabled && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleToggleEnabled}
              className={cn(
                "h-7 text-xs",
                rule.enabled
                  ? "border-emerald-200 bg-emerald-50 text-emerald-600 hover:bg-emerald-100"
                  : "border-border bg-muted text-muted-foreground hover:bg-accent"
              )}
            >
              {rule.enabled ? "已启用" : "已禁用"}
            </Button>
          )}
          {readOnly && (
            <span
              className={cn(
                "text-xs font-medium",
                rule.enabled ? "text-emerald-600" : "text-muted-foreground"
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
