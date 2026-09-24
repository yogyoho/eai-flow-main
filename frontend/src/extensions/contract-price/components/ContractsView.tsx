"use client";

import { useQueryClient } from "@tanstack/react-query";
import { zhCN } from "date-fns/locale";
import {
  AlertTriangle,
  ArrowRight,
  CalendarIcon,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  FileSearch,
  FileUp,
  FolderOpen,
  Inbox,
  Layers,
  FileText,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { contractPriceApi } from "@/extensions/contract-price/api";
import {
  ContractSourceDialog,
  type ContractSourceDoc,
} from "@/extensions/contract-price/components/ContractSourceDialog";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import type { SeedDraft } from "@/extensions/contract-price/components/SeedEditorDrawer";
import { UnmatchedTablesDrawer } from "@/extensions/contract-price/components/UnmatchedTablesDrawer";
import {
  useConfig,
  useDocuments,
  useReparseDocument,
  useRunCluster,
  useRunPipeline,
  useUpdateConfig,
  useUpdateDocument,
} from "@/extensions/contract-price/hooks";
import type { UnmatchedTable } from "@/extensions/contract-price/types";

/** Unified doc lifecycle stage. No confirm gate — parsed docs go straight to
 * "已解析", then cluster run advances to "已分组". `tone` is a full badge
 * class set (text/border/bg) for the collapsed-row status chip. */
function docStage(doc: { parse_status: string; confirm_status: string }): {
  label: string;
  tone: string;
  pending: boolean;
} {
  if (doc.confirm_status === "clustered")
    return {
      label: "已分组",
      tone: "text-blue-600 border-blue-500/30 bg-blue-500/5",
      pending: false,
    };
  if (doc.parse_status === "failed")
    return {
      label: "解析失败",
      tone: "text-destructive border-destructive/30 bg-destructive/5",
      pending: false,
    };
  if (doc.parse_status === "pending")
    return {
      label: "已上传",
      tone: "text-muted-foreground border-muted-foreground/30 bg-muted-foreground/5",
      pending: false,
    };
  if (doc.parse_status === "parsing")
    return {
      label: "解析中",
      tone: "text-primary border-primary/30 bg-primary/5",
      pending: false,
    };
  if (doc.parse_status === "no_tables")
    return {
      label: "无价格表",
      tone: "text-muted-foreground border-muted-foreground/30 bg-muted-foreground/5",
      pending: false,
    };
  if (doc.parse_status === "needs_review")
    return {
      label: "待人工核验",
      tone: "text-amber-600 border-amber-500/30 bg-amber-500/5",
      pending: false,
    };
  return {
    label: "已解析",
    tone: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5",
    pending: false,
  };
}

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

/** Labeled field cell for the expanded 合同记录 panel. */
function DocField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <span className="text-muted-foreground block text-xs">{label}</span>
      {children}
    </div>
  );
}

/** Bordered full-width input for the 合同记录 panel; commits on blur/Enter.
 * Manual补 fallback for project fields the front-page OCR regex missed. */
function ProjectFieldInput({
  value,
  placeholder,
  onCommit,
}: {
  value: string | null;
  placeholder: string;
  onCommit: (v: string) => void;
}) {
  const [draft, setDraft] = useState(value ?? "");
  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);
  const commit = () => {
    const next = draft.trim();
    if (next !== (value ?? "")) onCommit(next);
  };
  return (
    <Input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
      placeholder={placeholder}
      className="bg-background h-8 w-full"
    />
  );
}

/** Upload dialog: drag-drop + file picker + folder picker. Filters .pdf/.docx,
 * shows selected files with sizes + remove, dedup by name+size. */
function UploadDialog({
  open,
  onOpenChange,
  onUpload,
  uploading,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Must resolve with the per-file outcome: failed files stay selected for retry. */
  onUpload: (
    files: File[],
    autoParse: boolean,
  ) => Promise<{ total: number; failed: File[] }>;
  uploading: boolean;
}) {
  const [selected, setSelected] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [autoParse, setAutoParse] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const addFiles = (files: FileList | File[]) => {
    const filtered = Array.from(files).filter(
      (f) =>
        f.name.toLowerCase().endsWith(".pdf") ||
        f.name.toLowerCase().endsWith(".docx"),
    );
    setSelected((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}-${f.size}`));
      return [
        ...prev,
        ...filtered.filter((f) => !seen.has(`${f.name}-${f.size}`)),
      ];
    });
  };

  /** 开始上传:全部成功 → 清空并自动关闭;有请求级失败 → 保持打开,
   * 失败文件留在选择列表供重试。上传期间允许手动关闭,进度见页头按钮。 */
  const startUpload = async () => {
    if (selected.length === 0 || uploading) return;
    setUploadError(null);
    const { failed } = await onUpload(selected, autoParse);
    if (failed.length === 0) {
      setSelected([]);
      setAutoParse(false);
      onOpenChange(false);
    } else {
      const failedKeys = new Set(failed.map((f) => `${f.name}-${f.size}`));
      setSelected((prev) =>
        prev.filter((f) => failedKeys.has(`${f.name}-${f.size}`)),
      );
      setUploadError(
        `${failed.length} 个文件上传失败,已保留在选择列表,可直接重试或移除。`,
      );
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) {
          setSelected([]);
          setAutoParse(false);
          setUploadError(null);
        }
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>上传合同</DialogTitle>
          <DialogDescription>
            支持批量选择 PDF/DOCX 文件或整个文件夹。
          </DialogDescription>
        </DialogHeader>

        {/* Drag-drop zone */}
        <div
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors ${
            dragOver
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/30 hover:border-muted-foreground/50"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(e.dataTransfer.files);
          }}
          onClick={() => fileRef.current?.click()}
        >
          <FileUp className="text-muted-foreground h-10 w-10" />
          <p className="text-foreground text-sm font-medium">
            拖拽合同文件到此处
          </p>
          <p className="text-muted-foreground text-xs">
            或点击选择文件 · 支持多选
          </p>
        </div>

        {/* Auto-parse toggle */}
        <label className="flex cursor-pointer items-center gap-2 text-sm select-none">
          <input
            type="checkbox"
            checked={autoParse}
            onChange={(e) => setAutoParse(e.target.checked)}
            className="accent-primary"
          />
          <span
            className={
              autoParse
                ? "text-foreground font-medium"
                : "text-muted-foreground"
            }
          >
            上传后自动解析
          </span>
          <span className="text-muted-foreground text-xs">
            {autoParse
              ? "（上传完即触发 OCR 提取）"
              : "（上传后需手动点「开始解析」）"}
          </span>
        </label>

        {/* Browse buttons */}
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            onClick={() => fileRef.current?.click()}
          >
            <FileUp className="h-4 w-4" /> 选择文件
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            onClick={() => folderRef.current?.click()}
          >
            <FolderOpen className="h-4 w-4" /> 选择文件夹
          </Button>
        </div>

        {/* Hidden inputs */}
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          ref={folderRef}
          type="file"
          multiple
          className="hidden"
          {...({ webkitdirectory: "", directory: "" } as Record<
            string,
            string
          >)}
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />

        {/* Selected files list */}
        {selected.length > 0 && (
          <div className="max-h-48 space-y-1 overflow-y-auto">
            <p className="text-muted-foreground text-xs">
              已选 {selected.length} 个文件 · 共{" "}
              {(selected.reduce((s, f) => s + f.size, 0) / 1048576).toFixed(1)}
              MB
            </p>
            {selected.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className="bg-muted/50 flex items-center justify-between rounded-md px-3 py-1.5 text-sm"
              >
                <span className="flex-1 truncate">{f.name}</span>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-muted-foreground text-xs tabular-nums">
                    {(f.size / 1048576).toFixed(1)}MB
                  </span>
                  {!uploading && (
                    <button
                      onClick={() =>
                        setSelected((prev) => prev.filter((_, j) => j !== i))
                      }
                      className="text-destructive hover:text-destructive/80"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {uploadError && (
          <p className="text-destructive text-sm">{uploadError}</p>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setSelected([]);
              onOpenChange(false);
            }}
          >
            取消
          </Button>
          <Button
            disabled={selected.length === 0 || uploading}
            onClick={() => void startUpload()}
          >
            <FileUp className="h-4 w-4" />
            {uploading ? "上传中…" : `开始上传 (${selected.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Styled date picker field (Shadcn Calendar + Popover, not native input);
 * rendered inside the expanded 合同记录 panel. */
function DateCell({
  value,
  onCommit,
}: {
  value: string | null;
  onCommit: (v: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const date = value ? new Date(value + "T00:00:00") : undefined;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="border-input hover:bg-accent/50 bg-background flex h-8 w-full items-center justify-start gap-1.5 rounded-md border px-3 text-left text-sm font-normal tabular-nums"
        >
          <CalendarIcon className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
          <span
            className={value ? "text-foreground" : "text-muted-foreground/50"}
          >
            {value ?? "选择日期"}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={date}
          onSelect={(d) => {
            if (d) {
              const y = d.getFullYear();
              const m = String(d.getMonth() + 1).padStart(2, "0");
              const day = String(d.getDate()).padStart(2, "0");
              onCommit(`${y}-${m}-${day}`);
            } else {
              onCommit(null);
            }
            setOpen(false);
          }}
          initialFocus
          locale={zhCN}
        />
      </PopoverContent>
    </Popover>
  );
}

export function ContractsView() {
  const [keyword, setKeyword] = useState("");
  const [applied, setApplied] = useState("");
  const qc = useQueryClient();
  const update = useUpdateDocument();
  const runCluster = useRunCluster();
  const runPipeline = useRunPipeline();
  const reparse = useReparseDocument();
  const { data: configData } = useConfig();
  const updateConfig = useUpdateConfig();
  const [unmatchedDoc, setUnmatchedDoc] = useState<{
    id: string;
    name: string;
    tables: UnmatchedTable[];
  } | null>(null);
  // 「合同原文」查看器目标文档(null = 关闭)
  const [sourceDoc, setSourceDoc] = useState<ContractSourceDoc | null>(null);
  const [batch, setBatch] = useState<{
    total: number;
    done: number;
    failed: number;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showClusterConfirm, setShowClusterConfirm] = useState(false);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  // 已保存规则的未匹配表键(文件名:页:表序);PUT 成功才标记,抽屉的
  // "已保存规则"标记与重解析门槛都由此驱动(单一事实源)。
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  // 折叠/展开的合同行(参照 ItemsView 的 Set 模式;默认全部折叠)。
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /** Batch upload: push each file to the cpa-contracts bucket sequentially,
   * track per-file progress, then trigger a parse run (upload implies parse). */
  const handleFiles = async (
    files: FileList | File[],
    autoParse = false,
  ): Promise<{ total: number; failed: File[] }> => {
    // Filter to .pdf/.docx (webkitdirectory grabs ALL files in a folder).
    const list = Array.from(files).filter(
      (f) =>
        f.name.toLowerCase().endsWith(".pdf") ||
        f.name.toLowerCase().endsWith(".docx"),
    );
    if (!list.length) return { total: 0, failed: [] };
    setBatch({ total: list.length, done: 0, failed: 0 });
    // Concurrent upload pool (6 at a time) — sequential is too slow for 100+ files.
    const POOL = 6;
    let done = 0;
    let failed = 0;
    const failedFiles: File[] = [];
    for (let i = 0; i < list.length; i += POOL) {
      await Promise.allSettled(
        list.slice(i, i + POOL).map(async (f) => {
          try {
            await contractPriceApi.uploadDocument(f);
          } catch {
            failed += 1;
            failedFiles.push(f);
          }
          done += 1;
          setBatch({ total: list.length, done, failed });
        }),
      );
    }
    void qc.invalidateQueries({ queryKey: ["cpa"] });
    if (autoParse && failed < list.length) {
      runPipeline.mutate({ trigger: "manual" });
    }
    if (failed > 0) {
      // 对话框外的全局失败反馈(页头按钮只有计数,这里补失败说明)
      setNotice(
        `上传完成 ${list.length - failed}/${list.length},${failed} 个失败,可重开「上传合同」重试。`,
      );
    }
    return { total: list.length, failed: failedFiles };
  };

  // 列表分页(纯前端接线:后端 Page{total},skip/limit 透传)
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const { data, isLoading, isFetching, refetch } = useDocuments({
    keyword: applied || undefined,
    skip: page * pageSize,
    limit: pageSize,
  });

  const docs = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pendingCount = docs.filter((d) => d.parse_status === "pending").length;

  /** 未匹配表抽屉"保存规则": upsert 进 config.table_seeds。
   * config GET 会注入后端内置规则,这里拿到的即全量列表,按 id 覆盖或追加。
   * PUT 成功后才把表键记入 savedKeys(标记滞后于真实写入,避免假"已保存")。 */
  const createSeedFromDrawer = (seed: SeedDraft, key: string) => {
    if (!configData) {
      alert("配置尚未加载,请稍后重试");
      return;
    }
    const seeds = configData.table_seeds ?? [];
    const next = {
      ...configData,
      table_seeds: seeds.some((s) => s.id === seed.id)
        ? seeds.map((s) => (s.id === seed.id ? seed : s))
        : [...seeds, seed],
    };
    updateConfig.mutate(next, {
      onSuccess: () => {
        setSavedKeys((prev) => new Set(prev).add(key));
        setNotice(
          `已保存规则「${seed.display_name}」。回到抽屉点「重解析本文档」应用(读 OCR 缓存,秒级)。`,
        );
      },
      onError: (e) =>
        alert(`规则保存失败:${e instanceof Error ? e.message : e}`),
    });
  };

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="合同解析"
        description="上传合同扫描件(PDF/DOCX),存入独立 MinIO bucket。合同上传后进行合同文件解析处理,其中的图片内容将触发 OCR 提取。"
        icon={<FileText className="h-6 w-6" />}
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => setShowUploadDialog(true)}
              disabled={!!batch && batch.done < batch.total}
            >
              <FileUp className="h-4 w-4" />
              {batch
                ? batch.done === batch.total
                  ? `完成 ${batch.total - batch.failed}/${batch.total}`
                  : `上传中 ${batch.done}/${batch.total}`
                : "上传合同"}
            </Button>
            <ArrowRight className="text-muted-foreground/60 h-4 w-4" />
            <Button
              size="sm"
              disabled={runPipeline.isPending || pendingCount === 0}
              onClick={() => runPipeline.mutate({ trigger: "manual" })}
              title={
                pendingCount > 0
                  ? `解析 ${pendingCount} 份待解析合同`
                  : "没有待解析的合同"
              }
            >
              <FileSearch className="h-4 w-4" />
              {runPipeline.isPending
                ? "解析中…"
                : pendingCount > 0
                  ? `开始解析 (${pendingCount})`
                  : "开始解析"}
            </Button>
            <ChevronRight className="text-muted-foreground/30 h-4 w-4" />
            <Button
              size="sm"
              disabled={runCluster.isPending}
              onClick={() => setShowClusterConfirm(true)}
            >
              <Layers className="h-4 w-4" />
              {runCluster.isPending ? "聚类中…" : "聚类分组"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw
                className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
              />
              刷新
            </Button>
          </div>
        }
      />

      {notice && <p className="text-sm text-blue-600">{notice}</p>}

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(keyword);
          setPage(0);
        }}
      >
        <div className="relative max-w-sm flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索文件名 / 合同号 / 供应商"
            className="pl-9"
          />
        </div>
        <Button type="submit" size="sm">
          搜索
        </Button>
      </form>

      <div className="bg-background border-border overflow-hidden rounded-xl border shadow-sm">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-border bg-muted/50 border-b">
              <th className="text-muted-foreground px-6 py-3 text-xs font-semibold tracking-wider uppercase">
                合同文件
              </th>
              <th className="text-muted-foreground px-6 py-3 text-right text-xs font-semibold tracking-wider uppercase">
                操作
              </th>
            </tr>
          </thead>
          <tbody className="divide-border divide-y">
            {isLoading ? (
              <tr>
                <td
                  colSpan={2}
                  className="text-muted-foreground py-12 text-center"
                >
                  加载中…
                </td>
              </tr>
            ) : docs.length === 0 ? (
              <tr>
                <td
                  colSpan={2}
                  className="text-muted-foreground py-12 text-center"
                >
                  <div className="flex flex-col items-center gap-3">
                    <Inbox
                      className="h-12 w-12 opacity-30"
                      strokeWidth={1.5}
                      aria-hidden
                    />
                    <span>
                      暂无合同。点右上「上传合同」或总览页「立即分析」。
                    </span>
                  </div>
                </td>
              </tr>
            ) : (
              docs.map((doc) => {
                const meta = doc.parse_meta as {
                  tables_found?: number;
                  goods_tables?: number;
                  rows_extracted?: number;
                  unmatched_tables?: UnmatchedTable[];
                  matched_seeds?: Record<string, number>;
                } | null;
                const unmatched = meta?.unmatched_tables ?? [];
                // 引导语义(用户定案 2026-09-24): 已命中规则(有价格表提取)的合同
                // 不再提示建规则——"N张表未识别"只服务零命中的全新版式合同;
                // 未匹配清单仍记录在 parse_meta 供自进化捕获。
                const needsSeedGuide = !meta?.goods_tables && unmatched.length > 0;
                const stage = docStage(doc);
                const isExpanded = expanded.has(doc.id);
                return (
                  <Fragment key={doc.id}>
                    {/* 折叠态:文件名 + 状态徽章 + 关键计数徽章 + 展开箭头 */}
                    <tr className="hover:bg-muted/50 transition-colors">
                      <td className="px-6 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            aria-expanded={isExpanded}
                            onClick={() => toggleExpand(doc.id)}
                            className="text-muted-foreground hover:text-foreground shrink-0"
                            title={isExpanded ? "收起合同记录" : "展开合同记录"}
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </button>
                          <span
                            className="max-w-[420px] truncate font-medium"
                            title={doc.file_name}
                          >
                            {doc.file_name}
                          </span>
                          <span
                            className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${stage.tone}`}
                          >
                            {stage.label}
                          </span>
                          {doc.items_needs_review > 0 && (
                            <span
                              className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-xs text-amber-600"
                              title="validation_status=needs_review 的分项行数 / 分项总行数"
                            >
                              ⚠ {doc.items_needs_review}/{doc.items_total}{" "}
                              待核验
                            </span>
                          )}
                          {needsSeedGuide && (
                            <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-xs text-amber-600">
                              ⚠ {unmatched.length} 张疑似价格表
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-3 text-right">
                        <div className="flex items-center justify-end gap-0.5">
                          <Button
                            size="sm"
                            variant="outline"
                            title="重新解析(读 OCR 缓存,秒级)"
                            disabled={reparse.isPending}
                            onClick={() => {
                              if (
                                !confirm(
                                  `重新解析 ${doc.file_name}?(读取 OCR 缓存,通常秒级)`,
                                )
                              )
                                return;
                              reparse.mutate(doc.id, {
                                onSuccess: () =>
                                  setNotice(
                                    `已启动「${doc.file_name}」的重新解析,在「任务」页看进度。`,
                                  ),
                                onError: (e) =>
                                  alert(
                                    `重解析启动失败:${e instanceof Error ? e.message : e}\n(可能已有解析任务在跑,去「任务」页确认)`,
                                  ),
                              });
                            }}
                          >
                            <RotateCcw className="h-3.5 w-3.5 text-blue-600" />
                            重新解析
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            title="删除合同及其分项"
                            onClick={async () => {
                              if (
                                !confirm(`删除合同 ${doc.file_name} 及其分项？`)
                              )
                                return;
                              await contractPriceApi.deleteDocument(doc.id);
                              void qc.invalidateQueries({ queryKey: ["cpa"] });
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                    {/* 展开态:解析信息(附属数据行) + 合同记录表单 */}
                    {isExpanded && (
                      <tr className="bg-muted/30 hover:bg-muted/30">
                        <td colSpan={2} className="px-6 py-4">
                          <div className="space-y-5">
                            <div className="space-y-2">
                              <span className="text-muted-foreground text-xs font-semibold tracking-wide">
                                解析信息
                              </span>
                              <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tabular-nums">
                                <span>
                                  {(doc.file_type ?? "?").toUpperCase()}
                                </span>
                                <span className="opacity-40">·</span>
                                <span>
                                  {meta
                                    ? `${meta.goods_tables ?? 0}货 / ${meta.tables_found ?? 0}表 / ${meta.rows_extracted ?? 0}行`
                                    : "—"}
                                </span>
                                {meta?.matched_seeds &&
                                  Object.keys(meta.matched_seeds).length >
                                    0 && (
                                    <>
                                      <span className="opacity-40">·</span>
                                      <span>
                                        命中{" "}
                                        {Object.keys(meta.matched_seeds).join(
                                          "/",
                                        )}
                                      </span>
                                    </>
                                  )}
                                <span className="opacity-40">·</span>
                                <span>
                                  {stage.label}({doc.parse_status})
                                </span>
                                {doc.page_count != null && (
                                  <>
                                    <span className="opacity-40">·</span>
                                    <span>{doc.page_count} 页</span>
                                  </>
                                )}
                                <span className="opacity-40">·</span>
                                <span>解析于 {formatDate(doc.parsed_at)}</span>
                              </div>
                              {doc.error && (
                                <p className="text-destructive text-xs">
                                  解析错误:{doc.error}
                                </p>
                              )}
                              {needsSeedGuide && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs text-amber-600 hover:text-amber-600"
                                  onClick={() =>
                                    setUnmatchedDoc({
                                      id: doc.id,
                                      name: doc.file_name,
                                      tables: unmatched,
                                    })
                                  }
                                >
                                  <AlertTriangle className="h-3.5 w-3.5" />
                                  {unmatched.length} 张疑似价格表 ·
                                  建立定位规则
                                </Button>
                              )}
                            </div>
                            <div className="space-y-2">
                              <span className="text-muted-foreground text-xs font-semibold tracking-wide">
                                合同记录
                              </span>
                              <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
                                <DocField label="项目名称">
                                  <ProjectFieldInput
                                    value={doc.project_name}
                                    placeholder="项目名称"
                                    onCommit={(v) =>
                                      update.mutate({
                                        id: doc.id,
                                        body: { project_name: v },
                                      })
                                    }
                                  />
                                </DocField>
                                <DocField label="合同编号">
                                  <ProjectFieldInput
                                    value={doc.contract_no}
                                    placeholder="合同编号"
                                    onCommit={(v) =>
                                      update.mutate({
                                        id: doc.id,
                                        body: { contract_no: v },
                                      })
                                    }
                                  />
                                </DocField>
                                <DocField label="供应商">
                                  <ProjectFieldInput
                                    value={doc.supplier}
                                    placeholder="供应商"
                                    onCommit={(v) =>
                                      update.mutate({
                                        id: doc.id,
                                        body: { supplier: v },
                                      })
                                    }
                                  />
                                </DocField>
                                <DocField label="项目所在地">
                                  <ProjectFieldInput
                                    value={doc.project_location}
                                    placeholder="项目所在地"
                                    onCommit={(v) =>
                                      update.mutate({
                                        id: doc.id,
                                        body: { project_location: v },
                                      })
                                    }
                                  />
                                </DocField>
                                <DocField label="签订日期">
                                  <DateCell
                                    value={doc.sign_date}
                                    onCommit={(v) =>
                                      update.mutate({
                                        id: doc.id,
                                        body: { sign_date: v },
                                      })
                                    }
                                  />
                                </DocField>
                              </div>
                            </div>
                            <div className="space-y-2">
                              <span className="text-muted-foreground text-xs font-semibold tracking-wide">
                                合同原文
                              </span>
                              <div className="flex flex-wrap items-center gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={!doc.preview_prefix}
                                  title={
                                    doc.preview_prefix
                                      ? "逐页查看原文预览(←/→ 翻页)"
                                      : "文档尚未解析,暂无页面预览"
                                  }
                                  onClick={() =>
                                    setSourceDoc({
                                      id: doc.id,
                                      file_name: doc.file_name,
                                      file_type: doc.file_type,
                                    })
                                  }
                                >
                                  <Eye className="h-3.5 w-3.5" />
                                  查看原文
                                </Button>
                                <Button size="sm" variant="outline" asChild>
                                  <a
                                    href={contractPriceApi.fileUrl(doc.id)}
                                    title="下载原始 PDF/DOCX 文件"
                                  >
                                    <Download className="h-3.5 w-3.5" />
                                    下载原件
                                  </a>
                                </Button>
                                {!doc.preview_prefix && (
                                  <span className="text-muted-foreground text-xs">
                                    解析完成后可逐页预览原文。
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>

        {/* 分页(纯前端接线:后端 Page{total} + skip/limit;展开态按 doc id 记忆,翻页不串行) */}
        <div className="border-border flex items-center justify-between border-t px-6 py-3">
          <span className="text-muted-foreground text-xs">共 {total} 条</span>
          <div className="flex items-center gap-3">
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v));
                setPage(0);
              }}
            >
              <SelectTrigger className="h-7 w-[110px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[10, 20, 50].map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    每页 {n} 条
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-1">
              <Button
                size="icon"
                variant="outline"
                disabled={page <= 0}
                onClick={() => setPage(page - 1)}
                aria-label="上一页"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-muted-foreground px-1 text-xs tabular-nums">
                第 {page + 1} / {totalPages} 页
              </span>
              <Button
                size="icon"
                variant="outline"
                disabled={page >= totalPages - 1}
                onClick={() => setPage(page + 1)}
                aria-label="下一页"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={showClusterConfirm} onOpenChange={setShowClusterConfirm}>
        <DialogContent>
          <DialogHeader>
            <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100">
              <AlertTriangle className="h-6 w-6 text-amber-600" />
            </div>
            <DialogTitle className="text-center">开始分组?</DialogTitle>
            <DialogDescription className="text-center">
              将对所有「已解析」合同的货物价格进行聚类分组。价格待核验项会归组但不计入均值。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center">
            <Button
              variant="outline"
              onClick={() => setShowClusterConfirm(false)}
            >
              取消
            </Button>
            <Button
              onClick={() => {
                setShowClusterConfirm(false);
                runCluster.mutate({});
              }}
            >
              确认分组
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <UploadDialog
        open={showUploadDialog}
        onOpenChange={setShowUploadDialog}
        uploading={!!batch && batch.done < batch.total}
        onUpload={(files, autoParse) => handleFiles(files, autoParse)}
      />

      <UnmatchedTablesDrawer
        open={unmatchedDoc !== null}
        fileName={unmatchedDoc?.name ?? ""}
        tables={unmatchedDoc?.tables ?? []}
        savedKeys={savedKeys}
        onClose={() => setUnmatchedDoc(null)}
        onCreateSeed={createSeedFromDrawer}
        saving={updateConfig.isPending}
        onReparse={() => {
          if (!unmatchedDoc) return;
          reparse.mutate(unmatchedDoc.id, {
            onSuccess: () => {
              // 效果验证闭环: 轮询至重解析完成, 比对已保存表键是否仍在
              // unmatched_tables——在=规则未命中, 不在=已识别(rows_extracted
              // 为文档总提取行数)。
              const doc = unmatchedDoc;
              const docKeys = doc.tables
                .map((t) => ({
                  key: `${doc.name}:${t.page}:${t.table_idx}`,
                  title: t.title || `第${t.page}页表${t.table_idx + 1}`,
                }))
                .filter((t) => savedKeys.has(t.key));
              setUnmatchedDoc(null);
              setNotice("重解析中(读 OCR 缓存,秒级),完成后自动验证新规则效果...");
              const listKey = {
                keyword: applied || undefined,
                skip: page * pageSize,
                limit: pageSize,
              };
              const runVerify = async () => {
                for (let i = 0; i < 45; i++) {
                  await new Promise((r) => setTimeout(r, 2000));
                  const res = await qc.fetchQuery({
                    queryKey: ["cpa", "documents", listKey],
                    queryFn: () => contractPriceApi.listDocuments(listKey),
                  });
                  const fresh = res.items.find((d) => d.id === doc.id);
                  if (!fresh || fresh.parse_status === "parsing") continue;
                  const meta = (fresh.parse_meta ?? {}) as {
                    unmatched_tables?: { page: number; table_idx: number }[];
                    rows_extracted?: number;
                  };
                  const still = docKeys.filter((t) =>
                    (meta.unmatched_tables ?? []).some(
                      (u) => `${doc.name}:${u.page}:${u.table_idx}` === t.key,
                    ),
                  );
                  void qc.invalidateQueries({ queryKey: ["cpa"] });
                  if (still.length === 0) {
                    setNotice(
                      `✓ 新规则已生效:${docKeys
                        .map((t) => `「${t.title}」`)
                        .join("")} 已识别提取,本合同共提取 ${
                        meta.rows_extracted ?? 0
                      } 行。`,
                    );
                  } else {
                    setNotice(
                      `⚠ ${docKeys.length - still.length}/${docKeys.length} 张表已识别;其余仍未命中——请调整标题关键词或列锚点后重试。`,
                    );
                  }
                  return;
                }
                setNotice("重解析超过 90 秒仍未完成,稍后刷新页面查看提取结果。");
              };
              void runVerify();
            },
            onError: (e) =>
              alert(
                `重解析启动失败:${e instanceof Error ? e.message : e}\n(可能已有解析任务在跑,去「任务」页确认)`,
              ),
          });
        }}
        reparsePending={reparse.isPending}
      />

      <ContractSourceDialog
        doc={sourceDoc}
        open={sourceDoc !== null}
        onOpenChange={(v) => {
          if (!v) setSourceDoc(null);
        }}
      />
    </div>
  );
}
