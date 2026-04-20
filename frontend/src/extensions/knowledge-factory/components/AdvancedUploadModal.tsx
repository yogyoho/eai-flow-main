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

import { kfApi, kbApi } from "@/extensions/api";
import type { KnowledgeBase, ChunkConfig, KBBusinessType, ChunkMethod, SampleReport } from "@/extensions/types";

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
  /** Toast提示 */
  onToast: (message: string, type: "success" | "error" | "info") => void;
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
  onToast,
}: AdvancedUploadModalProps) {
  // 步骤状态
  const [step, setStep] = useState<"kb" | "config" | "upload">("kb");
  
  // 知识库相关
  const [kbOptions, setKbOptions] = useState<KBSelectOption[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>(defaultKbId || "");
  const [showKbDropdown, setShowKbDropdown] = useState(false);
  const [showNewKbForm, setShowNewKbForm] = useState(false);
  const [loadingKbs, setLoadingKbs] = useState(true);
  
  // 新建知识库表单
  const [newKbName, setNewKbName] = useState("");
  const [newKbDescription, setNewKbDescription] = useState("");
  const [creatingKb, setCreatingKb] = useState(false);
  
  // 分块配置
  const [chunkConfig, setChunkConfig] = useState<ChunkConfig>(PRESETS[businessType]);
  const [useRecommended, setUseRecommended] = useState(true);
  
  // 文件相关
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ current: 0, total: 0 });
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // 加载知识库列表
  useEffect(() => {
    loadKnowledgeBases();
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
        }))
      );
    } catch (e) {
      onToast("加载知识库列表失败", "error");
    } finally {
      setLoadingKbs(false);
    }
  };

  const handleCreateKb = async () => {
    if (!newKbName.trim()) {
      onToast("请输入知识库名称", "error");
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
      onToast("知识库创建成功", "success");
    } catch (e: any) {
      onToast(e.message || "创建知识库失败", "error");
    } finally {
      setCreatingKb(false);
    }
  };

  const handleFilesChange = (newFiles: FileList | null) => {
    if (!newFiles) return;
    const validFiles = Array.from(newFiles).filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      return ["pdf", "docx", "doc", "txt", "md"].includes(ext || "");
    });
    if (validFiles.length < newFiles.length) {
      onToast(`已过滤 ${newFiles.length - validFiles.length} 个不支持的文件`, "info");
    }
    setFiles((prev) => [...prev, ...validFiles]);
  };

  const handleUpload = async () => {
    if (!selectedKbId) {
      onToast("请选择目标知识库", "error");
      return;
    }
    if (files.length === 0) {
      onToast("请选择要上传的文件", "error");
      return;
    }

    setUploading(true);
    setUploadProgress({ current: 0, total: files.length });

    try {
      const results = await kfApi.uploadDocs(
        selectedKbId,
        files,
        useRecommended ? undefined : chunkConfig,
        (current, total) => setUploadProgress({ current, total })
      );
      onToast(`成功上传 ${results.length} 个文件`, "success");
      onSuccess(results);
      onClose();
    } catch (e: any) {
      onToast(e.message || "上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  const selectedKb = kbOptions.find((kb) => kb.id === selectedKbId);

  // ===== 步骤1: 选择知识库 =====
  const renderStepKB = () => (
    <div className="space-y-6">
      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">
          选择知识库 <span className="text-red-500">*</span>
        </label>

        {/* 知识库选择下拉 */}
        <div className="relative">
          <button
            type="button"
            onClick={() => !loadingKbs && setShowKbDropdown(!showKbDropdown)}
            disabled={loadingKbs}
            className="flex w-full items-center justify-between rounded-lg border border-gray-300 bg-white px-4 py-3 text-left shadow-sm transition-all hover:border-indigo-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-50"
          >
            <span className={selectedKbId ? "text-gray-900" : "text-gray-400"}>
              {selectedKbId
                ? kbOptions.find((o) => o.id === selectedKbId)?.label
                : loadingKbs
                  ? "加载中..."
                  : "选择已有知识库或创建新的..."}
            </span>
            {loadingKbs ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            ) : (
              <ChevronDown
                className={cn(
                  "h-5 w-5 text-gray-400 transition-transform",
                  showKbDropdown && "rotate-180"
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
                className="absolute top-full left-0 right-0 z-[100] mt-2 max-h-64 overflow-auto rounded-xl border border-gray-200 bg-white shadow-lg"
              >
                {kbOptions.length === 0 ? (
                  <div className="px-4 py-8 text-center text-sm text-gray-500">
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
                          ? "bg-indigo-50"
                          : "hover:bg-gray-50"
                      )}
                    >
                      <Database className="mt-0.5 h-5 w-5 shrink-0 text-indigo-500" />
                      <div className="min-w-0 flex-1">
                        <div
                          className={cn(
                            "font-medium",
                            selectedKbId === kb.id ? "text-indigo-700" : "text-gray-900"
                          )}
                        >
                          {kb.label}
                        </div>
                        {kb.subLabel && (
                          <div className="mt-0.5 text-xs text-gray-500">{kb.subLabel}</div>
                        )}
                      </div>
                      {selectedKbId === kb.id && (
                        <CheckCircle2 className="h-5 w-5 shrink-0 text-indigo-500" />
                      )}
                    </button>
                  ))
                )}
                <div className="border-t border-gray-100" />
                <button
                  type="button"
                  onClick={() => {
                    setShowKbDropdown(false);
                    setShowNewKbForm(true);
                  }}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left text-indigo-600 transition-colors hover:bg-indigo-50"
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
            <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-5 space-y-4">
              <div className="flex items-center gap-2 text-indigo-700">
                <Plus className="h-5 w-5" />
                <h4 className="font-medium">创建新知识库</h4>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  知识库名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={newKbName}
                  onChange={(e) => setNewKbName(e.target.value)}
                  placeholder="例如：环评报告样例库"
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">描述</label>
                <textarea
                  value={newKbDescription}
                  onChange={(e) => setNewKbDescription(e.target.value)}
                  rows={2}
                  placeholder="简要描述该知识库的用途..."
                  className="w-full resize-none rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowNewKbForm(false)}
                  className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleCreateKb}
                  disabled={!newKbName.trim() || creatingKb}
                  className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
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
          <h4 className="font-medium text-gray-900">分块策略配置</h4>
          <p className="mt-1 text-sm text-gray-500">RAGFlow 将按此配置解析和分块文档</p>
        </div>
        {/* 推荐配置开关 */}
        <label className="flex items-center gap-2 cursor-pointer">
          <span className={cn("text-sm", useRecommended ? "text-indigo-600 font-medium" : "text-gray-500")}>
            推荐配置
          </span>
          <button
            type="button"
            onClick={() => setUseRecommended(!useRecommended)}
            className={cn(
              "relative h-6 w-11 rounded-full transition-colors",
              useRecommended ? "bg-indigo-600" : "bg-gray-300"
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
                useRecommended && "translate-x-5"
              )}
            />
          </button>
        </label>
      </div>

      {useRecommended ? (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-indigo-500" />
            <div>
              <h5 className="font-medium text-indigo-700">推荐：工程报告分块配置</h5>
              <p className="mt-1 text-sm text-indigo-600/80">
                自动按章节分块，识别 3 级标题，保留页码溯源，适合环评报告、技术方案等工程文档。
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
              <div key={k} className="rounded-lg bg-white/80 px-3 py-2">
                <span className="text-gray-500">{k}: </span>
                <span className="font-medium text-gray-900">{v}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {/* 分块方式 */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">分块方式</label>
            <select
              value={chunkConfig.chunk_method}
              onChange={(e) =>
                setChunkConfig({ ...chunkConfig, chunk_method: e.target.value as ChunkMethod })
              }
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            >
              <option value="naive">简单分块</option>
              <option value="report">报告类（按章节）</option>
              <option value="laws">法律法规（按条款）</option>
              <option value="paper">学术论文</option>
              <option value="book">书籍</option>
            </select>
          </div>

          {/* 报告类特有配置 */}
          {chunkConfig.chunk_method === "report" && (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">报告类型</label>
                <select
                  value={chunkConfig.report_type || "general"}
                  onChange={(e) =>
                    setChunkConfig({
                      ...chunkConfig,
                      report_type: e.target.value as "general" | "engineering_report",
                    })
                  }
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                >
                  <option value="general">通用</option>
                  <option value="engineering_report">工程报告</option>
                </select>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-zinc-700">
                  标题识别深度{" "}
                  <span className="ml-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 tabular-nums">
                    H{chunkConfig.heading_depth || 3}
                  </span>
                </label>
                <StyledRangeSlider
                  min={1}
                  max={6}
                  step={1}
                  value={chunkConfig.heading_depth || 3}
                  onChange={(e) =>
                    setChunkConfig({ ...chunkConfig, heading_depth: Number(e.target.value) })
                  }
                  footer={
                    <div className="flex justify-between px-0.5 text-xs font-medium text-zinc-500">
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
            <label className="mb-1 block text-sm font-medium text-zinc-700">
              每块 Token 数{" "}
              <span className="ml-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 tabular-nums">
                {chunkConfig.chunk_token_num || 128}
              </span>
            </label>
            <StyledRangeSlider
              min={32}
              max={512}
              step={32}
              value={chunkConfig.chunk_token_num || 128}
              onChange={(e) =>
                setChunkConfig({ ...chunkConfig, chunk_token_num: Number(e.target.value) })
              }
              footer={
                <div className="flex justify-between px-0.5 text-xs font-medium text-zinc-500">
                  <span>32</span>
                  <span>512</span>
                </div>
              }
            />
          </div>

          {/* 开关选项 */}
          <div className="space-y-3">
            {[
              { key: "include_page_index", label: "页码溯源", desc: "保留页码信息用于定位" },
              { key: "preserve_tables", label: "保留表格", desc: "表格作为独立块" },
              { key: "ocr_enabled", label: "OCR识别", desc: "启用图像文字识别" },
            ].map(({ key, label, desc }) => (
              <label
                key={key}
                className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 cursor-pointer"
              >
                <div>
                  <span className="font-medium text-gray-900">{label}</span>
                  <span className="ml-2 text-sm text-gray-500">({desc})</span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setChunkConfig({ ...chunkConfig, [key]: !(chunkConfig as any)[key] })
                  }
                  className={cn(
                    "relative h-6 w-11 rounded-full transition-colors",
                    (chunkConfig as any)[key] !== false ? "bg-indigo-600" : "bg-gray-300"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
                      (chunkConfig as any)[key] !== false && "translate-x-5"
                    )}
                  />
                </button>
              </label>
            ))}
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
            ? "border-indigo-400 bg-indigo-50"
            : "border-gray-200 hover:border-indigo-300 hover:bg-gray-50"
        )}
      >
        <Upload className="mx-auto mb-3 h-10 w-10 text-gray-300" />
        <p className="text-sm font-medium text-gray-700">拖拽文件到此处，或点击选择</p>
        <p className="mt-1 text-xs text-gray-400">支持 PDF、Word、TXT、Markdown 格式</p>
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
        <div className="max-h-48 space-y-2 overflow-auto rounded-lg border border-gray-200 bg-gray-50 p-3">
          {files.map((f, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg bg-white px-3 py-2 shadow-sm"
            >
              <div className="flex items-center gap-3 min-w-0">
                <FileText className="h-5 w-5 shrink-0 text-indigo-500" />
                <span className="truncate text-sm text-gray-700">{f.name}</span>
              </div>
              <button
                type="button"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                className="shrink-0 p-1 text-gray-400 hover:text-red-500 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 上传进度 */}
      {uploading && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-indigo-700">
              上传中... ({uploadProgress.current}/{uploadProgress.total})
            </span>
            <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
          </div>
          <div className="h-2 bg-indigo-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-600 transition-all duration-300"
              style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }}
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
    <div className="fixed inset-0 z-50 overflow-y-auto overflow-x-hidden">
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
          className="relative z-10 w-full max-w-2xl overflow-visible rounded-2xl bg-white shadow-2xl"
        >
        {/* Header — overflow-visible 时由首尾区块承担圆角 */}
        <div className="flex items-center justify-between rounded-t-2xl border-b border-gray-100 bg-white px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              {businessType === "sample_reports"
                ? "上传样例报告"
                : businessType === "laws_regulations"
                  ? "上传法规标准"
                  : "上传模板"}
            </h3>
            <p className="mt-0.5 text-sm text-gray-500">
              {businessType === "sample_reports"
                ? "上传工程报告样例到知识库"
                : "上传文档到知识库"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Step Indicator */}
        <div className="flex border-b border-gray-100 px-6 py-3 bg-gray-50/50">
          {steps.map((s, i) => (
            <div key={s.key} className="flex items-center">
              {i > 0 && <ChevronRight className="mx-2 h-4 w-4 text-gray-300" />}
              <button
                type="button"
                onClick={() => {
                  // 只允许返回上一步或点击已完成步骤
                  const targetIndex = steps.findIndex((x) => x.key === s.key);
                  if (targetIndex < currentStepIndex || !selectedKbId) {
                    if (targetIndex === 0) setStep("kb");
                    else if (targetIndex === 1 && selectedKbId) setStep("config");
                    else if (targetIndex === 2 && selectedKbId) setStep("upload");
                  }
                }}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  step === s.key
                    ? "bg-indigo-100 text-indigo-700"
                    : currentStepIndex > i
                      ? "text-gray-500 hover:bg-gray-100 cursor-pointer"
                      : "text-gray-400 cursor-not-allowed"
                )}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full text-xs",
                    step === s.key
                      ? "bg-indigo-600 text-white"
                      : currentStepIndex > i
                        ? "bg-indigo-200 text-indigo-700"
                        : "bg-gray-200 text-gray-500"
                  )}
                >
                  {currentStepIndex > i ? <CheckCircle2 className="h-3 w-3" /> : i + 1}
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
            <div className="max-h-[min(70vh,720px)] overflow-y-auto overflow-x-hidden pr-1 [-webkit-overflow-scrolling:touch]">
              {renderStepConfig()}
            </div>
          )}
          {step === "upload" && renderStepUpload()}
        </div>

        {/* Footer */}
        <div className="relative z-0 flex items-center justify-between rounded-b-2xl border-t border-gray-100 bg-gray-50 px-6 py-4">
          <div>
            {selectedKb && (
              <span className="text-sm text-gray-500">
                目标知识库:{" "}
                <span className="font-medium text-gray-700">{selectedKb.name}</span>
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
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                上一步
              </button>
            )}
            {step === "kb" && (
              <button
                type="button"
                onClick={() => selectedKbId && setStep("config")}
                disabled={!selectedKbId}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
              >
                下一步
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
            {step === "config" && (
              <button
                type="button"
                onClick={() => setStep("upload")}
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700"
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
                className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
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
