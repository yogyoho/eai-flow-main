/**
 * 03 实体库（EAI-CUSTOM, 2026-09-27 原型还原版）——完全对照
 * docs/designs/ontostudio-frontend-redesign-20260926.html#entities 还原：
 *
 * - 全宽「实体检索」面板：hd 右侧 = 域/类型/状态 三个过滤钮 + API 接线标签；
 *   行点击 → 右侧抽屉（原型 openDrawer 形态，含遮罩）展示属性与关联链接。
 * - 列序 = 原型：实体 / 类型 / 规范名（norm）/ 置信度 / 状态 / 提及 / 更新 / 行操作
 *   （pending→去审核、merged→查看合并、其余→详情）；无裸 pk 列。
 * - 页脚 = 原型：左「共 N 行 · 每页 50 · 分页控件」+ 真实上一页/下一页；
 *   右「导出当前筛选」「批量送审」（均规划中，见按钮 tooltip）。
 * 数据面：/ontology/object-types + /objects/{type}（q + filters + cursor）
 * + /ontology/aggregate（域计数 / 总行数 / 提及计数 Top200）。
 */
import {
  ChevronLeft,
  ChevronRight,
  Database,
  Loader2,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  fetchAggregate,
  fetchObjectTypes,
  fetchObjects,
} from "@/api/ontology-graph-api";
import { DetailPanel } from "@/components/DetailPanel";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { domainAlias } from "@/lib/terms";
import { cn } from "@/lib/utils";

const PAGE_SIZES = [10, 25, 50, 100] as const;

/** graph_entity 状态枚举（registry doc_graph.yaml 声明）。 */
const STATUS_ENUM = ["active", "pending_review", "merged", "rejected"] as const;
type EntityStatus = (typeof STATUS_ENUM)[number];

const STATUS_META: Record<
  EntityStatus,
  { label: string; tone: "primary" | "warning" | "gray" | "danger" }
> = {
  active: { label: "已确认", tone: "primary" },
  pending_review: { label: "待审", tone: "warning" },
  merged: { label: "已合并", tone: "gray" },
  rejected: { label: "已驳回", tone: "danger" },
};

/** 原型列序（graph_entity）；提及 = graph_mention 按 entity_id 聚合（Top 200，窗口外 "—"）。
 *  api 名一律用 registry api_name（camelCase 透出契约：/objects 投影按 api_name 命名，
 *  docstring「字段名用 api_name(camelCase)」）——此前误写物理列 snake_case
 *  （canonical_name/norm_name）致「实体/规范名」两列全取空渲染为 "—"
 *  （EAI-CUSTOM 2026-09-29 抽查修复）。 */
const GRAPH_ENTITY_COLUMNS = [
  { api: "canonicalName", label: "实体" },
  { api: "etype", label: "类型" },
  { api: "normName", label: "规范名" },
  { api: "confidence", label: "置信度" },
  { api: "status", label: "状态" },
  { api: "__mentions", label: "提及" },
  { api: "updatedAt", label: "更新" },
];

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value).slice(0, 40);
  const text = String(value);
  return text.length > 48 ? `${text.slice(0, 48)}…` : text;
}

function fmtTime(value: unknown): string {
  if (!value) return "—";
  // ISO → MM-DD HH:mm（原型列形态）
  return String(value).slice(5, 16).replace("T", " ");
}

/** 过滤下拉（shadcn Select，用户指定组件）：radix Item 禁空串 value，「全部」走哨兵映射；
 *  allowAll=false（类型选择）不渲染「全部」项——各类型属性不同，混合视图无意义。 */
function FilterSelect({
  label,
  value,
  onChange,
  options,
  active,
  disabled,
  allowAll = true,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
  active: boolean;
  disabled?: boolean;
  allowAll?: boolean;
}) {
  const ALL = "__all__";
  return (
    <Select
      value={value || ALL}
      onValueChange={(v) => onChange(v === ALL ? "" : v)}
      disabled={disabled}
    >
      <SelectTrigger
        size="sm"
        aria-label={label}
        className={cn(
          "h-7 w-auto gap-1 rounded-md px-2.5 text-sm font-medium shadow-none",
          active
            ? "border-primary/40 text-primary"
            : "text-muted-foreground",
        )}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent position="popper" className="max-h-72">
        {allowAll ? <SelectItem value={ALL}>{label}：全部</SelectItem> : null}
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function EntitiesPage({ initialEntity }: { initialEntity?: string }) {
  const schemaQuery = useQuery({
    queryKey: ["ontology", "object-types"],
    queryFn: fetchObjectTypes,
  });
  const objectTypes = schemaQuery.data?.object_types ?? [];
  const [apiName, setApiName] = useState<string | null>(null);
  const activeType = apiName ?? objectTypes[0]?.name ?? null;
  const activeMeta = objectTypes.find((t) => t.name === activeType) ?? null;
  const isGraphEntity = activeType === "graph_entity";

  // 域选项（带行数）+ 总行数：aggregate（与总览页共享缓存）
  const domainAggQuery = useQuery({
    queryKey: ["ontology", "aggregate", "graph_entity", "domain"],
    queryFn: ({ signal }) => fetchAggregate("graph_entity", "domain", { signal }),
    enabled: isGraphEntity,
    staleTime: 60_000,
  });
  const domainOptions = domainAggQuery.data ?? [];

  // 提及计数：graph_mention 按 entity_id 聚合（Top 200 by 计数，窗口外 "—"）
  const mentionAggQuery = useQuery({
    queryKey: ["ontology", "aggregate", "graph_mention", "entity_id"],
    queryFn: ({ signal }) =>
      fetchAggregate("graph_mention", "entity_id", { limit: 200, signal }),
    enabled: isGraphEntity,
    staleTime: 60_000,
  });
  const mentionCountById = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of mentionAggQuery.data ?? []) {
      if (row.group) map.set(row.group, row.value);
    }
    return map;
  }, [mentionAggQuery.data]);

  // EAI-CUSTOM(2026-10-01 B1.6): 默认域改 eia——doc_graph 域 0 行, 缺省落空态像「无数据」假象
  const [domainFilter, setDomainFilter] = useState("eia");
  const [statusFilter, setStatusFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  // 页码分页（0 基，对齐合同价格分项校验）：skip = page * pageSize，total 由服务端返回
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(10);
  const [selectedId, setSelectedId] = useState<string | null>(
    // 深链直开（校验违规下钻 #entities:<uuid>）：抽屉打开该实体详情
    initialEntity ? `graph_entity:${initialEntity}` : null,
  );

  const filters = useMemo(() => {
    const list: Array<{ column: string; op: string; value: unknown }> = [];
    if (isGraphEntity && domainFilter)
      list.push({ column: "domain", op: "eq", value: domainFilter });
    if (isGraphEntity && statusFilter)
      list.push({ column: "status", op: "eq", value: statusFilter });
    return list;
  }, [isGraphEntity, domainFilter, statusFilter]);

  const rowsQuery = useQuery({
    queryKey: ["ontology", "objects", activeType, search, page, pageSize, filters],
    queryFn: ({ signal }) =>
      fetchObjects(activeType as string, {
        q: search || undefined,
        limit: pageSize,
        offset: page * pageSize,
        order: isGraphEntity ? "createdAt" : undefined,
        desc: isGraphEntity,
        filters,
        signal,
      }),
    enabled: activeType !== null,
    placeholderData: keepPreviousData,
  });
  const rows = rowsQuery.data?.data ?? [];
  const total = rowsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const columns = useMemo(() => {
    if (isGraphEntity) return GRAPH_ENTITY_COLUMNS;
    return (activeMeta?.properties ?? [])
      .slice(0, 6)
      .map((p) => ({ api: p, label: p }));
  }, [isGraphEntity, activeMeta]);

  const switchType = (name: string) => {
    setApiName(name);
    setSearchInput("");
    setSearch("");
    setDomainFilter("");
    setStatusFilter("");
    setPage(0);
    setSelectedId(null);
  };

  const resetPage = () => {
    setPage(0);
    setSelectedId(null);
  };

  /** 页码窗口（合同价格分项校验同款）：最多 5 个，跟随当前页滑动并钳在两端。 */
  const pageWindow = useMemo(() => {
    const start = Math.max(0, Math.min(page - 2, totalPages - 5));
    return Array.from({ length: Math.min(5, totalPages) }, (_, i) => start + i);
  }, [page, totalPages]);

  const pkField = activeMeta?.pk ?? "id";
  const hasFilter = Boolean(domainFilter || statusFilter || search);

  /** 行操作（原型列尾）：pending→去审核（实心）/ merged→查看合并 / 其余→详情（幽灵）。 */
  function RowAction({ status, nodeId }: { status: EntityStatus | ""; nodeId: string }) {
    if (status === "pending_review") {
      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            window.location.hash = "resolve";
          }}
          className="bg-primary text-primary-foreground hover:opacity-90 rounded-md px-2 py-1 text-xs font-medium"
        >
          去审核
        </button>
      );
    }
    if (status === "merged") {
      return (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedId(nodeId); // 打开抽屉查看合并上下文
          }}
          className="border-border bg-card text-foreground hover:bg-muted rounded-md border px-2 py-1 text-xs"
        >
          查看合并
        </button>
      );
    }
    return (
      <span className="text-primary text-xs">详情</span>
    );
  }

  return (
    /* 纵向滚动层（样式=全站 6px 细条）：长表/详情超出视口时页面滚动 */
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1100px] p-6">
      <PageHeader
        clause="03"
        icon={Database}
        title="实体库"
        description="跨域实体检索与状态过滤，支持行级详情抽屉。"
        actions={
          rowsQuery.isFetching ? (
            <Loader2 className="text-primary h-4 w-4 animate-spin" />
          ) : null
        }
      />

      <Panel
        title="实体检索"
        subtitle={hasFilter ? "已过滤" : undefined}
        actions={
          <div className="flex flex-wrap items-center gap-1.5">
            {isGraphEntity ? (
              <FilterSelect
                label="域"
                value={domainFilter}
                onChange={(v) => {
                  setDomainFilter(v);
                  resetPage();
                }}
                active={Boolean(domainFilter)}
                options={domainOptions.map((r) => ({
                  value: r.group ?? "",
                  // EAI-CUSTOM(2026-10-01 B1.5): 域名附中文别名（terms.ts 单源）
                  label: `${r.group || "—"}${r.group ? `（${domainAlias(r.group) ?? r.group}）` : ""}`,
                }))}
              />
            ) : null}
            <FilterSelect
              label="类型"
              value={activeType ?? ""}
              onChange={(v) => switchType(v)}
              active={false}
              allowAll={false}
              disabled={schemaQuery.isLoading}
              options={objectTypes.map((t) => ({
                value: t.name,
                label: t.display_name || t.name,
              }))}
            />
            {isGraphEntity ? (
              <FilterSelect
                label="状态"
                value={statusFilter}
                onChange={(v) => {
                  setStatusFilter(v);
                  resetPage();
                }}
                active={Boolean(statusFilter)}
                options={STATUS_ENUM.map((s) => ({
                  value: s,
                  label: STATUS_META[s].label,
                }))}
              />
            ) : null}
            <span
              className="text-muted-foreground/80 hidden cursor-help font-mono text-xs lg:inline"
              title="数据源：GET /ontology/objects/{type}（q + filters + cursor 分页）"
            >
              实体数据服务
            </span>
            <div className="relative">
              <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setSearch(searchInput.trim());
                    resetPage();
                  }
                }}
                placeholder="检索实体名…"
                className="border-border bg-muted text-foreground placeholder:text-muted-foreground focus:border-primary h-7 w-40 rounded-md border pr-2 pl-7 text-sm outline-none"
              />
            </div>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-border bg-muted/60 border-b">
                {columns.map((c) => (
                  <th
                    key={c.api}
                    className={cn(
                      "text-muted-foreground px-4 py-2 text-left text-xs font-medium",
                      c.api === "confidence" || c.api === "__mentions"
                        ? "text-right"
                        : "text-left",
                    )}
                  >
                    {c.label}
                  </th>
                ))}
                <th className="w-28 px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {rowsQuery.isLoading ? (
                <tr>
                  <td
                    colSpan={columns.length + 1}
                    className="text-muted-foreground px-4 py-10 text-center text-sm"
                  >
                    <Loader2 className="mx-auto mb-1 h-4 w-4 animate-spin" />
                    加载中…
                  </td>
                </tr>
              ) : rowsQuery.isError ? (
                <tr>
                  <td
                    colSpan={columns.length + 1}
                    className="text-destructive px-4 py-10 text-center text-sm"
                  >
                    加载失败：{(rowsQuery.error as Error).message}
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length + 1}
                    className="text-muted-foreground px-4 py-10 text-center text-sm"
                  >
                    {hasFilter ? "无匹配结果——试试放宽过滤器" : "该类型暂无实例"}
                  </td>
                </tr>
              ) : (
                rows.map((row, i) => {
                  const nodeId = `${activeType}:${row[pkField]}`;
                  const status = isGraphEntity
                    ? (String(row.status ?? "") as EntityStatus)
                    : "";
                  const meta = STATUS_META[status];
                  return (
                    <tr
                      key={`${String(row[pkField])}-${i}`}
                      onClick={() => setSelectedId(nodeId)}
                      className={cn(
                        "border-border cursor-pointer border-b transition-colors last:border-b-0 hover:bg-muted",
                        selectedId === nodeId && "bg-primary/5",
                      )}
                    >
                      {columns.map((c) => {
                        const value = row[c.api];
                        if (c.api === "canonicalName") {
                          return (
                            <td
                              key={c.api}
                              className="max-w-[14rem] truncate px-4 py-2.5 font-medium"
                            >
                              {renderCell(value)}
                            </td>
                          );
                        }
                        if (c.api === "etype") {
                          return (
                            <td key={c.api} className="px-4 py-2.5">
                              <span className="bg-secondary text-secondary-foreground rounded-md px-1.5 py-0.5 font-mono text-xs">
                                {renderCell(value)}
                              </span>
                            </td>
                          );
                        }
                        if (c.api === "normName") {
                          return (
                            <td
                              key={c.api}
                              className="max-w-[12rem] truncate px-4 py-2.5 font-medium"
                            >
                              {renderCell(value)}
                            </td>
                          );
                        }
                        if (c.api === "confidence") {
                          return (
                            <td
                              key={c.api}
                              className="px-4 py-2.5 text-right font-mono text-xs tabular-nums"
                            >
                              {value === null || value === undefined
                                ? "—"
                                : Number(value).toFixed(2)}
                            </td>
                          );
                        }
                        if (c.api === "status") {
                          return (
                            <td key={c.api} className="px-4 py-2.5">
                              {meta ? <Chip tone={meta.tone}>{meta.label}</Chip> : "—"}
                            </td>
                          );
                        }
                        if (c.api === "__mentions") {
                          const count = mentionCountById.get(String(row.id ?? ""));
                          return (
                            <td
                              key={c.api}
                              className="px-4 py-2.5 text-right tabular-nums"
                            >
                              {count ?? "—"}
                            </td>
                          );
                        }
                        if (c.api === "updatedAt") {
                          return (
                            <td
                              key={c.api}
                              className="text-muted-foreground px-4 py-2.5 font-mono text-xs"
                            >
                              {fmtTime(value)}
                            </td>
                          );
                        }
                        return (
                          <td
                            key={c.api}
                            className="max-w-[12rem] truncate px-4 py-2.5"
                          >
                            {renderCell(value)}
                          </td>
                        );
                      })}
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end">
                          <RowAction status={status} nodeId={String(row[pkField] ?? "")} />
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* 页脚（合同价格分项校验同款分页条）：左计数 · 右 首页/◀/页码窗/▶/末页 + 规划动作 */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-muted-foreground text-sm">
          共 <b className="text-foreground tabular-nums">{total.toLocaleString()}</b> 条 · 第{" "}
          {page + 1}/{totalPages} 页
          {hasFilter ? " · 已过滤" : ""}
        </span>
        <div className="flex flex-wrap items-center gap-1">
          <Select
            value={String(pageSize)}
            onValueChange={(v) => {
              setPageSize(Number(v));
              setPage(0);
              setSelectedId(null);
            }}
          >
            <SelectTrigger
              size="sm"
              aria-label="每页条数"
              className="text-muted-foreground h-7 w-auto gap-1 rounded-md px-2 text-sm font-medium shadow-none"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper">
              {PAGE_SIZES.map((size) => (
                <SelectItem key={size} value={String(size)}>
                  {size} 条/页
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <button
            type="button"
            disabled={page <= 0}
            onClick={() => {
              setPage(0);
              setSelectedId(null);
            }}
            className="border-border bg-card hover:bg-muted rounded-md border px-2.5 py-1 text-sm font-medium disabled:opacity-40"
          >
            首页
          </button>
          <button
            type="button"
            aria-label="上一页"
            disabled={page <= 0}
            onClick={() => {
              setPage(page - 1);
              setSelectedId(null);
            }}
            className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-sm disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          {pageWindow.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => {
                setPage(p);
                setSelectedId(null);
              }}
              className={cn(
                "rounded-md border px-2.5 py-1 text-sm font-medium tabular-nums",
                p === page
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-foreground hover:bg-muted",
              )}
            >
              {p + 1}
            </button>
          ))}
          <button
            type="button"
            aria-label="下一页"
            disabled={page >= totalPages - 1}
            onClick={() => {
              setPage(page + 1);
              setSelectedId(null);
            }}
            className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-sm disabled:opacity-40"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            disabled={page >= totalPages - 1}
            onClick={() => {
              setPage(totalPages - 1);
              setSelectedId(null);
            }}
            className="border-border bg-card hover:bg-muted rounded-md border px-2.5 py-1 text-sm font-medium disabled:opacity-40"
          >
            末页
          </button>
          <span className="mx-1 text-border">|</span>
          <button
            type="button"
            disabled
            title="规划中"
            className="border-border bg-card rounded-md border px-2.5 py-1 text-sm opacity-60"
          >
            导出当前筛选{" "}
            <span className="text-warning font-mono text-xs">规划</span>
          </button>
          <button
            type="button"
            disabled
            title="规划中（TODOS·批量摊销）"
            className="bg-primary text-primary-foreground rounded-md px-2.5 py-1 text-sm font-medium opacity-60"
          >
            批量送审
          </button>
        </div>
      </div>
      </div>

      {/* 行详情抽屉（原型 openDrawer 形态：遮罩 + 右滑入） */}
      {selectedId ? (
        <>
          <div
            className="bg-foreground/30 fixed inset-0 z-40"
            onClick={() => setSelectedId(null)}
            data-testid="entities-drawer-scrim"
          />
          <div
            className="bg-background border-border fixed inset-y-0 right-0 z-50 flex w-[420px] max-w-[92vw] flex-col border-l shadow-xl"
            data-testid="entities-drawer"
          >
            <div className="border-border flex items-center justify-between border-b px-4 py-3">
              <b className="text-sm font-semibold">实体详情</b>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="border-border text-muted-foreground hover:text-foreground rounded-md border px-2 py-0.5 text-sm"
              >
                关闭 ✕
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <DetailPanel nodeId={selectedId} />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
