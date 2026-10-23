"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Boxes,
  Check,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  GitMerge,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { contractPriceApi } from "@/extensions/contract-price/api";
import {
  EmptyRow,
  PageHeader,
} from "@/extensions/contract-price/components/PageHeader";
import { TracebackDrawer } from "@/extensions/contract-price/components/TracebackDrawer";
import {
  Pill,
  type PillTone,
} from "@/extensions/contract-price/components/ui/bits";
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
  useMoveItemToNew,
  useDeleteCluster,
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

// EAI-CUSTOM: 状态徽章统一走 Pill（cpa UI 重构规范 §2-4），tone→语义色映射
const statusTone: Record<string, PillTone> = {
  pending: "warn",
  confirmed: "success",
  rejected: "gray",
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
  // 移动对话框增强(2026-10-22): 全量分组搜索 + 新建分组模式
  const [moveSearch, setMoveSearch] = useState("");
  const [moveMode, setMoveMode] = useState<"existing" | "new">("existing");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupCategory, setNewGroupCategory] = useState("");
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
  const moveToNewMutation = useMoveItemToNew();
  const deleteClusterMutation = useDeleteCluster();
  // 分组卡片菜单(2026-10-23): 重命名 / 删除(方案A)
  const [renameTarget, setRenameTarget] = useState<CpaCluster | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameCategory, setRenameCategory] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CpaCluster | null>(null);
  const batchConfirmMutation = useBatchConfirmClusters();

  const clusters = clustersQuery.data?.items ?? [];
  const total = clustersQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const detail = clusterQuery.data;

  // EAI-CUSTOM F3a 离群语义分层: 簇明细内按文档成片判定 + 行 id → 降级说明 tooltip。
  const detailItems: CpaItem[] = detail?.items ?? [];
  const statRows = useMemo(() => detailItems.map(itemToStatRow), [detailItems]);
  const baselineDocs = useMemo(() => baselineShiftDocIds(statRows), [statRows]);
  const baselineTooltips = useMemo(
    () => buildBaselineTooltips(statRows),
    [statRows],
  );

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
    if (!moveItem) return;
    if (moveMode === "new") {
      if (!newGroupName.trim()) return;
      await moveToNewMutation.mutateAsync({
        item_id: moveItem.itemId,
        name: newGroupName.trim(),
        category: newGroupCategory.trim(),
      });
    } else {
      if (!moveTarget) return;
      await moveMutation.mutateAsync({
        item_id: moveItem.itemId,
        target_cluster_id: moveTarget,
      });
    }
    setMoveItem(null);
    setMoveTarget(null);
    setMoveSearch("");
    setMoveMode("existing");
    setNewGroupName("");
    setNewGroupCategory("");
  };

  return (
    <div className="space-y-4 p-6">
      {/* 页头卡：刷新动作收进 PageHeader 右槽，不随长描述换行 */}
      <PageHeader
        title="分组审核"
        description="审核自动分组：合并同义组、移动误归类项、拒绝错误组、编辑类别。确认后统计才生效。分组为上次「聚类分析」的结果——删除或修改货物后需重新聚类刷新，此处不提供单独删除。"
        icon={<Boxes />}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => clustersQuery.refetch()}
          >
            <RefreshCw className="h-4 w-4" />
            刷新
          </Button>
        }
      />

      {/* 控件行：搜索 + 筛选 + 批量操作 */}
      <div className="flex flex-wrap items-center gap-2">
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
          {/* EAI-CUSTOM: 覆写对齐 docmgr 白底凸起 segmented（bg-secondary 凹槽 + rounded-sm xs 触发器） */}
          <TabsList className="bg-secondary h-auto rounded-md p-0.5">
            <TabsTrigger
              className="h-auto flex-none rounded-sm px-2.5 py-1 text-xs"
              value="pending"
            >
              待审核
            </TabsTrigger>
            <TabsTrigger
              className="h-auto flex-none rounded-sm px-2.5 py-1 text-xs"
              value="confirmed"
            >
              已确认
            </TabsTrigger>
            <TabsTrigger
              className="h-auto flex-none rounded-sm px-2.5 py-1 text-xs"
              value="rejected"
            >
              已拒绝
            </TabsTrigger>
            <TabsTrigger
              className="h-auto flex-none rounded-sm px-2.5 py-1 text-xs"
              value="all"
            >
              全部
            </TabsTrigger>
          </TabsList>
        </Tabs>
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
                  <li key={c.id} className="group flex items-center gap-2">
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
                      <Pill
                        tone={statusTone[c.status] ?? "gray"}
                        className="shrink-0"
                      >
                        {statusLabel[c.status] ?? c.status}
                      </Pill>
                    </button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          aria-label={`分组操作：${c.representative_name}`}
                          className="text-muted-foreground hover:bg-muted hover:text-foreground mr-1 shrink-0 rounded p-1 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => {
                            setRenameTarget(c);
                            setRenameName(c.representative_name);
                            setRenameCategory(c.category ?? "");
                          }}
                        >
                          <Pencil className="mr-2 h-4 w-4" /> 重命名
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => setDeleteTarget(c)}
                        >
                          <Trash2 className="mr-2 h-4 w-4" /> 删除分组
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
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
                    <Pill
                      tone={statusTone[detail.status] ?? "gray"}
                      className="shrink-0"
                    >
                      {statusLabel[detail.status] ?? detail.status}
                    </Pill>
                  )}
                </div>

                {/* Stats —— 指标格样式（§2-2 缩小版：label 上 / 16px semibold 数值下） */}
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
                      className="border-border bg-card rounded-md border px-3 py-2"
                    >
                      <p className="text-muted-foreground text-xs">{label}</p>
                      <p className="text-foreground text-base font-semibold tabular-nums">
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
                                        ? "text-amber-600 dark:text-amber-400"
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
                            <TableCell className="text-muted-foreground font-mono text-xs">
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
                                  <Crosshair className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />
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

      {/* Move-to-target dialog（2026-10-22 增强: 全量分组搜索 + 新建分组） */}
      {moveItem ? (
        <MoveDialog
          moveItem={moveItem}
          selectedId={selectedId}
          moveTarget={moveTarget}
          setMoveTarget={setMoveTarget}
          moveSearch={moveSearch}
          setMoveSearch={setMoveSearch}
          moveMode={moveMode}
          setMoveMode={setMoveMode}
          newGroupName={newGroupName}
          setNewGroupName={setNewGroupName}
          newGroupCategory={newGroupCategory}
          setNewGroupCategory={setNewGroupCategory}
          pending={moveMutation.isPending || moveToNewMutation.isPending}
          onMove={doMove}
          onClose={() => setMoveItem(null)}
        />
      ) : null}

      {/* Rename cluster dialog (2026-10-23) */}
      {renameTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setRenameTarget(null)}
          />
          <div className="border-border bg-background relative w-full max-w-sm rounded-xl border p-6 shadow-xl">
            <h3 className="text-foreground mb-4 text-lg font-semibold">
              重命名分组
            </h3>
            <div className="space-y-3">
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  分组名称
                </label>
                <Input
                  autoFocus
                  value={renameName}
                  onChange={(e) => setRenameName(e.target.value)}
                />
              </div>
              <div>
                <label className="text-foreground mb-1 block text-sm font-medium">
                  类别
                </label>
                <Input
                  value={renameCategory}
                  onChange={(e) => setRenameCategory(e.target.value)}
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setRenameTarget(null)}
              >
                取消
              </Button>
              <Button
                size="sm"
                disabled={!renameName.trim() || updateMutation.isPending}
                onClick={() => {
                  updateMutation.mutate(
                    {
                      id: renameTarget.id,
                      body: {
                        representative_name: renameName.trim(),
                        category: renameCategory.trim(),
                      },
                    },
                    {
                      onSuccess: () => setRenameTarget(null),
                      onError: (e) =>
                        alert(
                          `重命名失败：${e instanceof Error ? e.message : String(e)}`,
                        ),
                    },
                  );
                }}
              >
                保存
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Delete cluster dialog (2026-10-23 方案A) */}
      {deleteTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setDeleteTarget(null)}
          />
          <div className="border-border bg-background relative w-full max-w-sm rounded-xl border p-6 shadow-xl">
            <h3 className="text-foreground mb-2 text-lg font-semibold">
              删除分组
            </h3>
            <p className="text-muted-foreground mb-4 text-sm">
              删除「{deleteTarget.representative_name}」后，其{" "}
              <b>{deleteTarget.item_count}</b> 个货物项将变为
              <b>未分组</b>
              ——货物数据完整保留（分项校验不受影响），下次「聚类分析」会重新归组。
              与代表名不同的成员会自动登记区分规则，防止下次聚类重新错并。
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteTarget(null)}
              >
                取消
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={deleteClusterMutation.isPending}
                onClick={() => {
                  deleteClusterMutation.mutate(deleteTarget.id, {
                    onSuccess: () => {
                      if (selectedId === deleteTarget.id) setSelectedId(null);
                      setChecked((s) => {
                        const n = new Set(s);
                        n.delete(deleteTarget.id);
                        return n;
                      });
                      setDeleteTarget(null);
                    },
                    onError: (e) =>
                      alert(
                        `删除失败：${e instanceof Error ? e.message : String(e)}`,
                      ),
                  });
                }}
              >
                {deleteClusterMutation.isPending ? "删除中…" : "删除分组"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <TracebackDrawer
        docId={trace?.document_id ?? null}
        page={trace?.source_page ?? null}
        bbox={trace?.source_bbox ?? null}
        itemId={trace?.id ?? null}
        onClose={() => setTrace(null)}
      />
    </div>
  );
}

/** 移动对话框(2026-10-22): 全量分组(≤500)+客户端搜索,或新建分组模式。
 * 旧 Select 在 300+ 簇下不可用且只列当前页;列表行点击即选中。 */
function MoveDialog({
  moveItem,
  selectedId,
  moveTarget,
  setMoveTarget,
  moveSearch,
  setMoveSearch,
  moveMode,
  setMoveMode,
  newGroupName,
  setNewGroupName,
  newGroupCategory,
  setNewGroupCategory,
  pending,
  onMove,
  onClose,
}: {
  moveItem: { itemId: string; name: string };
  selectedId: string | null;
  moveTarget: string | null;
  setMoveTarget: (v: string | null) => void;
  moveSearch: string;
  setMoveSearch: (v: string) => void;
  moveMode: "existing" | "new";
  setMoveMode: (v: "existing" | "new") => void;
  newGroupName: string;
  setNewGroupName: (v: string) => void;
  newGroupCategory: string;
  setNewGroupCategory: (v: string) => void;
  pending: boolean;
  onMove: () => void;
  onClose: () => void;
}) {
  // 对话框打开时一次性拉全量分组(≤500;分组数百级,一页足够)
  const allQ = useQuery({
    queryKey: ["cpa", "clusters", "move-dialog-all"],
    queryFn: () => contractPriceApi.listClusters({ limit: 500 }),
    enabled: true,
    staleTime: 30_000,
  });
  const all = useMemo(() => allQ.data?.items ?? [], [allQ.data]);
  const kw = moveSearch.trim().toLowerCase();
  const options = useMemo(
    () =>
      all
        .filter((c: CpaCluster) => c.id !== selectedId)
        .filter((c: CpaCluster) =>
          kw
            ? c.representative_name.toLowerCase().includes(kw) ||
              (c.category ?? "").toLowerCase().includes(kw)
            : true,
        ),
    [all, selectedId, kw],
  );
  const canMove = moveMode === "new" ? !!newGroupName.trim() : !!moveTarget;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="border-border bg-background relative w-full max-w-xl rounded-xl border p-6 shadow-xl">
        <h3 className="text-foreground mb-1 text-lg font-semibold">
          移动明细到{moveMode === "new" ? "新分组" : "其他分组"}
        </h3>
        <p className="text-muted-foreground mb-4 truncate text-xs">
          货物：{moveItem.name}
        </p>
        <div className="mb-3 flex gap-1">
          <button
            type="button"
            className={
              moveMode === "existing"
                ? "bg-primary text-primary-foreground rounded-md px-3 py-1 text-xs font-medium"
                : "text-muted-foreground hover:bg-muted rounded-md px-3 py-1 text-xs"
            }
            onClick={() => setMoveMode("existing")}
          >
            选择已有分组
          </button>
          <button
            type="button"
            className={
              moveMode === "new"
                ? "bg-primary text-primary-foreground rounded-md px-3 py-1 text-xs font-medium"
                : "text-muted-foreground hover:bg-muted rounded-md px-3 py-1 text-xs"
            }
            onClick={() => setMoveMode("new")}
          >
            新建分组
          </button>
        </div>
        {moveMode === "existing" ? (
          <>
            <Input
              autoFocus
              placeholder="搜索分组名 / 类别…"
              value={moveSearch}
              onChange={(e) => setMoveSearch(e.target.value)}
            />
            <div className="border-border mt-2 max-h-56 overflow-y-auto rounded-md border">
              {allQ.isLoading ? (
                <p className="text-muted-foreground p-3 text-xs">加载分组中…</p>
              ) : options.length === 0 ? (
                <p className="text-muted-foreground p-3 text-xs">
                  没有匹配的分组。可以切换到「新建分组」。
                </p>
              ) : (
                options.map((c: CpaCluster) => (
                  <button
                    key={c.id}
                    type="button"
                    className={
                      moveTarget === c.id
                        ? "bg-accent text-accent-foreground flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm"
                        : "hover:bg-muted/60 flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm"
                    }
                    onClick={() => setMoveTarget(c.id)}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {c.representative_name}
                    </span>
                    {c.category ? (
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {c.category}
                      </span>
                    ) : null}
                    <span className="text-muted-foreground shrink-0 text-xs">
                      {c.item_count}项
                    </span>
                  </button>
                ))
              )}
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="text-foreground mb-1 block text-sm font-medium">
                新分组名称
              </label>
              <Input
                autoFocus
                value={newGroupName}
                placeholder="如：桥架内穿线 铜芯导线"
                onChange={(e) => setNewGroupName(e.target.value)}
              />
            </div>
            <div>
              <label className="text-foreground mb-1 block text-sm font-medium">
                类别（可选）
              </label>
              <Input
                value={newGroupCategory}
                placeholder="如：电气工程"
                onChange={(e) => setNewGroupCategory(e.target.value)}
              />
            </div>
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button size="sm" onClick={onMove} disabled={!canMove || pending}>
            {pending ? "移动中…" : moveMode === "new" ? "建组并移入" : "移动"}
          </Button>
        </div>
      </div>
    </div>
  );
}
