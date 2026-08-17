"use client";

import {
  AlertTriangle,
  BookOpen,
  Globe,
  Info,
  MapPin,
  ShieldCheck,
  Target,
  Wrench,
  X,
} from "lucide-react";
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
import {
  deleteRule,
  updateRule,
} from "@/extensions/knowledge-factory/complianceRulesApi";
import {
  DEFAULT_RULE_DICTIONARIES,
  RULE_TYPES,
  SEVERITY_LEVELS,
  type ComplianceRule,
  type ValidationConfig,
  type RuleDictionaries,
} from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

import {
  buildRuleUpdatePayload,
  formatValidationConfig,
  getRegionLabel,
} from "./rule-detail-utils";

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
    setValidationConfigText(
      formatValidationConfig(
        rule.validationConfig as unknown as ValidationConfig,
      ) ?? "",
    );
    setIsEditing(false);
    setError(null);
  }, [rule]);

  const severityInfo = SEVERITY_LEVELS.find(
    (item) => item.value === editedRule.severity,
  );
  const severityColor = severityInfo?.color ?? "var(--muted-foreground)";
  const typeLabel =
    editedRule.typeName ??
    RULE_TYPES.find((item) => item.value === editedRule.type)?.label ??
    editedRule.type;
  const industryLabel =
    editedRule.industryName ??
    dictionaries.industries.find((item) => item.value === editedRule.industry)
      ?.label ??
    editedRule.industry;

  const reportTypeLabels = (editedRule.reportTypes ?? []).map((reportType) => {
    const found = dictionaries.reportTypes.find(
      (item) => item.value === reportType,
    );
    return found?.label ?? reportType;
  });

  const applicableRegionLabels = editedRule.nationalLevel
    ? ["全国"]
    : (editedRule.applicableRegions ?? []).map((region) =>
        getRegionLabel(region, dictionaries),
      );

  const handleChange = <K extends keyof ComplianceRule>(
    field: K,
    value: ComplianceRule[K],
  ) => {
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
      applicableRegions: checked
        ? ["nationwide"]
        : (prev.applicableRegions ?? []).filter(
            (region) => region !== "nationwide",
          ),
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

      if (
        !payload.nationalLevel &&
        (!payload.applicableRegions || payload.applicableRegions.length === 0)
      ) {
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
    setValidationConfigText(
      formatValidationConfig(
        rule.validationConfig as unknown as ValidationConfig,
      ) ?? "",
    );
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
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-6"
      onClick={onClose}
    >
      <div
        className="bg-background flex max-h-[90vh] w-full max-w-[1040px] flex-col overflow-hidden rounded-xl border shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="bg-card flex items-start justify-between gap-4 border-b px-6 py-4">
          <div className="min-w-0">
            <h2 className="text-foreground text-lg font-bold">
              {isEditing ? "编辑规则" : "规则详情"}
            </h2>
            <p className="text-muted-foreground mt-0.5 truncate text-sm">
              {rule.ruleId} · {rule.name}
            </p>
          </div>
          <button
            className="text-muted-foreground hover:bg-accent hover:text-foreground flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg transition-colors"
            onClick={onClose}
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Content ── */}
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {error && (
            <div className="bg-destructive/10 border-destructive/20 text-destructive flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-sm">
              <span className="inline-flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                {error}
              </span>
              <button
                onClick={() => setError(null)}
                className="shrink-0 hover:opacity-70"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Identity strip: compact attribute badges */}
          <div className="flex flex-wrap items-center gap-2 px-1">
            <span className="bg-muted text-foreground border-border/60 inline-flex items-center gap-1 rounded-md border px-2 py-1 font-mono text-sm font-medium">
              <Target className="text-muted-foreground h-3 w-3" />
              {rule.ruleId}
            </span>
            {isEditing ? (
              <Select
                value={editedRule.type}
                onValueChange={(value) => handleChange("type", value)}
              >
                <SelectTrigger className="border-primary/20 bg-primary/5 text-primary h-auto w-auto min-w-0 gap-1 px-2 py-1 text-sm">
                  <SelectValue />
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
              <span className="bg-primary/10 text-primary border-primary/20 inline-flex items-center rounded-md border px-2 py-1 text-sm font-medium">
                {typeLabel}
              </span>
            )}
            {isEditing ? (
              <Select
                value={editedRule.severity}
                onValueChange={(value) => handleChange("severity", value)}
              >
                <SelectTrigger
                  className="h-auto w-auto min-w-0 gap-1 border-transparent px-2 py-1 text-sm font-semibold"
                  style={{
                    color: severityColor,
                    backgroundColor: `${severityColor}1a`,
                  }}
                >
                  <SelectValue />
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
                className="inline-flex items-center rounded-md border py-1 pr-2.5 pl-2 text-sm font-semibold"
                style={{
                  color: severityColor,
                  borderColor: `${severityColor}40`,
                  backgroundColor: `${severityColor}14`,
                }}
              >
                {editedRule.severityName ?? severityInfo?.label}
              </span>
            )}
            {isEditing ? (
              <div className="flex items-center gap-1.5">
                <Checkbox
                  id="rule-detail-enabled-strip"
                  checked={editedRule.enabled}
                  onCheckedChange={(checked) =>
                    handleChange("enabled", checked === true)
                  }
                />
                <label
                  htmlFor="rule-detail-enabled-strip"
                  className="text-foreground cursor-pointer text-sm"
                >
                  启用
                </label>
              </div>
            ) : (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-sm font-medium",
                  editedRule.enabled
                    ? "bg-success/10 text-success border-success/20"
                    : "bg-muted text-muted-foreground border-border",
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 shrink-0 rounded-full",
                    editedRule.enabled ? "bg-success" : "bg-muted-foreground",
                  )}
                />
                {editedRule.enabled ? "已启用" : "已禁用"}
              </span>
            )}
          </div>

          {/* 3-column main grid */}
          <div className="grid grid-cols-3 gap-4">
            {/* Col 1: 基本信息 + 适用范围 */}
            <div className="space-y-4">
              <section className="bg-card rounded-xl border p-4">
                <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <Info className="text-muted-foreground h-3.5 w-3.5" />
                  基本信息
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      规则名称
                    </label>
                    {isEditing ? (
                      <Input
                        type="text"
                        value={editedRule.name}
                        onChange={(event) =>
                          handleChange("name", event.target.value)
                        }
                        className="h-8 text-sm"
                      />
                    ) : (
                      <span className="bg-muted text-foreground border-border/60 inline-flex items-center rounded-md border px-2.5 py-1 text-sm font-medium">
                        {rule.name}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      行业
                    </label>
                    {isEditing ? (
                      <Select
                        value={editedRule.industry}
                        onValueChange={(value) =>
                          handleChange("industry", value)
                        }
                      >
                        <SelectTrigger className="h-8 text-sm">
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
                      <span className="bg-muted text-foreground border-border/60 inline-flex items-center rounded-md border px-2.5 py-1 text-sm font-medium">
                        {industryLabel}
                      </span>
                    )}
                  </div>
                </div>
              </section>

              <section className="bg-card rounded-xl border p-4">
                <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <Globe className="text-muted-foreground h-3.5 w-3.5" />
                  适用范围
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      报告类型
                    </label>
                    {isEditing ? (
                      <div className="bg-muted/50 grid grid-cols-2 gap-2 rounded-lg border p-2.5">
                        {dictionaries.reportTypes.map((item) => {
                          const id = `rule-detail-report-${item.value}`;
                          return (
                            <div
                              key={item.value}
                              className="flex items-start gap-1.5"
                            >
                              <Checkbox
                                id={id}
                                className="mt-0.5 shrink-0"
                                checked={(
                                  editedRule.reportTypes ?? []
                                ).includes(item.value)}
                                onCheckedChange={(checked) =>
                                  handleReportTypeToggle(
                                    item.value,
                                    checked === true,
                                  )
                                }
                              />
                              <label
                                htmlFor={id}
                                className="cursor-pointer text-sm leading-tight"
                              >
                                {item.label}
                              </label>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {reportTypeLabels.map((label) => (
                          <span
                            key={label}
                            className="bg-primary/5 text-primary border-primary/20 inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium"
                          >
                            {label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      地区
                    </label>
                    {isEditing ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-1.5">
                          <Checkbox
                            id="rule-detail-national"
                            checked={editedRule.nationalLevel}
                            onCheckedChange={(checked) =>
                              handleNationalLevelChange(checked === true)
                            }
                          />
                          <label
                            htmlFor="rule-detail-national"
                            className="text-foreground cursor-pointer text-sm"
                          >
                            全国规则
                          </label>
                        </div>
                        <div
                          className={cn(
                            "bg-muted/50 grid grid-cols-2 gap-2 rounded-lg border p-2.5",
                            editedRule.nationalLevel &&
                              "pointer-events-none opacity-50",
                          )}
                        >
                          {dictionaries.regions
                            .filter((item) => item.value !== "nationwide")
                            .map((item) => {
                              const id = `rule-detail-region-${item.value}`;
                              return (
                                <div
                                  key={item.value}
                                  className="flex items-start gap-1.5"
                                >
                                  <Checkbox
                                    id={id}
                                    className="mt-0.5 shrink-0"
                                    checked={(
                                      editedRule.applicableRegions ?? []
                                    ).includes(item.value)}
                                    disabled={editedRule.nationalLevel}
                                    onCheckedChange={(checked) =>
                                      handleRegionToggle(
                                        item.value,
                                        checked === true,
                                      )
                                    }
                                  />
                                  <label
                                    htmlFor={id}
                                    className={cn(
                                      "cursor-pointer text-sm leading-tight",
                                      editedRule.nationalLevel &&
                                        "cursor-not-allowed opacity-60",
                                    )}
                                  >
                                    {item.label}
                                  </label>
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {applicableRegionLabels.map((label) => (
                          <span
                            key={label}
                            className="bg-success/10 text-success border-success/20 inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium"
                          >
                            {label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </div>

            {/* Col 2: 规则描述 + 章节映射 */}
            <div className="space-y-4">
              <section className="bg-card rounded-xl border p-4">
                <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <BookOpen className="text-muted-foreground h-3.5 w-3.5" />
                  规则描述
                </h3>
                {isEditing ? (
                  <Textarea
                    value={editedRule.description ?? ""}
                    onChange={(event) =>
                      handleChange("description", event.target.value)
                    }
                    rows={3}
                    className="text-sm"
                    placeholder="规则说明（可选）"
                  />
                ) : (
                  <div className="bg-muted/50 border-border/60 rounded-lg border p-2.5">
                    <p className="text-foreground m-0 text-sm leading-relaxed break-words whitespace-pre-wrap">
                      {editedRule.description ?? "无描述"}
                    </p>
                  </div>
                )}
              </section>

              <section className="bg-card rounded-xl border p-4">
                <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <MapPin className="text-muted-foreground h-3.5 w-3.5" />
                  章节映射
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      来源章节
                    </label>
                    {isEditing ? (
                      <Textarea
                        value={sourceSectionsInput}
                        onChange={(event) =>
                          setSourceSectionsInput(event.target.value)
                        }
                        rows={2}
                        className="text-sm"
                        placeholder="多个章节用逗号或换行分隔"
                      />
                    ) : (
                      <div className="bg-muted/50 border-border/60 rounded-lg border p-2">
                        <p className="text-foreground m-0 text-sm leading-relaxed break-words whitespace-pre-wrap">
                          {(rule.sourceSections?.length ?? 0) > 0
                            ? (rule.sourceSections ?? []).join("、")
                            : "—"}
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      目标章节
                    </label>
                    {isEditing ? (
                      <Textarea
                        value={targetSectionsInput}
                        onChange={(event) =>
                          setTargetSectionsInput(event.target.value)
                        }
                        rows={2}
                        className="text-sm"
                        placeholder="多个章节用逗号或换行分隔"
                      />
                    ) : (
                      <div className="bg-muted/50 border-border/60 rounded-lg border p-2">
                        <p className="text-foreground m-0 text-sm leading-relaxed break-words whitespace-pre-wrap">
                          {(rule.targetSections?.length ?? 0) > 0
                            ? (rule.targetSections ?? []).join("、")
                            : "—"}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </div>

            {/* Col 3: 错误与修复 + 元信息 */}
            <div className="space-y-4">
              <section className="bg-card rounded-xl border p-4">
                <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <Wrench className="text-muted-foreground h-3.5 w-3.5" />
                  错误与修复
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      错误提示
                    </label>
                    {isEditing ? (
                      <Textarea
                        value={editedRule.errorMessage ?? ""}
                        onChange={(event) =>
                          handleChange("errorMessage", event.target.value)
                        }
                        rows={2}
                        className="text-sm"
                      />
                    ) : (
                      <div className="bg-destructive/8 border-destructive/15 border-l-destructive/50 rounded-lg border border-l-2 p-2.5">
                        <p className="text-foreground m-0 text-sm leading-relaxed break-words whitespace-pre-wrap">
                          {editedRule.errorMessage ?? "—"}
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-muted-foreground text-sm font-medium">
                      修复建议
                    </label>
                    {isEditing ? (
                      <Textarea
                        value={editedRule.autoFixSuggestion ?? ""}
                        onChange={(event) =>
                          handleChange("autoFixSuggestion", event.target.value)
                        }
                        rows={2}
                        className="text-sm"
                      />
                    ) : (
                      <div className="bg-success/8 border-success/15 border-l-success/50 rounded-lg border border-l-2 p-2.5">
                        <p className="text-foreground m-0 text-sm leading-relaxed break-words whitespace-pre-wrap">
                          {editedRule.autoFixSuggestion ?? "—"}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </section>

              <section className="bg-card rounded-xl border p-4">
                <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
                  <Info className="text-muted-foreground h-3.5 w-3.5" />
                  元信息
                </h3>
                <div className="space-y-2">
                  {rule.seedVersion && (
                    <div className="flex items-center justify-between py-1">
                      <span className="text-muted-foreground text-sm">
                        种子版本
                      </span>
                      <span className="text-foreground font-mono text-sm font-medium">
                        {rule.seedVersion}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between py-1">
                    <span className="text-muted-foreground text-sm">
                      创建时间
                    </span>
                    <span className="text-foreground text-sm tabular-nums">
                      {new Date(rule.createdAt ?? new Date()).toLocaleString()}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1">
                    <span className="text-muted-foreground text-sm">
                      更新时间
                    </span>
                    <span className="text-foreground text-sm tabular-nums">
                      {new Date(rule.updatedAt ?? new Date()).toLocaleString()}
                    </span>
                  </div>
                </div>
              </section>
            </div>
          </div>

          {/* Full-width: 验证配置 */}
          <section className="bg-card rounded-xl border p-4">
            <h3 className="text-foreground mb-3 flex items-center gap-1.5 text-sm font-semibold">
              <ShieldCheck className="text-muted-foreground h-3.5 w-3.5" />
              验证配置
            </h3>
            {isEditing ? (
              <div className="flex flex-col gap-1.5">
                <label className="text-muted-foreground text-sm font-medium">
                  Validation Config JSON
                </label>
                <Textarea
                  className="min-h-[280px] font-mono text-sm"
                  value={validationConfigText}
                  onChange={(event) =>
                    setValidationConfigText(event.target.value)
                  }
                  rows={14}
                  spellCheck={false}
                />
              </div>
            ) : (rule.validationConfig?.fields?.length ?? 0) > 0 ? (
              <div className="-mx-1 overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="bg-muted/50 border-b">
                      <th className="text-foreground px-3 py-2.5 text-left font-semibold">
                        字段名称
                      </th>
                      <th className="text-foreground px-3 py-2.5 text-left font-semibold">
                        阈值
                      </th>
                      <th className="text-foreground px-3 py-2.5 text-left font-semibold">
                        单位
                      </th>
                      <th className="text-foreground px-3 py-2.5 text-left font-semibold">
                        标准
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      rule.validationConfig?.fields as
                        | {
                            fieldName: string;
                            limit?: number;
                            min?: number;
                            max?: number;
                            unit?: string;
                            standard?: string;
                          }[]
                        | undefined
                    )?.map((field, index) => (
                      <tr
                        key={`${field.fieldName}-${index}`}
                        className="border-border/40 hover:bg-muted/30 border-b transition-colors"
                      >
                        <td className="text-foreground px-3 py-2 font-medium">
                          {field.fieldName}
                        </td>
                        <td className="text-muted-foreground px-3 py-2 tabular-nums">
                          {field.limit !== undefined
                            ? `≤ ${field.limit}`
                            : field.min !== undefined && field.max !== undefined
                              ? `${field.min} – ${field.max}`
                              : field.min !== undefined
                                ? `≥ ${field.min}`
                                : "—"}
                        </td>
                        <td className="text-muted-foreground px-3 py-2">
                          {field.unit ?? "—"}
                        </td>
                        <td className="text-muted-foreground px-3 py-2">
                          {field.standard ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="bg-muted/50 border-border/60 rounded-lg border p-3 text-center">
                <p className="text-muted-foreground m-0 text-sm">
                  无验证字段配置
                </p>
              </div>
            )}
          </section>
        </div>

        {/* ── Footer ── */}
        <div className="bg-muted/50 flex items-center justify-between gap-3 border-t px-5 py-3.5">
          <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
            <ShieldCheck className="h-3 w-3" />
            <span className="font-mono">{rule.ruleId}</span>
          </div>
          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCancel}
                  disabled={saving}
                >
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={() => void handleSave()}
                  disabled={saving}
                >
                  {saving ? "保存中..." : "保存"}
                </Button>
              </>
            ) : (
              <>
                {onViewLogs && (
                  <Button variant="outline" size="sm" onClick={onViewLogs}>
                    查看日志
                  </Button>
                )}
                {onTestRule && (
                  <Button
                    size="sm"
                    className="bg-primary hover:bg-primary/90 text-white"
                    onClick={onTestRule}
                  >
                    测试规则
                  </Button>
                )}
                {!readOnly && onDelete && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => void handleDelete()}
                    disabled={deleting}
                  >
                    {deleting ? "删除中..." : "删除"}
                  </Button>
                )}
                {!readOnly && (
                  <Button size="sm" onClick={() => setIsEditing(true)}>
                    编辑
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
