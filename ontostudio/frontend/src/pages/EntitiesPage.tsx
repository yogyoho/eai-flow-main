/**
 * 03 实体库（EAI-CUSTOM, 2026-09-27 原型重构）：静态示例 → 真数据。
 *
 * 数据面（后端早已存在，本页补接线即成真——见 2026-09-26 页面盘点）：
 * /ontology/object-types（类型清单）+ /objects/{type}（引擎属性投影，q 走
 * searchable ILIKE，cursor 分页）+ DetailPanel（复用图谱浏览详情组件，
 * nodeId = "<api>:<pk>" Explorer 方言）。
 * 设计稿 docs/designs/ontostudio-frontend-redesign-20260926.html#entities。
 */
import { Database, Loader2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  fetchObjectTypes,
  fetchObjects,
} from "@/api/ontology-graph-api";
import { DetailPanel } from "@/components/DetailPanel";
import { PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value).slice(0, 60);
  const text = String(value);
  return text.length > 60 ? `${text.slice(0, 60)}…` : text;
}

export function EntitiesPage() {
  const schemaQuery = useQuery({
    queryKey: ["ontology", "object-types"],
    queryFn: fetchObjectTypes,
  });
  const objectTypes = schemaQuery.data?.object_types ?? [];
  const [apiName, setApiName] = useState<string | null>(null);
  const activeType = apiName ?? objectTypes[0]?.name ?? null;
  const activeMeta = objectTypes.find((t) => t.name === activeType) ?? null;

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([]);
  const cursor = cursorStack.length > 0 ? cursorStack[cursorStack.length - 1] : null;
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const rowsQuery = useQuery({
    queryKey: ["ontology", "objects", activeType, search, cursor],
    queryFn: ({ signal }) =>
      fetchObjects(activeType as string, {
        q: search || undefined,
        limit: PAGE_SIZE,
        cursor,
        signal,
      }),
    enabled: activeType !== null,
    placeholderData: keepPreviousData,
  });
  const rows = rowsQuery.data?.data ?? [];
  const columns = useMemo(
    () => (activeMeta?.properties ?? []).slice(0, 6),
    [activeMeta],
  );

  const switchType = (name: string) => {
    setApiName(name);
    setSearchInput("");
    setSearch("");
    setCursorStack([]);
    setSelectedId(null);
  };

  const pkField = activeMeta?.pk ?? "id";

  return (
    <div className="p-6">
      <PageHeader
        clause="03"
        icon={Database}
        title="实体库"
        description="全部对象类型实例检索（真数据）：类型切换 / 全文搜索 / 游标分页；行点击查看属性与关联链接。"
        actions={
          rowsQuery.isFetching ? (
            <Loader2 className="text-primary h-4 w-4 animate-spin" />
          ) : null
        }
      />

      {/* 类型切换 chips */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {schemaQuery.isLoading ? (
          <span className="text-muted-foreground text-xs">加载类型清单…</span>
        ) : (
          objectTypes.map((t) => (
            <button
              key={t.name}
              type="button"
              onClick={() => switchType(t.name)}
              title={t.description || t.name}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                activeType === t.name
                  ? "border-primary/25 bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {t.display_name || t.name}
            </button>
          ))
        )}
      </div>

      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel
          title={activeMeta?.display_name || activeType || "实体"}
          subtitle={activeType ? `类型 ${activeType} · 共 ${rows.length} 行本页` : undefined}
          actions={
            <form
              className="flex items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(searchInput.trim());
                setCursorStack([]);
                setSelectedId(null);
              }}
            >
              <div className="relative">
                <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2" />
                <input
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="检索实体名…"
                  className="border-border bg-muted text-foreground placeholder:text-muted-foreground focus:border-primary h-8 w-52 rounded-lg border pr-2 pl-7 text-xs outline-none"
                />
              </div>
              <button
                type="submit"
                className="border-border bg-card hover:bg-muted rounded-lg border px-2.5 py-1.5 text-xs font-medium"
              >
                搜索
              </button>
            </form>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-border bg-muted/60 border-b">
                  <th className="text-muted-foreground px-4 py-2 text-left text-[11.5px] font-medium">
                    {pkField}
                  </th>
                  {columns.map((c) => (
                    <th
                      key={c}
                      className="text-muted-foreground px-4 py-2 text-left text-[11.5px] font-medium"
                    >
                      {c}
                    </th>
                  ))}
                  <th className="w-16 px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {rowsQuery.isLoading ? (
                  <tr>
                    <td
                      colSpan={columns.length + 2}
                      className="text-muted-foreground px-4 py-10 text-center text-xs"
                    >
                      <Loader2 className="mx-auto mb-1 h-4 w-4 animate-spin" />
                      加载中…
                    </td>
                  </tr>
                ) : rowsQuery.isError ? (
                  <tr>
                    <td
                      colSpan={columns.length + 2}
                      className="text-destructive px-4 py-10 text-center text-xs"
                    >
                      加载失败：{(rowsQuery.error as Error).message}
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length + 2}
                      className="text-muted-foreground px-4 py-10 text-center text-xs"
                    >
                      {search ? `无「${search}」匹配结果` : "该类型暂无实例"}
                    </td>
                  </tr>
                ) : (
                  rows.map((row, i) => {
                    const pk = renderCell(row[pkField]);
                    const nodeId = `${activeType}:${row[pkField]}`;
                    return (
                      <tr
                        key={`${pk}-${i}`}
                        onClick={() => setSelectedId(nodeId)}
                        className={cn(
                          "border-border cursor-pointer border-b transition-colors last:border-b-0 hover:bg-muted",
                          selectedId === nodeId && "bg-primary/5",
                        )}
                      >
                        <td className="px-4 py-2.5 font-mono text-[11.5px]">{pk}</td>
                        {columns.map((c) => (
                          <td key={c} className="max-w-[16rem] truncate px-4 py-2.5">
                            {renderCell(row[c])}
                          </td>
                        ))}
                        <td className="text-primary px-4 py-2.5 text-right text-[11.5px]">
                          详情
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="border-border text-muted-foreground flex items-center justify-between border-t px-4 py-2.5 text-[11.5px]">
            <span>每页 {PAGE_SIZE} 行 · cursor 分页</span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={cursorStack.length === 0}
                onClick={() => setCursorStack((s) => s.slice(0, -1))}
                className="border-border bg-card rounded-lg border px-2.5 py-1 disabled:opacity-40"
              >
                上一页
              </button>
              <button
                type="button"
                disabled={!rowsQuery.data?.next_cursor}
                onClick={() =>
                  setCursorStack((s) => [...s, rowsQuery.data?.next_cursor ?? null])
                }
                className="border-border bg-card rounded-lg border px-2.5 py-1 disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          </div>
        </Panel>

        <Panel title="详情" className="xl:sticky xl:top-0">
          {selectedId ? (
            <DetailPanel nodeId={selectedId} />
          ) : (
            <div className="text-muted-foreground px-4 py-10 text-center text-xs leading-loose">
              点击左侧行查看
              <br />
              属性与关联链接
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
