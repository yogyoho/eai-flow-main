"use client";

import {
  AlertTriangle,
  Boxes,
  Check,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  GitMerge,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  EmptyRow,
  PageHeader,
} from "@/extensions/contract-price/components/PageHeader";
import { TracebackDrawer } from "@/extensions/contract-price/components/TracebackDrawer";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";
import {
  useBatchConfirmClusters,
  useCluster,
  useClusters,
  useConfirmCluster,
  useMergeClusters,
  useMoveItem,
  useRejectCluster,
  useUpdateCluster,
} from "@/extensions/contract-price/hooks";
import {
  baselineShiftDocIds,
  buildBaselineTooltips,
  itemToStatRow,
  rowOutlierTier,
} from "@/extensions/contract-price/outlier-semantics";
import type { CpaCluster, CpaItem } from "@/extensions/contract-price/types";
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
        "hover:border-border focus-visible:border-border h-8 border-transparent bg-transparent px-1",
        className,
      )}
    />
  );
}

const PAGE_SIZE = 20;

/** 标签 chip 输入(参照角色管理-自定义策略「条件值」控件): 徽章带叉删除,输入
 * 回车/逗号添加,Backspace 空草稿删尾。值=逗号连接串(category 列, 零迁移)。 */
function TagChipsInput({
  value,
  placeholder,
  onCommit,
}: {
  value: string | null;
  placeholder: string;
  onCommit: (v: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const tags = useMemo(
    () =>
      (value ?? "")
        .split(/[,，、]/)
        .map((s) => s.trim())
        .filter(Boolean),
    [value],
  );
  const commit = (next: string[]) => onCommit(next.join(","));
  const add = () => {
    const parts = draft
      .split(/[,，、]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length === 0) return;
    commit([...tags, ...parts.filter((p) => !tags.includes(p))]);
    setDraft("");
  };
  const remove = (t: string) => commit(tags.filter((x) => x !== t));
  return (
    <div className="bg-background border-input focus-within:ring-primary/50 flex min-h-8 flex-wrap items-center gap-1 rounded border px-2 py-0.5 focus-within:ring-2">
      {tags.map((t) => (
        <span
          key={t}
          className="border-primary/20 bg-primary/10 text-primary inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs"
        >
          {t}
          <button
            type="button"
            title="删除"
            onClick={() => remove(t)}
            className="hover:text-destructive transition-colors"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        type="text"
        className="placeholder:text-muted-foreground h-6 min-w-[90px] flex-1 bg-transparent text-sm outline-none"
        value={draft}
        placeholder={tags.length ? "" : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === "," || e.key === "，") {
            e.preventDefault();
            add();
          }
          if (e.key === "Backspace" && !draft && tags.length)
            remove(tags[tags.length - 1]!);
        }}
        onBlur={add}
      />
    </div>
  );
}

export function ClustersView() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<
    "pending" | "confirmed" | "rejected" | "all"
  >("pending");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [page, setPage] = useState(1);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeName, setMergeName] = useState("");
  const [mergeCategory, setMergeCategory] = useState("");
  const [moveItem, setMoveItem] = useState<{
    itemId: string;
    name: string;
  } | null>(null);
  const [moveTarget, setMoveTarget] = useState<string | null>(null);
  const [trace, setTrace] = useState<CpaItem | null>(null);

  const skip = (page - 1) * PAGE_SIZE;
  const clustersQuery = useClusters({
    cluster_status: filter === "all" ? undefined : filter,
    keyword: appliedSearch || undefined,
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

  // EAI-CUSTOM F3a 离群语义分层: 簇明细内按文档成片判定 + 行 id → 降级说明 tooltip。
  const detailItems: CpaItem[] = detail?.items ?? [];
  const statRows = useMemo(() => detailItems.map(itemToStatRow), [detailItems]);
  const baselineDocs = useMemo(() => baselineShiftDocIds(statRows), [statRows]);
  const baselineTooltips = useMemo(() => buildBaselineTooltips(statRows), [statRows]);

  // clamp page when the tail empties after a batch confirm / reject / merge
  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [page, totalPages]);

  const pageIds = clusters.map((c) => c.id);
  const allChecked =
    pageIds.length > 0 && pageIds.every((id) => checked.has(id));
  const someChecked = pageIds.some((id) => checked.has(id));
  const checkedPendingCount = clusters.filter(
    (c) => checked.has(c.id) && c.status === "pending",
  ).length;
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (selectAllRef.current)
      selectAllRef.current.indeterminate = someChecked && !allChecked;
  }, [someChecked, allChecked]);

  const toggleCheck = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
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
    setMergeCategory(first?.category ?? "");
    setMergeOpen(true);
  };

  const doMerge = async () => {
    if (!mergeName.trim() || checked.size < 2) return;
    await mergeMutation.mutateAsync({
      cluster_ids: [...checked],
      representative_name: mergeName.trim(),
      category: mergeCategory.trim(),
    });
    setMergeOpen(false);
    setChecked(new Set());
    setSelectedId(null);
  };

  const doMove = async () => {
    if (!moveItem || !moveTarget) return;
    await moveMutation.mutateAsync({
      item_id: moveItem.itemId,
      target_cluster_id: moveTarget,
    });
    setMoveItem(null);
    setMoveTarget(null);
  };

  return (
    <div className="space-y-6 p-8">
      {/* 标题行：刷新钉在最右，不随长描述换行 */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <PageHeader
            title="分组审核"
            description="审核自动分组：合并同义组、移动误归类项、拒绝错误组、编辑类别。确认后统计才生效。分组为上次「聚类分析」的结果——删除或修改货物后需重新聚类刷新，此处不提供单独删除。"
            icon={<Boxes className="h-6 w-6" />}
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => clustersQuery.refetch()}
        >
          <RefreshCw className="h-4 w-4" />
          刷新
        </Button>
      </div>

      {/* 控件行：搜索 + 筛选 + 批量操作 */}
      <div className="flex flex-wrap items-center gap-2">
        {/* 搜索: 与分项校验"搜索货物名称"同款样式;跨页找同类候选组,勾选后走「合并选中」 */}
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setAppliedSearch(search.trim());
            setPage(1);
            setChecked(new Set());
          }}
        >
          <div className="relative w-64">
            <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索分组名称/类目"
              className="pl-9"
            />
          </div>
          <Button type="submit" size="sm">
            搜索
          </Button>
        </form>
        {/* 与对话页-项目页 tabs（ui/tabs）同一组件，样式自动对齐 */}
        <Tabs
          value={filter}
          onValueChange={(v) => {
            setFilter(v as typeof filter);
            setPage(1);
            setChecked(new Set());
            setBatchMsg(null);
          }}
        >
          <TabsList>
            <TabsTrigger value="pending">待审核</TabsTrigger>
            <TabsTrigger value="confirmed">已确认</TabsTrigger>
            <TabsTrigger value="rejected">已拒绝</TabsTrigger>
            <TabsTrigger value="all">全部</TabsTrigger>
          </TabsList>
        </Tabs>
        {checkedPendingCount > 0 ? (
          <Button
            size="sm"
            onClick={doBatchConfirm}
            disabled={batchConfirmMutation.isPending}
          >
            <Check className="h-4 w-4" />
            批量确认({checkedPendingCount})
          </Button>
        ) : null}
        {checked.size >= 2 ? (
          <Button
            size="sm"
            onClick={openMerge}
            disabled={mergeMutation.isPending}
          >
            <GitMerge className="h-4 w-4" />
            合并选中({checked.size})
          </Button>
        ) : null}
        {batchMsg ? (
          <span className="text-muted-foreground text-xs">{batchMsg}</span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
        {/* Left: cluster list with multi-select */}
        <Card className="max-h-[calc(100vh-220px)] overflow-hidden">
          <div className="border-border border-b px-4 py-3 pt-0">
            <div className="flex items-center justify-between">
              <h3 className="text-foreground text-sm font-semibold">
                货物分组
              </h3>
              {clusters.length > 0 ? (
                <label className="text-muted-foreground flex cursor-pointer items-center gap-1.5 text-xs select-none">
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
            <p className="text-muted-foreground text-xs">
              共 {total} 个分组
              {total > 0
                ? ` · 第 ${skip + 1}-${Math.min(skip + clusters.length, total)} 条`
                : ""}
            </p>
          </div>
          <CardContent className="max-h-[calc(100vh-280px)] overflow-y-auto p-0">
            {clustersQuery.isLoading ? (
              <p className="text-muted-foreground p-6 text-center text-sm">
                加载中…
              </p>
            ) : clusters.length === 0 ? (
              <p className="text-muted-foreground p-6 text-center text-sm">
                没有符合条件的分组。
              </p>
            ) : (
              <ul className="divide-border divide-y">
                {clusters.map((c) => (
                  <li key={c.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={checked.has(c.id)}
                      onChange={() => toggleCheck(c.id)}
                      className="accent-primary ml-3 shrink-0"
                    />
                    <button
                      onClick={() => setSelectedId(c.id)}
                      className={cn(
                        "hover:bg-accent flex min-w-0 flex-1 items-center justify-between gap-2 px-2 py-3 text-left transition-colors",
                        selectedId === c.id && "bg-accent",
                      )}
                    >
                      <div className="min-w-0">
                        <p className="text-foreground truncate text-sm font-medium">
                          {c.representative_name}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {c.category
                            ?.split(/[,，、]/)
                            .map((t) => t.trim())
                            .filter(Boolean)
                            .map((t) => (
                              <span
                                key={t}
                                className="bg-muted text-muted-foreground mr-1 rounded px-1.5 py-0.5"
                              >
                                {t}
                              </span>
                            ))}
                          <span>{c.item_count} 项</span>
                        </p>
                      </div>
                      <span
                        className={cn(
                          "shrink-0 rounded px-1.5 py-0.5 text-xs",
                          statusBadge[c.status],
                        )}
                      >
                        {statusLabel[c.status] ?? c.status}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
          {total > PAGE_SIZE ? (
            <div className="border-border text-muted-foreground flex items-center justify-between border-t px-4 py-2 text-xs">
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
          <CardContent className="space-y-4 p-6 pt-0">
            {!selectedId ? (
              <p className="text-muted-foreground py-12 text-center text-sm">
                ← 从左侧选择一个分组查看明细。
              </p>
            ) : clusterQuery.isLoading ? (
              <p className="text-muted-foreground py-12 text-center text-sm">
                加载中…
              </p>
            ) : !detail ? (
              <p className="text-muted-foreground py-12 text-center text-sm">
                分组不存在。
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {/* 分组名可改: 与类别同款 InlineEdit,blur/Enter 提交 PATCH */}
                    <InlineEdit
                      value={detail.representative_name}
                      placeholder="分组名称"
                      onCommit={(v) => {
                        if (!v.trim()) return; // 空名拒绝,保留原名
                        updateMutation.mutate({
                          id: detail.id,
                          body: { representative_name: v },
                        });
                      }}
                      className="text-foreground text-lg font-semibold"
                    />
                    <div className="text-muted-foreground mt-1 flex items-center gap-2 text-xs">
                      <span>标签:</span>
                      <TagChipsInput
                        value={detail.category}
                        placeholder="加标签"
                        onCommit={(v) =>
                          updateMutation.mutate({
                            id: detail.id,
                            body: { category: v },
                          })
                        }
                      />
                      <span>
                        · {detail.item_count} 项 · v{detail.version}
                      </span>
                    </div>
                  </div>
                  {detail.status === "pending" ? (
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        size="sm"
                        onClick={() =>
                          confirmMutation.mutate({
                            id: detail.id,
                            expected_version: detail.version,
                          })
                        }
                        disabled={confirmMutation.isPending}
                      >
                        <Check className="h-4 w-4" />
                        确认分组
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          rejectMutation.mutate({
                            id: detail.id,
                            expected_version: detail.version,
                          })
                        }
                        disabled={rejectMutation.isPending}
                        title="拒绝该分组（从已确认统计中剔除）"
                      >
                        <X className="h-4 w-4" />
                        拒绝
                      </Button>
                    </div>
                  ) : (
                    <span
                      className={cn(
                        "shrink-0 rounded px-2 py-0.5 text-xs",
                        statusBadge[detail.status],
                      )}
                    >
                      {statusLabel[detail.status] ?? detail.status}
                    </span>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {(
                    [
                      ["均值", detail.stats?.mean],
                      ["最大", detail.stats?.max],
                      ["最小", detail.stats?.min],
                      ["中位数", detail.stats?.median],
                    ] as const
                  ).map(([label, val]) => (
                    <div
                      key={label}
                      className="border-border rounded-lg border p-3"
                    >
                      <p className="text-muted-foreground text-xs">{label}</p>
                      <p className="text-foreground text-sm font-semibold tabular-nums">
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
                      detail.items.map((item) => {
                        // EAI-CUSTOM F3a: 成片文档的离群行降级为琥珀「跨合同基线
                        // 差异」,真散点行保持红色异常。
                        const tier = rowOutlierTier(item, baselineDocs);
                        const tierTip =
                          tier === "baseline-shift"
                            ? baselineTooltips.get(item.id)
                            : undefined;
                        return (
                        <TableRow
                          key={item.id}
                          className={
                            tier === "outlier"
                              ? "bg-destructive/10"
                              : tier === "baseline-shift"
                                ? "bg-amber-500/5"
                                : ""
                          }
                        >
                          <TableCell className="font-medium">
                            {item.is_outlier ? (
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1",
                                  tier === "baseline-shift" && "cursor-help",
                                )}
                                title={tierTip}
                              >
                                <AlertTriangle
                                  className={cn(
                                    "h-3.5 w-3.5",
                                    tier === "baseline-shift"
                                      ? "text-amber-600"
                                      : "text-destructive",
                                  )}
                                />
                                {item.goods_name}
                              </span>
                            ) : (
                              item.goods_name
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {item.spec_model ?? "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground text-right tabular-nums">
                            {item.quantity != null
                              ? `${item.quantity}${item.unit ?? ""}`
                              : "—"}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {item.unit_price?.toLocaleString() ?? "—"}
                          </TableCell>
                          <TableCell className="text-muted-foreground px-4 py-3 font-mono text-xs">
                            {item.source_contract_no ?? "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={item.source_page == null}
                                title={
                                  item.source_page == null
                                    ? "无溯源坐标"
                                    : "溯源到原文"
                                }
                                onClick={() => setTrace(item)}
                              >
                                <Crosshair className="h-3.5 w-3.5 text-rose-500" />
                                溯源
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                title="移动到其他分组"
                                onClick={() => {
                                  setMoveItem({
                                    itemId: item.id,
                                    name: item.goods_name,
                                  });
                                  setMoveTarget(null);
                                }}
                              >
                                移动到…
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>

                {confirmMutation.isError ? (
                  <p className="text-destructive text-sm">
                    确认失败：{confirmMutation.error.message}
                  </p>
                ) : null}
                {rejectMutation.isError ? (
                  <p className="text-destructive text-sm">
                    拒绝失败：{rejectMutation.error.message}
                  </p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Merge dialog */}
      {mergeOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setMergeOpen(false)}
          />
          <div className="border-border bg-background relative w-full max-w-md rounded-xl border p-6 shadow-xl">
            <h3 className="text-foreground mb-1 text-lg font-semibold">
              合并 {checked.size} 个分组
            </h3>
            <p className="text-muted-foreground mb-4 text-xs">
              选中分组的全部明细将归并到一个新组，原分组删除。代表性名称会成为新组名。
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  代表性名称
                </label>
                <Input
                  value={mergeName}
                  onChange={(e) => setMergeName(e.target.value)}
                  placeholder="新组名"
                />
              </div>
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  类别
                </label>
                <Input
                  value={mergeCategory}
                  onChange={(e) => setMergeCategory(e.target.value)}
                  placeholder="类别"
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMergeOpen(false)}
              >
                取消
              </Button>
              <Button
                size="sm"
                onClick={doMerge}
                disabled={!mergeName.trim() || mergeMutation.isPending}
              >
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
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setMoveItem(null)}
          />
          <div className="border-border bg-background relative w-full max-w-md rounded-xl border p-6 shadow-xl">
            <h3 className="text-foreground mb-1 text-lg font-semibold">
              移动明细到其他分组
            </h3>
            <p className="text-muted-foreground mb-4 truncate text-xs">
              货物：{moveItem.name}
            </p>
            <label className="text-foreground mb-1 block text-sm font-medium">
              目标分组
            </label>
            <Select value={moveTarget ?? ""} onValueChange={setMoveTarget}>
              <SelectTrigger>
                <SelectValue placeholder="选择目标分组" />
              </SelectTrigger>
              <SelectContent>
                {clusters
                  .filter((c: CpaCluster) => c.id !== selectedId)
                  .map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.representative_name}
                      {c.category ? `（${c.category} · ${c.item_count}项）` : `（${c.item_count}项）`}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMoveItem(null)}
              >
                取消
              </Button>
              <Button
                size="sm"
                onClick={doMove}
                disabled={!moveTarget || moveMutation.isPending}
              >
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
