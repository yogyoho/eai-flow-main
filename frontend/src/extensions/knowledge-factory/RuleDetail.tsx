"use client";

import React, { useEffect, useState } from "react";

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

import { deleteRule, updateRule } from "@/extensions/knowledge-factory/complianceRulesApi";
import {
  buildRuleUpdatePayload,
  formatValidationConfig,
  getRegionLabel,
} from "./rule-detail-utils";
import {
  DEFAULT_RULE_DICTIONARIES,
  RULE_TYPES,
  SEVERITY_LEVELS,
  type ComplianceRule,
  type ValidationConfig,
  type RuleDictionaries,
} from "@/extensions/knowledge-factory/types";

interface RuleDetailProps {
  rule: ComplianceRule;
  onClose: () => void;
  onUpdate?: () => void;
  onDelete?: (ruleId: string) => void;
  onTestRule?: () => void;
  onViewLogs?: () => void;
  readOnly?: boolean;
  dictionaries?: RuleDictionaries;
}

export function RuleDetail({
  rule,
  onClose,
  onUpdate,
  onDelete,
  onTestRule,
  onViewLogs,
  readOnly = false,
  dictionaries = DEFAULT_RULE_DICTIONARIES,
}: RuleDetailProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedRule, setEditedRule] = useState(rule);
  const [sourceSectionsInput, setSourceSectionsInput] = useState("");
  const [targetSectionsInput, setTargetSectionsInput] = useState("");
  const [validationConfigText, setValidationConfigText] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectContentClassName = "z-[1010]";

  useEffect(() => {
    setEditedRule(rule);
    setSourceSectionsInput((rule.sourceSections ?? []).join(", "));
    setTargetSectionsInput((rule.targetSections ?? []).join(", "));
    setValidationConfigText(formatValidationConfig(rule.validationConfig as unknown as ValidationConfig) ?? "");
    setIsEditing(false);
    setError(null);
  }, [rule]);

  const severityInfo = SEVERITY_LEVELS.find((item) => item.value === editedRule.severity);
  const severityColor = severityInfo?.color ?? "#6b7280";
  const typeLabel =
    editedRule.typeName ?? RULE_TYPES.find((item) => item.value === editedRule.type)?.label ?? editedRule.type;
  const industryLabel =
    editedRule.industryName ??
    dictionaries.industries.find((item) => item.value === editedRule.industry)?.label ??
    editedRule.industry;

  const reportTypeLabels = (editedRule.reportTypes ?? []).map((reportType) => {
    const found = dictionaries.reportTypes.find((item) => item.value === reportType);
    return found?.label ?? reportType;
  });

  const applicableRegionLabels = editedRule.nationalLevel
    ? ["全国"]
    : (editedRule.applicableRegions ?? []).map((region) => getRegionLabel(region, dictionaries));

  const handleChange = <K extends keyof ComplianceRule>(field: K, value: ComplianceRule[K]) => {
    setEditedRule((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleReportTypeToggle = (reportType: string, checked: boolean) => {
    setEditedRule((prev) => ({
      ...prev,
      reportTypes: checked
        ? [...(prev.reportTypes ?? []), reportType]
        : (prev.reportTypes ?? []).filter((value) => value !== reportType),
    }));
  };

  const handleRegionToggle = (region: string, checked: boolean) => {
    setEditedRule((prev) => ({
      ...prev,
      applicableRegions: checked
        ? [...(prev.applicableRegions ?? []), region]
        : (prev.applicableRegions ?? []).filter((value) => value !== region),
    }));
  };

  const handleNationalLevelChange = (checked: boolean) => {
    setEditedRule((prev) => ({
      ...prev,
      nationalLevel: checked,
      applicableRegions: checked ? ["nationwide"] : (prev.applicableRegions ?? []).filter((region) => region !== "nationwide"),
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      const payload = buildRuleUpdatePayload({
        rule: editedRule,
        sourceSectionsInput,
        targetSectionsInput,
        validationConfigText,
        dictionaries,
      });

      if (payload.reportTypes?.length === 0) {
        throw new Error("至少需要选择一个适用报告类型");
      }

      if (!payload.nationalLevel && (!payload.applicableRegions || payload.applicableRegions.length === 0)) {
        throw new Error("地方规则至少需要选择一个适用地区");
      }

      if (!rule.ruleId) {
        throw new Error("规则ID不存在");
      }
      await updateRule(rule.ruleId, payload);
      setIsEditing(false);
      onUpdate?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditedRule(rule);
    setSourceSectionsInput((rule.sourceSections ?? []).join(", "));
    setTargetSectionsInput((rule.targetSections ?? []).join(", "));
    setValidationConfigText(formatValidationConfig(rule.validationConfig as unknown as ValidationConfig) ?? "");
    setIsEditing(false);
    setError(null);
  };

  const handleDelete = async () => {
    if (!onDelete) {
      return;
    }

    if (!window.confirm(`确定要删除规则 "${rule.name}" 吗？此操作不可撤销。`)) {
      return;
    }

    setDeleting(true);
    setError(null);
    try {
      if (!rule.ruleId) {
        throw new Error("规则ID不存在");
      }
      await deleteRule(rule.ruleId);
      onDelete(rule.ruleId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 flex items-center justify-center p-6 bg-slate-900/45 z-[1000]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[1040px] max-h-[90vh] flex flex-col bg-background rounded-xl border shadow-xl overflow-hidden"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex justify-between items-start gap-4 px-6 py-5 border-b">
          <div>
            <h2 className="text-xl font-bold text-foreground m-0">
              {isEditing ? "编辑规则" : "规则详情"}
            </h2>
            <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
              {rule.ruleId} · {rule.name}
            </p>
          </div>
          <button
            className="w-8 h-8 flex items-center justify-center bg-transparent border-none rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground transition-colors text-2xl leading-none cursor-pointer"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <div className="flex items-center justify-between gap-3 p-3 rounded-lg bg-destructive/10 text-destructive mb-4">
              {error}
              <button onClick={() => setError(null)}>×</button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <section className="p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">基本信息</h3>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">规则 ID</label>
                <span className="inline-flex items-center max-w-full px-3 py-1.5 rounded-md font-medium font-mono bg-muted text-foreground border border-border">
                  {rule.ruleId}
                </span>
              </div>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">规则名称</label>
                {isEditing ? (
                  <Input
                    type="text"
                    value={editedRule.name}
                    onChange={(event) => handleChange("name", event.target.value)}
                  />
                ) : (
                  <span className="text-sm text-foreground font-semibold">{rule.name}</span>
                )}
              </div>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">规则类型</label>
                {isEditing ? (
                  <Select value={editedRule.type} onValueChange={(value) => handleChange("type", value)}>
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
                ) : (
                  <span className="inline-flex items-center max-w-full px-3 py-1.5 rounded-full font-medium bg-blue-50 text-blue-700 border border-blue-200">
                    {typeLabel}
                  </span>
                )}
              </div>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">严重级别</label>
                {isEditing ? (
                  <Select
                    value={editedRule.severity}
                    onValueChange={(value) => handleChange("severity", value as ComplianceRule["severity"])}
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
                ) : (
                  <span
                    className="inline-flex items-center max-w-full pl-3 rounded-md font-semibold border"
                    style={{
                      color: severityColor,
                      borderColor: `${severityColor}47`,
                      backgroundColor: `${severityColor}1a`,
                      boxShadow: `inset 3px 0 0 0 ${severityColor}`,
                    }}
                  >
                    {editedRule.severityName ?? severityInfo?.label}
                  </span>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-muted-foreground">启用状态</label>
                {isEditing ? (
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="rule-detail-enabled"
                      checked={editedRule.enabled}
                      onCheckedChange={(checked) => handleChange("enabled", checked === true)}
                    />
                    <label htmlFor="rule-detail-enabled" className="text-sm text-foreground cursor-pointer">
                      启用
                    </label>
                  </div>
                ) : (
                  <span
                    className={cn(
                      "inline-flex items-center max-w-full px-3 py-1.5 rounded-full font-medium before:content-[''] before:w-2 before:h-2 before:rounded-full before:shrink-0",
                      editedRule.enabled
                        ? "bg-success/10 text-success border border-success/20 before:bg-success before:shadow-[0_0_0_2px_rgba(16,185,129,0.25)]"
                        : "bg-muted text-muted-foreground border border-border before:bg-muted-foreground"
                    )}
                  >
                    {editedRule.enabled ? "已启用" : "已禁用"}
                  </span>
                )}
              </div>
            </section>

            <section className="p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">行业与适用范围</h3>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">行业</label>
                {isEditing ? (
                  <Select value={editedRule.industry} onValueChange={(value) => handleChange("industry", value)}>
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
                ) : (
                  <span className="text-sm text-muted-foreground">{industryLabel}</span>
                )}
              </div>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">适用报告类型</label>
                {isEditing ? (
                  <div className="grid grid-cols-2 gap-3 p-3 border rounded-lg bg-muted">
                    {dictionaries.reportTypes.map((item) => {
                      const id = `rule-detail-report-${item.value}`;
                      return (
                        <div key={item.value} className="flex items-start gap-2 text-sm text-foreground">
                          <Checkbox
                            id={id}
                            className="mt-0.5 shrink-0"
                            checked={(editedRule.reportTypes ?? []).includes(item.value)}
                            onCheckedChange={(checked) => handleReportTypeToggle(item.value, checked === true)}
                          />
                          <label htmlFor={id} className="cursor-pointer leading-tight">{item.label}</label>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {reportTypeLabels.map((label) => (
                      <span
                        key={label}
                        className="inline-flex items-center max-w-full px-3 py-1.5 rounded-md font-medium bg-background text-primary border border-primary/30"
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-muted-foreground">适用范围</label>
                {isEditing ? (
                  <>
                    <div className="flex items-center gap-2 mb-2.5">
                      <Checkbox
                        id="rule-detail-national"
                        checked={editedRule.nationalLevel}
                        onCheckedChange={(checked) => handleNationalLevelChange(checked === true)}
                      />
                      <label htmlFor="rule-detail-national" className="text-sm text-foreground cursor-pointer">
                        全国规则
                      </label>
                    </div>
                    <div
                      className={cn(
                        "grid grid-cols-2 gap-3 p-3 border rounded-lg bg-muted",
                        editedRule.nationalLevel && "opacity-55"
                      )}
                    >
                      {dictionaries.regions
                        .filter((item) => item.value !== "nationwide")
                        .map((item) => {
                          const id = `rule-detail-region-${item.value}`;
                          return (
                            <div key={item.value} className="flex items-start gap-2 text-sm text-foreground">
                              <Checkbox
                                id={id}
                                className="mt-0.5 shrink-0"
                                checked={(editedRule.applicableRegions ?? []).includes(item.value)}
                                disabled={editedRule.nationalLevel}
                                onCheckedChange={(checked) => handleRegionToggle(item.value, checked === true)}
                              />
                              <label
                                htmlFor={id}
                                className={cn(
                                  "leading-tight cursor-pointer",
                                  editedRule.nationalLevel && "cursor-not-allowed opacity-60"
                                )}
                              >
                                {item.label}
                              </label>
                            </div>
                          );
                        })}
                    </div>
                  </>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {applicableRegionLabels.map((label) => (
                      <span
                        key={label}
                        className="inline-flex items-center max-w-full px-3 py-1.5 rounded-md font-medium bg-success/10 text-success border border-success/20"
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </section>

            <section className="col-span-2 p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">规则描述</h3>
              {isEditing ? (
                <div className="flex flex-col gap-2">
                  <Textarea
                    value={editedRule.description ?? ""}
                    onChange={(event) => handleChange("description", event.target.value)}
                    rows={3}
                    placeholder="规则说明（可选）"
                  />
                </div>
              ) : (
                <div className="p-3 rounded-lg bg-muted border">
                  <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">
                    {editedRule.description ?? "无描述"}
                  </p>
                </div>
              )}
            </section>

            <section className="p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">章节映射</h3>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">来源章节</label>
                {isEditing ? (
                  <Textarea
                    value={sourceSectionsInput}
                    onChange={(event) => setSourceSectionsInput(event.target.value)}
                    rows={3}
                    placeholder="多个章节用逗号或换行分隔"
                  />
                ) : (
                  <div className="p-2.5 rounded-lg bg-muted border">
                    <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">
                      {(rule.sourceSections?.length ?? 0) > 0 ? (rule.sourceSections ?? []).join("、") : "无"}
                    </p>
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-muted-foreground">目标章节</label>
                {isEditing ? (
                  <Textarea
                    value={targetSectionsInput}
                    onChange={(event) => setTargetSectionsInput(event.target.value)}
                    rows={3}
                    placeholder="多个章节用逗号或换行分隔"
                  />
                ) : (
                  <div className="p-2.5 rounded-lg bg-muted border">
                    <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">
                      {(rule.targetSections?.length ?? 0) > 0 ? (rule.targetSections ?? []).join("、") : "无"}
                    </p>
                  </div>
                )}
              </div>
            </section>

            <section className="p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">错误与修复</h3>

              <div className="flex flex-col gap-2 mb-4">
                <label className="text-sm font-medium text-muted-foreground">错误提示</label>
                {isEditing ? (
                  <Textarea
                    value={editedRule.errorMessage ?? ""}
                    onChange={(event) => handleChange("errorMessage", event.target.value)}
                    rows={2}
                  />
                ) : (
                  <div
                    className="p-2.5 rounded-lg border"
                    style={{
                      backgroundColor: "#fef2f2",
                      borderColor: "#fecaca",
                      boxShadow: "inset 3px 0 0 0 #ef4444",
                    }}
                  >
                    <p className="text-sm text-red-800 leading-relaxed whitespace-pre-wrap break-words m-0">
                      {editedRule.errorMessage ?? "无"}
                    </p>
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium text-muted-foreground">修复建议</label>
                {isEditing ? (
                  <Textarea
                    value={editedRule.autoFixSuggestion ?? ""}
                    onChange={(event) => handleChange("autoFixSuggestion", event.target.value)}
                    rows={2}
                  />
                ) : (
                  <div
                    className="p-2.5 rounded-lg border"
                    style={{
                      backgroundColor: "#f0fdf4",
                      borderColor: "#bbf7d0",
                      boxShadow: "inset 3px 0 0 0 #22c55e",
                    }}
                  >
                    <p className="text-sm text-green-800 leading-relaxed whitespace-pre-wrap break-words m-0">
                      {editedRule.autoFixSuggestion ?? "无"}
                    </p>
                  </div>
                )}
              </div>
            </section>

            <section className="col-span-2 p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">验证配置</h3>

              {isEditing ? (
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium text-muted-foreground">Validation Config JSON</label>
                  <Textarea
                    className="min-h-[320px] font-mono text-sm"
                    value={validationConfigText}
                    onChange={(event) => setValidationConfigText(event.target.value)}
                    rows={16}
                    spellCheck={false}
                  />
                </div>
              ) : (rule.validationConfig?.fields?.length ?? 0) > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr>
                        <th className="p-3 text-left border-b bg-muted text-foreground font-semibold">字段名称</th>
                        <th className="p-3 text-left border-b bg-muted text-foreground font-semibold">阈值</th>
                        <th className="p-3 text-left border-b bg-muted text-foreground font-semibold">单位</th>
                        <th className="p-3 text-left border-b bg-muted text-foreground font-semibold">标准</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(rule.validationConfig?.fields as { fieldName: string; limit?: number; min?: number; max?: number; unit?: string; standard?: string }[] | undefined)?.map((field, index) => (
                        <tr key={`${field.fieldName}-${index}`}>
                          <td className="p-3 text-left border-b text-muted-foreground">{field.fieldName}</td>
                          <td className="p-3 text-left border-b text-muted-foreground">
                            {field.limit !== undefined
                              ? `≤ ${field.limit}`
                              : field.min !== undefined && field.max !== undefined
                                ? `${field.min} - ${field.max}`
                                : field.min !== undefined
                                  ? `≥ ${field.min}`
                                  : "-"}
                          </td>
                          <td className="p-3 text-left border-b text-muted-foreground">{field.unit ?? "-"}</td>
                          <td className="p-3 text-left border-b text-muted-foreground">{field.standard ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-2.5 rounded-lg bg-muted border">
                  <p className="text-sm text-muted-foreground leading-relaxed m-0">无验证字段配置</p>
                </div>
              )}
            </section>

            <section className="p-4 border rounded-xl bg-background">
              <h3 className="text-sm font-semibold text-foreground mb-3">元信息</h3>
              <div className="grid gap-3">
                {rule.seedVersion && (
                  <div className="grid grid-cols-[100px_1fr] gap-3 items-start">
                    <span className="text-sm font-medium text-muted-foreground">种子版本</span>
                    <span className="text-sm text-foreground font-mono">{rule.seedVersion}</span>
                  </div>
                )}
                <div className="grid grid-cols-[100px_1fr] gap-3 items-start">
                  <span className="text-sm font-medium text-muted-foreground">创建时间</span>
                  <span className="text-sm text-foreground leading-relaxed break-words">
                    {new Date(rule.createdAt ?? new Date()).toLocaleString()}
                  </span>
                </div>
                <div className="grid grid-cols-[100px_1fr] gap-3 items-start">
                  <span className="text-sm font-medium text-muted-foreground">更新时间</span>
                  <span className="text-sm text-foreground leading-relaxed break-words">
                    {new Date(rule.updatedAt ?? new Date()).toLocaleString()}
                  </span>
                </div>
              </div>
            </section>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-6 py-5 border-t bg-muted">
          {isEditing ? (
            <>
              <Button variant="outline" onClick={handleCancel} disabled={saving}>
                取消
              </Button>
              <Button onClick={() => void handleSave()} disabled={saving}>
                {saving ? "保存中..." : "保存"}
              </Button>
            </>
          ) : (
            <>
              {onViewLogs && (
                <Button variant="outline" onClick={onViewLogs}>
                  查看日志
                </Button>
              )}
              {onTestRule && (
                <Button
                  className="bg-violet-600 hover:bg-violet-700 text-white"
                  onClick={onTestRule}
                >
                  测试规则
                </Button>
              )}
              {!readOnly && onDelete && (
                <Button
                  variant="destructive"
                  onClick={() => void handleDelete()}
                  disabled={deleting}
                >
                  {deleting ? "删除中..." : "删除"}
                </Button>
              )}
              {!readOnly && (
                <Button onClick={() => setIsEditing(true)}>
                  编辑
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
