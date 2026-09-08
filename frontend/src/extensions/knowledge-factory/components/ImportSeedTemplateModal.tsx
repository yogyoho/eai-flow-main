"use client";

// EAI-CUSTOM: coal-eia v2 D12——从 stage seed JSON 导入模板的对话框。
// seed 是 seed_gen.py 从 stage JSON 单向派生的模板工件；粘贴 JSON 或选文件，
// 前端先解析出章/节计数预览，确认后调 POST /api/kf/templates/import-seed。

import {
  AlertCircle,
  CheckCircle2,
  FileJson,
  Loader2,
  Upload,
  X,
} from "lucide-react";
import React, { useRef, useState } from "react";
import { toast } from "sonner";

import { kfApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

export interface ImportSeedResult {
  id: string;
  name: string;
  status: string;
  sections_count: number;
  storage_note?: string;
}

interface ImportSeedTemplateModalProps {
  onClose: () => void;
  onSuccess: (result: ImportSeedResult) => void;
}

interface SeedPreview {
  chapters: number;
  leafSections: number;
  totalNodes: number;
  suggestedName: string;
  suggestedDomain: string;
  version: string;
  stage: string;
}

/** 递归统计章节树：章数=顶层节点数，节数=叶节点数，总节点数=扁平总数 */
function countTree(sections: unknown[]): {
  chapters: number;
  leafSections: number;
  totalNodes: number;
} {
  let totalNodes = 0;
  let leafSections = 0;

  const walk = (node: Record<string, unknown>) => {
    totalNodes += 1;
    const children = Array.isArray(node.children) ? node.children : [];
    if (children.length === 0) leafSections += 1; // 叶节点=节（裸章按 1 节计）
    for (const child of children) {
      if (child && typeof child === "object")
        walk(child as Record<string, unknown>);
    }
  };

  for (const sec of sections) {
    if (sec && typeof sec === "object") walk(sec as Record<string, unknown>);
  }
  return { chapters: sections.length, leafSections, totalNodes };
}

/** 客户端预解析：只做形状检查与计数预览，权威校验在后端（TemplateSection 真模型） */
function parseSeed(text: string): {
  seed: Record<string, unknown>;
  preview: SeedPreview;
} {
  let seed: Record<string, unknown>;
  try {
    seed = JSON.parse(text);
  } catch {
    throw new Error("JSON 解析失败：内容不是合法 JSON");
  }
  if (!seed || typeof seed !== "object" || Array.isArray(seed)) {
    throw new Error("seed 必须是 JSON 对象");
  }
  const rootJson = seed.root_sections_json as
    | Record<string, unknown>
    | undefined;
  const sections = rootJson?.sections;
  if (!Array.isArray(sections) || sections.length === 0) {
    throw new Error("root_sections_json.sections 必须为非空数组");
  }

  const counts = countTree(sections);
  const template = (seed.template ?? {}) as Record<string, unknown>;
  const metadata = (seed.metadata ?? {}) as Record<string, unknown>;

  return {
    seed,
    preview: {
      chapters: counts.chapters,
      leafSections: counts.leafSections,
      totalNodes: counts.totalNodes,
      suggestedName: typeof template.name === "string" ? template.name : "",
      suggestedDomain:
        typeof template.domain === "string" ? template.domain : "",
      version: typeof template.version === "string" ? template.version : "v1.0",
      stage: typeof metadata.stage === "string" ? metadata.stage : "",
    },
  };
}

export default function ImportSeedTemplateModal({
  onClose,
  onSuccess,
}: ImportSeedTemplateModalProps) {
  const [rawText, setRawText] = useState("");
  const [preview, setPreview] = useState<SeedPreview | null>(null);
  const [parsedSeed, setParsedSeed] = useState<Record<string, unknown> | null>(
    null,
  );
  const [parseError, setParseError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [publish, setPublish] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const applyParse = (text: string) => {
    setRawText(text);
    setParseError(null);
    setPreview(null);
    setParsedSeed(null);
    if (!text.trim()) return;
    try {
      const { seed, preview: p } = parseSeed(text);
      setParsedSeed(seed);
      setPreview(p);
      if (!name) setName(p.suggestedName);
      if (!domain) setDomain(p.suggestedDomain);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "seed 解析失败");
    }
  };

  const handleFileSelect = (file: File | undefined) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = typeof reader.result === "string" ? reader.result : "";
      applyParse(text);
    };
    reader.onerror = () => setParseError(`读取文件失败: ${file.name}`);
    reader.readAsText(file);
  };

  const canSubmit = Boolean(
    parsedSeed && preview && name.trim() && domain.trim() && !submitting,
  );

  const handleImport = async () => {
    if (!parsedSeed || !canSubmit) return;
    setSubmitting(true);
    setImportError(null);
    try {
      const result = await kfApi.importSeedTemplate({
        seed: parsedSeed,
        name: name.trim(),
        domain: domain.trim(),
        publish,
      });
      toast.success(
        `seed 模板导入成功：${result.name}（${result.status === "published" ? "已发布" : "草稿"}，${result.sections_count} 个章节节点）`,
      );
      onSuccess(result);
    } catch (e) {
      // kfRequest 已把后端 detail（409 同名 / 422 校验失败）提取为 message
      const msg = e instanceof Error ? e.message : "导入失败";
      setImportError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div className="bg-background flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="border-border flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2">
            <FileJson className="text-primary h-5 w-5" />
            <h3 className="text-foreground text-lg font-semibold">
              导入 seed 模板
            </h3>
          </div>
          <button
            onClick={onClose}
            className="hover:bg-accent rounded-lg p-1.5 transition-colors"
          >
            <X className="text-muted-foreground h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <p className="text-muted-foreground text-sm">
            粘贴 seed JSON（由环评技能 seed_gen 从 stage
            生成，kind=kf_template_seed），或选择本地 .json 文件。
          </p>

          {/* File picker */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors"
            >
              <Upload className="h-4 w-4" />
              选择 JSON 文件
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => {
                handleFileSelect(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </div>

          {/* Paste area */}
          <textarea
            value={rawText}
            onChange={(e) => applyParse(e.target.value)}
            rows={8}
            spellCheck={false}
            placeholder={`{\n  "kind": "kf_template_seed",\n  "metadata": { ... },\n  "template": { "domain": "...", "name": "..." },\n  "root_sections_json": { "sections": [ ... ] }\n}`}
            className="border-input focus:ring-primary/30 focus:border-primary w-full resize-y rounded-lg border px-3 py-2 font-mono text-xs focus:ring-2 focus:outline-none"
          />

          {parseError && (
            <div className="text-destructive bg-destructive/10 flex items-start gap-2 rounded-lg px-3 py-2 text-sm">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {parseError}
            </div>
          )}

          {/* Preview */}
          {preview && (
            <div className="border-border bg-muted/30 space-y-2 rounded-lg border px-4 py-3">
              <div className="text-foreground flex items-center gap-2 text-sm font-medium">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                解析成功
                {preview.stage && (
                  <span className="text-muted-foreground font-normal">
                    · 阶段：{preview.stage}
                  </span>
                )}
              </div>
              <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
                <span>
                  章 <b className="text-foreground">{preview.chapters}</b>
                </span>
                <span>
                  节 <b className="text-foreground">{preview.leafSections}</b>
                </span>
                <span>
                  章节节点合计{" "}
                  <b className="text-foreground">{preview.totalNodes}</b>
                </span>
                <span>
                  版本 <b className="text-foreground">{preview.version}</b>
                </span>
              </div>
            </div>
          )}

          {/* Name / domain / publish */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-foreground text-sm font-medium">
                模板名称
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="缺省取 seed.template.name"
                className="border-input focus:ring-primary/30 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
              />
            </div>
            <div className="space-y-2">
              <label className="text-foreground text-sm font-medium">
                业务领域
              </label>
              <input
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="缺省取 seed.template.domain"
                className="border-input focus:ring-primary/30 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
              />
            </div>
          </div>
          <label className="text-foreground flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={publish}
              onChange={(e) => setPublish(e.target.checked)}
              className="border-input h-4 w-4 accent-[var(--primary)]"
            />
            导入后直接发布（默认存为草稿）
          </label>

          {importError && (
            <div className="text-destructive bg-destructive/10 flex items-start gap-2 rounded-lg px-3 py-2 text-sm">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {importError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-border flex justify-end gap-3 border-t px-6 py-4">
          <button
            onClick={onClose}
            className="border-border hover:bg-accent rounded-lg border px-4 py-2 text-sm transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleImport}
            disabled={!canSubmit}
            className={cn(
              "bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileJson className="h-4 w-4" />
            )}
            导入
          </button>
        </div>
      </div>
    </div>
  );
}
