"use client";

import { useQueryClient } from "@tanstack/react-query";
import { zhCN } from "date-fns/locale";
import {
  AlertTriangle,
  ArrowRight,
  CalendarIcon,
  ChevronRight,
  FileSearch,
  FileUp,
  FolderOpen,
  Layers,
  PackageSearch,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
import { sparePartsApi } from "@/extensions/spare-parts/api";
import { PageHeader } from "@/extensions/spare-parts/components/PageHeader";
import {
  useDocuments,
  useReparseDocument,
  useRunCluster,
  useRunPipeline,
  useUpdateDocument,
} from "@/extensions/spare-parts/hooks";

/** Unified doc lifecycle stage. No confirm gate — parsed docs go straight to
 * "已解析", then cluster run advances to "已分组". */
function docStage(doc: { parse_status: string; confirm_status: string }): {
  label: string;
  tone: string;
  pending: boolean;
} {
  if (doc.confirm_status === "clustered")
    return { label: "已分组", tone: "text-blue-600", pending: false };
  if (doc.parse_status === "failed")
    return { label: "解析失败", tone: "text-destructive", pending: false };
  if (doc.parse_status === "pending")
    return { label: "已上传", tone: "text-muted-foreground", pending: false };
  if (doc.parse_status === "parsing")
    return { label: "解析中", tone: "text-primary", pending: false };
  return { label: "已解析", tone: "text-emerald-600", pending: false };
}

function formatDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("zh-CN", { hour12: false });
}

/** Inline borderless input that looks like text until focused; commits on blur.
 * Manual补 fallback for project fields the front-page OCR regex missed. */
function ProjectFieldInput({
  value,
  placeholder,
  onCommit,
  width = "w-[170px]",
}: {
  value: string | null;
  placeholder: string;
  onCommit: (v: string) => void;
  width?: string;
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
      className={`h-8 ${width} hover:border-border focus-visible:border-border border-transparent bg-transparent px-1`}
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
  onUpload: (files: File[], autoParse: boolean) => void;
  uploading: boolean;
}) {
  const [selected, setSelected] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [autoParse, setAutoParse] = useState(false);
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

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!uploading) {
          onOpenChange(v);
          if (!v) {
            setSelected([]);
            setAutoParse(false);
          }
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

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setSelected([]);
              onOpenChange(false);
            }}
            disabled={uploading}
          >
            取消
          </Button>
          <Button
            disabled={selected.length === 0 || uploading}
            onClick={() => onUpload(selected, autoParse)}
          >
            <FileUp className="h-4 w-4" />
            {uploading ? "上传中…" : `开始上传 (${selected.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Styled date picker cell (Shadcn Calendar + Popover, not native input). */
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
          className="hover:border-border flex h-8 w-[130px] items-center gap-1.5 rounded border-transparent bg-transparent px-1 text-sm tabular-nums"
        >
          <CalendarIcon className="text-muted-foreground h-3.5 w-3.5" />
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
  const [batch, setBatch] = useState<{
    total: number;
    done: number;
    failed: number;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showClusterConfirm, setShowClusterConfirm] = useState(false);
  const [showUploadDialog, setShowUploadDialog] = useState(false);

  /** Batch upload: push each file to the csp documents bucket sequentially,
   * track per-file progress, then trigger a parse run (upload implies parse). */
  const handleFiles = async (files: FileList | File[], autoParse = false) => {
    // Filter to .pdf/.docx (webkitdirectory grabs ALL files in a folder).
    const list = Array.from(files).filter(
      (f) =>
        f.name.toLowerCase().endsWith(".pdf") ||
        f.name.toLowerCase().endsWith(".docx"),
    );
    if (!list.length) return;
    setBatch({ total: list.length, done: 0, failed: 0 });
    // Concurrent upload pool (6 at a time) — sequential is too slow for 100+ files.
    const POOL = 6;
    let done = 0;
    let failed = 0;
    for (let i = 0; i < list.length; i += POOL) {
      await Promise.allSettled(
        list.slice(i, i + POOL).map(async (f) => {
          try {
            await sparePartsApi.uploadDocument(f);
          } catch {
            failed += 1;
          }
          done += 1;
          setBatch({ total: list.length, done, failed });
        }),
      );
    }
    void qc.invalidateQueries({ queryKey: ["csp"] });
    if (autoParse && failed < list.length) {
      runPipeline.mutate({ trigger: "manual" });
    }
  };

  const { data, isLoading, isFetching, refetch } = useDocuments({
    keyword: applied || undefined,
    limit: 50,
  });

  const docs = data?.items ?? [];
  const pendingCount = docs.filter((d) => d.parse_status === "pending").length;

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="合同解析"
        description="上传合同扫描件(PDF/DOCX),存入独立 MinIO bucket。合同上传后进行合同文件解析处理,其中的图片内容将触发 OCR 提取。"
        icon={<PackageSearch className="h-4 w-4" />}
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
              {runCluster.isPending ? "聚类中…" : "聚类分析"}
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
        }}
      >
        <div className="relative max-w-sm flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索合同号 / 供应商"
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
                合同
              </th>
              <th className="text-muted-foreground px-6 py-3 text-xs font-semibold tracking-wider uppercase">
                项目名称
              </th>
              <th className="text-muted-foreground px-6 py-3 text-xs font-semibold tracking-wider uppercase">
                项目所在地
              </th>
              <th className="text-muted-foreground px-6 py-3 text-xs font-semibold tracking-wider uppercase">
                供应商
              </th>
              <th className="text-muted-foreground px-6 py-3 text-xs font-semibold tracking-wider uppercase">
                签订日期
              </th>
              <th className="text-muted-foreground px-6 py-3 text-xs font-semibold tracking-wider uppercase">
                状态
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
                  colSpan={7}
                  className="text-muted-foreground py-12 text-center"
                >
                  加载中…
                </td>
              </tr>
            ) : docs.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="text-muted-foreground py-12 text-center"
                >
                  暂无合同。点右上「上传合同」或总览页「立即分析」。
                </td>
              </tr>
            ) : (
              docs.map((doc) => {
                const meta = doc.parse_meta as {
                  tables_found?: number;
                  goods_tables?: number;
                  rows_extracted?: number;
                } | null;
                const stage = docStage(doc);
                return (
                  <tr
                    key={doc.id}
                    className="hover:bg-muted/50 group transition-colors"
                  >
                    <td className="px-6 py-4">
                      {/* 折行:文件名(主) + 类型·健康度·解析时间(次,淡小字) */}
                      <div className="max-w-[340px] min-w-[220px]">
                        <div
                          className="truncate font-medium"
                          title={doc.file_name}
                        >
                          {doc.file_name}
                        </div>
                        <div className="text-muted-foreground truncate text-xs tabular-nums">
                          {(doc.file_type ?? "?").toUpperCase()}
                          <span className="mx-1 opacity-40">·</span>
                          {meta
                            ? `${meta.goods_tables ?? 0}货/${meta.tables_found ?? 0}表/${meta.rows_extracted ?? 0}行`
                            : "—"}
                          <span className="mx-1 opacity-40">·</span>
                          {formatDate(doc.parsed_at)}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 align-middle">
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
                    </td>
                    <td className="px-6 py-4 align-middle">
                      <ProjectFieldInput
                        value={doc.project_location}
                        placeholder="项目所在地"
                        width="w-[120px]"
                        onCommit={(v) =>
                          update.mutate({
                            id: doc.id,
                            body: { project_location: v },
                          })
                        }
                      />
                    </td>
                    <td className="px-6 py-4 align-middle">
                      <ProjectFieldInput
                        value={doc.supplier}
                        placeholder="供应商"
                        onCommit={(v) =>
                          update.mutate({ id: doc.id, body: { supplier: v } })
                        }
                      />
                    </td>
                    <td className="px-6 py-4 align-middle">
                      <DateCell
                        value={doc.sign_date}
                        onCommit={(v) =>
                          update.mutate({ id: doc.id, body: { sign_date: v } })
                        }
                      />
                    </td>
                    <td className="px-6 py-4">
                      <span className={stage.tone}>{stage.label}</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-0.5">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="text-blue-600 hover:text-blue-600"
                          title="重新解析(重新 OCR,约几分钟)"
                          disabled={reparse.isPending}
                          onClick={() => {
                            if (
                              !confirm(
                                `重新解析 ${doc.file_name}?\n会重新 OCR(约几分钟),完成后状态回到 parsed/needs_review。`,
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
                          <RotateCcw className="h-4 w-4" />
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
                            await sparePartsApi.deleteDocument(doc.id);
                            void qc.invalidateQueries({ queryKey: ["csp"] });
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
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
        onUpload={(files, autoParse) => {
          void handleFiles(files, autoParse);
        }}
      />
    </div>
  );
}
