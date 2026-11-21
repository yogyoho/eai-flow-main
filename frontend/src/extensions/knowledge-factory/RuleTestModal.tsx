/**
 * 规则测试弹窗组件
 */

import { X } from "lucide-react";
import React, { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { testRule } from "@/extensions/knowledge-factory/complianceRulesApi";
import { cn } from "@/lib/utils";

import { parseRuleTestInput } from "./rule-test-utils";

interface RuleTestModalProps {
  ruleId?: string;
  ruleName: string;
  onClose: () => void;
}

export function RuleTestModal({
  ruleId,
  ruleName,
  onClose,
}: RuleTestModalProps) {
  const [testData, setTestData] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{
    success: boolean;
    issues: Array<{
      ruleId: string;
      ruleName: string;
      severity: string;
      checkResult: string;
      message: string;
      fieldName?: string;
      suggestion?: string;
    }>;
    durationMs: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTest = async () => {
    if (!ruleId) {
      setError("规则ID不可用");
      return;
    }
    setTesting(true);
    setError(null);

    try {
      const response = await testRule(ruleId, parseRuleTestInput(testData));

      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-background flex max-h-[90vh] w-full max-w-[700px] flex-col overflow-hidden rounded-xl shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-foreground m-0 text-lg font-semibold">
            测试规则: {ruleName}
          </h2>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {/* 测试数据输入 */}
          <div className="mb-4">
            <label className="text-foreground mb-2 block text-sm font-medium">
              输入测试数据 (JSON 格式或纯文本)
            </label>
            <Textarea
              value={testData}
              onChange={(e) => setTestData(e.target.value)}
              placeholder={`示例 JSON:
{
  "sections": {
    "sec_03_工程分析": {
      "SO2排放量": "2.3",
      "NOx排放量": "5.8"
    },
    "sec_05_环境影响预测": {
      "SO2排放量": "2.5"
    }
  }
}

或纯文本:
工程分析中 SO2排放量为 2.3 t/a，环境影响预测中 SO2排放量为 2.5 t/a`}
              rows={12}
              className="font-mono text-sm"
            />
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="bg-destructive/10 text-destructive mt-3 rounded-md p-3 text-sm">
              {error}
            </div>
          )}

          {/* 测试结果 */}
          {result && (
            <div className="bg-muted mt-4 rounded-lg p-4">
              <h4 className="text-foreground mb-3 text-sm font-semibold">
                测试结果
              </h4>
              <div className="mb-3 flex items-center justify-between">
                <span
                  className={cn(
                    "rounded px-3 py-1 text-sm font-medium",
                    result.success
                      ? "bg-success/10 text-success"
                      : "bg-destructive/10 text-destructive",
                  )}
                >
                  {result.success ? "通过" : "失败"}
                </span>
                <span className="text-muted-foreground text-xs">
                  耗时: {result.durationMs.toFixed(0)}ms
                </span>
              </div>
              {result.issues.length > 0 ? (
                <div className="max-h-[300px] overflow-y-auto">
                  {result.issues.map((issue, idx) => (
                    <div
                      key={idx}
                      className={cn(
                        "bg-background mb-2 rounded-md p-3 last:mb-0",
                        issue.severity === "critical" &&
                          "border-destructive border-l-2",
                        issue.severity === "warning" &&
                          "border-warning border-l-2",
                        issue.severity === "info" &&
                          "border-primary border-l-2",
                      )}
                    >
                      <div className="mb-1.5 flex items-start gap-2">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.5 text-xs font-medium",
                            issue.severity === "critical"
                              ? "bg-destructive/10 text-destructive"
                              : issue.severity === "warning"
                                ? "bg-warning/10 text-warning"
                                : "bg-muted text-muted-foreground",
                          )}
                        >
                          {issue.severity}
                        </span>
                        <span className="text-foreground flex-1 text-sm">
                          {issue.message}
                        </span>
                      </div>
                      {issue.fieldName && (
                        <div className="text-muted-foreground mt-1 text-xs">
                          字段: {issue.fieldName}
                        </div>
                      )}
                      {issue.suggestion && (
                        <div className="text-success mt-1 text-xs">
                          建议: {issue.suggestion}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-success bg-success/10 rounded-md p-4 text-center">
                  没有发现问题
                </div>
              )}
            </div>
          )}
        </div>

        <div className="bg-muted flex justify-end gap-2 border-t px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
          <Button onClick={handleTest} disabled={testing || !testData.trim()}>
            {testing ? "测试中..." : "执行测试"}
          </Button>
        </div>
      </div>
    </div>
  );
}
