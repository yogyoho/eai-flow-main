"use client";

/**
 * 详情面板 (EAI-CUSTOM, plan 2026-09-12 ontology-ui Task 3 Step 3.4).
 *
 * 选中节点（id = "<api_name>:<pk>"）→ api_name 徽章 + properties 全列（dl 表）+
 * 关联链接：从 fetchObjectTypes 找以该 api_name 为 source/target 的 enabled link_types，
 * 逐个按需拉 /objects/{api}/{pk}/links/{lt}；对侧 label 优先查已加载图节点
 * （explorer/graphStore 单例），查不到回退 pk。证据链（dg_mention）本 v1 不做。
 */
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import {
  fetchObjectLinks,
  fetchObjectTypes,
  type LinkTypeSummary,
  type ObjectTypeSummary,
} from "@/extensions/ontology/api/ontology-graph-api";
import { graph, type NodeAttributes } from "@/extensions/ontology/explorer/graphStore";

/** id = "<api_name>:<pk>" → [api_name, pk]（pk 内可能再含 ":"，按首个冒号切）。 */
function splitNodeId(nodeId: string): [string, string] | null {
  const sep = nodeId.indexOf(":");
  if (sep <= 0 || sep >= nodeId.length - 1) {
    return null;
  }
  return [nodeId.slice(0, sep), nodeId.slice(sep + 1)];
}

function formatPropertyValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  try {
    return JSON.stringify(value) ?? "—";
  } catch {
    return "—";
  }
}

/** pk 值安全字符串化（行数据为 unknown 投影，非原始值回退空串）。 */
function pkToString(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return "";
}

function findObjectType(schema: { object_types: ObjectTypeSummary[] } | undefined, name: string) {
  return schema?.object_types.find((obj) => obj.name === name);
}

interface LinkTypeRowsProps {
  apiName: string;
  pk: string;
  linkType: LinkTypeSummary;
  opposite: ObjectTypeSummary;
}

/** 单个链接类型的对侧行列表（ TanStack Query 按需拉取，仅节点被选中时 enabled）。 */
function LinkTypeRows({ apiName, pk, linkType, opposite }: LinkTypeRowsProps) {
  const outgoing = linkType.source === apiName;
  const linksQuery = useQuery({
    queryKey: ["ontology", "links", apiName, pk, linkType.name],
    queryFn: ({ signal }) => fetchObjectLinks(apiName, pk, linkType.name, { signal }),
    enabled: Boolean(apiName && pk),
    retry: 0,
  });

  const rows = linksQuery.data?.data ?? [];

  return (
    <div className="mb-2">
      <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-[10.5px]">
        <span className="text-primary font-mono">{linkType.name}</span>
        <span>{outgoing ? "→ 出" : "← 入"}</span>
        <span className="ml-auto tabular-nums">{linksQuery.isLoading ? "…" : rows.length}</span>
      </div>
      {linksQuery.isError ? (
        <div className="text-muted-foreground border-border rounded-md border border-dashed px-2 py-1.5 text-[11px]">
          {String(linksQuery.error)}
        </div>
      ) : null}
      {!linksQuery.isError && rows.map((row, index) => {
        const pkText = pkToString(row[opposite.pk]);
        const oppositeId = `${opposite.name}:${pkText}`;
        const label = (
          graph.hasNode(oppositeId)
            ? String(graph.getNodeAttribute(oppositeId, "label"))
            : ""
        ) || pkText || "?";
        return (
          <div
            key={`${oppositeId}-${index}`}
            className="border-border text-foreground mt-1 flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-[11.5px]"
          >
            <span className="truncate" title={label}>
              {label}
            </span>
            <span className="text-muted-foreground ml-auto shrink-0 text-[10px]">
              {outgoing ? "→" : "←"} {outgoing ? linkType.target : linkType.source}
            </span>
          </div>
        );
      })}
      {!linksQuery.isError && !linksQuery.isLoading && rows.length === 0 ? (
        <div className="text-muted-foreground px-2 py-1 text-[11px]">无关联实例</div>
      ) : null}
    </div>
  );
}

export function DetailPanel({ nodeId }: { nodeId: string | null }) {
  const schemaQuery = useQuery({
    queryKey: ["ontology", "object-types"],
    queryFn: fetchObjectTypes,
  });

  if (!nodeId) {
    return (
      <div className="text-muted-foreground px-3 py-10 text-center text-xs leading-loose">
        点击图中节点查看
        <br />
        属性与关联链接
      </div>
    );
  }

  const parsed = splitNodeId(nodeId);
  if (!parsed) {
    return (
      <div className="text-muted-foreground px-3 py-10 text-center text-xs">
        无法识别的节点标识：{nodeId}
      </div>
    );
  }
  const [apiName, pk] = parsed;

  const attrs = graph.hasNode(nodeId)
    ? (graph.getNodeAttributes(nodeId) as NodeAttributes)
    : null;
  const properties = (attrs?.properties ?? {}) as Record<string, unknown>;
  const linkTypes = (schemaQuery.data?.link_types ?? []).filter(
    (lt) => lt.enabled && (lt.source === apiName || lt.target === apiName),
  );

  return (
    <div className="px-3 py-3">
      <div className="mb-1 break-all text-sm font-semibold leading-snug text-foreground">
        {attrs?.label ?? pk}
      </div>
      <div className="mb-3 flex flex-wrap gap-1">
        <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[10.5px]">
          {apiName}
        </span>
        {findObjectType(schemaQuery.data, apiName) ? (
          <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[10.5px]">
            {findObjectType(schemaQuery.data, apiName)?.display_name}
          </span>
        ) : null}
      </div>

      <h3 className="text-muted-foreground mb-1.5 text-[10.5px] font-medium tracking-widest">属性</h3>
      {Object.keys(properties).length > 0 ? (
        <dl className="grid grid-cols-[96px_1fr] gap-x-2.5 gap-y-1 text-xs">
          {Object.entries(properties).map(([key, value]) => (
            <div key={key} className="col-span-2 grid grid-cols-subgrid">
              <dt className="text-muted-foreground break-words">{key}</dt>
              <dd className="text-foreground break-all tabular-nums">{formatPropertyValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="text-muted-foreground text-[11px]">
          {schemaQuery.isLoading ? "加载属性清单…" : "无可显示属性"}
        </div>
      )}

      <h3 className="text-muted-foreground mt-4 mb-1.5 text-[10.5px] font-medium tracking-widest">
        关联链接
      </h3>
      {schemaQuery.isLoading ? (
        <div className="text-muted-foreground flex items-center gap-1.5 text-[11px]">
          <Loader2 className="h-3 w-3 animate-spin" />
          加载链接类型…
        </div>
      ) : linkTypes.length === 0 ? (
        <div className="text-muted-foreground text-[11px]">该对象类型未声明 enabled 链接</div>
      ) : (
        linkTypes.map((lt) => {
          const oppositeName = lt.source === apiName ? lt.target : lt.source;
          const opposite = findObjectType(schemaQuery.data, oppositeName);
          if (!opposite) {
            return null;
          }
          return (
            <LinkTypeRows
              key={lt.name}
              apiName={apiName}
              pk={pk}
              linkType={lt}
              opposite={opposite}
            />
          );
        })
      )}
    </div>
  );
}
