"use client";

import { X, Loader2, CheckCircle2, Info } from "lucide-react";
import React, { useState, useEffect } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { loadModels } from "@/core/models/api";
import { kfApi, kbApi } from "@/extensions/api";
import type {
  ExtractionTaskResponse,
  ExtractionTaskCreate,
  ExtractionConfig,
  SampleReport,
} from "@/extensions/knowledge-factory/types";
import type { KnowledgeBase } from "@/extensions/types";
import { isDocumentReady } from "@/extensions/types";

import { cn } from "@/lib/utils";

interface Props {
  onClose: () => void;
  onSuccess: (task: ExtractionTaskResponse) => void;
  onToast: (msg: string, type: "success" | "error" | "info") => void;
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

export default function ExtractionTaskModal({ onClose, onSuccess, onToast }: Props) {
  const [name, setName] = useState(() => `模板抽取-${new Date().toLocaleDateString("zh-CN").replace(/\//g, "-")}`);
  const [selectedDomain, setSelectedDomain] = useState("");
  const [reports, setReports] = useState<SampleReport[]>([]);
  const [kbList, setKbList] = useState<KnowledgeBase[]>([]);
  const [selectedReports, setSelectedReports] = useState<Set<string>>(new Set());
  const [config, setConfig] = useState<ExtractionConfig>(DEFAULT_CONFIG);
  const [submitting, setSubmitting] = useState(false);
  const [loadingReports, setLoadingReports] = useState(true);
  const [modelOptions, setModelOptions] = useState<{ value: string; label: string }[]>([]);
  const [loadingModels, setLoadingModels] = useState(true);

  // 知识库变化时自动过滤报告列表（统一字符串比较，避免 UUID 格式差异）
  const filteredReports = selectedDomain
    ? reports.filter((r) => String(r.knowledge_base_id ?? "") === String(selectedDomain))
    : reports;

  // 加载知识库列表、样例报告和模型列表
  useEffect(() => {
    const loadReports = async () => {
      setLoadingReports(true);
      try {
        // 加载知识库列表
        const kbRes = await kbApi.list({ limit: 100 });
        setKbList(kbRes.knowledge_bases);

        // 并行加载所有已完成的文档
        const readyReports: SampleReport[] = [];
        await Promise.allSettled(
          kbRes.knowledge_bases.map(async (kb) => {
            try {
              const docRes = await kfApi.listDocs(kb.id, { limit: 100 });
              for (const doc of docRes.documents) {
                if (isDocumentReady(doc.status)) {
                  readyReports.push({
                    ...doc,
                    knowledge_base_id: doc.knowledge_base_id,
                    knowledge_base_name: kb.name,
                  } as unknown as SampleReport);
                }
              }
            } catch { /* skip */ }
          })
        );
        setReports(readyReports);
      } catch { /* ignore */ }
      setLoadingReports(false);
    };

    const loadModelsList = async () => {
      setLoadingModels(true);
      try {
        const response = await loadModels();
        const options = response.models.map((m) => ({
          value: m.name,
          label: m.display_name || m.name,
        }));
        setModelOptions(options);
        // 如果默认值为空且有模型，设置为第一个
        if (!config.llm_model && options.length > 0) {
          setConfig((c) => ({ ...c, llm_model: options.at(0)?.value ?? "" }));
        }
      } catch { /* ignore */ }
      setLoadingModels(false);
    };

    loadReports();
    loadModelsList();
  }, []);

  const toggleReport = (id: string) => {
    setSelectedReports((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!name.trim()) { onToast("请输入任务名称", "error"); return; }
    if (selectedReports.size === 0) { onToast("请至少选择 1 份样例报告", "error"); return; }

    setSubmitting(true);
    try {
      const data: ExtractionTaskCreate = {
        name: name.trim(),
        domain: selectedDomain || "default",
        source_report_ids: Array.from(selectedReports),
        target_template_name: name.trim(),
        config,
      };
      const task = await kfApi.createTask(data);
      onSuccess(task);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "创建任务失败";
      onToast(msg, "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <TooltipProvider>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-y-auto">
          {/* Header */}
          <div className="flex justify-between items-center px-6 py-4 border-b border-border shrink-0 sticky top-0 bg-white z-10">
            <h3 className="text-lg font-semibold text-foreground">新建模板抽取任务</h3>
            <button onClick={onClose} className="p-1.5 hover:bg-accent rounded-lg transition-colors">
              <X className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 px-6 py-5 space-y-5">
            {/* 任务名称 */}
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

            {/* 知识库选择 */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">选择知识库</label>
              <AdminSelect
                value={selectedDomain}
                onChange={setSelectedDomain}
                options={[
                  { value: "", label: "全部知识库" },
                  ...kbList.map((kb) => ({ value: kb.id, label: kb.name })),
                ]}
                placeholder="全部知识库"
              />
            </div>

            {/* 源报告选择 */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium text-foreground">源报告选择（至少 1 份）</label>
                <span className="text-xs text-muted-foreground">
                  已选 {selectedReports.size} 份
                </span>
              </div>
              <div className="border border-border rounded-lg divide-y divide-border max-h-52 overflow-y-auto">
              {loadingReports ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" /> 加载报告中...
                </div>
              ) : filteredReports.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                  暂无已解析的报告，请先在「样例报告」上传并等待解析完成
                </div>
              ) : (
                filteredReports.map((report) => (
                  <label
                    key={report.id}
                    className={cn(
                      "flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/50 transition-colors",
                      selectedReports.has(report.id) && "bg-blue-50"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedReports.has(report.id)}
                      onChange={() => toggleReport(report.id)}
                      className="w-4 h-4 shrink-0 rounded border-zinc-300 focus:ring-2 focus:ring-blue-500/30 focus:ring-offset-0"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{report.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {(report as SampleReport & { knowledge_base_name?: string }).knowledge_base_name || ""}
                      </p>
                    </div>
                    <CheckCircle2 className={cn(
                      "w-4 h-4 shrink-0",
                      selectedReports.has(report.id) ? "text-primary" : "text-transparent"
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
                    placeholder={loadingModels ? "加载中..." : "选择模型"}
                    disabled={loadingModels}
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">分段策略</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3 h-3 text-zinc-400 cursor-help" />
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
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">融合阈值 ({config.merge_threshold})</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3 h-3 text-zinc-400 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="font-medium mb-1">融合阈值</p>
                        <p className="text-muted-foreground text-xs">配合语义切分使用。当切分后的段落语义相似度高于此阈值时，会自动合并成一个 chunk。</p>
                        <p className="text-muted-foreground text-xs mt-1">例如：0.85 表示相似度超过 85% 的段落会被合并，避免产生过多碎片化的小段落。</p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <input
                    type="range"
                    min={0.5}
                    max={1}
                    step={0.05}
                    value={config.merge_threshold}
                    onChange={(e) => setConfig((c) => ({ ...c, merge_threshold: parseFloat(e.target.value) }))}
                    className="w-full accent-primary"
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">最小章节字数</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="w-3 h-3 text-zinc-400 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="font-medium mb-1">最小章节字数</p>
                        <p className="text-muted-foreground text-xs">过滤过短的碎片段落。如果某个章节字数低于此值，会被丢弃或合并到相邻章节。</p>
                        <p className="text-muted-foreground text-xs mt-1">默认值 100 字符，可避免 LLM 分析没有意义的短文本（如签名、日期、页眉页脚等）。</p>
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
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-border shrink-0 sticky bottom-0 bg-white z-10">
            <button
              onClick={onClose}
              className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors"
            >
              取消
            </button>
            <button
              disabled={submitting || selectedReports.size === 0}
              onClick={handleSubmit}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
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