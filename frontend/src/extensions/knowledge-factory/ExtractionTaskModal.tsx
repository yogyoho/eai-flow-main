"use client";

import { X, Loader2, CheckCircle2, Info } from "lucide-react";
import React, { useState, useEffect, useRef } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { loadModels } from "@/core/models/api";
import { kfApi, kbApi } from "@/extensions/api";
import type {
  ExtractionTaskResponse,
  ExtractionTaskCreate,
  ExtractionConfig,
  ExtractionDomain,
  DictItemResponse,
  MergeMode,
  TemplateListItem,
} from "@/extensions/knowledge-factory/types";
import { MERGE_MODE_OPTIONS } from "@/extensions/knowledge-factory/types";
import type { KnowledgeBase } from "@/extensions/types";
import { isDocumentReady } from "@/extensions/types";
import { cn } from "@/lib/utils";

interface Props {
  onClose: () => void;
  onSuccess: (task: ExtractionTaskResponse) => void;
}

const DEFAULT_CONFIG: ExtractionConfig = {
  llm_model: "",
  chunk_strategy: "semantic",
  merge_threshold: 0.85,
  min_section_length: 100,
};

const CHUNK_STRATEGY_OPTIONS = [
  { value: "semantic", label: "语义切分" },
  { value: "section", label: "按章节" },
  { value: "fixed", label: "固定长度" },
];

interface ReportItem {
  id: string;
  name: string;
  kb_name: string;
  kb_id: string;
}

function formatDateTime(): string {
  const now = new Date();
  const y = now.getFullYear();
  const M = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  const h = String(now.getHours()).padStart(2, "0");
  const m = String(now.getMinutes()).padStart(2, "0");
  return `模板抽取-${y}-${M}-${d}-${h}${m}`;
}

export default function ExtractionTaskModal({ onClose, onSuccess }: Props) {
  const [name, setName] = useState(formatDateTime);
  const [templateName, setTemplateName] = useState("");
  const templateNameManuallyEdited = useRef(false);
  const [domains, setDomains] = useState<ExtractionDomain[]>([]);
  const [selectedDomain, setSelectedDomain] = useState("default");
  const [industryOptions, setIndustryOptions] = useState<{ value: string; label: string }[]>([]);
  const [reportTypeOptions, setReportTypeOptions] = useState<{ value: string; label: string }[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState("");
  const [selectedReportType, setSelectedReportType] = useState("");

  // 自动生成模板名称：业务领域_报告类型_模板
  const updateAutoTemplateName = (industryValue: string, reportTypeValue: string) => {
    if (templateNameManuallyEdited.current) return;
    const indLabel = industryOptions.find((o) => o.value === industryValue)?.label ?? "";
    const rtLabel = reportTypeOptions.find((o) => o.value === reportTypeValue)?.label ?? "";
    const parts = [indLabel, rtLabel, "模板"].filter(Boolean);
    setTemplateName(parts.length > 1 ? parts.join("_") : "");
  };

  const handleIndustryChange = (val: string) => {
    setSelectedIndustry(val);
    updateAutoTemplateName(val, selectedReportType);
  };

  const handleReportTypeChange = (val: string) => {
    setSelectedReportType(val);
    updateAutoTemplateName(selectedIndustry, val);
  };

  const handleTemplateNameChange = (val: string) => {
    templateNameManuallyEdited.current = true;
    setTemplateName(val);
  };
  const [selectedKb, setSelectedKb] = useState("__all__");
  const [reportItems, setReportItems] = useState<ReportItem[]>([]);
  const [kbList, setKbList] = useState<KnowledgeBase[]>([]);
  const [selectedReports, setSelectedReports] = useState<Set<string>>(new Set());
  const [config, setConfig] = useState<ExtractionConfig>(DEFAULT_CONFIG);
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("__new__");
  const [mergeMode, setMergeMode] = useState<MergeMode>("merge");
  const [submitting, setSubmitting] = useState(false);
  const [loadingData, setLoadingData] = useState(true);
  const [modelOptions, setModelOptions] = useState<{ value: string; label: string }[]>([]);

  // 当领域变化时，加载该领域下的模板列表
  useEffect(() => {
    let cancelled = false;
    kfApi.listTemplates({ domain: selectedDomain, limit: 50 }).then((res) => {
      if (!cancelled) setTemplates(res.templates);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [selectedDomain]);

  // 加载领域、知识库、报告、模型
  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      setLoadingData(true);
      try {
        // 并行加载
        const [domRes, kbRes, modelsRes, indRes, rtRes] = await Promise.allSettled([
          kfApi.listDomains(),
          kbApi.list({ limit: 100 }),
          loadModels(),
          kfApi.listDictItems("industry", { limit: 100 }),
          kfApi.listDictItems("report_type", { limit: 100 }),
        ]);

        if (cancelled) return;

        // 领域
        if (domRes.status === "fulfilled" && domRes.value.domains.length > 0) {
          setDomains(domRes.value.domains);
          setSelectedDomain(domRes.value.domains[0]!.id);
        }

        // 业务领域下拉选项
        if (indRes.status === "fulfilled") {
          setIndustryOptions(indRes.value.items.map((d: DictItemResponse) => ({ value: d.id, label: d.label })));
        }

        // 报告类型下拉选项
        if (rtRes.status === "fulfilled") {
          setReportTypeOptions(rtRes.value.items.map((d: DictItemResponse) => ({ value: d.id, label: d.label })));
        }

        // 知识库
        if (kbRes.status === "fulfilled") {
          const kbs = kbRes.value.knowledge_bases;
          setKbList(kbs);

          // 并行加载每个KB的已解析文档
          const items: ReportItem[] = [];
          await Promise.allSettled(
            kbs.map(async (kb) => {
              try {
                const docRes = await kfApi.listDocs(kb.id, { limit: 200 });
                for (const doc of docRes.documents) {
                  if (isDocumentReady(doc.status)) {
                    items.push({ id: doc.id, name: doc.name, kb_name: kb.name, kb_id: kb.id });
                  }
                }
              } catch { /* skip */ }
            })
          );
          if (!cancelled) setReportItems(items);
        }

        // 模型
        if (modelsRes.status === "fulfilled") {
          const options = modelsRes.value.models.map((m) => ({
            value: m.name,
            label: m.display_name || m.name,
          }));
          setModelOptions(options);
          if (!config.llm_model && options.length > 0) {
            setConfig((c) => ({ ...c, llm_model: options[0]!.value }));
          }
        }
      } catch { /* ignore */ }
      if (!cancelled) setLoadingData(false);
    };
    void init();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredReports = selectedKb === "__all__"
    ? reportItems
    : reportItems.filter((r) => r.kb_id === selectedKb);

  const toggleReport = (id: string) => {
    setSelectedReports((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId);

  const handleSubmit = async () => {
    if (!name.trim()) { toast.error("请输入任务名称"); return; }
    if (selectedReports.size === 0) { toast.error("请至少选择 1 份样例报告"); return; }

    setSubmitting(true);
    try {
      const isExisting = selectedTemplateId !== "__new__";
      const finalTemplateName = isExisting
        ? (selectedTemplate?.name || name.trim())
        : (templateName.trim() || name.trim());
      const data: ExtractionTaskCreate = {
        name: name.trim(),
        domain: selectedDomain,
        industry: selectedIndustry || undefined,
        report_type: selectedReportType || undefined,
        source_report_ids: Array.from(selectedReports),
        target_template_name: finalTemplateName,
        target_template_id: isExisting ? selectedTemplateId : undefined,
        merge_mode: isExisting ? mergeMode : undefined,
        config,
      };
      const task = await kfApi.createTask(data);
      onSuccess(task);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "创建任务失败";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <TooltipProvider>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
        <div className="bg-background rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-y-auto">
          {/* Header */}
          <div className="flex justify-between items-center px-6 py-4 border-b border-border shrink-0 sticky top-0 bg-background z-10">
            <h3 className="text-lg font-semibold text-foreground">新建模板抽取任务</h3>
            <button onClick={onClose} className="p-1.5 hover:bg-accent rounded-lg transition-colors">
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 px-6 py-5 space-y-5">
            {/* 任务名称 + 模板名称 */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">任务名称</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="请输入任务名称"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">模板名称</label>
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => handleTemplateNameChange(e.target.value)}
                  placeholder="选择业务领域和报告类型后自动生成"
                  className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>
            </div>

            {/* 业务领域 + 报告类型 */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">业务领域</label>
                <AdminSelect
                  value={selectedIndustry}
                  onChange={handleIndustryChange}
                  options={industryOptions}
                  placeholder="选择领域"
                  className="w-full"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">报告类型</label>
                <AdminSelect
                  value={selectedReportType}
                  onChange={handleReportTypeChange}
                  options={reportTypeOptions}
                  placeholder="选择类型"
                  className="w-full"
                />
              </div>
            </div>

            {/* 报告大纲 + 知识库筛选 */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">报告大纲</label>
                <AdminSelect
                  value={selectedDomain}
                  onChange={setSelectedDomain}
                  options={
                    domains.length > 0
                      ? domains.map((d) => ({ value: d.id, label: d.name }))
                      : [{ value: "default", label: "默认" }]
                  }
                  placeholder="选择大纲"
                  className="w-full"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">知识库筛选</label>
                <AdminSelect
                  value={selectedKb}
                  onChange={setSelectedKb}
                  options={[
                    { value: "__all__", label: "全部知识库" },
                    ...kbList.map((kb) => ({ value: kb.id, label: kb.name })),
                  ]}
                  placeholder="全部知识库"
                  className="w-full"
                />
              </div>
            </div>

            {/* 目标模板选择 */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">目标模板</label>
              <AdminSelect
                value={selectedTemplateId}
                onChange={setSelectedTemplateId}
                options={[
                  { value: "__new__", label: "+ 创建新模板" },
                  ...templates.map((t) => ({
                    value: t.id,
                    label: `${t.name} (${t.version})`,
                  })),
                ]}
                placeholder="选择目标模板"
                className="w-full"
              />
              {templates.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  该领域下暂无已有模板，将自动创建新模板
                </p>
              )}
            </div>

            {/* 合并模式（仅选择已有模板时显示） */}
            {selectedTemplateId !== "__new__" && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">合并模式</label>
                <div className="grid grid-cols-3 gap-2">
                  {MERGE_MODE_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={cn(
                        "flex flex-col items-center gap-1 p-3 rounded-lg border-2 cursor-pointer transition-all",
                        mergeMode === opt.value
                          ? "border-primary bg-primary/5 shadow-sm"
                          : "border-border hover:border-primary/40 hover:bg-accent/50"
                      )}
                    >
                      <input
                        type="radio"
                        name="mergeMode"
                        value={opt.value}
                        checked={mergeMode === opt.value}
                        onChange={() => setMergeMode(opt.value)}
                        className="sr-only"
                      />
                      <span className={cn(
                        "text-sm font-semibold",
                        mergeMode === opt.value ? "text-primary" : "text-foreground"
                      )}>
                        {opt.label}
                      </span>
                      <span className="text-[10px] text-muted-foreground text-center leading-tight">
                        {opt.description}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* 源报告选择 */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium text-foreground">源报告选择（至少 1 份）</label>
                <span className="text-xs text-muted-foreground">已选 {selectedReports.size} 份</span>
              </div>
              <div className="border border-border rounded-lg divide-y divide-border max-h-52 overflow-y-auto">
                {loadingData ? (
                  <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                    <Loader2 className="w-4 h-4 animate-spin mr-2" /> 加载报告中...
                  </div>
                ) : filteredReports.length === 0 ? (
                  <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                    暂无已解析的报告
                  </div>
                ) : (
                  filteredReports.map((r) => (
                    <label
                      key={r.id}
                      className={cn(
                        "flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/50 transition-colors group",
                        selectedReports.has(r.id) && "bg-primary/5"
                      )}
                    >
                      <div className="relative shrink-0">
                        <input
                          type="checkbox"
                          checked={selectedReports.has(r.id)}
                          onChange={() => toggleReport(r.id)}
                          className="sr-only"
                        />
                        <div className={cn(
                          "w-4 h-4 rounded border-2 flex items-center justify-center transition-all duration-200",
                          "group-hover:border-primary/60",
                          selectedReports.has(r.id)
                            ? "bg-primary border-primary"
                            : "border-input bg-background"
                        )}>
                          <CheckCircle2 className={cn(
                            "w-3.5 h-3.5 text-primary-foreground transition-all duration-200",
                            selectedReports.has(r.id) ? "scale-100 opacity-100" : "scale-0 opacity-0"
                          )} />
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{r.name}</p>
                        <p className="text-xs text-muted-foreground truncate">{r.kb_name}</p>
                      </div>
                      <CheckCircle2 className={cn(
                        "w-4 h-4 shrink-0",
                        selectedReports.has(r.id) ? "text-primary" : "text-transparent"
                      )} />
                    </label>
                  ))
                )}
              </div>
            </div>

            {/* 抽取配置 */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">抽取配置</label>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <span className="text-xs text-muted-foreground">LLM 模型</span>
                  <AdminSelect
                    value={config.llm_model}
                    onChange={(value) => setConfig((c) => ({ ...c, llm_model: value }))}
                    options={modelOptions}
                    placeholder="选择模型"
                    className="w-full"
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">分段策略</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3 h-3 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="font-medium mb-1">分段策略</p>
                        <p className="text-muted-foreground mb-2">决定如何将文档切分成小块供 LLM 分析处理</p>
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left">
                              <th className="pr-2">策略</th>
                              <th>说明</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr><td className="pr-2 font-medium">语义切分</td><td>LLM 理解语义，在逻辑边界自动切分（推荐）</td></tr>
                            <tr><td className="pr-2 font-medium">按章节</td><td>依据文档自带的一级/二级标题切分</td></tr>
                            <tr><td className="pr-2 font-medium">固定长度</td><td>按固定字符数硬切分（可能截断语句）</td></tr>
                          </tbody>
                        </table>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <AdminSelect
                    value={config.chunk_strategy}
                    onChange={(value) => setConfig((c) => ({ ...c, chunk_strategy: value as "semantic" | "fixed" | "section" }))}
                    options={CHUNK_STRATEGY_OPTIONS}
                    placeholder="选择策略"
                    className="w-full"
                  />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-muted-foreground">融合阈值</span>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Info className="w-3 h-3 text-muted-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs">
                          <p className="font-medium mb-1">融合阈值</p>
                          <p className="text-muted-foreground text-xs">配合语义切分使用。当切分后的段落语义相似度高于此阈值时，会自动合并成一个 chunk。</p>
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <span className="text-xs font-semibold tabular-nums text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                      {config.merge_threshold.toFixed(2)}
                    </span>
                  </div>
                  <div className="relative pt-1 pb-2">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground/60 mb-1 px-0.5">
                      <span>0.50</span>
                      <span>0.75</span>
                      <span>1.00</span>
                    </div>
                    <div className="relative h-2 rounded-full bg-muted">
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-primary/80 to-primary transition-all duration-150"
                        style={{ width: `${((config.merge_threshold - 0.5) / 0.5) * 100}%` }}
                      />
                      <input
                        type="range"
                        min={0.5}
                        max={1}
                        step={0.05}
                        value={config.merge_threshold}
                        onChange={(e) => setConfig((c) => ({ ...c, merge_threshold: parseFloat(e.target.value) }))}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                      />
                      <div
                        className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white border-2 border-primary shadow-md transition-all duration-150 pointer-events-none"
                        style={{ left: `calc(${((config.merge_threshold - 0.5) / 0.5) * 100}% - 8px)` }}
                      />
                    </div>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">最小章节字数</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3 h-3 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="font-medium mb-1">最小章节字数</p>
                        <p className="text-muted-foreground text-xs">过滤过短的碎片段落。低于此值的章节会被丢弃或合并到相邻章节。</p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <input
                    type="number"
                    value={config.min_section_length}
                    onChange={(e) => setConfig((c) => ({ ...c, min_section_length: parseInt(e.target.value) || 100 }))}
                    className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-border shrink-0 sticky bottom-0 bg-background z-10">
            <button
              onClick={onClose}
              className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors"
            >
              取消
            </button>
            <button
              disabled={submitting || selectedReports.size === 0}
              onClick={handleSubmit}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {submitting ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> 创建中...</>
              ) : (
                "开始抽取"
              )}
            </button>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
