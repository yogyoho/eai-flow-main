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

import { LAW_TYPE_OPTIONS, getCategoryByCode } from "../config/lawCategories";
import { useImportLawWithFile } from "../hooks/useLawLibrary";
import { buildLawLibraryUrl } from "../law-library-api";
import type { LawType } from "@/extensions/knowledge-factory/types";
import { cn } from "../utils";

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
  keywords: string[];
  referredLaws: string[];
}

interface ParsedLawFileResponse {
  filename: string;
  content: string;
  char_count: number;
  success: boolean;
}

export default function ImportLawModal({ onClose, onSuccess }: ImportLawModalProps) {
  const [step, setStep] = useState<"form" | "uploading" | "completed" | "error">("form");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressLabel, setProgressLabel] = useState("");

  const [formData, setFormData] = useState<FormData>({
    title: "",
    lawNumber: "",
    lawType: "technical",
    department: "",
    effectiveDate: "",
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

  const handleAddKeyword = () => {
    if (keywordInput.trim() && !formData.keywords.includes(keywordInput.trim())) {
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
        ""
      );
      const preview = (result.content || "").slice(0, 500);
      setParsedPreview(
        preview + (result.content?.length > 500 ? "\n\n...（预览已截断）" : "")
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
    [handleFileSelect]
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
      <div className="bg-card rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
          <h3 className="text-lg font-semibold text-foreground">导入新法规</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-accent rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === "form" && (
            <div className="space-y-6">
              {/* Basic Info */}
              <div className="space-y-4">
                <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <FileText className="w-4 h-4" /> 法规基本信息
                </h4>

                <div className="grid gap-4">
                  <div>
                    <label className="block text-sm text-muted-foreground mb-1">
                      标题 <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, title: e.target.value }))
                      }
                      placeholder="请输入法规标题"
                      className="text-sm w-full px-3 py-2 border border-border rounded-lg bg-muted focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm text-muted-foreground mb-1">
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
                        className="text-sm w-full px-3 py-2 border border-border rounded-lg bg-muted focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
                      />
                    </div>

                    <div>
                      <label className="block text-sm text-muted-foreground mb-1">
                        法规类型 <span className="text-red-500">*</span>
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
                      <label className="block text-sm text-muted-foreground mb-1">
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
                        className="text-sm w-full px-3 py-2 border border-border rounded-lg bg-muted focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
                      />
                    </div>

                    <div>
                      <label className="block text-sm text-muted-foreground mb-1">
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
                        className="text-sm w-full px-3 py-2 border border-border rounded-lg bg-muted focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* File Upload */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <Upload className="w-4 h-4" /> 上传法规文件（可选）
                </h4>
                <p className="text-xs text-muted-foreground -mt-2">
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
                      "border-2 border-dashed border-border rounded-xl p-8 text-center cursor-pointer",
                      "hover:border-primary/50 hover:bg-muted/50 transition-all group"
                    )}
                  >
                    <Upload
                      className={cn(
                        "w-10 h-10 mx-auto mb-3 text-muted-foreground",
                        "group-hover:text-primary transition-colors"
                      )}
                    />
                    <p className="text-sm font-medium text-foreground">
                      点击选择文件 或 拖拽文件到这里
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      PDF、Word（.docx/.doc）、TXT、Markdown
                    </p>
                  </div>
                ) : (
                  <div className="border border-border rounded-xl p-4 space-y-3">
                    {/* File info */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 min-w-0">
                        <File className="w-8 h-8 text-indigo-500 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">
                            {selectedFile.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {(selectedFile.size / 1024).toFixed(1)} KB
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {isParsing ? (
                          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                        ) : (
                          <button
                            onClick={handleRemoveFile}
                            className="p-1 hover:bg-accent rounded-lg text-muted-foreground hover:text-red-500 transition-colors"
                            title="移除文件"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Parse status */}
                    {isParsing && (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        正在解析文件内容...
                      </div>
                    )}

                    {parseError && (
                      <div className="flex items-center gap-2 text-sm text-red-600">
                        <AlertCircle className="w-4 h-4" />
                        {parseError}
                      </div>
                    )}

                    {/* Content preview */}
                    {parsedPreview && (
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 text-sm text-emerald-600">
                          <CheckCircle2 className="w-4 h-4" />
                          文件解析成功，已提取正文
                        </div>
                        <div className="bg-muted rounded-lg p-3 max-h-40 overflow-y-auto">
                          <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-all">
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
                <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <FileText className="w-4 h-4" /> 标签与分类
                </h4>

                <div>
                  <label className="block text-sm text-muted-foreground mb-1">关键词</label>
                  <div className="flex items-center gap-2 mb-2">
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
                      className="flex-1 px-3 py-2 border border-border rounded-lg bg-muted focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all text-sm"
                    />
                    <button
                      onClick={handleAddKeyword}
                      className="p-2 hover:bg-accent rounded-lg border border-border"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  {formData.keywords.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {formData.keywords.map((kw) => (
                        <span
                          key={kw}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-muted text-sm rounded"
                        >
                          {kw}
                          <button
                            onClick={() => handleRemoveKeyword(kw)}
                            className="hover:text-red-500"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm text-muted-foreground mb-1">
                    被引用法规（标准号）
                  </label>
                  <div className="flex items-center gap-2 mb-2">
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
                      className="flex-1 px-3 py-2 border border-border rounded-lg bg-muted focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all text-sm"
                    />
                    <button
                      onClick={handleAddReferredLaw}
                      className="p-2 hover:bg-accent rounded-lg border border-border"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                  {formData.referredLaws.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {formData.referredLaws.map((law) => (
                        <span
                          key={law}
                          className="inline-flex items-center gap-1 px-2 py-1 bg-muted text-sm rounded"
                        >
                          {law}
                          <button
                            onClick={() => handleRemoveReferredLaw(law)}
                            className="hover:text-red-500"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Error */}
              {error && (
                <div className="flex items-center gap-2 text-red-600 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  {error}
                </div>
              )}
            </div>
          )}

          {step === "uploading" && (
            <div className="flex flex-col items-center py-12">
              <Loader2 className="w-12 h-12 text-primary animate-spin mb-4" />
              <p className="text-lg font-medium text-foreground">正在导入...</p>
              <p className="text-sm text-muted-foreground mt-2">{progressLabel}</p>
              <div className="w-64 h-2 bg-muted rounded-full mt-4 overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {step === "completed" && (
            <div className="flex flex-col items-center py-12">
              <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                <FileText className="w-6 h-6 text-green-600" />
              </div>
              <p className="text-lg font-medium text-foreground">导入成功</p>
              <p className="text-sm text-muted-foreground mt-2">
                法规已成功添加到{" "}
                {getCategoryByCode(formData.lawType)?.name ?? formData.lawType}
              </p>
            </div>
          )}

          {step === "error" && (
            <div className="flex flex-col items-center py-12">
              <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mb-4">
                <AlertCircle className="w-6 h-6 text-red-600" />
              </div>
              <p className="text-lg font-medium text-foreground">导入失败</p>
              <p className="text-sm text-red-600 mt-2">{error}</p>
              <button
                onClick={() => setStep("form")}
                className="mt-4 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors"
              >
                重试
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        {step === "form" && (
          <div className="flex justify-end gap-3 p-4 border-t border-border shrink-0">
            <button
              onClick={onClose}
              className="px-4 py-2 text-foreground hover:bg-accent rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSubmit}
              disabled={importMutation.isPending}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {importMutation.isPending && (
                <Loader2 className="w-4 h-4 animate-spin" />
              )}
              开始导入
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
