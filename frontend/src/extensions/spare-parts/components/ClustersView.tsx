"use client";

import { AlertTriangle, Check, ChevronLeft, ChevronRight, Crosshair, GitMerge, PackageSearch, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
import { EmptyRow, PageHeader } from "@/extensions/spare-parts/components/PageHeader";
import { TracebackDrawer } from "@/extensions/spare-parts/components/TracebackDrawer";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/spare-parts/components/ui/table";
import type { CspCluster, CspItem } from "@/extensions/spare-parts/types";
import {
  useBatchConfirmClusters,
  useCluster,
  useClusters,
  useConfirmCluster,
  useMergeClusters,
  useMoveItem,
  useRejectCluster,
  useUpdateCluster,
} from "@/extensions/spare-parts/hooks";
import { cn } from "@/lib/utils";

const statusBadge: Record<string, string> = {
  pending: "bg-warning/15 text-warning",
  confirmed: "bg-success/15 text-success",
  rejected: "bg-muted text-muted-foreground",
};

const statusLabel: Record<string, string> = {
  pending: "待审",
  confirmed: "已确认",
  rejected: "已拒绝",
};

/** Inline borderless input that looks like text until focused; commits on blur. */
function InlineEdit({
  value,
  placeholder,
  onCommit,
  className,
}: {
  value: string | null;
  placeholder: string;
  onCommit: (v: string) => void;
  className?: string;
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
      className={cn(
        "h-8 border-transparent bg-transparent px-1 hover:border-border focus-visible:border-border",
        className,
      )}
    />
  );
}

const PAGE_SIZE = 20;

export function ClustersView() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"pending" | "confirmed" | "rejected" | "all">("pending");
  const [page, setPage] = useState(1);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeName, setMergeName] = useState("");
  const [mergeCategory, setMergeCategory] = useState("未分类");
  const [moveItem, setMoveItem] = useState<{ itemId: string; name: string } | null>(null);
  const [moveTarget, setMoveTarget] = useState<string | null>(null);
  const [trace, setTrace] = useState<CspItem | null>(null);

  const skip = (page - 1) * PAGE_SIZE;
  const clustersQuery = useClusters({
    cluster_status: filter === "all" ? undefined : filter,
    skip,
    limit: PAGE_SIZE,
  });
  const clusterQuery = useCluster(selectedId);
  const confirmMutation = useConfirmCluster();
  const rejectMutation = useRejectCluster();
  const updateMutation = useUpdateCluster();
  const mergeMutation = useMergeClusters();
  const moveMutation = useMoveItem();
  const batchConfirmMutation = useBatchConfirmClusters();

  const clusters = clustersQuery.data?.items ?? [];
  const total = clustersQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const detail = clusterQuery.data;

  // clamp page when the tail empties after a batch confirm / reject / merge
  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [page, totalPages]);

  const pageIds = clusters.map((c) => c.id);
  const allChecked = pageIds.length > 0 && pageIds.every((id) => checked.has(id));
  const someChecked = pageIds.some((id) => checked.has(id));
  const checkedPendingCount = clusters.filter(
    (c) => checked.has(c.id) && c.status === "pending",
  ).length;
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someChecked && !allChecked;
  }, [someChecked, allChecked]);

  const toggleCheck = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const toggleSelectAll = () => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (allChecked) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const doBatchConfirm = async () => {
    const targets = clusters
      .filter((c) => checked.has(c.id) && c.status === "pending")
      .map((c) => ({ id: c.id, version: c.version }));
    if (targets.length === 0) return;
    setBatchMsg(null);
    try {
      const res = await batchConfirmMutation.mutateAsync(targets);
      setChecked(new Set());
      setBatchMsg(
        res.fail > 0
          ? `已确认 ${res.ok}/${res.total}，${res.fail} 个失败（可能被他人改动，请刷新重试）`
          : `已确认 ${res.ok} 个分组`,
      );
    } catch {
      setBatchMsg("批量确认失败，请重试。");
    }
  };

  const gotoPage = (p: number) => {
    setPage(p);
    setChecked(new Set());
    setSelectedId(null);
  };

  const openMerge = () => {
    // default representative name = first checked cluster's name
    const first = clusters.find((c) => checked.has(c.id));
    setMergeName(first?.representative_name ?? "");
    setMergeCategory(first?.category ?? "未分类");
    setMergeOpen(true);
  };

  const doMerge = async () => {
    if (!mergeName.trim() || checked.size < 2) return;
    await mergeMutation.mutateAsync({
      cluster_ids: [...checked],
      representative_name: mergeName.trim(),
      category: mergeCategory.trim() || "未分类",
    });
    setMergeOpen(false);
    setChecked(new Set());
    setSelectedId(null);
  };

  const doMove = async () => {
    if (!moveItem || !moveTarget) return;
    await moveMutation.mutateAsync({ item_id: moveItem.itemId, target_cluster_id: moveTarget });
    setMoveItem(null);
    setMoveTarget(null);
  };

  return (
    <div className="space-y-6 p-8">
      <PageHeader
        title="分组审核"
        description="审核自动分组：合并同义组、移动误归类项、拒绝错误组、编辑类别。确认后统计才生效。"
        icon={<PackageSearch className="w-4 h-4" />}
        actions={
          <>
            <div className="flex rounded-md border">
              {(["pending", "confirmed", "rejected", "all"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => { setFilter(f); setPage(1); setChecked(new Set()); setBatchMsg(null); }}
                  className={cn(
                    "px-3 py-1.5 text-sm transition-colors",
                    filter === f ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f === "pending" ? "待审核" : f === "confirmed" ? "已确认" : f === "rejected" ? "已拒绝" : "全部"}
                </button>
              ))}
            </div>
            {checkedPendingCount > 0 ? (
              <Button size="sm" onClick={doBatchConfirm} disabled={batchConfirmMutation.isPending}>
                <Check className="h-4 w-4" />
                批量确认({checkedPendingCount})
              </Button>
            ) : null}
            {checked.size >= 2 ? (
              <Button size="sm" onClick={openMerge} disabled={mergeMutation.isPending}>
                <GitMerge className="h-4 w-4" />
                合并选中({checked.size})
              </Button>
            ) : null}
            {batchMsg ? <span className="text-xs text-muted-foreground">{batchMsg}</span> : null}
            <Button variant="outline" size="sm" onClick={() => clustersQuery.refetch()}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
        {/* Left: cluster list with multi-select */}
        <Card className="max-h-[calc(100vh-220px)] overflow-hidden">
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">货物分组</h3>
              {clusters.length > 0 ? (
                <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-muted-foreground">
                  <input
                    ref={selectAllRef}
                    type="checkbox"
                    checked={allChecked}
                    onChange={toggleSelectAll}
                    className="accent-primary"
                  />
                  全选本页
                </label>
              ) : null}
            </div>
            <p className="text-xs text-muted-foreground">
              共 {total} 个分组
              {total > 0 ? ` · 第 ${skip + 1}-${Math.min(skip + clusters.length, total)} 条` : ""}
            </p>
          </div>
          <CardContent className="overflow-y-auto max-h-[calc(100vh-280px)] p-0">
            {clustersQuery.isLoading ? (
              <p className="p-6 text-center text-sm text-muted-foreground">加载中…</p>
            ) : clusters.length === 0 ? (
              <p className="p-6 text-center text-sm text-muted-foreground">没有符合条件的分组。</p>
            ) : (
              <ul className="divide-y divide-border">
                {clusters.map((c) => (
                  <li key={c.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={checked.has(c.id)}
                      onChange={() => toggleCheck(c.id)}
                      className="ml-3 accent-primary shrink-0"
                    />
                    <button
                      onClick={() => setSelectedId(c.id)}
                      className={cn(
                        "flex min-w-0 flex-1 items-center justify-between gap-2 px-2 py-3 text-left transition-colors hover:bg-accent",
                        selectedId === c.id && "bg-accent",
                      )}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">
                          {c.representative_name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {c.category} · {c.item_count} 项
                        </p>
                      </div>
                      <span className={cn("rounded px-1.5 py-0.5 text-xs shrink-0", statusBadge[c.status])}>
                        {statusLabel[c.status] ?? c.status}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
          {total > PAGE_SIZE ? (
            <div className="flex items-center justify-between border-t border-border px-4 py-2 text-xs text-muted-foreground">
              <span>
                第 {page}/{totalPages} 页
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2"
                  disabled={page <= 1}
                  onClick={() => gotoPage(page - 1)}
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                  上一页
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2"
                  disabled={page >= totalPages}
                  onClick={() => gotoPage(page + 1)}
                >
                  下一页
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ) : null}
        </Card>

        {/* Right: selected cluster detail */}
        <Card>
          <CardContent className="space-y-4 p-6">
            {!selectedId ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                ← 从左侧选择一个分组查看明细。
              </p>
            ) : clusterQuery.isLoading ? (
              <p className="py-12 text-center text-sm text-muted-foreground">加载中…</p>
            ) : !detail ? (
              <p className="py-12 text-center text-sm text-muted-foreground">分组不存在。</p>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <h2 className="text-lg font-semibold text-foreground">
                      {detail.representative_name}
                    </h2>
                    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <span>类别:</span>
                      <InlineEdit
                        value={detail.category}
                        placeholder="类别"
                        onCommit={(v) => updateMutation.mutate({ id: detail.id, body: { category: v } })}
                        className="w-32"
                      />
                      <span>· {detail.item_count} 项 · v{detail.version}</span>
                    </div>
                  </div>
                  {detail.status === "pending" ? (
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={() => confirmMutation.mutate({ id: detail.id, expected_version: detail.version })}
                        disabled={confirmMutation.isPending}
                      >
                        <Check className="h-4 w-4" />
                        确认分组
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => rejectMutation.mutate({ id: detail.id, expected_version: detail.version })}
                        disabled={rejectMutation.isPending}
                        title="拒绝该分组（从已确认统计中剔除）"
                      >
                        <X className="h-4 w-4" />
                        拒绝
                      </Button>
                    </div>
                  ) : (
                    <span className={cn("rounded px-2 py-0.5 text-xs shrink-0", statusBadge[detail.status])}>
                      {statusLabel[detail.status] ?? detail.status}
                    </span>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {([
                    ["均值", detail.stats?.mean],
                    ["最大", detail.stats?.max],
                    ["最小", detail.stats?.min],
                    ["中位数", detail.stats?.median],
                  ] as const).map(([label, val]) => (
                    <div key={label} className="rounded-lg border border-border p-3">
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="text-sm font-semibold tabular-nums text-foreground">
                        {val != null ? val.toLocaleString() : "—"}
                      </p>
                    </div>
                  ))}
                </div>

                {/* Items */}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>货物名称</TableHead>
                      <TableHead>规格</TableHead>
                      <TableHead className="text-right">工程量</TableHead>
                      <TableHead className="text-right">单价</TableHead>
                      <TableHead>来源合同</TableHead>
                      <TableHead className="text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.items.length === 0 ? (
                      <EmptyRow colSpan={6}>该组暂无明细。</EmptyRow>
                    ) : (
                      detail.items.map((item) => (
                        <TableRow key={item.id} className={item.is_outlier ? "bg-destructive/10" : ""}>
                          <TableCell className="font-medium">
                            {item.is_outlier ? (
                              <span className="inline-flex items-center gap-1">
                                <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
                                {item.part_name}
                              </span>
                            ) : (
                              item.part_name
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">{item.spec ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {item.quantity != null
                              ? `${item.quantity}${item.unit ? item.unit : ""}`
                              : "—"}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {item.unit_price?.toLocaleString() ?? "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {item.source_contract_no ?? "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
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
                              <Button
                                size="sm"
                                variant="ghost"
                                title="移动到其他分组"
                                onClick={() => { setMoveItem({ itemId: item.id, name: item.part_name }); setMoveTarget(null); }}
                              >
                                移动到…
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>

                {confirmMutation.isError ? (
                  <p className="text-sm text-destructive">确认失败：{(confirmMutation.error).message}</p>
                ) : null}
                {rejectMutation.isError ? (
                  <p className="text-sm text-destructive">拒绝失败：{(rejectMutation.error).message}</p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Merge dialog */}
      {mergeOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMergeOpen(false)} />
          <div className="relative w-full max-w-md rounded-xl border border-border bg-background p-6 shadow-xl">
            <h3 className="mb-1 text-lg font-semibold text-foreground">合并 {checked.size} 个分组</h3>
            <p className="mb-4 text-xs text-muted-foreground">
              选中分组的全部明细将归并到一个新组，原分组删除。代表性名称会成为新组名。
            </p>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">代表性名称</label>
                <Input value={mergeName} onChange={(e) => setMergeName(e.target.value)} placeholder="新组名" />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">类别</label>
                <Input value={mergeCategory} onChange={(e) => setMergeCategory(e.target.value)} placeholder="类别" />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setMergeOpen(false)}>取消</Button>
              <Button size="sm" onClick={doMerge} disabled={!mergeName.trim() || mergeMutation.isPending}>
                <GitMerge className="h-4 w-4" />
                合并
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Move-to-target dialog */}
      {moveItem ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMoveItem(null)} />
          <div className="relative w-full max-w-md rounded-xl border border-border bg-background p-6 shadow-xl">
            <h3 className="mb-1 text-lg font-semibold text-foreground">移动明细到其他分组</h3>
            <p className="mb-4 truncate text-xs text-muted-foreground">货物：{moveItem.name}</p>
            <label className="mb-1 block text-sm font-medium text-foreground">目标分组</label>
            <Select value={moveTarget ?? ""} onValueChange={setMoveTarget}>
              <SelectTrigger>
                <SelectValue placeholder="选择目标分组" />
              </SelectTrigger>
              <SelectContent>
                {clusters
                  .filter((c: CspCluster) => c.id !== selectedId)
                  .map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.representative_name}（{c.category} · {c.item_count}项）
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setMoveItem(null)}>取消</Button>
              <Button size="sm" onClick={doMove} disabled={!moveTarget || moveMutation.isPending}>
                移动
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <TracebackDrawer
        docId={trace?.document_id ?? null}
        page={trace?.source_page ?? null}
        bbox={trace?.source_bbox ?? null}
        onClose={() => setTrace(null)}
      />
    </div>
  );
}
