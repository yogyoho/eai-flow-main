"use client";

import { AlertCircle, X } from "lucide-react";
import React, { useMemo, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { createRule } from "@/extensions/knowledge-factory/complianceRulesApi";
import {
  buildRuleCreatePayload,
  createEmptyRuleDraft,
  parseCommaSeparatedInput,
  validateRuleDraft,
} from "./rule-form-utils";
import {
  DEFAULT_RULE_DICTIONARIES,
  RULE_TYPES,
  SEVERITY_LEVELS,
  type ComplianceRule,
  type ComplianceRuleCreate,
  type RuleDictionaries,
} from "@/extensions/knowledge-factory/types";

interface RuleCreatePanelProps {
  onClose: () => void;
  onCreated?: (rule: ComplianceRule) => void;
  dictionaries?: RuleDictionaries;
}

function FieldLabel({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
      {children}
    </label>
  );
}

export function RuleCreatePanel({
  onClose,
  onCreated,
  dictionaries = DEFAULT_RULE_DICTIONARIES,
}: RuleCreatePanelProps) {
  const selectContentClassName = "z-[1010]";
  const [draft, setDraft] = useState<ComplianceRuleCreate>(() => createEmptyRuleDraft(dictionaries));
  const [sourceSectionsInput, setSourceSectionsInput] = useState("");
  const [targetSectionsInput, setTargetSectionsInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validationPreview = useMemo(
    () =>
      buildRuleCreatePayload(draft, sourceSectionsInput, targetSectionsInput, dictionaries),
    [dictionaries, draft, sourceSectionsInput, targetSectionsInput],
  );

  const validationErrors = useMemo(
    () => validateRuleDraft(validationPreview),
    [validationPreview],
  );

  const handleChange = <K extends keyof ComplianceRuleCreate>(
    key: K,
    value: ComplianceRuleCreate[K],
  ) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const handleReportTypeToggle = (value: string, checked: boolean) => {
    setDraft((prev) => ({
      ...prev,
      reportTypes: checked
        ? [...prev.reportTypes, value]
        : prev.reportTypes.filter((item) => item !== value),
    }));
  };

  const handleRegionToggle = (value: string, checked: boolean) => {
    setDraft((prev) => ({
      ...prev,
      applicableRegions: checked
        ? [...prev.applicableRegions, value]
        : prev.applicableRegions.filter((item) => item !== value),
    }));
  };

  const handleSubmit = async () => {
    const payload = buildRuleCreatePayload(
      draft,
      sourceSectionsInput,
      targetSectionsInput,
      dictionaries,
    );
    const errors = validateRuleDraft(payload);
    if (errors.length > 0) {
      setError(errors.at(0) ?? null);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const created = await createRule(payload);
      onCreated?.(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建规则失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    >
      <div
        className={cn(
          "flex max-h-[90vh] w-full max-w-[960px] flex-col overflow-hidden rounded-xl border bg-background shadow-lg",
        )}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="rule-create-title"
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b px-5 py-4">
          <div>
            <h2 id="rule-create-title" className="text-base font-semibold leading-tight text-foreground">
              新建规则
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              创建新的合规规则定义，创建后可继续编辑、测试和查看日志。
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon-sm" className="shrink-0" onClick={onClose}>
            <X className="size-4" />
            <span className="sr-only">关闭</span>
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="size-4" />
              <AlertDescription className="flex items-center justify-between gap-2">
                <span>{error}</span>
                <Button type="button" variant="ghost" size="sm" className="h-7 shrink-0 px-2" onClick={() => setError(null)}>
                  关闭
                </Button>
              </AlertDescription>
            </Alert>
          )}

          <section className="mb-5">
            <h3 className="mb-3 text-sm font-semibold text-foreground">基本信息</h3>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <FieldLabel htmlFor="rule-id">规则ID</FieldLabel>
                <Input
                  id="rule-id"
                  value={draft.ruleId}
                  onChange={(e) => handleChange("ruleId", e.target.value)}
                  placeholder="例如 CSR-100"
                />
              </div>

              <div className="space-y-1.5">
                <FieldLabel htmlFor="rule-name">规则名称</FieldLabel>
                <Input
                  id="rule-name"
                  value={draft.name}
                  onChange={(e) => handleChange("name", e.target.value)}
                  placeholder="输入规则名称"
                />
              </div>

              <div className="space-y-1.5">
                <FieldLabel>规则类型</FieldLabel>
                <Select
                  value={draft.type}
                  onValueChange={(value) => {
                    const item = RULE_TYPES.find((t) => t.value === value);
                    setDraft((prev) => ({
                      ...prev,
                      type: value,
                      typeName: item?.label ?? prev.typeName,
                    }));
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="选择规则类型" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    {RULE_TYPES.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <FieldLabel>严重级别</FieldLabel>
                <Select
                  value={draft.severity}
                  onValueChange={(value) => {
                    const item = SEVERITY_LEVELS.find((s) => s.value === value);
                    setDraft((prev) => ({
                      ...prev,
                      severity: value,
                      severityName: item?.label ?? prev.severityName,
                    }));
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="选择严重级别" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    {SEVERITY_LEVELS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="mt-4 space-y-1.5">
              <FieldLabel htmlFor="rule-desc">描述</FieldLabel>
              <Textarea
                id="rule-desc"
                value={draft.description ?? ""}
                onChange={(e) => handleChange("description", e.target.value)}
                rows={3}
                className="min-h-[5rem] resize-y"
                placeholder="规则说明（可选）"
              />
            </div>
          </section>

          <section className="mb-5">
            <h3 className="mb-3 text-sm font-semibold text-foreground">行业与适用范围</h3>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <FieldLabel>行业</FieldLabel>
                <Select
                  value={draft.industry}
                  onValueChange={(value) => {
                    const item = dictionaries.industries.find((i) => i.value === value);
                    setDraft((prev) => ({
                      ...prev,
                      industry: value,
                      industryName: item?.label ?? prev.industryName,
                    }));
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="选择行业" />
                  </SelectTrigger>
                  <SelectContent className={selectContentClassName}>
                    {dictionaries.industries.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <FieldLabel>适用范围</FieldLabel>
                <div className="flex h-9 items-center gap-2 rounded-lg border border-input bg-transparent px-3">
                <Checkbox
                  id="rule-national"
                  checked={draft.nationalLevel}
                  onChange={(e) => handleChange("nationalLevel", e.target.checked)}
                />
                  <label htmlFor="rule-national" className="cursor-pointer text-sm font-medium leading-none text-foreground">
                    全国规则
                  </label>
                </div>
              </div>
            </div>

            <div className="mt-4 space-y-1.5">
              <FieldLabel>适用报告类型</FieldLabel>
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {dictionaries.reportTypes.map((item) => {
                    const id = `report-type-${item.value}`;
                    return (
                      <div key={item.value} className="flex items-start gap-2.5">
                        <Checkbox
                          id={id}
                          checked={draft.reportTypes.includes(item.value)}
                          onChange={(e) =>
                            handleReportTypeToggle(item.value, e.target.checked)
                          }
                          className="mt-0.5"
                        />
                        <label
                          htmlFor={id}
                          className="cursor-pointer text-sm leading-snug text-foreground"
                        >
                          {item.label}
                        </label>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {!draft.nationalLevel && (
              <div className="mt-4 space-y-1.5">
                <FieldLabel>地方适用地区</FieldLabel>
                <div className="rounded-lg border border-border bg-muted/30 p-3">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {dictionaries.regions
                      .filter((item) => item.value !== "nationwide")
                      .map((item) => {
                        const id = `region-${item.value}`;
                        return (
                          <div key={item.value} className="flex items-start gap-2.5">
                            <Checkbox
                              id={id}
                              checked={draft.applicableRegions.includes(item.value)}
                              onChange={(checked) =>
                                handleRegionToggle(item.value, checked.target.checked)
                              }
                              className="mt-0.5"
                            />
                            <label
                              htmlFor={id}
                              className="cursor-pointer text-sm leading-snug text-foreground"
                            >
                              {item.label}
                            </label>
                          </div>
                        );
                      })}
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="mb-5">
            <h3 className="mb-3 text-sm font-semibold text-foreground">章节与提示</h3>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <FieldLabel htmlFor="source-sections">来源章节</FieldLabel>
                <Textarea
                  id="source-sections"
                  value={sourceSectionsInput}
                  onChange={(e) => setSourceSectionsInput(e.target.value)}
                  placeholder="用逗号或换行分隔，例如 sec_03_工程分析"
                  rows={4}
                  className="min-h-[7rem] resize-y font-mono text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <FieldLabel htmlFor="target-sections">目标章节</FieldLabel>
                <Textarea
                  id="target-sections"
                  value={targetSectionsInput}
                  onChange={(e) => setTargetSectionsInput(e.target.value)}
                  placeholder="用逗号或换行分隔，例如 sec_05_环境影响预测"
                  rows={4}
                  className="min-h-[7rem] resize-y font-mono text-sm"
                />
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <FieldLabel htmlFor="error-msg">错误提示</FieldLabel>
                <Textarea
                  id="error-msg"
                  value={draft.errorMessage ?? ""}
                  onChange={(e) => handleChange("errorMessage", e.target.value)}
                  rows={3}
                  className="min-h-[5rem] resize-y"
                />
              </div>

              <div className="space-y-1.5">
                <FieldLabel htmlFor="fix-suggestion">修复建议</FieldLabel>
                <Textarea
                  id="fix-suggestion"
                  value={draft.autoFixSuggestion ?? ""}
                  onChange={(e) => handleChange("autoFixSuggestion", e.target.value)}
                  rows={3}
                  className="min-h-[5rem] resize-y"
                />
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-border bg-muted/20 p-4">
            <h3 className="mb-3 text-sm font-semibold text-foreground">创建预览</h3>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <div className="text-xs text-muted-foreground">规则类型名称</div>
                <div className="mt-0.5 font-medium text-foreground">{validationPreview.typeName}</div>
              </div>
              <div className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <div className="text-xs text-muted-foreground">严重级别名称</div>
                <div className="mt-0.5 font-medium text-foreground">{validationPreview.severityName}</div>
              </div>
              <div className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <div className="text-xs text-muted-foreground">行业名称</div>
                <div className="mt-0.5 font-medium text-foreground">{validationPreview.industryName}</div>
              </div>
              <div className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <div className="text-xs text-muted-foreground">来源章节数量</div>
                <div className="mt-0.5 font-medium text-foreground">
                  {parseCommaSeparatedInput(sourceSectionsInput).length}
                </div>
              </div>
              <div className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <div className="text-xs text-muted-foreground">目标章节数量</div>
                <div className="mt-0.5 font-medium text-foreground">
                  {parseCommaSeparatedInput(targetSectionsInput).length}
                </div>
              </div>
            </div>
          </section>
        </div>

        <div className="flex shrink-0 justify-end gap-2 border-t bg-muted/30 px-5 py-4">
          <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={saving || validationErrors.length > 0}
            title={validationErrors[0] ?? undefined}
          >
            {saving ? "创建中..." : "创建规则"}
          </Button>
        </div>
      </div>
    </div>
  );
}
