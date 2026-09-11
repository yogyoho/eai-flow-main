"use client";

// EAI-CUSTOM (Plan 4): 标书样例台账 tab——镜像 eia-samples SampleLibrary library-tab; eia 域专用提取/质检面板不复刻(spec §2.3 samples 端点族)。样例库=技术供源库(用户定案 2026-09-11): 检索语料/深度统计只取技术章(bank_compile 侧已实现), 本台账管理全册登记与溯源。
// 具名导出 SampleLibrary——BidMaterials.tsx(tab 壳)以 { SampleLibrary } 具名导入, 勿改 default。
// 契约事实(Plan 4 Task 1 实读): samples.list 仅 industry/project_category/q/limit/offset(无 status/scenario 过滤,
// 裸数组响应无 total——多取 1 条探测 hasMore); 无单条 POST, 登记走 importBulk([{...}]);
// file_hash 后端硬校验 64 位长度（十六进制字符集为前端校验）。

import {
  Ban,
  ChevronDown,
  FileStack,
  Loader2,
  PlusCircle,
  RefreshCw,
  Search,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
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
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  bidMaterialsApi,
  SAMPLE_SCENARIOS,
  SAMPLE_STATUSES,
  type BidSampleBulkResult,
  type BidSampleRecord,
  type BidSampleUpsertInput,
} from "./bid-materials-api";

const PAGE_SIZE = 20;

// SHA-256 十六进制(小写化后校验)——后端 min/max length=64 硬校验, 前端先拦避免 422
const FILE_HASH_RE = /^[0-9a-f]{64}$/;

const STATUS_LABELS: Record<string, string> = Object.fromEntries(
  SAMPLE_STATUSES.map((s) => [s.value, s.label]),
);

const SCENARIO_LABELS: Record<string, string> = Object.fromEntries(
  SAMPLE_SCENARIOS.map((s) => [s.value, s.label]),
);

// 状态徽章配色（已入库=正常，已推 RAGFlow=信息，已停用=警示）
function statusBadgeClass(status: string): string {
  switch (status) {
    case "indexed":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "ragflow_pushed":
      return "bg-sky-50 text-sky-700 border-sky-200";
    case "disabled":
      return "bg-red-50 text-red-700 border-red-200";
    default:
      return "bg-muted text-muted-foreground";
  }
}

// bulk 导入必填字段（notes 可选——对齐 BidSampleUpsertInput）
const BULK_REQUIRED_FIELDS: (keyof BidSampleUpsertInput)[] = [
  "title",
  "source_path",
  "file_hash",
  "industry",
  "project_category",
  "scenario",
  "status",
];

// 解析 bulk 粘贴文本——接受 registration.json 全文（{items:[…]}）/ 裸数组 […] / 单对象 {…} 三种形态，
// 逐条校验必填字段与 file_hash 形态（校验即归一：file_hash trim+小写回写，与登记对话框同口径去重），
// 返回首个错误的条目序号
function parseBulkItems(text: string): {
  items?: BidSampleUpsertInput[];
  error?: string;
} {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return {
      error:
        'JSON 解析失败：支持 registration.json 全文（{"items":[…]}）、裸数组 […] 或单对象 {…}',
    };
  }
  let raw: unknown[];
  if (Array.isArray(parsed)) {
    raw = parsed;
  } else if (
    parsed !== null &&
    typeof parsed === "object" &&
    Array.isArray((parsed as { items?: unknown }).items)
  ) {
    raw = (parsed as { items: unknown[] }).items;
  } else if (parsed !== null && typeof parsed === "object") {
    raw = [parsed];
  } else {
    return { error: '无法识别的形态：支持 {"items":[…]} / […] / 单对象 {…}' };
  }
  if (raw.length === 0) {
    return { error: "解析结果为空：需要至少一条样例记录" };
  }
  const items: BidSampleUpsertInput[] = [];
  for (let i = 0; i < raw.length; i++) {
    const item = raw[i];
    if (item === null || typeof item !== "object" || Array.isArray(item)) {
      return { error: `第 ${i + 1} 条不是 JSON 对象` };
    }
    const rec = item as Record<string, unknown>;
    for (const field of BULK_REQUIRED_FIELDS) {
      const value = rec[field];
      if (typeof value !== "string" || value.trim() === "") {
        return { error: `第 ${i + 1} 条缺少必填字段 ${field}` };
      }
    }
    // 归一化后回写（trim+小写）——导入负载与登记对话框同形态，file_hash 去重口径一致
    const fileHash = String(rec.file_hash).trim().toLowerCase();
    if (!FILE_HASH_RE.test(fileHash)) {
      return { error: `第 ${i + 1} 条 file_hash 非 64 位十六进制（SHA-256）` };
    }
    // 字段已逐条校验为非空 string，双重断言安全；除 file_hash 归一外原样透传（含额外键，与原行为一致）
    items.push({
      ...(rec as unknown as BidSampleUpsertInput),
      file_hash: fileHash,
    });
  }
  return { items };
}

export function SampleLibrary() {
  const [samples, setSamples] = useState<BidSampleRecord[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [industryFilter, setIndustryFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchSamples = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      try {
        // 裸数组响应无 total：limit 多取 1 条探测 hasMore，展示时截断回 PAGE_SIZE
        const result = await bidMaterialsApi.samples.list({
          industry: industryFilter || undefined,
          project_category: categoryFilter || undefined,
          q: search || undefined,
          limit: PAGE_SIZE + 1,
          offset: (targetPage - 1) * PAGE_SIZE,
        });
        setHasMore(result.length > PAGE_SIZE);
        setSamples(result.slice(0, PAGE_SIZE));
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "加载样例台账失败");
      } finally {
        setLoading(false);
      }
    },
    [page, industryFilter, categoryFilter, search],
  );

  useEffect(() => {
    void fetchSamples();
    // 筛选/页码变化经 fetchSamples 的 useCallback 依赖即拉取
  }, [fetchSamples]);

  const handleDisable = useCallback(
    async (sample: BidSampleRecord) => {
      if (
        !window.confirm(
          `确认停用样例「${sample.title}」？停用后不再作为技术供源。`,
        )
      )
        return;
      try {
        await bidMaterialsApi.samples.disable(sample.id);
        toast.success("样例已停用");
        void fetchSamples();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "停用失败");
      }
    },
    [fetchSamples],
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-foreground text-base font-semibold">
            技术供源库
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            标书样例全册登记与溯源台账。检索语料仅含技术章（bank_compile
            侧切片），商务章不入库推送。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void fetchSamples()}
            disabled={loading}
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowImportDialog(true)}
          >
            <Upload className="h-4 w-4" />
            批量导入
          </Button>
          <Button size="sm" onClick={() => setShowCreateDialog(true)}>
            <PlusCircle className="h-4 w-4" />
            登记样例
          </Button>
        </div>
      </div>

      {/* Filters: 行业 / 项目类别（后端透传）+ 标题搜索（q）——list 无 status/scenario 过滤参数，不渲染对应筛选器 */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="按行业过滤"
          value={industryFilter}
          onChange={(e) => {
            setIndustryFilter(e.target.value);
            setPage(1);
          }}
          className="w-40"
        />
        <Input
          placeholder="按项目类别过滤"
          value={categoryFilter}
          onChange={(e) => {
            setCategoryFilter(e.target.value);
            setPage(1);
          }}
          className="w-48"
        />
        <div className="relative ml-auto w-64">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2" />
          <Input
            placeholder="搜索标题"
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
      ) : samples.length === 0 &&
        page === 1 &&
        !industryFilter &&
        !categoryFilter &&
        !search ? (
        <Empty className="border-border rounded-xl border border-dashed py-16">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FileStack className="h-6 w-6" />
            </EmptyMedia>
            <EmptyTitle>技术供源库还是空的</EmptyTitle>
            <EmptyDescription>
              登记标书样例（全册登记与溯源），或粘贴 bank_compile 产
              registration.json 批量导入。检索语料仅含技术章，商务章不入库推送。
            </EmptyDescription>
          </EmptyHeader>
          <div className="flex items-center justify-center gap-2">
            <Button size="sm" onClick={() => setShowCreateDialog(true)}>
              <PlusCircle className="h-4 w-4" />
              登记第一条样例
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowImportDialog(true)}
            >
              <Upload className="h-4 w-4" />
              批量导入
            </Button>
          </div>
        </Empty>
      ) : (
        <div className="border-border overflow-hidden rounded-xl border">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="bg-muted/50 text-muted-foreground border-border border-b text-left">
                  <th className="px-4 py-3 font-medium">标题</th>
                  <th className="px-4 py-3 font-medium">行业</th>
                  <th className="px-4 py-3 font-medium">项目类别</th>
                  <th className="px-4 py-3 font-medium">场景</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">哈希前8</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {samples.map((s) => (
                  <SampleRow
                    key={s.id}
                    sample={s}
                    expanded={expandedId === s.id}
                    onToggleExpand={() =>
                      setExpandedId((cur) => (cur === s.id ? null : s.id))
                    }
                    onDisable={() => void handleDisable(s)}
                  />
                ))}
                {samples.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="text-muted-foreground px-4 py-12 text-center"
                    >
                      当前筛选条件下没有样例。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination（offset 制——裸数组无 total，只做上一页/下一页） */}
      {(samples.length > 0 || page > 1) && (
        <div className="text-muted-foreground flex items-center justify-between text-sm">
          <span>每页 {PAGE_SIZE} 条</span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </Button>
            <span className="tabular-nums">第 {page} 页</span>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasMore || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      )}

      <RegisterSampleDialog
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

// 单行 + 详情展开行（notes/source_path/完整哈希）——拆出以保持列结构清晰
function SampleRow({
  sample,
  expanded,
  onToggleExpand,
  onDisable,
}: {
  sample: BidSampleRecord;
  expanded: boolean;
  onToggleExpand: () => void;
  onDisable: () => void;
}) {
  const disabled = sample.status === "disabled";
  return (
    <>
      <tr
        className={cn(
          "border-border hover:bg-muted/30 border-b transition-colors last:border-b-0",
          disabled && "opacity-60",
        )}
      >
        <td className="max-w-[280px] px-4 py-3">
          <div
            className="text-foreground truncate font-medium"
            title={sample.title}
          >
            {sample.title}
          </div>
        </td>
        <td className="text-muted-foreground px-4 py-3 whitespace-nowrap">
          {sample.industry}
        </td>
        <td className="text-muted-foreground px-4 py-3 whitespace-nowrap">
          {sample.project_category}
        </td>
        <td className="px-4 py-3 whitespace-nowrap">
          {SCENARIO_LABELS[sample.scenario] ?? sample.scenario}
        </td>
        <td className="px-4 py-3">
          <Badge variant="outline" className={statusBadgeClass(sample.status)}>
            {STATUS_LABELS[sample.status] ?? sample.status}
          </Badge>
        </td>
        <td className="text-muted-foreground px-4 py-3 font-mono text-xs">
          {sample.file_hash.slice(0, 8)}
        </td>
        <td className="px-4 py-3 text-right">
          <div className="flex items-center justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-primary"
              title={
                expanded
                  ? "收起溯源详情"
                  : "展开溯源详情（来源路径/备注/完整哈希）"
              }
              onClick={onToggleExpand}
            >
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform",
                  expanded && "rotate-180",
                )}
              />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-red-600"
              title="停用样例"
              onClick={onDisable}
            >
              <Ban className="h-4 w-4" />
            </Button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="border-border bg-muted/20 border-b last:border-b-0">
          <td colSpan={7} className="px-4 py-3">
            <div className="grid gap-1.5 text-xs">
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20 shrink-0">
                  来源路径
                </span>
                <code className="text-foreground break-all">
                  {sample.source_path}
                </code>
              </div>
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20 shrink-0">
                  file_hash
                </span>
                <code className="text-foreground break-all">
                  {sample.file_hash}
                </code>
              </div>
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20 shrink-0">
                  备注
                </span>
                <span className="text-foreground whitespace-pre-wrap">
                  {sample.notes ?? "—"}
                </span>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ============== 登记样例对话框（无单条 POST 端点——经 importBulk([item]) 幂等导入） ==============

function RegisterSampleDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const emptyForm = useMemo<BidSampleUpsertInput>(
    () => ({
      title: "",
      source_path: "",
      file_hash: "",
      industry: "",
      project_category: "",
      scenario: "bid_sample",
      status: "indexed",
      notes: "",
    }),
    [],
  );
  const [form, setForm] = useState<BidSampleUpsertInput>(emptyForm);
  const [hashError, setHashError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const setField = (patch: Partial<BidSampleUpsertInput>) =>
    setForm((f) => ({ ...f, ...patch }));

  const submit = async () => {
    const title = form.title.trim();
    const sourcePath = form.source_path.trim();
    const industry = form.industry.trim();
    const projectCategory = form.project_category.trim();
    const fileHash = form.file_hash.trim().toLowerCase();
    if (!title || !sourcePath || !industry || !projectCategory) {
      toast.error("请填写标题、来源路径、行业与项目类别");
      return;
    }
    // 后端硬校验 64 位十六进制——不匹配则前端拦截，不发请求
    if (!FILE_HASH_RE.test(fileHash)) {
      setHashError(
        "file_hash 须为 64 位十六进制（SHA-256），后端长度硬校验不符将 422",
      );
      return;
    }
    setHashError(null);
    setSubmitting(true);
    try {
      const res = await bidMaterialsApi.samples.importBulk([
        {
          title,
          source_path: sourcePath,
          file_hash: fileHash,
          industry,
          project_category: projectCategory,
          scenario: form.scenario,
          status: form.status,
          notes: form.notes?.trim() ? form.notes.trim() : null,
        },
      ]);
      toast.success(
        `样例已登记：新增 ${res.created}，更新 ${res.updated}，合计 ${res.total}（按 file_hash 幂等）`,
      );
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
            手工登记一份标书样例（全册登记与溯源）。后端无单条登记端点，经 bulk
            幂等导入提交——file_hash 重复时仅入库一次。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="bid-sample-title">标题 *</Label>
            <Input
              id="bid-sample-title"
              value={form.title}
              placeholder="如：××市××医院综合楼施工投标技术标（脱敏册）"
              onChange={(e) => setField({ title: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="bid-sample-path">来源路径 *</Label>
            <Input
              id="bid-sample-path"
              value={form.source_path}
              placeholder="references/samples/xxx.docx"
              onChange={(e) => setField({ source_path: e.target.value })}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="bid-sample-hash">
              文件哈希（SHA-256 十六进制，64 位）*
            </Label>
            <Input
              id="bid-sample-hash"
              value={form.file_hash}
              placeholder="如 736abe72c5cc68a7…（64 位十六进制）"
              onChange={(e) => {
                setField({ file_hash: e.target.value });
                if (hashError) setHashError(null);
              }}
              className="font-mono"
            />
            {hashError && (
              <p className="text-destructive text-xs">{hashError}</p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="bid-sample-industry">行业 *</Label>
              <Input
                id="bid-sample-industry"
                value={form.industry}
                placeholder="如：建筑 / 煤炭 / 医疗"
                onChange={(e) => setField({ industry: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="bid-sample-category">项目类别 *</Label>
              <Input
                id="bid-sample-category"
                value={form.project_category}
                placeholder="如：房建施工 / 矿井建设"
                onChange={(e) => setField({ project_category: e.target.value })}
              />
            </div>
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
              <AdminSelect
                value={form.status}
                onValueChange={(v) => setField({ status: v })}
                options={SAMPLE_STATUSES}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="bid-sample-notes">备注</Label>
            <Textarea
              id="bid-sample-notes"
              rows={2}
              value={form.notes ?? ""}
              placeholder="脱敏要求 / 来源册说明 / 溯源备注"
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

// ============== 批量导入对话框（bank_compile 产 registration.json 直接粘贴） ==============

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
  const [result, setResult] = useState<BidSampleBulkResult | null>(null);

  // 输入即解析校验——提交前给出条数与首个错误（含条目序号）
  const parsed = useMemo<{ items?: BidSampleUpsertInput[]; error?: string }>(
    () => (text.trim() ? parseBulkItems(text) : {}),
    [text],
  );

  const submit = async () => {
    if (!parsed.items) return;
    setSubmitting(true);
    try {
      const res = await bidMaterialsApi.samples.importBulk(parsed.items);
      setResult(res);
      toast.success(
        `导入完成：新增 ${res.created} 条，更新 ${res.updated} 条，合计 ${res.total} 条（按 file_hash 幂等）`,
      );
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
            bank_compile 产 registration.json 直接粘贴（{`{"items":[…]}`}{" "}
            形态）；也接受裸数组 […] 或单对象 {"{…}"}。每条含 title /
            source_path / file_hash / industry / project_category / scenario /
            status，可选 notes。按 file_hash 幂等 upsert，可重复执行。
          </DialogDescription>
        </DialogHeader>
        <Textarea
          rows={10}
          className="font-mono text-xs"
          placeholder={`{\n  "items": [\n    {\n      "title": "××工程施工投标文件（技术标·脱敏册）",\n      "source_path": "references/samples/xxx.docx",\n      "file_hash": "736abe72c5cc68a7…（64 位十六进制）",\n      "industry": "建筑",\n      "project_category": "房建施工",\n      "scenario": "bid_sample",\n      "status": "indexed"\n    }\n  ]\n}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {parsed.error ? (
          <p className="text-destructive text-sm">{parsed.error}</p>
        ) : parsed.items ? (
          <p className="text-sm text-emerald-700">
            已解析 {parsed.items.length} 条，校验通过，可导入。
          </p>
        ) : null}
        {result && (
          <p className="text-muted-foreground text-sm">
            上次导入：新增 {result.created} 条，更新 {result.updated} 条，合计{" "}
            {result.total} 条。
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            关闭
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={submitting || !parsed.items}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
