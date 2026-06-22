"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, BookOpen, Globe, Info, MapPin, ShieldCheck, Target, Wrench, X } from "lucide-react";

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
import { deleteRule, updateRule } from "@/extensions/knowledge-factory/complianceRulesApi";
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
    setValidationConfigText(formatValidationConfig(rule.validationConfig as unknown as ValidationConfig) ?? "");
    setIsEditing(false);
    setError(null);
  }, [rule]);

  const severityInfo = SEVERITY_LEVELS.find((item) => item.value === editedRule.severity);
  const severityColor = severityInfo?.color ?? "var(--muted-foreground)";
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
      className="fixed inset-0 flex items-center justify-center p-6 bg-black/50 z-[1000]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[1040px] max-h-[90vh] flex flex-col bg-background rounded-xl border shadow-xl overflow-hidden"
        onClick={(event) => event.stopPropagation()}
      >
        {/* ── Header ── */}
        <div className="flex justify-between items-start gap-4 px-6 py-4 border-b bg-card">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? "编辑规则" : "规则详情"}
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground truncate">
              {rule.ruleId} · {rule.name}
            </p>
          </div>
          <button
            className="w-8 h-8 flex shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
            onClick={onClose}
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Content ── */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {error && (
            <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              <span className="inline-flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                {error}
              </span>
              <button onClick={() => setError(null)} className="shrink-0 hover:opacity-70">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Identity strip: compact attribute badges */}
          <div className="flex flex-wrap items-center gap-2 px-1">
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-sm font-mono font-medium bg-muted text-foreground border border-border/60">
              <Target className="h-3 w-3 text-muted-foreground" />
              {rule.ruleId}
            </span>
            {isEditing ? (
              <Select value={editedRule.type} onValueChange={(value) => handleChange("type", value)}>
                <SelectTrigger className="h-auto py-1 px-2 text-sm gap-1 w-auto min-w-0 border-primary/20 bg-primary/5 text-primary">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className={selectContentClassName}>
                  {RULE_TYPES.map((item) => (<SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>))}
                </SelectContent>
              </Select>
            ) : (
              <span className="inline-flex items-center px-2 py-1 rounded-md text-sm font-medium bg-primary/10 text-primary border border-primary/20">
                {typeLabel}
              </span>
            )}
            {isEditing ? (
              <Select value={editedRule.severity} onValueChange={(value) => handleChange("severity", value)}>
                <SelectTrigger className="h-auto py-1 px-2 text-sm gap-1 w-auto min-w-0 border-transparent font-semibold" style={{color: severityColor, backgroundColor: `${severityColor}1a`}}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className={selectContentClassName}>
                  {SEVERITY_LEVELS.map((item) => (<SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>))}
                </SelectContent>
              </Select>
            ) : (
              <span
                className="inline-flex items-center pl-2 pr-2.5 py-1 rounded-md text-sm font-semibold border"
                style={{color: severityColor, borderColor: `${severityColor}40`, backgroundColor: `${severityColor}14`}}
              >
                {editedRule.severityName ?? severityInfo?.label}
              </span>
            )}
            {isEditing ? (
              <div className="flex items-center gap-1.5">
                <Checkbox id="rule-detail-enabled-strip" checked={editedRule.enabled} onCheckedChange={(checked) => handleChange("enabled", checked === true)} />
                <label htmlFor="rule-detail-enabled-strip" className="text-sm text-foreground cursor-pointer">启用</label>
              </div>
            ) : (
              <span className={cn(
                "inline-flex items-center gap-1 px-2 py-1 rounded-md text-sm font-medium border",
                editedRule.enabled ? "bg-success/10 text-success border-success/20" : "bg-muted text-muted-foreground border-border"
              )}>
                <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", editedRule.enabled ? "bg-success" : "bg-muted-foreground")} />
                {editedRule.enabled ? "已启用" : "已禁用"}
              </span>
            )}
          </div>

          {/* 3-column main grid */}
          <div className="grid grid-cols-3 gap-4">
            {/* Col 1: 基本信息 + 适用范围 */}
            <div className="space-y-4">
              <section className="p-4 border rounded-xl bg-card">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
                  <Info className="h-3.5 w-3.5 text-muted-foreground" />
                  基本信息
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">规则名称</label>
                    {isEditing ? (
                      <Input type="text" value={editedRule.name} onChange={(event) => handleChange("name", event.target.value)} className="h-8 text-sm" />
                    ) : (
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-sm font-medium bg-muted text-foreground border border-border/60">{rule.name}</span>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">行业</label>
                    {isEditing ? (
                      <Select value={editedRule.industry} onValueChange={(value) => handleChange("industry", value)}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="选择行业" /></SelectTrigger>
                        <SelectContent className={selectContentClassName}>
                          {dictionaries.industries.map((item) => (<SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-sm font-medium bg-muted text-foreground border border-border/60">{industryLabel}</span>
                    )}
                  </div>
                </div>
              </section>

              <section className="p-4 border rounded-xl bg-card">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
                  <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                  适用范围
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">报告类型</label>
                    {isEditing ? (
                      <div className="grid grid-cols-2 gap-2 p-2.5 border rounded-lg bg-muted/50">
                        {dictionaries.reportTypes.map((item) => {
                          const id = `rule-detail-report-${item.value}`;
                          return (
                            <div key={item.value} className="flex items-start gap-1.5">
                              <Checkbox id={id} className="mt-0.5 shrink-0" checked={(editedRule.reportTypes ?? []).includes(item.value)} onCheckedChange={(checked) => handleReportTypeToggle(item.value, checked === true)} />
                              <label htmlFor={id} className="text-sm cursor-pointer leading-tight">{item.label}</label>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {reportTypeLabels.map((label) => (
                          <span key={label} className="inline-flex items-center px-2 py-0.5 rounded-md text-sm font-medium bg-primary/5 text-primary border border-primary/20">{label}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">地区</label>
                    {isEditing ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-1.5">
                          <Checkbox id="rule-detail-national" checked={editedRule.nationalLevel} onCheckedChange={(checked) => handleNationalLevelChange(checked === true)} />
                          <label htmlFor="rule-detail-national" className="text-sm text-foreground cursor-pointer">全国规则</label>
                        </div>
                        <div className={cn("grid grid-cols-2 gap-2 p-2.5 border rounded-lg bg-muted/50", editedRule.nationalLevel && "opacity-50 pointer-events-none")}>
                          {dictionaries.regions.filter((item) => item.value !== "nationwide").map((item) => {
                            const id = `rule-detail-region-${item.value}`;
                            return (
                              <div key={item.value} className="flex items-start gap-1.5">
                                <Checkbox id={id} className="mt-0.5 shrink-0" checked={(editedRule.applicableRegions ?? []).includes(item.value)} disabled={editedRule.nationalLevel} onCheckedChange={(checked) => handleRegionToggle(item.value, checked === true)} />
                                <label htmlFor={id} className={cn("text-sm leading-tight cursor-pointer", editedRule.nationalLevel && "cursor-not-allowed opacity-60")}>{item.label}</label>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {applicableRegionLabels.map((label) => (
                          <span key={label} className="inline-flex items-center px-2 py-0.5 rounded-md text-sm font-medium bg-success/10 text-success border border-success/20">{label}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </div>

            {/* Col 2: 规则描述 + 章节映射 */}
            <div className="space-y-4">
              <section className="p-4 border rounded-xl bg-card">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
                  <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
                  规则描述
                </h3>
                {isEditing ? (
                  <Textarea value={editedRule.description ?? ""} onChange={(event) => handleChange("description", event.target.value)} rows={3} className="text-sm" placeholder="规则说明（可选）" />
                ) : (
                  <div className="p-2.5 rounded-lg bg-muted/50 border border-border/60">
                    <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">{editedRule.description || "无描述"}</p>
                  </div>
                )}
              </section>

              <section className="p-4 border rounded-xl bg-card">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
                  <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                  章节映射
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">来源章节</label>
                    {isEditing ? (
                      <Textarea value={sourceSectionsInput} onChange={(event) => setSourceSectionsInput(event.target.value)} rows={2} className="text-sm" placeholder="多个章节用逗号或换行分隔" />
                    ) : (
                      <div className="p-2 rounded-lg bg-muted/50 border border-border/60">
                        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">{(rule.sourceSections?.length ?? 0) > 0 ? (rule.sourceSections ?? []).join("、") : "—"}</p>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">目标章节</label>
                    {isEditing ? (
                      <Textarea value={targetSectionsInput} onChange={(event) => setTargetSectionsInput(event.target.value)} rows={2} className="text-sm" placeholder="多个章节用逗号或换行分隔" />
                    ) : (
                      <div className="p-2 rounded-lg bg-muted/50 border border-border/60">
                        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">{(rule.targetSections?.length ?? 0) > 0 ? (rule.targetSections ?? []).join("、") : "—"}</p>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </div>

            {/* Col 3: 错误与修复 + 元信息 */}
            <div className="space-y-4">
              <section className="p-4 border rounded-xl bg-card">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
                  <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
                  错误与修复
                </h3>
                <div className="space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">错误提示</label>
                    {isEditing ? (
                      <Textarea value={editedRule.errorMessage ?? ""} onChange={(event) => handleChange("errorMessage", event.target.value)} rows={2} className="text-sm" />
                    ) : (
                      <div className="p-2.5 rounded-lg bg-destructive/8 border border-destructive/15 border-l-2 border-l-destructive/50">
                        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">{editedRule.errorMessage || "—"}</p>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-sm font-medium text-muted-foreground">修复建议</label>
                    {isEditing ? (
                      <Textarea value={editedRule.autoFixSuggestion ?? ""} onChange={(event) => handleChange("autoFixSuggestion", event.target.value)} rows={2} className="text-sm" />
                    ) : (
                      <div className="p-2.5 rounded-lg bg-success/8 border border-success/15 border-l-2 border-l-success/50">
                        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words m-0">{editedRule.autoFixSuggestion || "—"}</p>
                      </div>
                    )}
                  </div>
                </div>
              </section>

              <section className="p-4 border rounded-xl bg-card">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
                  <Info className="h-3.5 w-3.5 text-muted-foreground" />
                  元信息
                </h3>
                <div className="space-y-2">
                  {rule.seedVersion && (
                    <div className="flex justify-between items-center py-1">
                      <span className="text-sm text-muted-foreground">种子版本</span>
                      <span className="text-sm text-foreground font-mono font-medium">{rule.seedVersion}</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center py-1">
                    <span className="text-sm text-muted-foreground">创建时间</span>
                    <span className="text-sm text-foreground tabular-nums">{new Date(rule.createdAt ?? new Date()).toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center py-1">
                    <span className="text-sm text-muted-foreground">更新时间</span>
                    <span className="text-sm text-foreground tabular-nums">{new Date(rule.updatedAt ?? new Date()).toLocaleString()}</span>
                  </div>
                </div>
              </section>
            </div>
          </div>

          {/* Full-width: 验证配置 */}
          <section className="p-4 border rounded-xl bg-card">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
              <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />
              验证配置
            </h3>
            {isEditing ? (
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-muted-foreground">Validation Config JSON</label>
                <Textarea className="min-h-[280px] font-mono text-sm" value={validationConfigText} onChange={(event) => setValidationConfigText(event.target.value)} rows={14} spellCheck={false} />
              </div>
            ) : (rule.validationConfig?.fields?.length ?? 0) > 0 ? (
              <div className="overflow-x-auto -mx-1">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="px-3 py-2.5 text-left text-foreground font-semibold">字段名称</th>
                      <th className="px-3 py-2.5 text-left text-foreground font-semibold">阈值</th>
                      <th className="px-3 py-2.5 text-left text-foreground font-semibold">单位</th>
                      <th className="px-3 py-2.5 text-left text-foreground font-semibold">标准</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(rule.validationConfig?.fields as { fieldName: string; limit?: number; min?: number; max?: number; unit?: string; standard?: string }[] | undefined)?.map((field, index) => (
                      <tr key={`${field.fieldName}-${index}`} className="border-b border-border/40 hover:bg-muted/30 transition-colors">
                        <td className="px-3 py-2 text-foreground font-medium">{field.fieldName}</td>
                        <td className="px-3 py-2 text-muted-foreground tabular-nums">
                          {field.limit !== undefined ? `≤ ${field.limit}` : field.min !== undefined && field.max !== undefined ? `${field.min} – ${field.max}` : field.min !== undefined ? `≥ ${field.min}` : "—"}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">{field.unit || "—"}</td>
                        <td className="px-3 py-2 text-muted-foreground">{field.standard || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-muted/50 border border-border/60 text-center">
                <p className="text-sm text-muted-foreground m-0">无验证字段配置</p>
              </div>
            )}
          </section>
        </div>

        {/* ── Footer ── */}
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-t bg-muted/50">
          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <ShieldCheck className="h-3 w-3" />
            <span className="font-mono">{rule.ruleId}</span>
          </div>
          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <Button variant="outline" size="sm" onClick={handleCancel} disabled={saving}>取消</Button>
                <Button size="sm" onClick={() => void handleSave()} disabled={saving}>{saving ? "保存中..." : "保存"}</Button>
              </>
            ) : (
              <>
                {onViewLogs && <Button variant="outline" size="sm" onClick={onViewLogs}>查看日志</Button>}
                {onTestRule && <Button size="sm" className="bg-primary hover:bg-primary/90 text-white" onClick={onTestRule}>测试规则</Button>}
                {!readOnly && onDelete && <Button variant="destructive" size="sm" onClick={() => void handleDelete()} disabled={deleting}>{deleting ? "删除中..." : "删除"}</Button>}
                {!readOnly && <Button size="sm" onClick={() => setIsEditing(true)}>编辑</Button>}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
