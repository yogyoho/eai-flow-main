"use client";

import {
  X,
  Upload,
  FileText,
  Loader2,
  Plus,
  AlertCircle,
  File,
  CheckCircle2,
  Trash2,
} from "lucide-react";
import React, { useState, useCallback, useRef } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { authFormFetch } from "@/extensions/api/client";
import type { LawType } from "@/extensions/knowledge-factory/types";

import { LAW_TYPE_OPTIONS, getCategoryByCode } from "../config/lawCategories";
import { useImportLawWithFile, useLawIndustries } from "../hooks/useLawLibrary";
import { buildLawLibraryUrl } from "../law-library-api";
import { cn } from "../utils";

// Radix Select 禁止空字符串选项值，「不标记行业」用哨兵值表示，组装提交时映射回 ""
const INDUSTRY_NONE = "__none__";

interface ImportLawModalProps {
  onClose: () => void;
  onSuccess?: () => void;
}

interface FormData {
  title: string;
  lawNumber: string;
  lawType: LawType;
  department: string;
  effectiveDate: string;
  industry: string;
  keywords: string[];
  referredLaws: string[];
}

interface ParsedLawFileResponse {
  filename: string;
  content: string;
  char_count: number;
  success: boolean;
}

export default function ImportLawModal({
  onClose,
  onSuccess,
}: ImportLawModalProps) {
  const [step, setStep] = useState<
    "form" | "uploading" | "completed" | "error"
  >("form");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressLabel, setProgressLabel] = useState("");

  const [formData, setFormData] = useState<FormData>({
    title: "",
    lawNumber: "",
    lawType: "technical",
    department: "",
    effectiveDate: "",
    industry: "",
    keywords: [],
    referredLaws: [],
  });

  const [keywordInput, setKeywordInput] = useState("");
  const [referredLawInput, setReferredLawInput] = useState("");

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [parsedPreview, setParsedPreview] = useState<string | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importMutation = useImportLawWithFile();
  const {
    data: industries,
    isLoading: industriesLoading,
    isError: industriesError,
    refetch: refetchIndustries,
  } = useLawIndustries();

  const handleAddKeyword = () => {
    if (
      keywordInput.trim() &&
      !formData.keywords.includes(keywordInput.trim())
    ) {
      setFormData((prev) => ({
        ...prev,
        keywords: [...prev.keywords, keywordInput.trim()],
      }));
      setKeywordInput("");
    }
  };

  const handleRemoveKeyword = (kw: string) => {
    setFormData((prev) => ({
      ...prev,
      keywords: prev.keywords.filter((k) => k !== kw),
    }));
  };

  const handleAddReferredLaw = () => {
    if (
      referredLawInput.trim() &&
      !formData.referredLaws.includes(referredLawInput.trim())
    ) {
      setFormData((prev) => ({
        ...prev,
        referredLaws: [...prev.referredLaws, referredLawInput.trim()],
      }));
      setReferredLawInput("");
    }
  };

  const handleRemoveReferredLaw = (law: string) => {
    setFormData((prev) => ({
      ...prev,
      referredLaws: prev.referredLaws.filter((l) => l !== law),
    }));
  };

  const handleFileSelect = useCallback(async (file: File) => {
    const allowed = [".pdf", ".docx", ".doc", ".txt", ".md"];
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      setParseError(`不支持的文件类型，仅支持: ${allowed.join(" ")}`);
      return;
    }

    setSelectedFile(file);
    setParseError(null);
    setParsedPreview(null);
    setIsParsing(true);

    try {
      const formDataFd = new FormData();
      formDataFd.append("file", file);

      const result = await authFormFetch<ParsedLawFileResponse>(
        buildLawLibraryUrl("/kf/laws/parse-file"),
        formDataFd,
        "",
      );
      const preview = (result.content || "").slice(0, 500);
      setParsedPreview(
        preview + (result.content?.length > 500 ? "\n\n...（预览已截断）" : ""),
      );
    } catch (e) {
      console.error("解析文件失败:", e);
      setParseError(e instanceof Error ? e.message : "解析失败");
    } finally {
      setIsParsing(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) void handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setParsedPreview(null);
    setParseError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = async () => {
    if (!formData.title.trim()) {
      setError("请输入法规标题");
      return;
    }
    if (!formData.lawType) {
      setError("请选择法规类型");
      return;
    }

    setError(null);
    setStep("uploading");

    const tick = (label: string, target: number) => {
      setProgressLabel(label);
      setProgress(target);
    };

    try {
      tick("解析文件内容...", 20);

      const formDataFd = new FormData();
      formDataFd.append("title", formData.title.trim());
      formDataFd.append("law_number", formData.lawNumber.trim() || "");
      formDataFd.append("law_type", formData.lawType);
      formDataFd.append("department", formData.department.trim() || "");
      formDataFd.append("effective_date", formData.effectiveDate || "");
      if (formData.industry) {
        formDataFd.append("sector", formData.industry);
      }
      if (formData.keywords.length) {
        formDataFd.append("keywords", formData.keywords.join(","));
      }
      if (formData.referredLaws.length) {
        formDataFd.append("referred_laws", formData.referredLaws.join(","));
      }
      if (selectedFile) {
        formDataFd.append("file", selectedFile);
      }

      tick("保存法规记录...", 60);

      await importMutation.mutateAsync(formDataFd);

      tick("导入完成", 100);
      setStep("completed");

      setTimeout(() => {
        onSuccess?.();
        onClose();
      }, 1500);
    } catch (err) {
      console.error("导入法规失败:", err);
      setError(err instanceof Error ? err.message : "导入失败");
      setStep("error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl shadow-xl">
        {/* Header */}
        <div className="border-border flex shrink-0 items-center justify-between border-b p-4">
          <h3 className="text-foreground text-lg font-semibold">导入新法规</h3>
          <button
            onClick={onClose}
            className="hover:bg-accent rounded-lg p-1 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === "form" && (
            <div className="space-y-6">
              {/* Basic Info */}
              <div className="space-y-4">
                <h4 className="text-foreground flex items-center gap-2 text-sm font-medium">
                  <FileText className="h-4 w-4" /> 法规基本信息
                </h4>

                <div className="grid gap-4">
                  <div>
                    <label className="text-muted-foreground mb-1 block text-sm">
                      标题{" "}
                      <span className="text-red-600 dark:text-red-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          title: e.target.value,
                        }))
                      }
                      placeholder="请输入法规标题"
                      className="border-border bg-muted focus:ring-primary/20 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm transition-all outline-none focus:ring-2"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-muted-foreground mb-1 block text-sm">
                        标准号
                      </label>
                      <input
                        type="text"
                        value={formData.lawNumber}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            lawNumber: e.target.value,
                          }))
                        }
                        placeholder="如 GB 3095-2012"
                        className="border-border bg-muted focus:ring-primary/20 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm transition-all outline-none focus:ring-2"
                      />
                    </div>

                    <div>
                      <label className="text-muted-foreground mb-1 block text-sm">
                        法规类型{" "}
                        <span className="text-red-600 dark:text-red-400">
                          *
                        </span>
                      </label>
                      <AdminSelect
                        value={formData.lawType}
                        onChange={(v) =>
                          setFormData((prev) => ({
                            ...prev,
                            lawType: v as LawType,
                          }))
                        }
                        options={LAW_TYPE_OPTIONS}
                        className="w-full"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-muted-foreground mb-1 block text-sm">
                        发布部门
                      </label>
                      <input
                        type="text"
                        value={formData.department}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            department: e.target.value,
                          }))
                        }
                        placeholder="如 生态环境部"
                        className="border-border bg-muted focus:ring-primary/20 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm transition-all outline-none focus:ring-2"
                      />
                    </div>

                    <div>
                      <label className="text-muted-foreground mb-1 block text-sm">
                        生效日期
                      </label>
                      <input
                        type="date"
                        value={formData.effectiveDate}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            effectiveDate: e.target.value,
                          }))
                        }
                        className="border-border bg-muted focus:ring-primary/20 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm transition-all outline-none focus:ring-2"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-muted-foreground mb-1 block text-sm">
                      行业领域（可选，用作检索前缀）
                    </label>
                    <AdminSelect
                      value={formData.industry || INDUSTRY_NONE}
                      onChange={(v) =>
                        setFormData((prev) => ({
                          ...prev,
                          industry: v === INDUSTRY_NONE ? "" : v,
                        }))
                      }
                      options={[
                        { value: INDUSTRY_NONE, label: "不标记行业" },
                        ...(industries ?? []).map((it) => ({
                          value: it,
                          label: it,
                        })),
                      ]}
                      placeholder="请选择行业领域"
                      className="w-full"
                    />
                    {industriesLoading && (
                      <p className="text-muted-foreground mt-1 text-xs">
                        行业列表加载中…
                      </p>
                    )}
                    {industriesError && (
                      <p className="text-destructive mt-1 text-xs">
                        行业列表加载失败
                        <button
                          type="button"
                          className="ml-2 underline"
                          onClick={() => refetchIndustries()}
                        >
                          重试
                        </button>
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* File Upload */}
              <div className="space-y-3">
                <h4 className="text-foreground flex items-center gap-2 text-sm font-medium">
                  <Upload className="h-4 w-4" /> 上传法规文件（可选）
                </h4>
                <p className="text-muted-foreground -mt-2 text-xs">
                  支持 PDF、Word（.docx/.doc）、TXT、Markdown，自动提取正文内容
                </p>

                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.doc,.txt,.md"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void handleFileSelect(f);
                  }}
                />

                {!selectedFile ? (
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    onDrop={handleDrop}
                    onDragOver={(e) => e.preventDefault()}
                    className={cn(
                      "border-border cursor-pointer rounded-xl border-2 border-dashed p-8 text-center",
                      "hover:border-primary/50 hover:bg-muted/50 group transition-all",
                    )}
                  >
                    <Upload
                      className={cn(
                        "text-muted-foreground mx-auto mb-3 h-10 w-10",
                        "group-hover:text-primary transition-colors",
                      )}
                    />
                    <p className="text-foreground text-sm font-medium">
                      点击选择文件 或 拖拽文件到这里
                    </p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      PDF、Word（.docx/.doc）、TXT、Markdown
                    </p>
                  </div>
                ) : (
                  <div className="border-border space-y-3 rounded-xl border p-4">
                    {/* File info */}
                    <div className="flex items-center justify-between">
                      <div className="flex min-w-0 items-center gap-3">
                        <File className="text-primary h-8 w-8 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-foreground truncate text-sm font-medium">
                            {selectedFile.name}
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {(selectedFile.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {isParsing ? (
                          <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" />
                        ) : (
                          <button
                            onClick={handleRemoveFile}
                            className="hover:bg-accent text-muted-foreground rounded-lg p-1 transition-colors hover:text-red-600 dark:text-red-400"
                            title="移除文件"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Parse status */}
                    {isParsing && (
                      <div className="text-muted-foreground flex items-center gap-2 text-sm">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        正在解析文件内容...
                      </div>
                    )}

                    {parseError && (
                      <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                        <AlertCircle className="h-4 w-4" />
                        {parseError}
                      </div>
                    )}

                    {/* Content preview */}
                    {parsedPreview && (
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 className="h-4 w-4" />
                          文件解析成功，已提取正文
                        </div>
                        <div className="bg-muted max-h-40 overflow-y-auto rounded-lg p-3">
                          <pre className="text-muted-foreground text-xs break-all whitespace-pre-wrap">
                            {parsedPreview}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Keywords */}
              <div className="space-y-3">
                <h4 className="text-foreground flex items-center gap-2 text-sm font-medium">
                  <FileText className="h-4 w-4" /> 标签与分类
                </h4>

                <div>
                  <label className="text-muted-foreground mb-1 block text-sm">
                    关键词
                  </label>
                  <div className="mb-2 flex items-center gap-2">
                    <input
                      type="text"
                      value={keywordInput}
                      onChange={(e) => setKeywordInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddKeyword();
                        }
                      }}
                      placeholder="输入关键词后按回车添加"
                      className="border-border bg-muted focus:ring-primary/20 focus:border-primary flex-1 rounded-lg border px-3 py-2 text-sm transition-all outline-none focus:ring-2"
                    />
                    <button
                      onClick={handleAddKeyword}
                      className="hover:bg-accent border-border rounded-lg border p-2"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                  {formData.keywords.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {formData.keywords.map((kw) => (
                        <span
                          key={kw}
                          className="bg-muted inline-flex items-center gap-1 rounded px-2 py-1 text-sm"
                        >
                          {kw}
                          <button
                            onClick={() => handleRemoveKeyword(kw)}
                            className="hover:text-red-600 dark:text-red-400"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <label className="text-muted-foreground mb-1 block text-sm">
                    被引用法规（标准号）
                  </label>
                  <div className="mb-2 flex items-center gap-2">
                    <input
                      type="text"
                      value={referredLawInput}
                      onChange={(e) => setReferredLawInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddReferredLaw();
                        }
                      }}
                      placeholder="输入标准号后按回车添加"
                      className="border-border bg-muted focus:ring-primary/20 focus:border-primary flex-1 rounded-lg border px-3 py-2 text-sm transition-all outline-none focus:ring-2"
                    />
                    <button
                      onClick={handleAddReferredLaw}
                      className="hover:bg-accent border-border rounded-lg border p-2"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                  {formData.referredLaws.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {formData.referredLaws.map((law) => (
                        <span
                          key={law}
                          className="bg-muted inline-flex items-center gap-1 rounded px-2 py-1 text-sm"
                        >
                          {law}
                          <button
                            onClick={() => handleRemoveReferredLaw(law)}
                            className="hover:text-red-600 dark:text-red-400"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Error */}
              {error && (
                <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}
            </div>
          )}

          {step === "uploading" && (
            <div className="flex flex-col items-center py-12">
              <Loader2 className="text-primary mb-4 h-12 w-12 animate-spin" />
              <p className="text-foreground text-lg font-medium">正在导入...</p>
              <p className="text-muted-foreground mt-2 text-sm">
                {progressLabel}
              </p>
              <div className="bg-muted mt-4 h-2 w-64 overflow-hidden rounded-full">
                <div
                  className="bg-primary h-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {step === "completed" && (
            <div className="flex flex-col items-center py-12">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10">
                <FileText className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
              </div>
              <p className="text-foreground text-lg font-medium">导入成功</p>
              <p className="text-muted-foreground mt-2 text-sm">
                法规已成功添加到{" "}
                {getCategoryByCode(formData.lawType)?.name ?? formData.lawType}
              </p>
            </div>
          )}

          {step === "error" && (
            <div className="flex flex-col items-center py-12">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10">
                <AlertCircle className="h-6 w-6 text-red-600 dark:text-red-400" />
              </div>
              <p className="text-foreground text-lg font-medium">导入失败</p>
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                {error}
              </p>
              <button
                onClick={() => setStep("form")}
                className="bg-primary hover:bg-primary/90 mt-4 rounded-lg px-4 py-2 text-white transition-colors"
              >
                重试
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        {step === "form" && (
          <div className="border-border flex shrink-0 justify-end gap-3 border-t p-4">
            <button
              onClick={onClose}
              className="text-foreground hover:bg-accent rounded-lg px-4 py-2 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSubmit}
              disabled={importMutation.isPending}
              className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-white transition-colors disabled:opacity-50"
            >
              {importMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              开始导入
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
