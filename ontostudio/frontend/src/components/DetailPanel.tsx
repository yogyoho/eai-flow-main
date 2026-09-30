/* 复制自 frontend/src/extensions/ontology/components/DetailPanel.tsx（S2 Task 1）——仅 import 路径改本地，内容零改动。 */
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
} from "@/api/ontology-graph-api";
import { graph, type NodeAttributes } from "@/explorer/graphStore";
import {
  fetchEiaEtypeLabels,
  getPredicateLabels,
  localizePredicate,
  normalizePatternAttrs,
  patternAttr,
} from "@/explorerDataSource";

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

/**
 * EAI-CUSTOM(2026-10-01 domain_pattern 结构化卡片): B 库规律行（properties.etype=
 * "domain_pattern"）的 attrs 字段不再以原始 JSON 一坨渲染——规律类型/主体→客体/谓词/
 * 支撑样本数/来源报告 chips/变体/pattern_desc/refined_desc 引用块逐项结构化。
 * attrs 缺失或形状不符时返回 null（调用方回退通用属性表，行为不变）。
 * 中文标注真源与画布边标签同源：谓词 = eia.yaml 注释块（getPredicateLabels），
 * etype = registry summary classes（fetchEiaEtypeLabels）；接口失败回退原文。
 */
const PATTERN_REPORT_CHIPS = 8;

function DomainPatternCard({ properties }: { properties: Record<string, unknown> }) {
  const attrs = normalizePatternAttrs(properties.attrs);
  const predicateLabels = useQuery({
    queryKey: ["ontology", "predicate-labels"],
    queryFn: getPredicateLabels,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const etypeLabels = useQuery({
    queryKey: ["ontology", "eia-etype-labels"],
    queryFn: fetchEiaEtypeLabels,
    staleTime: Number.POSITIVE_INFINITY,
  });

  if (!attrs) {
    return null;
  }

  const zhEtype = (value: unknown): string => {
    const text = typeof value === "string" ? value.trim() : "";
    if (!text) {
      return "";
    }
    const zh = etypeLabels.data?.get(text);
    return zh ? `${zh} ${text}` : text;
  };

  const subject = patternAttr(attrs, "subject_name");
  const object = patternAttr(attrs, "object_name");
  const patternType = patternAttr(attrs, "pattern_type").text;
  const scope = patternAttr(attrs, "scope").text;
  const predicate = patternAttr(attrs, "predicate").text;
  const predicateZh = predicate && predicateLabels.data ? localizePredicate(predicate, predicateLabels.data) : predicate;
  const support = patternAttr(attrs, "support_count").count;
  const occurrence = patternAttr(attrs, "occurrence_count").count;
  const reports = patternAttr(attrs, "source_reports")
    .text.split("、")
    .map((name) => name.trim())
    .filter(Boolean);
  const subjectVariants = patternAttr(attrs, "subject_variants")
    .text.split("、")
    .map((name) => name.trim())
    .filter(Boolean);
  const objectVariants = patternAttr(attrs, "object_variants")
    .text.split("、")
    .map((name) => name.trim())
    .filter(Boolean);
  const desc = patternAttr(attrs, "pattern_desc").text;
  const refinedDesc = patternAttr(attrs, "refined_desc").text;
  const refinedAt = patternAttr(attrs, "refined_at").text;

  return (
    <div
      className="border-primary/25 bg-primary/[0.04] mb-3 rounded-lg border p-2.5"
      data-testid="domain-pattern-card"
    >
      <div className="text-muted-foreground mb-1.5 flex items-center gap-1.5 text-[10.5px] font-medium tracking-widest">
        领域模式 · B 库规律
        {patternType ? (
          <span className="bg-primary/10 text-primary ml-auto rounded-full px-2 py-0.5 text-[10px] tracking-normal">
            {patternType}规律
          </span>
        ) : null}
      </div>

      {/* 主体 → 客体 */}
      <div className="border-border bg-card mb-2 rounded-md border px-2.5 py-2">
        <div className="text-foreground flex items-center gap-1.5 text-xs font-medium">
          <span className="truncate" title={subject.text}>
            {subject.text || "—"}
          </span>
          <span className="text-muted-foreground shrink-0">→</span>
          <span className="truncate" title={object.text}>
            {object.text || "—"}
          </span>
        </div>
        {subject.text || object.text ? (
          <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-[10px]">
            <span className="truncate">{zhEtype(patternAttr(attrs, "subject_etype").text)}</span>
            <span className="shrink-0">→</span>
            <span className="truncate">{zhEtype(patternAttr(attrs, "object_etype").text)}</span>
          </div>
        ) : null}
      </div>

      {/* 指标行：支撑样本 / 共现 / 谓词 */}
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        {support !== null ? (
          <span className="text-muted-foreground">
            支撑样本 <b className="text-foreground tabular-nums">{support}</b> 份报告
          </span>
        ) : null}
        {occurrence !== null ? (
          <span className="text-muted-foreground">
            共现 <b className="text-foreground tabular-nums">{occurrence}</b> 次
          </span>
        ) : null}
        {predicateZh ? (
          <span className="text-muted-foreground">
            谓词 <b className="text-foreground">{predicateZh}</b>
          </span>
        ) : null}
        {scope ? (
          <span className="text-muted-foreground">
            归属 <b className="text-foreground font-mono">{scope}</b>
          </span>
        ) : null}
      </div>

      {/* 来源报告 chips */}
      {reports.length > 0 ? (
        <div className="mb-2">
          <div className="text-muted-foreground mb-1 text-[10.5px]">来源报告 · {reports.length}</div>
          <div className="flex flex-wrap gap-1">
            {reports.slice(0, PATTERN_REPORT_CHIPS).map((report) => (
              <span
                key={report}
                className="border-border text-muted-foreground rounded-full border px-1.5 py-0.5 font-mono text-[10px]"
              >
                {report}
              </span>
            ))}
            {reports.length > PATTERN_REPORT_CHIPS ? (
              <span className="text-muted-foreground px-0.5 py-0.5 text-[10px] tabular-nums">
                +{reports.length - PATTERN_REPORT_CHIPS}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* 端点变体名（归并版蒸馏产物，缺省不渲染） */}
      {subjectVariants.length > 0 || objectVariants.length > 0 ? (
        <div className="mb-2">
          <div className="text-muted-foreground mb-1 text-[10.5px]">端点变体</div>
          <div className="flex flex-wrap gap-1">
            {subjectVariants.map((variant) => (
              <span
                key={`s-${variant}`}
                className="border-border bg-card text-muted-foreground rounded-full border px-1.5 py-0.5 text-[10px]"
              >
                主: {variant}
              </span>
            ))}
            {objectVariants.map((variant) => (
              <span
                key={`o-${variant}`}
                className="border-border bg-card text-muted-foreground rounded-full border px-1.5 py-0.5 text-[10px]"
              >
                客: {variant}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {/* 规律描述 */}
      {desc ? (
        <div className="mb-2">
          <div className="text-muted-foreground mb-1 text-[10.5px]">规律描述</div>
          <p className="text-foreground text-[11.5px] leading-relaxed">{desc}</p>
        </div>
      ) : null}

      {/* 精炼解读（引用块） */}
      {refinedDesc ? (
        <div className="border-primary/40 border-l-2 pl-2">
          <div className="text-primary mb-1 text-[10.5px] font-medium">
            精炼解读
            {refinedAt ? (
              <span className="text-muted-foreground ml-1 font-normal tabular-nums">
                · {refinedAt.slice(0, 10)}
              </span>
            ) : null}
          </div>
          <p className="text-foreground text-[11.5px] leading-relaxed">{refinedDesc}</p>
        </div>
      ) : null}
    </div>
  );
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
  // EAI-CUSTOM(2026-10-01 domain_pattern): 规律行走结构化卡片；attrs 已被卡片消化时
  // 通用属性表剔除该列（否则整段 JSON 原样渲染不可读）。卡片渲染不出（attrs 缺失/畸形）
  // 时保持通用行为——attrs 留在表里兜底。
  const isDomainPattern = properties.etype === "domain_pattern";
  const patternAttrs = isDomainPattern ? normalizePatternAttrs(properties.attrs) : null;
  const genericEntries = Object.entries(properties).filter(
    ([key]) => !(patternAttrs && key === "attrs"),
  );
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
        {isDomainPattern ? (
          <span className="border-primary/40 text-primary rounded-full border px-2 py-0.5 text-[10.5px]">
            领域模式
          </span>
        ) : null}
      </div>

      {isDomainPattern ? <DomainPatternCard properties={properties} /> : null}

      <h3 className="text-muted-foreground mb-1.5 text-[10.5px] font-medium tracking-widest">属性</h3>
      {genericEntries.length > 0 ? (
        <dl className="grid grid-cols-[96px_1fr] gap-x-2.5 gap-y-1 text-xs">
          {genericEntries.map(([key, value]) => (
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
      {/* 跨页入口（EAI-CUSTOM 2026-09-27 原型重构③） */}
      <div className="border-border mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
        <span className="text-muted-foreground text-[10px]">快捷：</span>
        <button
          type="button"
          onClick={() => {
            window.location.hash = "resolve";
          }}
          className="border-border bg-card hover:bg-muted rounded-md border px-2 py-0.5 text-[10.5px] font-medium"
        >
          消解审核
        </button>
        <button
          type="button"
          onClick={() => {
            window.location.hash = "modeler";
          }}
          className="border-border bg-card hover:bg-muted rounded-md border px-2 py-0.5 text-[10.5px] font-medium"
        >
          本体建模器
        </button>
      </div>
    </div>
  );
}
