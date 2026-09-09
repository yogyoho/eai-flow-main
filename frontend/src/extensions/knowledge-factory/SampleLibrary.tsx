"use client";

// EAI-CUSTOM: 样例库 tab（coal-eia-report v2 BS3 MVP）——样例台账 + 入库向导。
// 提取流水线 / 质检面板留二期。后端：/api/kf/samples*（knowledge_factory routers）。

import {
  FileStack,
  Loader2,
  PlusCircle,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  SCENARIO_LABELS,
  SAMPLE_SCENARIOS,
  SAMPLE_STATUSES,
  STATUS_LABELS,
  sampleLibraryApi,
  type KFSampleRecord,
  type KFSampleUpsertInput,
} from "./sample-library-api";

const PAGE_SIZE = 20;

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// 状态徽章配色（已解析/已转换=正常，仅登记=次要，加密/失败=警示）
function statusBadgeClass(status: string): string {
  switch (status) {
    case "parsed":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "converted":
      return "bg-sky-50 text-sky-700 border-sky-200";
    case "encrypted":
    case "converted_failed":
      return "bg-red-50 text-red-700 border-red-200";
    default:
      return "bg-muted text-muted-foreground";
  }
}

export default function SampleLibrary() {
  const [samples, setSamples] = useState<KFSampleRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [scenarioFilter, setScenarioFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);

  const fetchSamples = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      try {
        const result = await sampleLibraryApi.list({
          scenario: scenarioFilter || undefined,
          search: search || undefined,
          page: targetPage,
          limit: PAGE_SIZE,
        });
        setSamples(result.samples);
        setTotal(result.total);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "加载样例台账失败");
      } finally {
        setLoading(false);
      }
    },
    [page, scenarioFilter, search],
  );

  useEffect(() => {
    void fetchSamples();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 筛选/页码变化即拉取
  }, [scenarioFilter, page, search]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleDelete = useCallback(
    async (sample: KFSampleRecord) => {
      if (!window.confirm(`确认删除样例「${sample.title}」？`)) return;
      try {
        await sampleLibraryApi.remove(sample.id);
        toast.success("样例已删除");
        void fetchSamples();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "删除失败");
      }
    },
    [fetchSamples],
  );

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-foreground text-xl font-semibold">样例库</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            环评报告样例文件登记台账（场景 × 状态双轴）。提取流水线与质检面板将在后续版本提供。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void fetchSamples()} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowImportDialog(true)}>
            <Upload className="h-4 w-4" />
            批量导入
          </Button>
          <Button size="sm" onClick={() => setShowCreateDialog(true)}>
            <PlusCircle className="h-4 w-4" />
            登记样例
          </Button>
        </div>
      </div>

      {/* Filters: scenario chips + search */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <FilterChip
            label="全部"
            active={scenarioFilter === ""}
            onClick={() => {
              setScenarioFilter("");
              setPage(1);
            }}
          />
          {SAMPLE_SCENARIOS.map((s) => (
            <FilterChip
              key={s.value}
              label={s.label}
              active={scenarioFilter === s.value}
              onClick={() => {
                setScenarioFilter(s.value);
                setPage(1);
              }}
            />
          ))}
        </div>
        <div className="relative ml-auto w-64">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="搜索标题 / 来源路径"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="pl-8"
          />
        </div>
      </div>

      {/* Table */}
      {loading && samples.length === 0 ? (
        <div className="text-muted-foreground flex items-center justify-center gap-2 py-20 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </div>
      ) : total === 0 && !search && !scenarioFilter ? (
        <Empty className="border-border rounded-xl border border-dashed py-16">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FileStack className="h-6 w-6" />
            </EmptyMedia>
            <EmptyTitle>样例库还是空的</EmptyTitle>
            <EmptyDescription>
              登记已解析的环评报告样例文件，或从既有台账 JSON 批量导入。样例是模板抽取与范文库（samples_bank）的语料基本盘。
            </EmptyDescription>
          </EmptyHeader>
          <div className="flex items-center justify-center gap-2">
            <Button size="sm" onClick={() => setShowCreateDialog(true)}>
              <PlusCircle className="h-4 w-4" />
              登记第一条样例
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowImportDialog(true)}>
              <Upload className="h-4 w-4" />
              批量导入
            </Button>
          </div>
        </Empty>
      ) : (
        <div className="border-border overflow-hidden rounded-xl border">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="bg-muted/50 text-muted-foreground border-border border-b text-left">
                  <th className="px-4 py-3 font-medium">标题</th>
                  <th className="px-4 py-3 font-medium">场景</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">置信</th>
                  <th className="px-4 py-3 font-medium">哈希前8</th>
                  <th className="px-4 py-3 font-medium">登记时间</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {samples.map((s) => (
                  <tr key={s.id} className="border-border hover:bg-muted/30 border-b transition-colors last:border-b-0">
                    <td className="max-w-[320px] px-4 py-3">
                      <div className="text-foreground truncate font-medium" title={s.title}>
                        {s.title}
                      </div>
                      <div className="text-muted-foreground truncate text-xs" title={s.source_path}>
                        {s.variant ?? s.source_path}
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">{SCENARIO_LABELS[s.scenario] ?? s.scenario}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={statusBadgeClass(s.status)}>
                        {STATUS_LABELS[s.status] ?? s.status}
                      </Badge>
                    </td>
                    <td className="text-muted-foreground px-4 py-3 tabular-nums whitespace-nowrap">
                      {s.confidence == null ? "—" : s.confidence.toFixed(2)}
                    </td>
                    <td className="text-muted-foreground px-4 py-3 font-mono text-xs">{s.file_hash.slice(0, 8)}</td>
                    <td className="text-muted-foreground px-4 py-3 text-xs whitespace-nowrap">{formatDateTime(s.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground hover:text-red-600"
                        onClick={() => void handleDelete(s)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {samples.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-muted-foreground px-4 py-12 text-center">
                      当前筛选条件下没有样例。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination */}
      {total > 0 && (
        <div className="text-muted-foreground flex items-center justify-between text-sm">
          <span>共 {total} 条样例</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
              上一页
            </Button>
            <span className="tabular-nums">
              {page} / {totalPages}
            </span>
            <Button variant="outline" size="sm" disabled={page >= totalPages || loading} onClick={() => setPage((p) => p + 1)}>
              下一页
            </Button>
          </div>
        </div>
      )}

      <CreateSampleDialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreated={() => {
          setShowCreateDialog(false);
          setPage(1);
          void fetchSamples(1);
        }}
      />
      <BulkImportDialog
        open={showImportDialog}
        onClose={() => setShowImportDialog(false)}
        onImported={() => {
          setShowImportDialog(false);
          setPage(1);
          void fetchSamples(1);
        }}
      />
    </div>
  );
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

// ============== 登记样例对话框 ==============

function CreateSampleDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const emptyForm = useMemo<KFSampleUpsertInput>(
    () => ({
      title: "",
      source_path: "",
      file_hash: "",
      scenario: "planning_eia",
      status: "filename_only",
      variant: "",
      confidence: null,
      notes: "",
    }),
    [],
  );
  const [form, setForm] = useState<KFSampleUpsertInput>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const setField = (patch: Partial<KFSampleUpsertInput>) => setForm((f) => ({ ...f, ...patch }));

  const submit = async () => {
    if (!form.title.trim() || !form.source_path.trim() || form.file_hash.trim().length < 8) {
      toast.error("请填写标题、来源路径，哈希至少 8 个字符");
      return;
    }
    setSubmitting(true);
    try {
      await sampleLibraryApi.create({
        ...form,
        title: form.title.trim(),
        source_path: form.source_path.trim(),
        file_hash: form.file_hash.trim().toLowerCase(),
        variant: form.variant?.trim() ? form.variant.trim() : null,
        notes: form.notes?.trim() ? form.notes.trim() : null,
      });
      toast.success("样例已登记");
      setForm(emptyForm);
      onCreated();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "登记失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? undefined : onClose())}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>登记样例</DialogTitle>
          <DialogDescription>
            手工登记一份已解析的环评报告样例文件。哈希重复（409）表示该文件已在库中。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="sample-title">标题 *</Label>
            <Input
              id="sample-title"
              value={form.title}
              placeholder="如：横城矿区总体规划（修编）环境影响报告书（报批版 2021.1）"
              onChange={(e) => setField({ title: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="sample-path">来源路径 *</Label>
            <Input
              id="sample-path"
              value={form.source_path}
              placeholder="D:/…/样例文件/xxx.docx"
              onChange={(e) => setField({ source_path: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="sample-hash">文件哈希（SHA-256 十六进制）*</Label>
            <Input
              id="sample-hash"
              value={form.file_hash}
              placeholder="至少 8 位；入库向导自动计算"
              onChange={(e) => setField({ file_hash: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>场景</Label>
              <AdminSelect
                value={form.scenario}
                onValueChange={(v) => setField({ scenario: v })}
                options={SAMPLE_SCENARIOS}
              />
            </div>
            <div className="grid gap-2">
              <Label>状态</Label>
              <AdminSelect value={form.status} onValueChange={(v) => setField({ status: v })} options={SAMPLE_STATUSES} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="sample-variant">版本备注</Label>
              <Input
                id="sample-variant"
                value={form.variant ?? ""}
                placeholder="修编·报批版 / 新建 / 改扩建…"
                onChange={(e) => setField({ variant: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="sample-confidence">置信 0–1</Label>
              <Input
                id="sample-confidence"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.confidence ?? ""}
                placeholder="0.95"
                onChange={(e) =>
                  setField({ confidence: e.target.value === "" ? null : Number(e.target.value) })
                }
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="sample-notes">备注</Label>
            <Textarea
              id="sample-notes"
              rows={2}
              value={form.notes ?? ""}
              placeholder="去重裁决 / 脱敏要求 / 提取通道等备注"
              onChange={(e) => setField({ notes: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void submit()} disabled={submitting}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            登记
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============== 批量导入对话框 ==============

function BulkImportDialog({
  open,
  onClose,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}) {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ created: number; updated: number } | null>(null);

  const submit = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      toast.error("JSON 解析失败：请粘贴形如 [{title, source_path, file_hash, scenario, status}, …] 的数组");
      return;
    }
    if (!Array.isArray(parsed) || parsed.length === 0) {
      toast.error("需要一个非空的 JSON 数组");
      return;
    }
    setSubmitting(true);
    try {
      const res = await sampleLibraryApi.importBulk(parsed as KFSampleUpsertInput[]);
      setResult({ created: res.created, updated: res.updated });
      toast.success(`导入完成：新增 ${res.created} 条，更新 ${res.updated} 条（按哈希幂等）`);
      setText("");
      onImported();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "导入失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setResult(null);
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>批量导入样例</DialogTitle>
          <DialogDescription>
            粘贴 JSON 数组（每条含 title / source_path / file_hash / scenario / status，可选 variant、confidence、notes）。按
            file_hash 幂等 upsert，可重复执行。
          </DialogDescription>
        </DialogHeader>
        <Textarea
          rows={10}
          className="font-mono text-xs"
          placeholder={`[\n  {\n    "title": "横城矿区总体规划（修编）环境影响报告书",\n    "source_path": "D:/…/横城…docx",\n    "file_hash": "736abe72c5cc68a7…",\n    "scenario": "planning_eia",\n    "status": "parsed",\n    "confidence": 0.95\n  }\n]`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {result && (
          <p className="text-muted-foreground text-sm">
            上次导入：新增 {result.created} 条，更新 {result.updated} 条。
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            关闭
          </Button>
          <Button onClick={() => void submit()} disabled={submitting || !text.trim()}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
