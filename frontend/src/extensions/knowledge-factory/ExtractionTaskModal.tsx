"use client";

import {
  CheckCircle2,
  Database,
  Info,
  Loader2,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import React, { useState, useEffect, useRef } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
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

type ExtractMode = "B" | "A";

const DEFAULT_CONFIG: ExtractionConfig = {
  llm_model: "",
  chunk_strategy: "semantic",
  merge_threshold: 0.85,
  min_section_length: 100,
  max_depth: 4,
};

const MAX_DEPTH_OPTIONS = [
  { value: 2, label: "H2（2级）", description: "章、节" },
  { value: 3, label: "H3（3级）", description: "章、节、条" },
  { value: 4, label: "H4（4级）", description: "章、节、条、款" },
  { value: 5, label: "H5（5级）", description: "章、节、条、款、项" },
  { value: 6, label: "H6（6级）", description: "最深层级" },
];

const MODE_OPTIONS: {
  value: ExtractMode;
  label: string;
  desc: string;
  icon: typeof UploadCloud;
}[] = [
  {
    value: "B",
    label: "直接上传文件",
    desc: "推荐 · doc_parser 解析，提取更精准",
    icon: UploadCloud,
  },
  {
    value: "A",
    label: "从知识库选择",
    desc: "已上传到 RAGFlow 的样例报告",
    icon: Database,
  },
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
  const [industryOptions, setIndustryOptions] = useState<
    { value: string; label: string }[]
  >([]);
  const [reportTypeOptions, setReportTypeOptions] = useState<
    { value: string; label: string }[]
  >([]);
  const [selectedIndustry, setSelectedIndustry] = useState("");
  const [selectedReportType, setSelectedReportType] = useState("");
  const [mode, setMode] = useState<ExtractMode>("B");

  // 自动生成模板名称：业务领域_报告类型_模板
  const updateAutoTemplateName = (
    industryValue: string,
    reportTypeValue: string,
  ) => {
    if (templateNameManuallyEdited.current) return;
    const indLabel =
      industryOptions.find((o) => o.value === industryValue)?.label ?? "";
    const rtLabel =
      reportTypeOptions.find((o) => o.value === reportTypeValue)?.label ?? "";
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
  const [selectedReports, setSelectedReports] = useState<Set<string>>(
    new Set(),
  );
  const [config, setConfig] = useState<ExtractionConfig>(DEFAULT_CONFIG);
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("__new__");
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [uploadedDocIds, setUploadedDocIds] = useState<string[]>([]);
  const [uploadedFileNames, setUploadedFileNames] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadFiles = async (fileList: File[]) => {
    if (fileList.length === 0) return;

    const kb = kbList.find((k) => k.status === "active") ?? kbList[0];
    if (!kb) {
      toast.error("没有可用的知识库，请先在样例管理 tab 创建知识库");
      return;
    }

    setUploadingFiles(true);
    try {
      // Read CSRF token directly from cookie — FormData uploads need explicit
      // X-CSRF-Token header. withCsrf() may return {} if cookie is inaccessible
      // via document.cookie in certain browser contexts.
      const csrfMatch = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
      const csrfToken = csrfMatch?.[1] ?? "";
      const ids: string[] = [];
      const names: string[] = [];
      for (const file of fileList) {
        const formData = new FormData();
        formData.append("file", file);
        const headers: Record<string, string> = {};
        if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
        const res = await fetch(
          `/api/extensions/knowledge-bases/${kb.id}/documents`,
          {
            method: "POST",
            credentials: "include",
            headers,
            body: formData,
          },
        );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          const detail = err.detail ?? "";
          if (res.status === 403 && detail.includes("Permission denied")) {
            // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- split 结果可为 ""（"Permission denied: " 尾空段），空串需回退到完整 detail
            const perm = detail.split(": ")[1] || detail;
            throw new Error(`权限不足：缺少 ${perm} 权限，请联系管理员`);
          }
          if (res.status === 403) {
            // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- detail 为 "" 时应显示友好提示而非空括号
            const hint = detail || "请确认已登录并有知识库上传权限";
            throw new Error(`无权限上传文件（${hint}）`);
          }
          // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- detail 为 "" 时应显示带状态码的兜底信息而非空错误
          throw new Error(detail || `上传失败 (${res.status})`);
        }
        const doc = await res.json();
        ids.push(doc.id);
        names.push(file.name);
      }
      setUploadedDocIds((prev) => [...prev, ...ids]);
      setUploadedFileNames((prev) => [...prev, ...names]);
      toast.success(`已上传 ${fileList.length} 个文件`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "上传失败";
      toast.error(msg);
    } finally {
      setUploadingFiles(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    void uploadFiles(Array.from(e.target.files ?? []));
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    void uploadFiles(Array.from(e.dataTransfer.files));
  };

  const removeUploadedFile = (index: number) => {
    setUploadedDocIds((prev) => prev.filter((_, i) => i !== index));
    setUploadedFileNames((prev) => prev.filter((_, i) => i !== index));
  };

  const [mergeMode, setMergeMode] = useState<MergeMode>("merge");
  const [submitting, setSubmitting] = useState(false);
  const [loadingData, setLoadingData] = useState(true);
  const [modelOptions, setModelOptions] = useState<
    { value: string; label: string }[]
  >([]);

  // 当领域变化时，加载该领域下的模板列表
  useEffect(() => {
    let cancelled = false;
    kfApi
      .listTemplates({ domain: selectedDomain, limit: 50 })
      .then((res) => {
        if (!cancelled) setTemplates(res.templates);
      })
      .catch(() => {
        /* template list is optional; ignore load failure */
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDomain]);

  // 加载领域、知识库、报告、模型
  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      setLoadingData(true);
      try {
        // 并行加载
        const [domRes, kbRes, modelsRes, indRes, rtRes] =
          await Promise.allSettled([
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
          setIndustryOptions(
            indRes.value.items.map((d: DictItemResponse) => ({
              value: d.id,
              label: d.label,
            })),
          );
        }

        // 报告类型下拉选项
        if (rtRes.status === "fulfilled") {
          setReportTypeOptions(
            rtRes.value.items.map((d: DictItemResponse) => ({
              value: d.id,
              label: d.label,
            })),
          );
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
                    items.push({
                      id: doc.id,
                      name: doc.name,
                      kb_name: kb.name,
                      kb_id: kb.id,
                    });
                  }
                }
              } catch {
                /* skip */
              }
            }),
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
      } catch {
        /* ignore */
      }
      if (!cancelled) setLoadingData(false);
    };
    void init();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredReports =
    selectedKb === "__all__"
      ? reportItems
      : reportItems.filter((r) => r.kb_id === selectedKb);

  const toggleReport = (id: string) => {
    setSelectedReports((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId);
  const canSubmit =
    mode === "A" ? selectedReports.size > 0 : uploadedDocIds.length > 0;

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error("请输入任务名称");
      return;
    }
    if (mode === "A" && selectedReports.size === 0) {
      toast.error("请至少选择 1 份样例报告");
      return;
    }
    if (mode === "B" && uploadedDocIds.length === 0) {
      toast.error("请上传至少 1 个 Word/PDF 文件");
      return;
    }

    setSubmitting(true);
    try {
      const isExisting = selectedTemplateId !== "__new__";
      const finalTemplateName = isExisting
        ? (selectedTemplate?.name ?? name.trim())
        : templateName.trim() || name.trim();
      const data: ExtractionTaskCreate = {
        name: name.trim(),
        domain: selectedDomain,
        industry: selectedIndustry || undefined,
        report_type: selectedReportType || undefined,
        // 按模式分流：A=知识库样例，B=直接上传文件
        source_report_ids: mode === "A" ? Array.from(selectedReports) : [],
        uploaded_file_ids:
          mode === "B" && uploadedDocIds.length > 0
            ? uploadedDocIds
            : undefined,
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
        <div className="bg-background flex max-h-[90vh] w-full max-w-2xl flex-col overflow-y-auto rounded-2xl shadow-2xl">
          {/* Header */}
          <div className="border-border bg-background sticky top-0 z-10 flex shrink-0 items-center justify-between border-b px-6 py-4">
            <h3 className="text-foreground text-lg font-semibold">
              新建模板抽取任务
            </h3>
            <button
              onClick={onClose}
              className="hover:bg-accent rounded-lg p-1.5 transition-colors"
            >
              <X className="text-muted-foreground h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 space-y-5 px-6 py-5">
            {/* 任务名称 + 模板名称（共享） */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  任务名称
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="请输入任务名称"
                  className="border-border focus:ring-primary/30 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  模板名称
                </label>
                <input
                  type="text"
                  value={templateName}
                  onChange={(e) => handleTemplateNameChange(e.target.value)}
                  placeholder="选择业务领域和报告类型后自动生成"
                  className="border-border focus:ring-primary/30 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                />
              </div>
            </div>

            {/* 业务领域 + 报告类型（共享） */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  业务领域
                </label>
                <AdminSelect
                  value={selectedIndustry}
                  onChange={handleIndustryChange}
                  options={industryOptions}
                  placeholder="选择领域"
                  className="w-full"
                />
              </div>
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  报告类型
                </label>
                <AdminSelect
                  value={selectedReportType}
                  onChange={handleReportTypeChange}
                  options={reportTypeOptions}
                  placeholder="选择类型"
                  className="w-full"
                />
              </div>
            </div>

            {/* 样例来源：模式切换（默认 B 直接上传） */}
            <div className="space-y-2">
              <label className="text-foreground text-sm font-medium">
                样例来源
              </label>
              <div className="grid grid-cols-2 gap-2">
                {MODE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setMode(opt.value)}
                    className={cn(
                      "flex items-start gap-2.5 rounded-lg border-2 p-3 text-left transition-all",
                      mode === opt.value
                        ? "border-primary bg-primary/5 shadow-sm"
                        : "border-border hover:border-primary/40 hover:bg-accent/50",
                    )}
                  >
                    <opt.icon
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        mode === opt.value
                          ? "text-primary"
                          : "text-muted-foreground",
                      )}
                    />
                    <div className="min-w-0">
                      <div
                        className={cn(
                          "text-sm font-semibold",
                          mode === opt.value
                            ? "text-primary"
                            : "text-foreground",
                        )}
                      >
                        {opt.label}
                      </div>
                      <div className="text-muted-foreground text-[10px] leading-tight">
                        {opt.desc}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* —— B 模式：文件拖拽框（默认）—— */}
            {mode === "B" && (
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  上传样例报告
                  <span className="text-muted-foreground ml-2 text-xs">
                    直接上传 Word/PDF，优先用 doc_parser 解析，提取更精准
                  </span>
                </label>
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  onClick={() =>
                    !uploadingFiles && fileInputRef.current?.click()
                  }
                  className={cn(
                    "cursor-pointer rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
                    dragging
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50 hover:bg-accent/30",
                    uploadingFiles && "cursor-wait opacity-80",
                  )}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".docx,.pdf"
                    multiple
                    onChange={handleFileUpload}
                    disabled={uploadingFiles}
                    className="hidden"
                  />
                  {uploadingFiles ? (
                    <div className="text-muted-foreground flex flex-col items-center gap-2">
                      <Loader2 className="h-7 w-7 animate-spin" />
                      <span className="text-sm">上传中...</span>
                    </div>
                  ) : (
                    <div className="text-muted-foreground flex flex-col items-center gap-2">
                      <UploadCloud className="h-7 w-7" />
                      <span className="text-foreground text-sm font-medium">
                        点击或拖拽 Word/PDF 文件到此处
                      </span>
                      <span className="text-xs">支持 .docx / .pdf，可多选</span>
                    </div>
                  )}
                </div>
                {uploadedFileNames.length > 0 && (
                  <div className="space-y-1">
                    {uploadedFileNames.map((fname, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded bg-green-50 px-2 py-1.5 text-xs text-green-700 dark:bg-green-950/30 dark:text-green-400"
                      >
                        <span className="flex min-w-0 items-center gap-1">
                          <CheckCircle2 className="h-3 w-3 shrink-0" />
                          <span className="truncate">{fname}</span>
                        </span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeUploadedFile(i);
                          }}
                          className="text-muted-foreground hover:text-destructive ml-2 shrink-0"
                          aria-label={`移除 ${fname}`}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* —— A 模式：报告大纲 + 知识库筛选 + 源报告选择 —— */}
            {mode === "A" && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <label className="text-foreground text-sm font-medium">
                      报告大纲
                    </label>
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
                    <label className="text-foreground text-sm font-medium">
                      知识库筛选
                    </label>
                    <AdminSelect
                      value={selectedKb}
                      onChange={setSelectedKb}
                      options={[
                        { value: "__all__", label: "全部知识库" },
                        ...kbList.map((kb) => ({
                          value: kb.id,
                          label: kb.name,
                        })),
                      ]}
                      placeholder="全部知识库"
                      className="w-full"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-foreground text-sm font-medium">
                      源报告选择（至少 1 份）
                    </label>
                    <span className="text-muted-foreground text-xs">
                      已选 {selectedReports.size} 份
                    </span>
                  </div>
                  <div className="border-border divide-border max-h-52 divide-y overflow-y-auto rounded-lg border">
                    {loadingData ? (
                      <div className="text-muted-foreground flex items-center justify-center py-8 text-sm">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />{" "}
                        加载报告中...
                      </div>
                    ) : filteredReports.length === 0 ? (
                      <div className="text-muted-foreground flex items-center justify-center py-8 text-sm">
                        暂无已解析的报告
                      </div>
                    ) : (
                      filteredReports.map((r) => (
                        <label
                          key={r.id}
                          className={cn(
                            "hover:bg-muted/50 group flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors",
                            selectedReports.has(r.id) && "bg-primary/5",
                          )}
                        >
                          <div className="relative shrink-0">
                            <input
                              type="checkbox"
                              checked={selectedReports.has(r.id)}
                              onChange={() => toggleReport(r.id)}
                              className="sr-only"
                            />
                            <div
                              className={cn(
                                "flex h-4 w-4 items-center justify-center rounded border-2 transition-all duration-200",
                                "group-hover:border-primary/60",
                                selectedReports.has(r.id)
                                  ? "bg-primary border-primary"
                                  : "border-input bg-background",
                              )}
                            >
                              <CheckCircle2
                                className={cn(
                                  "text-primary-foreground h-3.5 w-3.5 transition-all duration-200",
                                  selectedReports.has(r.id)
                                    ? "scale-100 opacity-100"
                                    : "scale-0 opacity-0",
                                )}
                              />
                            </div>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="text-foreground truncate text-sm font-medium">
                              {r.name}
                            </p>
                            <p className="text-muted-foreground truncate text-xs">
                              {r.kb_name}
                            </p>
                          </div>
                          <CheckCircle2
                            className={cn(
                              "h-4 w-4 shrink-0",
                              selectedReports.has(r.id)
                                ? "text-primary"
                                : "text-transparent",
                            )}
                          />
                        </label>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}

            {/* 目标模板（共享） */}
            <div className="space-y-2">
              <label className="text-foreground text-sm font-medium">
                目标模板
              </label>
              <AdminSelect
                value={selectedTemplateId}
                onChange={setSelectedTemplateId}
                options={[
                  { value: "__new__", label: "+ 创建新模板" },
                  ...templates.map((t) => ({
                    value: t.id,
                    label: `${t.name} (${t.version}) ${t.status === "published" ? "✅已发布" : "📝草稿"}`,
                  })),
                ]}
                placeholder="选择目标模板"
                className="w-full"
              />
              {templates.length === 0 && (
                <p className="text-muted-foreground text-xs">
                  该领域下暂无已有模板，将自动创建新模板
                </p>
              )}
              {selectedTemplateId !== "__new__" &&
                (() => {
                  const sel = templates.find(
                    (t) => t.id === selectedTemplateId,
                  );
                  if (sel?.status === "published") {
                    return (
                      <p className="text-xs text-amber-600 dark:text-amber-400">
                        ⚠️ 选择已发布模板：旧版本({sel.version}
                        )将自动保存到版本历史，新版本号递增并设为草稿状态，需审核后才能发布。
                      </p>
                    );
                  }
                  return null;
                })()}
            </div>

            {/* 合并模式（共享，仅选择已有模板时显示） */}
            {selectedTemplateId !== "__new__" && (
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  合并模式
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {MERGE_MODE_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className={cn(
                        "flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 p-3 transition-all",
                        mergeMode === opt.value
                          ? "border-primary bg-primary/5 shadow-sm"
                          : "border-border hover:border-primary/40 hover:bg-accent/50",
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
                      <span
                        className={cn(
                          "text-sm font-semibold",
                          mergeMode === opt.value
                            ? "text-primary"
                            : "text-foreground",
                        )}
                      >
                        {opt.label}
                      </span>
                      <span className="text-muted-foreground text-center text-[10px] leading-tight">
                        {opt.description}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* 抽取配置（共享） */}
            <div className="space-y-2">
              <label className="text-foreground text-sm font-medium">
                抽取配置
              </label>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <span className="text-muted-foreground text-xs">
                    LLM 模型
                  </span>
                  <AdminSelect
                    value={config.llm_model}
                    onChange={(value) =>
                      setConfig((c) => ({ ...c, llm_model: value }))
                    }
                    options={modelOptions}
                    placeholder="选择模型"
                    className="w-full"
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground text-xs">
                      章节深度
                    </span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="text-muted-foreground h-3 w-3 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="mb-1 font-medium">章节深度</p>
                        <p className="text-muted-foreground text-xs">
                          控制 LLM
                          推断模板章节时的最大层级深度。深度越大，识别的子章节越细。
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <AdminSelect
                    value={String(config.max_depth)}
                    onChange={(value) =>
                      setConfig((c) => ({
                        ...c,
                        max_depth: parseInt(value) || 4,
                      }))
                    }
                    options={MAX_DEPTH_OPTIONS.map((o) => ({
                      value: String(o.value),
                      label: o.label,
                    }))}
                    placeholder="选择深度"
                    className="w-full"
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-1">
                    <span className="text-muted-foreground text-xs">
                      最小章节字数
                    </span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="text-muted-foreground h-3 w-3 cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="mb-1 font-medium">最小章节字数</p>
                        <p className="text-muted-foreground text-xs">
                          过滤过短的碎片段落。低于此值的章节会被丢弃或合并到相邻章节。
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <input
                    type="number"
                    value={config.min_section_length}
                    onChange={(e) =>
                      setConfig((c) => ({
                        ...c,
                        min_section_length: parseInt(e.target.value) || 100,
                      }))
                    }
                    className="border-border focus:ring-primary/30 w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="border-border bg-background sticky bottom-0 z-10 flex shrink-0 justify-end gap-3 border-t px-6 py-4">
            <button
              onClick={onClose}
              className="border-border hover:bg-accent rounded-lg border px-4 py-2 text-sm transition-colors"
            >
              取消
            </button>
            <button
              disabled={submitting || !canSubmit}
              onClick={handleSubmit}
              className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> 创建中...
                </>
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
