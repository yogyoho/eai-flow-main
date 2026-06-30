"use client";

import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Crosshair,
  PackageSearch,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { TracebackDrawer } from "@/extensions/contract-price/components/TracebackDrawer";
import { EmptyRow, PageHeader } from "@/extensions/contract-price/components/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import type { CpaItem, CpaRun } from "@/extensions/contract-price/types";
import {
  useBatchDeleteItems,
  useDeleteItem,
  useDeleteItemsByRun,
  useItemContracts,
  useItems,
  useRuns,
  useUpdateItem,
} from "@/extensions/contract-price/hooks";

const PAGE_SIZE = 50;

const STATUS_TONE: Record<string, string> = {
  ok: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5",
  needs_review: "text-amber-600 border-amber-500/30 bg-amber-500/5",
  corrected: "text-blue-600 border-blue-500/30 bg-blue-500/5",
};
const STATUS_LABEL: Record<string, string> = {
  ok: "已校验",
  needs_review: "待核验",
  corrected: "已修正",
};

/** Styled checkbox matching roles-page PermCheckbox (CSS, no framer-motion). */
function FilterCheckbox({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <label className="group flex items-center gap-2 text-sm cursor-pointer select-none">
      <input type="checkbox" checked={checked} onChange={onChange} className="sr-only peer" />
      <span
        className={cn(
          "relative inline-flex items-center justify-center w-[18px] h-[18px] shrink-0 rounded-[5px] border-[1.5px] transition-all duration-200 ease-out",
          checked
            ? "bg-primary border-primary shadow-[0_1px_4px_rgba(var(--color-primary),0.3)]"
            : "bg-transparent border-muted-foreground/30 group-hover:border-muted-foreground/50",
        )}
      >
        <svg viewBox="0 0 14 14" fill="none" className="w-[11px] h-[11px]" aria-hidden="true">
          <path
            d="M3 7.5L5.8 10.2L11 4"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={cn(
              "transition-all duration-200 ease-out",
              checked ? "text-primary-foreground opacity-100" : "text-transparent opacity-0",
            )}
          />
        </svg>
      </span>
      <span className={cn("transition-colors duration-200", checked ? "text-foreground font-medium" : "text-muted-foreground")}>
        {label}
      </span>
    </label>
  );
}

/** Render tech_params dict as "k: v · k: v", or "无" when empty/null. */
function formatTechParams(tp: Record<string, string> | null | undefined): string {
  if (!tp) return "无";
  const entries = Object.entries(tp).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return "无";
  return entries.map(([k, v]) => `${k}: ${v}`).join(" · ");
}

/** Compact label/value field for the expanded detail row. */
function DetailField({ label, value, span }: { label: string; value: string; span?: boolean }) {
  return (
    <div className={span ? "col-span-2 sm:col-span-3 lg:col-span-4" : ""}>
      <span className="text-muted-foreground">{label}: </span>
      <span className="text-foreground tabular-nums">{value}</span>
    </div>
  );
}

/** Group items by run_id; null-run items go into a "历史数据" bucket. */
function groupByRun(items: CpaItem[], runs: CpaRun[]) {
  const runMap = new Map(runs.map((r) => [r.id, r]));
  const groups: { runId: string | null; run: CpaRun | null; items: CpaItem[] }[] = [];
  const seen = new Map<string | null, CpaItem[]>();

  for (const it of items) {
    const key = it.run_id ?? null;
    if (!seen.has(key)) seen.set(key, []);
    seen.get(key)!.push(it);
  }

  // sort: groups with run_id first (newest run first), then null-run
  const keys = [...seen.keys()].sort((a, b) => {
    if (!a && !b) return 0;
    if (!a) return 1;
    if (!b) return -1;
    const ra = runMap.get(a);
    const rb = runMap.get(b);
    return (rb?.started_at ?? "").localeCompare(ra?.started_at ?? "");
  });

  for (const k of keys) {
    groups.push({ runId: k, run: k ? runMap.get(k) ?? null : null, items: seen.get(k)! });
  }
  return groups;
}

export function ItemsView() {
  const [keyword, setKeyword] = useState("");
  const [applied, setApplied] = useState("");
  const [onlyOutliers, setOnlyOutliers] = useState(false);
  const [onlyReview, setOnlyReview] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [priceInput, setPriceInput] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [note, setNote] = useState("");
  const [trace, setTrace] = useState<CpaItem | null>(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null); // item id to confirm
  const [confirmBatchDelete, setConfirmBatchDelete] = useState(false);
  const [confirmGroupDelete, setConfirmGroupDelete] = useState<string | null>(null); // run id
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [contractFilter, setContractFilter] = useState<string>("all");

  const { data, isLoading, isFetching, refetch } = useItems({
    goods_name: applied || undefined,
    source_contract_no: contractFilter === "all" ? undefined : contractFilter,
    only_outliers: onlyOutliers,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  });
  const { data: runsData } = useRuns({ limit: 100 });
  const { data: contractsData } = useItemContracts();
  const updateItem = useUpdateItem();
  const deleteItem = useDeleteItem();
  const batchDeleteItems = useBatchDeleteItems();
  const deleteItemsByRun = useDeleteItemsByRun();

  const raw = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items = onlyReview ? raw.filter((i) => i.validation_status === "needs_review") : raw;
  const runs: CpaRun[] = runsData?.items ?? [];

  // Group items by run
  const groups = useMemo(() => groupByRun(items, runs), [items, runs]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = (groupItems: CpaItem[]) => {
    const ids = groupItems.map((i) => i.id);
    const allSelected = ids.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (allSelected) next.delete(id); else next.add(id);
      }
      return next;
    });
  };

  const toggleCollapse = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleDelete = async (id: string) => {
    await deleteItem.mutateAsync(id);
    setConfirmDelete(null);
    setSelected((prev) => { const n = new Set(prev); n.delete(id); return n; });
  };

  const handleBatchDelete = async () => {
    await batchDeleteItems.mutateAsync([...selected]);
    setConfirmBatchDelete(false);
    setSelected(new Set());
  };

  const handleGroupDelete = async (runId: string) => {
    await deleteItemsByRun.mutateAsync(runId);
    setConfirmGroupDelete(null);
  };

  const formatRunLabel = (run: CpaRun | null, runId: string | null) => {
    if (!run) return runId ? `任务 ${runId.slice(0, 8)}…` : "未关联分析任务";
    const d = new Date(run.started_at);
    const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    const phase = typeof run.progress === "object" && run.progress ? (run.progress as Record<string, unknown>).phase : null;
    return `${phase === "parse" ? "📄" : "📊"} ${ds} · ${run.status === "completed" ? "✅" : "⏳"} · ${run.items_extracted}条`;
  };

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="分项明细"
        description="每条货物的单价与参数。待核验项(OCR 数字粘连/量级异常)需用溯源对照原文后修正。"
        icon={<PackageSearch className="w-4 h-4" />}
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
        }
      />

      <Card>
        <CardContent className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setApplied(keyword);
                setPage(0);
              }}
            >
              <div className="relative max-w-sm">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="搜索货物名称"
                  className="pl-9"
                />
              </div>
              <Button type="submit" size="sm">
                搜索
              </Button>
            </form>
            <FilterCheckbox
              checked={onlyOutliers}
              onChange={() => { setOnlyOutliers(!onlyOutliers); setPage(0); }}
              label="仅看异常价格"
            />
            <FilterCheckbox
              checked={onlyReview}
              onChange={() => setOnlyReview(!onlyReview)}
              label="仅看待核验"
            />
            <Select
              value={contractFilter}
              onValueChange={(v) => { setContractFilter(v); setPage(0); }}
            >
              <SelectTrigger className="w-[200px] h-9">
                <SelectValue placeholder="来源合同" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部合同</SelectItem>
                {(contractsData ?? []).map((c) => (
                  <SelectItem key={c.source_contract_no} value={c.source_contract_no}>
                    {c.source_contract_no} ({c.count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isLoading ? (
            <div className="text-sm text-muted-foreground py-8 text-center">加载中…</div>
          ) : items.length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">暂无明细。</div>
          ) : (
            <>
              {/* Grouped table — scrollable container */}
              <div className="max-h-[calc(100vh-340px)] overflow-y-auto border border-border rounded-lg">
              {groups.map((group) => {
                const groupKey = group.runId ?? "__null__";
                const isCollapsed = collapsed.has(groupKey);
                const allSelected = group.items.length > 0 && group.items.every((it) => selected.has(it.id));

                return (
                  <div key={groupKey} className="border border-border rounded-lg overflow-hidden">
                    {/* Group header */}
                    <div className="flex items-center justify-between px-4 py-2 bg-muted/50">
                      <button
                        className="flex items-center gap-2 text-sm font-medium hover:text-foreground transition-colors"
                        onClick={() => toggleCollapse(groupKey)}
                      >
                        {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        {formatRunLabel(group.run, group.runId)}
                        <span className="text-xs text-muted-foreground">({group.items.length}条)</span>
                      </button>
                      <div className="flex items-center gap-2">
                        {group.items.some((it) => selected.has(it.id)) && (
                          <span className="text-xs text-muted-foreground">
                            已选 {group.items.filter((it) => selected.has(it.id)).length} 条
                          </span>
                        )}
                        {confirmBatchDelete ? (
                          <div className="flex items-center gap-1">
                            <span className="text-xs text-muted-foreground">确认删除已选?</span>
                            <Button size="sm" variant="destructive" className="text-xs h-7" onClick={handleBatchDelete} disabled={batchDeleteItems.isPending}>
                              确认
                            </Button>
                            <Button size="sm" variant="ghost" className="text-xs h-7" onClick={() => setConfirmBatchDelete(false)}>
                              取消
                            </Button>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-xs text-destructive hover:text-destructive"
                            disabled={!group.items.some((it) => selected.has(it.id))}
                            onClick={() => setConfirmBatchDelete(true)}
                          >
                            <Trash2 className="h-3 w-3" />
                            批量删除
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Group body */}
                    {!isCollapsed && (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-10">
                              <input
                                type="checkbox"
                                checked={allSelected}
                                ref={(el) => {
                                  if (el) el.indeterminate = !allSelected && group.items.some((it) => selected.has(it.id));
                                }}
                                onChange={() => toggleSelectAll(group.items)}
                                className="accent-primary cursor-pointer"
                              />
                            </TableHead>
                            <TableHead>货物名称</TableHead>
                            <TableHead>规格</TableHead>
                            <TableHead>来源合同</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead className="text-right">单价</TableHead>
                            <TableHead className="text-right w-[180px]">操作</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {group.items.map((item) => (
                            <Fragment key={item.id}>
                            <TableRow
                              className={cn(
                                "hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors",
                                item.is_outlier && !selected.has(item.id) ? "bg-destructive/10" : "",
                                selected.has(item.id) ? "bg-blue-50 dark:bg-blue-950/30" : "",
                              )}
                              style={{ cursor: "pointer" }}
                              onClick={(e) => {
                                const tag = (e.target as HTMLElement).tagName;
                                if (tag !== "BUTTON" && tag !== "INPUT" && tag !== "A" && tag !== "SVG" && tag !== "PATH") {
                                  toggleSelect(item.id);
                                }
                              }}
                            >
                              <TableCell>
                                <input
                                  type="checkbox"
                                  checked={selected.has(item.id)}
                                  onChange={() => toggleSelect(item.id)}
                                  className="accent-primary"
                                />
                              </TableCell>
                              <TableCell className="font-medium">
                                <div className="flex items-center gap-1.5">
                                  {editingId !== item.id && (
                                    <button
                                      type="button"
                                      onClick={() => toggleExpand(item.id)}
                                      className="text-muted-foreground hover:text-foreground shrink-0"
                                      title={expanded.has(item.id) ? "收起明细" : "展开明细"}
                                    >
                                      {expanded.has(item.id)
                                        ? <ChevronDown className="h-3.5 w-3.5" />
                                        : <ChevronRight className="h-3.5 w-3.5" />}
                                    </button>
                                  )}
                                  {editingId === item.id ? (
                                    <Input
                                      value={nameInput}
                                      onChange={(e) => setNameInput(e.target.value)}
                                      className="h-8 min-w-[140px]"
                                    />
                                  ) : item.is_outlier ? (
                                    <span className="inline-flex items-center gap-1">
                                      <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                                      {item.goods_name}
                                    </span>
                                  ) : (
                                    item.goods_name
                                  )}
                                </div>
                              </TableCell>
                              <TableCell className="text-muted-foreground">{item.spec_model ?? "—"}</TableCell>
                              <TableCell className="text-muted-foreground">
                                {item.source_contract_no ?? "—"}
                              </TableCell>
                              <TableCell>
                                <span
                                  className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${
                                    STATUS_TONE[item.validation_status] ?? STATUS_TONE.ok
                                  }`}
                                >
                                  {STATUS_LABEL[item.validation_status] ?? item.validation_status}
                                </span>
                              </TableCell>
                              <TableCell className="text-right tabular-nums">
                                {editingId === item.id ? (
                                  <Input
                                    type="number"
                                    value={priceInput}
                                    onChange={(e) => setPriceInput(e.target.value)}
                                    className="h-8 w-28 text-right"
                                  />
                                ) : item.unit_price == null ? (
                                  <span className="text-amber-600">待核验</span>
                                ) : item.is_outlier ? (
                                  <span className="text-destructive">{item.unit_price.toLocaleString()}</span>
                                ) : (
                                  item.unit_price.toLocaleString()
                                )}
                              </TableCell>
                              <TableCell className="text-right">
                                {editingId === item.id ? (
                                  <div className="flex items-center justify-end gap-1">
                                    <Input
                                      value={note}
                                      onChange={(e) => setNote(e.target.value)}
                                      placeholder="修正原因"
                                      className="h-8 w-32"
                                    />
                                    <Button
                                      size="sm"
                                      onClick={async () => {
                                        await updateItem.mutateAsync({
                                          id: item.id,
                                          body: {
                                            unit_price: Number(priceInput),
                                            goods_name: nameInput.trim() || undefined,
                                            note: note || undefined,
                                          },
                                        });
                                        setEditingId(null);
                                        setNote("");
                                      }}
                                    >
                                      保存
                                    </Button>
                                    <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                                      取消
                                    </Button>
                                  </div>
                                ) : (
                                  <div className="flex items-center justify-end gap-1">
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => {
                                        setEditingId(item.id);
                                        setPriceInput(String(item.unit_price ?? ""));
                                        setNameInput(item.goods_name ?? "");
                                      }}
                                    >
                                      修正
                                    </Button>
                                    {item.validation_status === "needs_review" && (
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="text-emerald-600 hover:text-emerald-600"
                                        title="溯源确认正确后标记为已校验(价格进入统计)"
                                        onClick={() =>
                                          updateItem.mutateAsync({
                                            id: item.id,
                                            body: { validation_status: "ok" },
                                          })
                                        }
                                      >
                                        ✓ 已校验
                                      </Button>
                                    )}
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      disabled={item.source_page == null}
                                      title={item.source_page == null ? "无溯源坐标" : "溯源到原文"}
                                      onClick={() => setTrace(item)}
                                    >
                                      <Crosshair className="h-3.5 w-3.5 text-rose-500" />
                                      溯源
                                    </Button>
                                    {confirmDelete === item.id ? (
                                      <div className="flex items-center gap-1">
                                        <Button
                                          size="sm"
                                          variant="destructive"
                                          className="text-xs h-7"
                                          onClick={() => handleDelete(item.id)}
                                          disabled={deleteItem.isPending}
                                        >
                                          确认
                                        </Button>
                                        <Button
                                          size="sm"
                                          variant="ghost"
                                          className="text-xs h-7"
                                          onClick={() => setConfirmDelete(null)}
                                        >
                                          取消
                                        </Button>
                                      </div>
                                    ) : (
                                      <Button
                                        size="sm"
                                        variant="ghost"
                                        className="text-muted-foreground hover:text-destructive"
                                        onClick={() => setConfirmDelete(item.id)}
                                      >
                                        <Trash2 className="h-3.5 w-3.5" />
                                      </Button>
                                    )}
                                  </div>
                                )}
                              </TableCell>
                            </TableRow>
                            {expanded.has(item.id) && (
                              <TableRow className="bg-muted/30 hover:bg-muted/30">
                                <TableCell colSpan={7} className="py-3">
                                  <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-xs sm:grid-cols-3 lg:grid-cols-4">
                                    <DetailField label="工程量" value={item.quantity != null ? `${item.quantity}${item.unit ? " " + item.unit : ""}` : "—"} />
                                    <DetailField label="含税单价" value={item.unit_price != null ? item.unit_price.toLocaleString() : "—"} />
                                    <DetailField label="不含税单价(审计)" value={item.price_untaxed != null ? item.price_untaxed.toLocaleString() : "—"} />
                                    <DetailField
                                      label="置信度"
                                      value={item.confidence != null ? `${(item.confidence * 100).toFixed(0)}%` : "—"}
                                    />
                                    <DetailField label="溯源页" value={item.source_page != null ? `第 ${item.source_page} 页` : "—"} />
                                    <DetailField label="技术参数" value={formatTechParams(item.tech_params)} span />
                                  </div>
                                </TableCell>
                              </TableRow>
                            )}
                            </Fragment>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                );
              })}
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between pt-2">
                <span className="text-xs text-muted-foreground">
                  共 {total} 条 · 第 {page + 1}/{totalPages} 页
                </span>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page <= 0}
                    onClick={() => { setPage(0); setSelected(new Set()); }}
                  >
                    首页
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page <= 0}
                    onClick={() => { setPage(page - 1); setSelected(new Set()); }}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const start = Math.max(0, Math.min(page - 2, totalPages - 5));
                    const p = start + i;
                    return (
                      <Button
                        key={p}
                        size="sm"
                        variant={p === page ? "default" : "outline"}
                        onClick={() => { setPage(p); setSelected(new Set()); }}
                      >
                        {p + 1}
                      </Button>
                    );
                  })}
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page >= totalPages - 1}
                    onClick={() => { setPage(page + 1); setSelected(new Set()); }}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page >= totalPages - 1}
                    onClick={() => { setPage(totalPages - 1); setSelected(new Set()); }}
                  >
                    末页
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <TracebackDrawer
        docId={trace?.document_id ?? null}
        page={trace?.source_page ?? null}
        bbox={trace?.source_bbox ?? null}
        onClose={() => setTrace(null)}
      />
    </div>
  );
}
