/**
 * 规则测试弹窗组件
 */

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { X } from "lucide-react";
import { testRule } from "@/extensions/knowledge-factory/complianceRulesApi";
import { parseRuleTestInput } from "./rule-test-utils";
import { cn } from "@/lib/utils";

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
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[1000]"
      onClick={onClose}
    >
      <div 
        className="w-full max-w-[700px] max-h-[90vh] flex flex-col bg-white rounded-xl shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-foreground m-0">测试规则: {ruleName}</h2>
          <Button variant="ghost" size="icon" className="w-8 h-8" onClick={onClose}>
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {/* 测试数据输入 */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-foreground mb-2">输入测试数据 (JSON 格式或纯文本)</label>
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
            <div className="p-3 bg-destructive/10 text-destructive rounded-md mt-3 text-sm">{error}</div>
          )}

          {/* 测试结果 */}
          {result && (
            <div className="mt-4 p-4 bg-muted rounded-lg">
              <h4 className="text-sm font-semibold text-foreground mb-3">测试结果</h4>
              <div className="flex justify-between items-center mb-3">
                <span className={cn(
                  "px-3 py-1 rounded text-sm font-medium",
                  result.success ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"
                )}>
                  {result.success ? "通过" : "失败"}
                </span>
                <span className="text-xs text-muted-foreground">耗时: {result.durationMs.toFixed(0)}ms</span>
              </div>
              {result.issues.length > 0 ? (
                <div className="max-h-[300px] overflow-y-auto">
                  {result.issues.map((issue, idx) => (
                    <div
                      key={idx}
                      className={cn(
                        "p-3 bg-background rounded-md mb-2 last:mb-0",
                        issue.severity === "critical" && "border-l-2 border-destructive",
                        issue.severity === "warning" && "border-l-2 border-warning",
                        issue.severity === "info" && "border-l-2 border-primary"
                      )}
                    >
                      <div className="flex items-start gap-2 mb-1.5">
                        <span className={cn(
                          "px-1.5 py-0.5 rounded text-xs font-medium",
                          issue.severity === "critical" ? "bg-destructive/10 text-destructive" :
                          issue.severity === "warning" ? "bg-warning/10 text-warning" :
                          "bg-muted text-muted-foreground"
                        )}>{issue.severity}</span>
                        <span className="flex-1 text-sm text-foreground">{issue.message}</span>
                      </div>
                      {issue.fieldName && (
                        <div className="text-xs text-muted-foreground mt-1">字段: {issue.fieldName}</div>
                      )}
                      {issue.suggestion && (
                        <div className="text-xs text-success mt-1">建议: {issue.suggestion}</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 text-center text-success bg-success/10 rounded-md">没有发现问题</div>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t bg-muted">
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
          <Button
            onClick={handleTest}
            disabled={testing || !testData.trim()}
          >
            {testing ? "测试中..." : "执行测试"}
          </Button>
        </div>
      </div>
    </div>
  );
}
