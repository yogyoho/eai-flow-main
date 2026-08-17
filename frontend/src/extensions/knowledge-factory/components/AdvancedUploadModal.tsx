"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Upload,
  FileText,
  Database,
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Plus,
  Sparkles,
} from "lucide-react";
import React, { useState, useEffect, useRef } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { kfApi, kbApi } from "@/extensions/api";
import type {
  KnowledgeBase,
  ChunkConfig,
  KBBusinessType,
  ChunkMethod,
  SampleReport,
} from "@/extensions/types";

import { StyledRangeSlider } from "./StyledRangeSlider";

interface KBSelectOption extends KnowledgeBase {
  label: string;
  subLabel?: string;
}

interface AdvancedUploadModalProps {
  /** 业务类型 */
  businessType: KBBusinessType;
  /** 默认选中的知识库ID */
  defaultKbId?: string;
  /** 关闭回调 */
  onClose: () => void;
  /** 上传成功回调 */
  onSuccess: (reports: SampleReport[]) => void;
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

/** 推荐的工程报告分块配置 */
const ENGINEERING_REPORT_PRESET: ChunkConfig = {
  chunk_method: "report",
  report_type: "engineering_report",
  heading_depth: 3,
  include_page_index: true,
  preserve_tables: true,
  chunk_token_num: 128,
  ocr_enabled: true,
};

/** 推荐的法规标准分块配置 */
const LAWS_PRESET: ChunkConfig = {
  chunk_method: "laws",
  chunk_token_num: 256,
  preserve_tables: true,
};

/** 推荐的模板库分块配置 */
const TEMPLATE_PRESET: ChunkConfig = {
  chunk_method: "naive",
  chunk_token_num: 128,
};

const PRESETS: Record<KBBusinessType, ChunkConfig> = {
  sample_reports: ENGINEERING_REPORT_PRESET,
  laws_regulations: LAWS_PRESET,
  template_library: TEMPLATE_PRESET,
};

export default function AdvancedUploadModal({
  businessType,
  defaultKbId,
  onClose,
  onSuccess,
}: AdvancedUploadModalProps) {
  // 步骤状态
  const [step, setStep] = useState<"kb" | "config" | "upload">("kb");

  // 知识库相关
  const [kbOptions, setKbOptions] = useState<KBSelectOption[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>(defaultKbId ?? "");
  const [showKbDropdown, setShowKbDropdown] = useState(false);
  const [showNewKbForm, setShowNewKbForm] = useState(false);
  const [loadingKbs, setLoadingKbs] = useState(true);

  // 新建知识库表单
  const [newKbName, setNewKbName] = useState("");
  const [newKbDescription, setNewKbDescription] = useState("");
  const [creatingKb, setCreatingKb] = useState(false);

  // 分块配置
  const [chunkConfig, setChunkConfig] = useState<ChunkConfig>(
    PRESETS[businessType],
  );
  const [useRecommended, setUseRecommended] = useState(true);

  // 文件相关
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({
    current: 0,
    total: 0,
  });
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // 加载知识库列表
  useEffect(() => {
    void loadKnowledgeBases();
  }, []);

  const loadKnowledgeBases = async () => {
    setLoadingKbs(true);
    try {
      const res = await kbApi.list({ limit: 100 });
      setKbOptions(
        res.knowledge_bases.map((kb) => ({
          ...kb,
          label: kb.name,
          subLabel: `${kb.chunk_method || "naive"} · ${kb.id.slice(0, 8)}...`,
        })),
      );
    } catch {
      toast.error("加载知识库列表失败");
    } finally {
      setLoadingKbs(false);
    }
  };

  const handleCreateKb = async () => {
    if (!newKbName.trim()) {
      toast.error("请输入知识库名称");
      return;
    }
    setCreatingKb(true);
    try {
      const kb = await kfApi.createKnowledgeBase({
        name: newKbName,
        description: newKbDescription,
        kb_type: "ragflow",
      });
      const newOption: KBSelectOption = {
        ...kb,
        label: kb.name,
        subLabel: `${kb.chunk_method || "naive"} · ${kb.id.slice(0, 8)}...`,
      };
      setKbOptions((prev) => [newOption, ...prev]);
      setSelectedKbId(kb.id);
      setShowNewKbForm(false);
      setNewKbName("");
      setNewKbDescription("");
      toast.success("知识库创建成功");
    } catch (e) {
      toast.error(
        e instanceof Error && e.message ? e.message : "创建知识库失败",
      );
    } finally {
      setCreatingKb(false);
    }
  };

  const handleFilesChange = (newFiles: FileList | null) => {
    if (!newFiles) return;
    const validFiles = Array.from(newFiles).filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      return ["pdf", "docx", "doc", "txt", "md"].includes(ext ?? "");
    });
    if (validFiles.length < newFiles.length) {
      toast.info(
        `已过滤 ${newFiles.length - validFiles.length} 个不支持的文件`,
      );
    }
    setFiles((prev) => [...prev, ...validFiles]);
  };

  const handleUpload = async () => {
    if (!selectedKbId) {
      toast.error("请选择目标知识库");
      return;
    }
    if (files.length === 0) {
      toast.error("请选择要上传的文件");
      return;
    }

    setUploading(true);
    setUploadProgress({ current: 0, total: files.length });

    try {
      const results = await kfApi.uploadDocs(
        selectedKbId,
        files,
        chunkConfig,
        (current, total) => setUploadProgress({ current, total }),
      );
      toast.success(`成功上传 ${results.length} 个文件`);
      onSuccess(results);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const selectedKb = kbOptions.find((kb) => kb.id === selectedKbId);

  // ===== 步骤1: 选择知识库 =====
  const renderStepKB = () => (
    <div className="space-y-6">
      <div>
        <label className="text-foreground mb-2 block text-sm font-medium">
          选择知识库 <span className="text-red-500">*</span>
        </label>

        {/* 知识库选择下拉 */}
        <div className="relative">
          <button
            type="button"
            onClick={() => !loadingKbs && setShowKbDropdown(!showKbDropdown)}
            disabled={loadingKbs}
            className="border-input bg-background hover:border-primary/40 focus:border-primary focus:ring-primary/20 flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left shadow-sm transition-all focus:ring-2 disabled:opacity-50"
          >
            <span
              className={
                selectedKbId ? "text-foreground" : "text-muted-foreground"
              }
            >
              {selectedKbId
                ? kbOptions.find((o) => o.id === selectedKbId)?.label
                : loadingKbs
                  ? "加载中..."
                  : "选择已有知识库或创建新的..."}
            </span>
            {loadingKbs ? (
              <Loader2 className="text-muted-foreground h-5 w-5 animate-spin" />
            ) : (
              <ChevronDown
                className={cn(
                  "text-muted-foreground h-5 w-5 transition-transform",
                  showKbDropdown && "rotate-180",
                )}
              />
            )}
          </button>

          <AnimatePresence>
            {showKbDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="border-border bg-background absolute top-full right-0 left-0 z-[100] mt-2 max-h-64 overflow-auto rounded-xl border shadow-lg"
              >
                {kbOptions.length === 0 ? (
                  <div className="text-muted-foreground px-4 py-8 text-center text-sm">
                    暂无法知识库，请先创建
                  </div>
                ) : (
                  kbOptions.map((kb) => (
                    <button
                      key={kb.id}
                      type="button"
                      onClick={() => {
                        setSelectedKbId(kb.id);
                        setShowKbDropdown(false);
                      }}
                      className={cn(
                        "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors",
                        selectedKbId === kb.id
                          ? "bg-primary/10 text-primary"
                          : "hover:bg-muted/50",
                      )}
                    >
                      <Database className="text-primary mt-0.5 h-5 w-5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div
                          className={cn(
                            "font-medium",
                            selectedKbId === kb.id
                              ? "text-primary"
                              : "text-foreground",
                          )}
                        >
                          {kb.label}
                        </div>
                        {kb.subLabel && (
                          <div className="text-muted-foreground mt-0.5 text-xs">
                            {kb.subLabel}
                          </div>
                        )}
                      </div>
                      {selectedKbId === kb.id && (
                        <CheckCircle2 className="text-primary h-5 w-5 shrink-0" />
                      )}
                    </button>
                  ))
                )}
                <div className="border-border border-t" />
                <button
                  type="button"
                  onClick={() => {
                    setShowKbDropdown(false);
                    setShowNewKbForm(true);
                  }}
                  className="text-primary hover:bg-primary/10 flex w-full items-center gap-3 px-4 py-3 text-left transition-colors"
                >
                  <Plus className="h-5 w-5" />
                  <span className="font-medium">创建新知识库</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* 新建知识库表单 */}
      <AnimatePresence>
        {showNewKbForm && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="border-primary/50 bg-primary/10 text-primary/50 space-y-4 rounded-xl border p-5">
              <div className="text-primary flex items-center gap-2">
                <Plus className="h-5 w-5" />
                <h4 className="font-medium">创建新知识库</h4>
              </div>
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  知识库名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={newKbName}
                  onChange={(e) => setNewKbName(e.target.value)}
                  placeholder="例如：环评报告样例库"
                  className="border-input bg-background focus:border-primary focus:ring-primary/20 w-full rounded-lg border px-4 py-2.5 text-sm focus:ring-2"
                />
              </div>
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  描述
                </label>
                <textarea
                  value={newKbDescription}
                  onChange={(e) => setNewKbDescription(e.target.value)}
                  rows={2}
                  placeholder="简要描述该知识库的用途..."
                  className="border-input bg-background focus:border-primary focus:ring-primary/20 w-full resize-none rounded-lg border px-4 py-2.5 text-sm focus:ring-2"
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowNewKbForm(false)}
                  className="border-input bg-background text-foreground hover:bg-muted/50 rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleCreateKb}
                  disabled={!newKbName.trim() || creatingKb}
                  className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50"
                >
                  {creatingKb ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  创建
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  // ===== 步骤2: 分块配置 =====
  const renderStepConfig = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-foreground font-medium">分块策略配置</h4>
          <p className="text-muted-foreground mt-1 text-sm">
            RAGFlow 将按此配置解析和分块文档
          </p>
        </div>
        {/* 推荐配置开关 */}
        <label className="flex cursor-pointer items-center gap-2">
          <span
            className={cn(
              "text-sm",
              useRecommended
                ? "text-primary font-medium"
                : "text-muted-foreground",
            )}
          >
            推荐配置
          </span>
          <button
            type="button"
            onClick={() => setUseRecommended(!useRecommended)}
            className={cn(
              "relative h-6 w-11 rounded-full transition-colors",
              useRecommended ? "bg-primary" : "bg-input",
            )}
          >
            <span
              className={cn(
                "bg-background absolute top-0.5 left-0.5 h-5 w-5 rounded-full shadow transition-transform",
                useRecommended && "translate-x-5",
              )}
            />
          </button>
        </label>
      </div>

      {useRecommended ? (
        <div className="border-primary/50 bg-primary/10 text-primary/50 rounded-xl border p-4">
          <div className="flex items-start gap-3">
            <Sparkles className="text-primary mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <h5 className="text-primary font-medium">
                推荐：工程报告分块配置
              </h5>
              <p className="text-primary/80 mt-1 text-sm">
                自动按章节分块，识别 3
                级标题，保留页码溯源，适合环评报告、技术方案等工程文档。
              </p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            {[
              ["分块方式", "报告类 (report)"],
              ["标题深度", "3 级"],
              ["页码溯源", "启用"],
              ["OCR识别", "启用"],
            ].map(([k, v]) => (
              <div key={k} className="bg-background/80 rounded-lg px-3 py-2">
                <span className="text-muted-foreground">{k}: </span>
                <span className="text-foreground font-medium">{v}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* 分块方式 */}
          <div>
            <label className="text-foreground mb-1.5 block text-sm font-medium">
              分块方式
            </label>
            <AdminSelect
              value={chunkConfig.chunk_method}
              onChange={(v) =>
                setChunkConfig({
                  ...chunkConfig,
                  chunk_method: v as ChunkMethod,
                })
              }
              options={[
                { value: "naive", label: "简单分块" },
                { value: "report", label: "报告类（按章节）" },
                { value: "laws", label: "法律法规（按条款）" },
                { value: "paper", label: "学术论文" },
                { value: "book", label: "书籍" },
              ]}
              placeholder="选择分块方式"
              className="border-input bg-background w-full rounded-lg border px-4 py-2.5 text-sm"
            />
          </div>

          {/* 报告类特有配置 */}
          {chunkConfig.chunk_method === "report" && (
            <>
              <div>
                <label className="text-foreground mb-1.5 block text-sm font-medium">
                  报告类型
                </label>
                <AdminSelect
                  value={chunkConfig.report_type ?? "general"}
                  onChange={(v) =>
                    setChunkConfig({
                      ...chunkConfig,
                      report_type: v as "general" | "engineering_report",
                    })
                  }
                  options={[
                    { value: "general", label: "通用报告" },
                    { value: "engineering_report", label: "工程报告" },
                  ]}
                  placeholder="选择报告类型"
                  className="border-input bg-background w-full rounded-lg border px-4 py-2.5 text-sm"
                />
              </div>

              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  标题识别深度{" "}
                  <span className="bg-primary/10 text-primary ml-1 rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums">
                    H{chunkConfig.heading_depth ?? 3}
                  </span>
                </label>
                <StyledRangeSlider
                  min={1}
                  max={6}
                  step={1}
                  value={chunkConfig.heading_depth ?? 3}
                  onChange={(e) =>
                    setChunkConfig({
                      ...chunkConfig,
                      heading_depth: Number(e.target.value),
                    })
                  }
                  footer={
                    <div className="text-muted-foreground flex justify-between px-0.5 text-xs font-medium">
                      <span>H1</span>
                      <span>H6</span>
                    </div>
                  }
                />
              </div>
            </>
          )}

          {/* 通用配置 */}
          <div>
            <label className="text-foreground mb-1 block text-sm font-medium">
              每块 Token 数{" "}
              <span className="bg-primary/10 text-primary ml-1 rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums">
                {chunkConfig.chunk_token_num ?? 128}
              </span>
            </label>
            <StyledRangeSlider
              min={32}
              max={512}
              step={32}
              value={chunkConfig.chunk_token_num ?? 128}
              onChange={(e) =>
                setChunkConfig({
                  ...chunkConfig,
                  chunk_token_num: Number(e.target.value),
                })
              }
              footer={
                <div className="text-muted-foreground flex justify-between px-0.5 text-xs font-medium">
                  <span>32</span>
                  <span>512</span>
                </div>
              }
            />
          </div>

          {/* 开关选项 */}
          <div className="space-y-3">
            {[
              {
                key: "include_page_index" as const,
                label: "页码溯源",
                desc: "保留页码信息用于定位",
              },
              {
                key: "preserve_tables" as const,
                label: "保留表格",
                desc: "表格作为独立块",
              },
              {
                key: "ocr_enabled" as const,
                label: "OCR识别",
                desc: "启用图像文字识别",
              },
            ].map(
              ({
                key,
                label,
                desc,
              }: {
                key: "include_page_index" | "preserve_tables" | "ocr_enabled";
                label: string;
                desc: string;
              }) => (
                <label
                  key={key}
                  className="border-border bg-background flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3"
                >
                  <div>
                    <span className="text-foreground font-medium">{label}</span>
                    <span className="text-muted-foreground ml-2 text-sm">
                      ({desc})
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setChunkConfig({
                        ...chunkConfig,
                        [key]: !chunkConfig[key],
                      })
                    }
                    className={cn(
                      "relative h-6 w-11 rounded-full transition-colors",
                      chunkConfig[key] !== false ? "bg-primary" : "bg-input",
                    )}
                  >
                    <span
                      className={cn(
                        "bg-background absolute top-0.5 left-0.5 h-5 w-5 rounded-full shadow transition-transform",
                        chunkConfig[key] !== false && "translate-x-5",
                      )}
                    />
                  </button>
                </label>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );

  // ===== 步骤3: 上传文件 =====
  const renderStepUpload = () => (
    <div className="space-y-6">
      {/* 拖拽上传区 */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFilesChange(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-all",
          dragOver
            ? "border-primary/40 bg-primary/10 text-primary"
            : "border-border hover:border-primary/40 hover:bg-muted/50",
        )}
      >
        <Upload className="text-muted-foreground mx-auto mb-3 h-10 w-10" />
        <p className="text-foreground text-sm font-medium">
          拖拽文件到此处，或点击选择
        </p>
        <p className="text-muted-foreground mt-1 text-xs">
          支持 PDF、Word、TXT、Markdown 格式
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.txt,.md"
          className="hidden"
          onChange={(e) => handleFilesChange(e.target.files)}
        />
      </div>

      {/* 文件列表 */}
      {files.length > 0 && (
        <div className="border-border bg-muted/50 max-h-48 space-y-2 overflow-auto rounded-lg border p-3">
          {files.map((f, i) => (
            <div
              key={i}
              className="bg-background flex items-center justify-between rounded-lg px-3 py-2 shadow-sm"
            >
              <div className="flex min-w-0 items-center gap-3">
                <FileText className="text-primary h-5 w-5 shrink-0" />
                <span className="text-foreground truncate text-sm">
                  {f.name}
                </span>
              </div>
              <button
                type="button"
                onClick={() =>
                  setFiles((prev) => prev.filter((_, j) => j !== i))
                }
                className="text-muted-foreground shrink-0 p-1 transition-colors hover:text-red-500"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 上传进度 */}
      {uploading && (
        <div className="border-primary/50 bg-primary/10 text-primary/50 rounded-lg border p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-primary text-sm font-medium">
              上传中... ({uploadProgress.current}/{uploadProgress.total})
            </span>
            <Loader2 className="text-primary h-5 w-5 animate-spin" />
          </div>
          <div className="bg-primary/10 h-2 overflow-hidden rounded-full">
            <div
              className="bg-primary h-full transition-all duration-300"
              style={{
                width: `${(uploadProgress.current / uploadProgress.total) * 100}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  );

  // ===== 步骤指示器 =====
  const steps = [
    { key: "kb", label: "选择知识库" },
    { key: "config", label: "分块配置" },
    { key: "upload", label: "上传文件" },
  ];

  const currentStepIndex = steps.findIndex((s) => s.key === step);

  return (
    <div className="fixed inset-0 z-50 overflow-x-hidden overflow-y-auto">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative flex min-h-full items-start justify-center p-4 py-10 sm:p-6 sm:py-12">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="bg-background relative z-10 w-full max-w-2xl overflow-visible rounded-2xl shadow-2xl"
        >
          {/* Header — overflow-visible 时由首尾区块承担圆角 */}
          <div className="border-border bg-background flex items-center justify-between rounded-t-2xl border-b px-6 py-4">
            <div>
              <h3 className="text-foreground text-lg font-semibold">
                {businessType === "sample_reports"
                  ? "上传样例报告"
                  : businessType === "laws_regulations"
                    ? "上传法规标准"
                    : "上传模板"}
              </h3>
              <p className="text-muted-foreground mt-0.5 text-sm">
                {businessType === "sample_reports"
                  ? "上传工程报告样例到知识库"
                  : "上传文档到知识库"}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-muted-foreground hover:bg-accent hover:text-foreground rounded-lg p-2 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Step Indicator */}
          <div className="border-border bg-muted flex border-b px-6 py-3">
            {steps.map((s, i) => (
              <div key={s.key} className="flex items-center">
                {i > 0 && (
                  <ChevronRight className="text-muted-foreground mx-2 h-4 w-4" />
                )}
                <button
                  type="button"
                  onClick={() => {
                    // 只允许返回上一步或点击已完成步骤
                    const targetIndex = steps.findIndex((x) => x.key === s.key);
                    if (targetIndex < currentStepIndex || !selectedKbId) {
                      if (targetIndex === 0) setStep("kb");
                      else if (targetIndex === 1 && selectedKbId)
                        setStep("config");
                      else if (targetIndex === 2 && selectedKbId)
                        setStep("upload");
                    }
                  }}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    step === s.key
                      ? "bg-primary/10 text-primary"
                      : currentStepIndex > i
                        ? "text-muted-foreground hover:bg-accent cursor-pointer"
                        : "text-muted-foreground cursor-not-allowed",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full text-xs",
                      step === s.key
                        ? "bg-primary text-white"
                        : currentStepIndex > i
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground",
                    )}
                  >
                    {currentStepIndex > i ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      i + 1
                    )}
                  </span>
                  {s.label}
                </button>
              </div>
            ))}
          </div>

          {/* Content：步骤1 不设内部滚动，下拉可自然增高；整页由最外层 overflow-y-auto 承载 */}
          <div className="relative z-10 p-6">
            {step === "kb" && renderStepKB()}
            {step === "config" && (
              <div className="max-h-[min(70vh,720px)] overflow-x-hidden overflow-y-auto pr-1 [-webkit-overflow-scrolling:touch]">
                {renderStepConfig()}
              </div>
            )}
            {step === "upload" && renderStepUpload()}
          </div>

          {/* Footer */}
          <div className="border-border bg-muted/50 relative z-0 flex items-center justify-between rounded-b-2xl border-t px-6 py-4">
            <div>
              {selectedKb && (
                <span className="text-muted-foreground text-sm">
                  目标知识库:{" "}
                  <span className="text-foreground font-medium">
                    {selectedKb.name}
                  </span>
                </span>
              )}
            </div>
            <div className="flex gap-3">
              {step !== "kb" && (
                <button
                  type="button"
                  onClick={() => {
                    if (step === "config") setStep("kb");
                    else if (step === "upload") setStep("config");
                  }}
                  className="border-input bg-background text-foreground hover:bg-muted/50 rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
                >
                  上一步
                </button>
              )}
              {step === "kb" && (
                <button
                  type="button"
                  onClick={() => selectedKbId && setStep("config")}
                  disabled={!selectedKbId}
                  className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50"
                >
                  下一步
                  <ChevronRight className="h-4 w-4" />
                </button>
              )}
              {step === "config" && (
                <button
                  type="button"
                  onClick={() => setStep("upload")}
                  className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors"
                >
                  下一步
                  <ChevronRight className="h-4 w-4" />
                </button>
              )}
              {step === "upload" && (
                <button
                  type="button"
                  onClick={handleUpload}
                  disabled={!files.length || uploading}
                  className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      上传中...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4" />
                      开始上传
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
