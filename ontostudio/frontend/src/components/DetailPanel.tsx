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
import { useMemo, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

/** 字段中文名映射（v4 文案包 F1）：中文主标 + 括注英文字段名；未映射键原样展示。 */
const FIELD_LABELS: Record<string, string> = {
  id: "实体 ID",
  domain: "域",
  etype: "类型",
  canonicalName: "名称",
  normName: "规范名",
  attrs: "属性",
  confidence: "置信度",
  status: "状态",
  validFrom: "生效自",
  validTo: "生效至",
  createdAt: "创建时间",
  updatedAt: "更新时间",
  thread_id: "来源会话",
  document_id: "来源文档",
};

/** attrs 键中文名 + 已知值可读化（v4 A 方案：attrs 渲染为中文键值行）。 */
const ATTR_KEY_LABELS: Record<string, string> = {
  scope: "归属",
  source_report: "来源报告",
  ingest_task: "抽取任务",
  evidence_type: "佐证类型",
  src: "来源",
  distillable: "可蒸馏",
};
const ATTR_VALUE_LABELS: Record<string, string> = {
  sample: "样例库",
  project: "项目",
};


import {
  fetchObjectDetail,
  fetchObjectLinks,
  fetchObjects,
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

/** 时间属性 → 本地时区 yyyy-MM-dd HH:mm:ss（原始为 UTC ISO 串；非法值回退原样）。 */
function formatDateTime(value: unknown): string {
  const d = value instanceof Date ? value : new Date(String(value ?? ""));
  if (isNaN(d.getTime())) {
    return formatPropertyValue(value);
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** 对侧实体名解析 hook：图内 label 优先，图外按需单行 GET canonicalName（缓存 5min）。 */
function useEntityName(entityPk: string) {
  const nodeId = `graph_entity:${entityPk}`;
  const inGraph = entityPk !== "" && graph.hasNode(nodeId);
  const q = useQuery({
    queryKey: ["ontology", "object", "graph_entity", entityPk],
    queryFn: ({ signal }) => fetchObjectDetail("graph_entity", entityPk, { signal }),
    enabled: !inGraph,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const fromGraph = inGraph
    ? String(graph.getNodeAttribute(nodeId, "label"))
    : "";
  const name =
    fromGraph ||
    String((q.data as { canonicalName?: string } | undefined)?.canonicalName ?? "") ||
    (entityPk ? `实体 ${entityPk.slice(0, 8)}…` : "—");
  return { name, inGraph };
}

/** 实体名链接：点击 → onFocusNode 在图中定位对侧。 */
function EntityNameLink({
  entityPk,
  onFocusNode,
  children,
}: {
  entityPk: string;
  onFocusNode?: (dialectId: string) => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={() => onFocusNode?.(`graph_entity:${entityPk}`)}
      title="点击在图中定位该实体"
      className="text-primary inline-flex items-center gap-1 font-medium hover:underline"
    >
      {children}
    </button>
  );
}

/** 图谱关系节点——三元组语义卡（主体 → 谓词 → 客体），替代 UUID 属性表（v4 图谱关系体验）。 */
function RelationNodeCard({
  pk,
  properties,
  onFocusNode,
  predicateLabels,
}: {
  pk: string;
  properties: Record<string, unknown>;
  onFocusNode?: (dialectId: string) => void;
  predicateLabels: Map<string, string>;
}) {
  const subjectId = String(properties.subjectId ?? "");
  const objectId = String(properties.objectId ?? "");
  const predicate = String(properties.predicate ?? "");
  const predicateCn = localizePredicate(predicate, predicateLabels);
  const subject = useEntityName(subjectId);
  const object = useEntityName(objectId);
  const attrs = (properties.attrs ?? {}) as Record<string, unknown>;

  return (
    <div className="px-3 py-3">
      <div className="mb-1 text-sm font-semibold leading-snug text-foreground">
        {subject.name}
        <span className="text-primary mx-1.5 font-mono text-xs">
          {predicateCn || predicate}
        </span>
        {object.name}
      </div>
      <div className="mb-3 flex flex-wrap gap-1">
        <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-xs">graph_relation</span>
        <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-xs">图谱关系</span>
      </div>
      <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-widest">关系</h3>
      <dl className="grid grid-cols-[96px_1fr] gap-x-2.5 gap-y-1 text-sm">
        <dt className="text-muted-foreground">谓词</dt>
        <dd className="text-foreground font-mono text-xs">
          {predicate}
          {predicateCn !== predicate ? `（${predicateCn}）` : ""}
        </dd>
        <dt className="text-muted-foreground">主体实体</dt>
        <dd className="text-foreground">
          <EntityNameLink entityPk={subjectId} onFocusNode={onFocusNode}>
            {subject.name}
          </EntityNameLink>
        </dd>
        <dt className="text-muted-foreground">客体实体</dt>
        <dd className="text-foreground">
          <EntityNameLink entityPk={objectId} onFocusNode={onFocusNode}>
            {object.name}
          </EntityNameLink>
        </dd>
        <dt className="text-muted-foreground">置信度</dt>
        <dd className="text-foreground tabular-nums">{String(properties.confidence ?? "—")}</dd>
        {Object.entries(attrs).map(([k, v]) => (
          <div key={k} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-muted-foreground">{ATTR_KEY_LABELS[k] ?? k}</dt>
            <dd className="text-foreground break-all tabular-nums">
              {typeof v === "boolean" ? (v ? "是" : "否") : String(v ?? "—")}
            </dd>
          </div>
        ))}
      </dl>
      <details className="mt-2">
        <summary className="text-muted-foreground cursor-pointer select-none text-[11px] hover:text-foreground">
          技术信息（关系 ID）
        </summary>
        <div className="text-muted-foreground mt-1 font-mono text-[10.5px] break-all">{pk}</div>
      </details>
    </div>
  );
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
      <div className="text-muted-foreground mb-1.5 flex items-center gap-1.5 text-xs font-medium tracking-widest">
        领域模式 · B 库规律
        {patternType ? (
          <span className="bg-primary/10 text-primary ml-auto rounded-full px-2 py-0.5 text-xs tracking-normal">
            {patternType}规律
          </span>
        ) : null}
      </div>

      {/* 主体 → 客体 */}
      <div className="border-border bg-card mb-2 rounded-md border px-2.5 py-2">
        <div className="text-foreground flex items-center gap-1.5 text-sm font-medium">
          <span className="truncate" title={subject.text}>
            {subject.text || "—"}
          </span>
          <span className="text-muted-foreground shrink-0">→</span>
          <span className="truncate" title={object.text}>
            {object.text || "—"}
          </span>
        </div>
        {subject.text || object.text ? (
          <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-xs">
            <span className="truncate">{zhEtype(patternAttr(attrs, "subject_etype").text)}</span>
            <span className="shrink-0">→</span>
            <span className="truncate">{zhEtype(patternAttr(attrs, "object_etype").text)}</span>
          </div>
        ) : null}
      </div>

      {/* 指标行：支撑样本 / 共现 / 谓词 */}
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
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
          <div className="text-muted-foreground mb-1 text-xs">来源报告 · {reports.length}</div>
          <div className="flex flex-wrap gap-1">
            {reports.slice(0, PATTERN_REPORT_CHIPS).map((report) => (
              <span
                key={report}
                className="border-border text-muted-foreground rounded-full border px-1.5 py-0.5 font-mono text-xs"
              >
                {report}
              </span>
            ))}
            {reports.length > PATTERN_REPORT_CHIPS ? (
              <span className="text-muted-foreground px-0.5 py-0.5 text-xs tabular-nums">
                +{reports.length - PATTERN_REPORT_CHIPS}
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* 端点变体名（归并版蒸馏产物，缺省不渲染） */}
      {subjectVariants.length > 0 || objectVariants.length > 0 ? (
        <div className="mb-2">
          <div className="text-muted-foreground mb-1 text-xs">端点变体</div>
          <div className="flex flex-wrap gap-1">
            {subjectVariants.map((variant) => (
              <span
                key={`s-${variant}`}
                className="border-border bg-card text-muted-foreground rounded-full border px-1.5 py-0.5 text-xs"
              >
                主: {variant}
              </span>
            ))}
            {objectVariants.map((variant) => (
              <span
                key={`o-${variant}`}
                className="border-border bg-card text-muted-foreground rounded-full border px-1.5 py-0.5 text-xs"
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
          <div className="text-muted-foreground mb-1 text-xs">规律描述</div>
          <p className="text-foreground text-xs leading-relaxed">{desc}</p>
        </div>
      ) : null}

      {/* 精炼解读（引用块） */}
      {refinedDesc ? (
        <div className="border-primary/40 border-l-2 pl-2">
          <div className="text-primary mb-1 text-xs font-medium">
            精炼解读
            {refinedAt ? (
              <span className="text-muted-foreground ml-1 font-normal tabular-nums">
                · {refinedAt.slice(0, 10)}
              </span>
            ) : null}
          </div>
          <p className="text-foreground text-xs leading-relaxed">{refinedDesc}</p>
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
  onFocusNode?: (dialectId: string) => void;
}

/** 链型组头中文（v4 关联链接语义化）：未知链型回退原样。 */
const LINK_TYPE_LABELS: Record<string, string> = {
  relation_subject: "作为主体的关系",
  relation_object: "作为客体的关系",
  mention_of_entity: "证据引文",
};

/** 关系行→对侧实体 pk（入向=主体，出向=客体）。 */
function oppositeEntityPk(row: Record<string, unknown>, thisPk: string): string {
  // objects API 行键为 camelCase（api_name 映射）——subjectId/objectId；snake 为历史兜底
  const subject = String(row.subjectId ?? row.subject_id ?? "");
  const object = String(row.objectId ?? row.object_id ?? "");
  if (!subject || !object) {
    return subject || object;
  }
  return subject === thisPk ? object : subject;
}

/** 单个链接类型的对侧行列表（ TanStack Query 按需拉取，仅节点被选中时 enabled）。 */
function LinkTypeRows({ apiName, pk, linkType, opposite, onFocusNode }: LinkTypeRowsProps) {
  const outgoing = linkType.source === apiName;
  const predicateLabels = useQuery({
    queryKey: ["ontology", "predicate-labels"],
    queryFn: getPredicateLabels,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const isRelationLink = opposite.name === "graph_relation";
  const isMentionLink = opposite.name === "graph_mention";

  // 名称索引（v4 关联链接语义化兜底）：对侧实体不在已加载图（graph/nodes 钳制 2000）
  // 时，从全量实体清单解析 canonical_name——一次拉取缓存 5min，与实体库同源。
  const namesQuery = useQuery({
    queryKey: ["ontology", "objects", "graph_entity", "name-index"],
    queryFn: ({ signal }) => fetchObjects("graph_entity", { limit: 5000, signal }),
    staleTime: 5 * 60_000,
  });
  const entityNameIndex = useMemo(
    () => new Map((namesQuery.data?.data ?? []).map((r) => [String(r.id), String((r as { canonicalName?: string }).canonicalName ?? r.label ?? r.id)])),
    [namesQuery.data],
  );
  const linksQuery = useQuery({
    queryKey: ["ontology", "links", apiName, pk, linkType.name],
    queryFn: ({ signal }) => fetchObjectLinks(apiName, pk, linkType.name, { signal }),
    enabled: Boolean(apiName && pk),
    retry: 0,
  });

  const rows = linksQuery.data?.data ?? [];

  return (
    <div className="mb-2">
      <div className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs">
        <span className="text-primary font-medium">{LINK_TYPE_LABELS[linkType.name] ?? linkType.name}</span>
        <span className="text-muted-foreground font-mono text-[10px]">{linkType.name}</span>
        <span>{outgoing ? "→ 出" : "← 入"}</span>
        <span className="ml-auto tabular-nums">{linksQuery.isLoading ? "…" : rows.length}</span>
      </div>
      {linksQuery.isError ? (
        <div className="text-muted-foreground border-border rounded-md border border-dashed px-2 py-1.5 text-xs">
          {String(linksQuery.error)}
        </div>
      ) : null}
      {!linksQuery.isError && rows.map((row, index) => {
        const pkText = pkToString(row[opposite.pk]);
        const oppositeId = `${opposite.name}:${pkText}`;

        // 关系行：对侧实体（入向行本实体是 object→对侧=subject；出向反之）+谓词中文
        if (isRelationLink) {
          const otherPk = oppositeEntityPk(row, pk);
          const otherNodeId = `graph_entity:${otherPk}`;
          // 名称解析三级：图内 label → 按需单行 GET（graph 外实体）→ 短 pk
          const otherName = (graph.hasNode(otherNodeId)
            ? String(graph.getNodeAttribute(otherNodeId, "label"))
            : "") || entityNameIndex.get(otherPk) || `实体 ${otherPk.slice(0, 8)}…`;
          const predicate = localizePredicate(
            String(row.predicate ?? ""),
            predicateLabels.data ?? new Map(),
          );
          return (
            <button
              key={`${oppositeId}-${index}`}
              type="button"
              onClick={() => onFocusNode?.(otherNodeId)}
              title={`${predicate} · 点击在图中定位 ${otherName}`}
              className="border-border text-foreground hover:border-primary/50 hover:bg-primary/5 mt-1 flex w-full items-center gap-1.5 rounded-md border px-2 py-1.5 text-left text-xs transition-colors"
            >
              <span className="text-primary truncate font-medium">{otherName}</span>
              <span className="text-muted-foreground ml-auto shrink-0 font-mono text-[10px]">{predicate}</span>
              <span className="text-muted-foreground shrink-0">{outgoing ? "→" : "←"}</span>
            </button>
          );
        }

        // 引文行：quote 片段优先（v4：引文=证据，不再是 UUID 卡）
        if (isMentionLink) {
          const quote = String(row.quote ?? "").trim();
          const doc = String(row.document_id ?? "");
          return (
            <div
              key={`${oppositeId}-${index}`}
              className="border-border text-foreground mt-1 rounded-md border px-2 py-1.5 text-xs"
            >
              <div className="truncate" title={quote || doc}>
                {quote ? `「${quote}」` : doc || "（无上下文引文）"}
              </div>
              {doc ? <div className="text-muted-foreground mt-0.5 truncate font-mono text-[10px]">{doc}</div> : null}
            </div>
          );
        }

        // 其余链型：对侧节点在图中→名称可点；否则回退原 UUID 行
        const label = (
          graph.hasNode(oppositeId)
            ? String(graph.getNodeAttribute(oppositeId, "label"))
            : ""
        ) || pkText || "?";
        return (
          <button
            key={`${oppositeId}-${index}`}
            type="button"
            onClick={() => onFocusNode?.(oppositeId)}
            title={label}
            className="border-border text-foreground hover:border-primary/50 hover:bg-primary/5 mt-1 flex w-full items-center gap-1.5 rounded-md border px-2 py-1.5 text-left text-xs transition-colors"
          >
            <span className="truncate">{label}</span>
            <span className="text-muted-foreground ml-auto shrink-0 text-xs">
              {outgoing ? "→" : "←"} {outgoing ? linkType.target : linkType.source}
            </span>
          </button>
        );
      })}
      {!linksQuery.isError && !linksQuery.isLoading && rows.length === 0 ? (
        <div className="text-muted-foreground px-2 py-1 text-xs">无关联实例</div>
      ) : null}
    </div>
  );
}

export function DetailPanel({
  nodeId,
  onFocusNode,
}: {
  nodeId: string | null;
  onFocusNode?: (dialectId: string) => void;
}) {
  const schemaQuery = useQuery({
    queryKey: ["ontology", "object-types"],
    queryFn: fetchObjectTypes,
  });
  // 谓词中文标注（图谱关系节点语义卡与规律卡共用，模块级缓存）
  const predicateLabelsQuery = useQuery({
    queryKey: ["ontology", "predicate-labels"],
    queryFn: getPredicateLabels,
    staleTime: Number.POSITIVE_INFINITY,
  });

  if (!nodeId) {
    return (
      <div className="text-muted-foreground px-3 py-10 text-center text-sm leading-loose">
        点击图中节点查看
        <br />
        属性与关联链接
      </div>
    );
  }

  const parsed = splitNodeId(nodeId);
  if (!parsed) {
    return (
      <div className="text-muted-foreground px-3 py-10 text-center text-sm">
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
  // 字段分层（v4 文案包 F1 续）：核心业务字段常驻；技术字段（ID/时间戳/时效）收进
  // 「其他信息」折叠；空值整行隐藏——生效自/至 实测常为 null，空行纯噪音。
  const TECH_FIELDS = new Set(["id", "createdAt", "updatedAt", "validFrom", "validTo"]);
  const isEmptyVal = (v: unknown) => v === null || v === undefined || v === "";
  const coreEntries = genericEntries.filter(([k, v]) => !TECH_FIELDS.has(k) && !isEmptyVal(v));
  const techEntries = genericEntries.filter(([k, v]) => TECH_FIELDS.has(k) && !isEmptyVal(v));
  const linkTypes = (schemaQuery.data?.link_types ?? []).filter(
    (lt) => lt.enabled && (lt.source === apiName || lt.target === apiName),
  );

  // EAI-CUSTOM(2026-10-01 v4 图谱关系节点): 三元组语义卡——UUID 标题与 subjectId/objectId
  // 裸行对操作者无意义，改为主体→谓词→客体的句子式呈现。
  if (apiName === "graph_relation") {
    return (
      <RelationNodeCard
        pk={pk}
        properties={properties}
        predicateLabels={predicateLabelsQuery.data ?? new Map()}
        onFocusNode={onFocusNode}
      />
    );
  }

  return (
    <div className="px-3 py-3">
      <div className="mb-1 break-all text-sm font-semibold leading-snug text-foreground">
        {attrs?.label ?? pk}
      </div>
      <div className="mb-3 flex flex-wrap gap-1">
        <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-xs">
          {apiName}
        </span>
        {findObjectType(schemaQuery.data, apiName) ? (
          <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-xs">
            {findObjectType(schemaQuery.data, apiName)?.display_name}
          </span>
        ) : null}
        {isDomainPattern ? (
          <span className="border-primary/40 text-primary rounded-full border px-2 py-0.5 text-xs">
            领域模式
          </span>
        ) : null}
      </div>

      {isDomainPattern ? <DomainPatternCard properties={properties} /> : null}
      <hr className="my-2" />
      <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-widest">属性</h3>
      
      {genericEntries.length > 0 ? (
        <dl className="grid grid-cols-[96px_1fr] gap-x-2.5 gap-y-1 text-[13px]">
          {coreEntries.map(([key, value]) => {
            const label = FIELD_LABELS[key];
            return (
            <div key={key} className="col-span-2 grid grid-cols-subgrid">
              <dt className="text-muted-foreground break-words">
                {label ?? key}
                {label ? <span className="ml-1 font-mono text-[9.5px] opacity-60">{key}</span> : null}
              </dt>
              <dd className="text-foreground break-all tabular-nums">
                {value !== null && typeof value === "object" && !Array.isArray(value) ? (
                  <span className="flex flex-col gap-0.5">
                    {Object.entries(value as Record<string, unknown>).map(([k2, v2]) => (
                      <span key={k2} className="flex items-baseline justify-between gap-2">
                        <span className="text-muted-foreground font-mono text-[10.5px]">
                          {ATTR_KEY_LABELS[k2] ?? k2}
                        </span>
                        <span className="break-all">
                          {typeof v2 === "boolean"
                            ? v2
                              ? "是"
                              : "否"
                            : ATTR_VALUE_LABELS[String(v2)] ?? String(v2)}
                        </span>
                      </span>
                    ))}
                  </span>
                ) : (
                  formatPropertyValue(value)
                )}
              </dd>
            </div>
            );
          })}
        </dl>
      ) : (
        <div className="text-muted-foreground text-xs">
          {schemaQuery.isLoading ? "加载属性清单…" : "无可显示属性"}
        </div>
      )}

      {techEntries.length > 0 ? (
        <details className="mt-2">
          <summary className="text-muted-foreground cursor-pointer select-none text-[11px] hover:text-foreground">
            其他信息（ID / 时间戳 / 时效）
          </summary>
          <dl className="mt-1.5 grid grid-cols-[96px_1fr] gap-x-2.5 gap-y-1 text-xs">
            {techEntries.map(([key, value]) => {
              const label = FIELD_LABELS[key];
              return (
                <div key={key} className="col-span-2 grid grid-cols-subgrid">
                  <dt className="text-muted-foreground break-words">
                    {label ?? key}
                    {label ? <span className="ml-1 font-mono text-[9.5px] opacity-60">{key}</span> : null}
                  </dt>
                  <dd className="text-foreground break-all tabular-nums">
                    {key === "createdAt" || key === "updatedAt" || key === "validFrom" || key === "validTo"
                      ? formatDateTime(value)
                      : formatPropertyValue(value)}
                  </dd>
                </div>
              );
            })}
          </dl>
        </details>
      ) : null}
      <hr className="my-2" />
      <h3 className="text-muted-foreground mt-4 mb-1.5 text-xs font-medium tracking-widest">
        关联链接
      </h3>
      {schemaQuery.isLoading ? (
        <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
          <Loader2 className="h-3 w-3 animate-spin" />
          加载链接类型…
        </div>
      ) : linkTypes.length === 0 ? (
        <div className="text-muted-foreground text-xs">该对象类型未声明 enabled 链接</div>
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
              onFocusNode={onFocusNode}
            />
          );
        })
      )}
      {/* 跨页入口（EAI-CUSTOM 2026-09-27 原型重构③） */}
      <div className="border-border mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
        <span className="text-muted-foreground text-xs">快捷：</span>
        <button
          type="button"
          onClick={() => {
            window.location.hash = "resolve";
          }}
          className="border-border bg-card hover:bg-muted rounded-md border px-2 py-0.5 text-xs font-medium"
        >
          消解审核
        </button>
        <button
          type="button"
          onClick={() => {
            window.location.hash = "modeler";
          }}
          className="border-border bg-card hover:bg-muted rounded-md border px-2 py-0.5 text-xs font-medium"
        >
          本体建模器
        </button>
      </div>
    </div>
  );
}
