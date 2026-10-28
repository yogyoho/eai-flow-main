/**
 * 03 实体库（EAI-CUSTOM, 2026-09-27 原型还原版）——完全对照
 * docs/designs/ontostudio-frontend-redesign-20260926.html#entities 还原：
 *
 * - 宽屏主从布局：左侧「实体检索」面板（搜索 + 域/类型过滤 + 状态 chips +
 *   表格 + 分页），右侧常驻详情栏（实体详情 / 关系 / 来源证据）。
 *   行点击更新详情栏；窄屏（<1280px）保留右侧抽屉交互。
 * - 列序 = 原型：实体（规范名/URI 作副行）/ 类型 / 域 / 置信度 / 状态 / 提及 /
 *   更新 / 行操作（pending→去审核、merged→查看合并、其余→详情）；无裸 pk 列。
 * - 页脚 = 原型：左「共 N 行 · 每页 50 · 分页控件」+ 真实上一页/下一页；
 *   右「批量送审」（规划中，见按钮 tooltip）。
 * 数据面：/ontology/object-types + /objects/{type}（q + filters + cursor）
 * + /ontology/aggregate（域计数 / 总行数 / 提及计数 Top200）。
 */
import {
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  Loader2,
  Plus,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
import { getPredicateLabels, localizePredicate } from "@/explorerDataSource";
import { domainAlias } from "@/lib/terms";
import { cn } from "@/lib/utils";

const PAGE_SIZES = [10, 25, 50, 100] as const;

/** graph_entity 状态枚举（registry core_graph.yaml 声明）。 */
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
  { api: "domain", label: "域" },
  { api: "confidence", label: "置信度" },
  { api: "status", label: "状态" },
  { api: "__mentions", label: "提及" },
  { api: "updatedAt", label: "更新" },
];

/** 通用对象列表不展示技术字段：主键 ID 与原始 attrs JSON（环评/营销实体等）。 */
const HIDDEN_GENERIC_FIELDS = new Set(["id", "attrs"]);

/** 通用对象字段中文名（registry api_name → 中文）。实体库类型切换后表头统一走这里；
 *  未收录的自定义字段回退 api_name，避免出现空表头。 */
const FIELD_LABELS: Record<string, string> = {
  id: "标识",
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
  subjectId: "主体实体",
  predicate: "谓词",
  objectId: "客体实体",
  entityId: "实体",
  relationId: "关系",
  threadId: "来源会话",
  documentId: "来源文档",
  docSpan: "文档定位",
  quote: "原文引用",
  extractedBy: "抽取者",
  extractedAt: "抽取时间",
  error: "抽取错误",
};

/** 关系对象列序（图谱/环评/营销关系共用）：只保留可读的业务字段（裸 id/attrs 不占列），
 *  主体/客体渲染实体名、谓词渲染中文标注。 */
const RELATION_COLUMNS = [
  { api: "subjectId", label: "主体实体" },
  { api: "predicate", label: "谓词" },
  { api: "objectId", label: "客体实体" },
  { api: "confidence", label: "置信度" },
  { api: "createdAt", label: "创建时间" },
];

/** 图谱证据列序：实体/关系 ID 渲染为对应名称，不展示裸 UUID；文档与引文保留溯源信息。 */
const MENTION_COLUMNS = [
  { api: "entityId", label: "实体" },
  { api: "relationId", label: "关系" },
  { api: "documentId", label: "来源文档" },
  { api: "quote", label: "原文引用" },
  { api: "extractedAt", label: "抽取时间" },
];

/** core_graph.yaml「# 谓词中文标注」的本地兜底（registry-content 需 system:access，
 *  无权限时仍保证图谱关系列表显示中文；动态标注可用时优先动态值）。 */
const CORE_PREDICATE_LABELS: Record<string, string> = {
  org_in_ecosystem_of: "归入生态",
  bidder_qualified_for: "具备投标资质",
  bidder_of_project: "投标",
  bidder_supplies_goods: "供货",
  bidder_holds_qualification: "持有资质",
  project_won_by_bidder: "中标",
  org_compiles_project: "编制",
  org_commissions_project: "委托",
  org_develops_project: "开发",
  org_involved_in: "参与",
};

/** 关系类型的对侧实体类型（图谱/环评/营销关系共用列语义）。 */
const RELATION_ENTITY_TYPES: Record<string, string> = {
  graph_relation: "graph_entity",
  eia_relation: "eia_entity",
  market_relation: "market_entity",
};

/** 关系列表主体/客体名称索引：/objects 单页上限 200（引擎 MAX_LIMIT），按 offset 排水。 */
const BULK_PAGE_SIZE = 200;
const EMPTY_LOOKUP = new Map<string, string>();

async function fetchAllObjects(
  objectType: string,
  signal?: AbortSignal,
): Promise<Array<Record<string, unknown>>> {
  const rows: Array<Record<string, unknown>> = [];
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  let pages = 0;
  while (offset < total && pages < 500) {
    pages += 1;
    const page = await fetchObjects(objectType, {
      limit: BULK_PAGE_SIZE,
      offset,
      signal,
    });
    total = page.total > 0 ? page.total : Number.POSITIVE_INFINITY;
    rows.push(...page.data);
    if (page.data.length < BULK_PAGE_SIZE) {
      break;
    }
    offset += page.data.length;
  }
  return rows;
}

async function fetchObjectNameIndex(
  objectType: string,
  signal?: AbortSignal,
): Promise<Map<string, string>> {
  const map = new Map<string, string>();
  for (const row of await fetchAllObjects(objectType, signal)) {
    const id = String(row.id ?? "");
    const name = String(
      row.canonicalName ?? row.name ?? row.label ?? "",
    ).trim();
    if (id && name) {
      map.set(id, name);
    }
  }
  return map;
}

function fieldLabel(api: string): string {
  return FIELD_LABELS[api] ?? api;
}

/** graph_entity 常见 etype 的中文名与药丸色调（未知类型回退原始值）。 */
const ETYPE_LABELS: Record<string, string> = {
  mine: "矿井",
  face: "工作面",
  equipment: "设备",
  sensor: "传感器",
  standard: "标准条款",
  document: "证据文档",
  team: "责任班组",
};

const ETYPE_TONES: Record<string, string> = {
  mine: "os-pill-main",
  face: "os-pill-main",
  equipment: "os-pill-orange",
  sensor: "os-pill-ok",
  standard: "os-pill-warn",
  document: "os-pill-gray",
  team: "os-pill-main",
};

function etypeLabel(value: unknown): string {
  const key = String(value ?? "");
  return ETYPE_LABELS[key] ?? key;
}

function etypeTone(value: unknown): string {
  return ETYPE_TONES[String(value ?? "")] ?? "os-pill-gray";
}

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
/** 右侧常驻详情栏断点：≥1280px 显示，较窄视口保留抽屉交互。 */
const RAIL_MEDIA_QUERY = "(min-width: 1280px)";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(query).matches,
  );
  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia(query);
    const onChange = () => setMatches(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

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
          "h-[30px] w-auto gap-1 rounded-[7px] border-[var(--border)] bg-[var(--card)] px-2.5 text-[12px] font-normal shadow-none",
          active
            ? "border-[var(--main-300)] bg-[var(--main-50)] text-[var(--main-600)]"
            : "text-[var(--text-2)]",
        )}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent position="popper" className="max-h-72 text-[13px]">
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
  const isMentionList = activeType === "graph_mention";
  const relationEntityType = activeType
    ? RELATION_ENTITY_TYPES[activeType]
    : undefined;
  const isRelationList = Boolean(relationEntityType);

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
    // 深链直开（校验违规下钻 #entities:<uuid>）：宽屏详情栏 / 窄屏抽屉打开该实体
    initialEntity ? `graph_entity:${initialEntity}` : null,
  );
  const isWideRail = useMediaQuery(RAIL_MEDIA_QUERY);

  useEffect(() => {
    // Esc 仅用于关闭窄屏抽屉；宽屏详情栏常驻，不响应 Esc。
    if (!selectedId || isWideRail) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedId, isWideRail]);

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

  // 关系列表：主体/客体 UUID → 实体名（全量名称索引排水，/objects 单页上限 200），
  // 谓词 → 中文标注（三域 registry 合并；接口不可达时用本地兜底）。
  const relationNameIndexQuery = useQuery({
    queryKey: [
      "ontology",
      "objects",
      relationEntityType,
      "name-index",
      "all",
    ],
    queryFn: ({ signal }) =>
      fetchObjectNameIndex(relationEntityType as string, signal),
    enabled: isRelationList && rows.length > 0,
    staleTime: 5 * 60_000,
  });
  const relationNameIndex = relationNameIndexQuery.data ?? EMPTY_LOOKUP;

  // 图谱证据：实体列按 graph_entity 名称解析；关系列按 graph_relation 三元组
  // （主体名 谓词中文 客体名）解析，均不展示裸 UUID。
  const mentionEntityNameIndexQuery = useQuery({
    queryKey: ["ontology", "objects", "graph_entity", "name-index", "all"],
    queryFn: ({ signal }) => fetchObjectNameIndex("graph_entity", signal),
    enabled: isMentionList && rows.length > 0,
    staleTime: 5 * 60_000,
  });
  const mentionEntityNameIndex =
    mentionEntityNameIndexQuery.data ?? EMPTY_LOOKUP;

  const mentionRelationIndexQuery = useQuery({
    queryKey: [
      "ontology",
      "objects",
      "graph_relation",
      "relation-index",
      "all",
    ],
    queryFn: ({ signal }) => fetchAllObjects("graph_relation", signal),
    enabled: isMentionList && rows.length > 0,
    staleTime: 5 * 60_000,
  });

  const relationPredicateLabelsQuery = useQuery({
    queryKey: ["ontology", "predicate-labels"],
    queryFn: getPredicateLabels,
    enabled: isRelationList || isMentionList,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const relationPredicateLabels =
    relationPredicateLabelsQuery.data ?? EMPTY_LOOKUP;

  const mentionRelationNameIndex = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of mentionRelationIndexQuery.data ?? []) {
      const id = String(row.id ?? "");
      if (!id) {
        continue;
      }
      const rawPredicate = String(row.predicate ?? "");
      const predicateCn =
        relationPredicateLabels.get(rawPredicate) ??
        CORE_PREDICATE_LABELS[rawPredicate] ??
        localizePredicate(rawPredicate, relationPredicateLabels);
      const subject =
        mentionEntityNameIndex.get(String(row.subjectId ?? "")) ?? "";
      const object =
        mentionEntityNameIndex.get(String(row.objectId ?? "")) ?? "";
      map.set(
        id,
        [subject || "未知实体", predicateCn || rawPredicate, object || "未知实体"]
          .filter(Boolean)
          .join(" "),
      );
    }
    return map;
  }, [
    mentionRelationIndexQuery.data,
    mentionEntityNameIndex,
    relationPredicateLabels,
  ]);

  const columns = useMemo(() => {
    if (isGraphEntity) return GRAPH_ENTITY_COLUMNS;
    if (isRelationList) return RELATION_COLUMNS;
    if (isMentionList) return MENTION_COLUMNS;
    return (activeMeta?.properties ?? [])
      .slice(0, 6)
      .filter((p) => !HIDDEN_GENERIC_FIELDS.has(p))
      .map((p) => ({ api: p, label: fieldLabel(p) }));
  }, [isGraphEntity, isRelationList, isMentionList, activeMeta]);

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
  // 默认域 eia 是空态保护，不算「已过滤」；手动切到其他域/状态/关键词才算。
  const hasFilter = Boolean(
    statusFilter ||
      search ||
      (isGraphEntity && domainFilter && domainFilter !== "eia"),
  );

  const resetFilters = () => {
    setDomainFilter(isGraphEntity ? "eia" : "");
    setStatusFilter("");
    setSearchInput("");
    setSearch("");
    resetPage();
  };

  // 详情优先使用当前页行投影，避免图存储尚未挂载时只有 ID、没有属性。
  const selectedRow = selectedId
    ? rows.find(
        (row) => `${activeType}:${String(row[pkField] ?? "")}` === selectedId,
      )
    : undefined;

  // 宽屏主从视图：默认选中当前页第一条，详情栏始终有内容；窄屏仍由行点击唤起抽屉。
  useEffect(() => {
    if (
      !isWideRail ||
      selectedId ||
      !activeType ||
      rowsQuery.isFetching ||
      rows.length === 0
    ) {
      return;
    }
    const firstRow = rows[0];
    if (!firstRow) return;
    setSelectedId(`${activeType}:${String(firstRow[pkField] ?? "")}`);
  }, [
    activeType,
    isWideRail,
    pkField,
    rows,
    rowsQuery.isFetching,
    selectedId,
  ]);

  const railTitle = selectedRow
    ? String(selectedRow.canonicalName ?? selectedRow.name ?? selectedRow[pkField] ?? "—")
    : (selectedId?.split(":").slice(1).join(":") ?? "—");
  const railDomain = selectedRow?.domain
    ? (domainAlias(String(selectedRow.domain)) ?? String(selectedRow.domain))
    : "";
  const railEtype =
    isGraphEntity && selectedRow?.etype ? etypeLabel(selectedRow.etype) : "";
  const railSub = selectedRow
    ? [
        selectedRow.uri ? String(selectedRow.uri) : "",
        railDomain,
        railEtype,
      ]
        .filter(Boolean)
        .join(" · ") || (activeMeta?.display_name ?? activeType ?? "")
    : (activeMeta?.display_name ?? activeType ?? "");
  const railAttrs =
    selectedRow?.attrs &&
    typeof selectedRow.attrs === "object" &&
    !Array.isArray(selectedRow.attrs)
      ? (selectedRow.attrs as Record<string, unknown>)
      : null;
  const railSource = railAttrs?.source ?? selectedRow?.source;
  const railPk = selectedRow ? String(selectedRow[pkField] ?? "") : "";
  const railId = selectedRow ? String(selectedRow.id ?? railPk) : railPk;
  const railMentions = selectedRow
    ? mentionCountById.get(String(selectedRow.id ?? ""))
    : undefined;
  const railStatus = isGraphEntity && selectedRow
    ? (String(selectedRow.status ?? "") as EntityStatus)
    : "";
  const railStatusMeta = STATUS_META[railStatus];

  // 来源证据：按当前对象拉取 mention 引文（宽屏「来源证据」卡专用的补充查询）。
  // 实体按 entity_id，关系按 relation_id；窄屏抽屉仍由 DetailPanel 的
  // mention_of_entity 链接承载，这里 enabled 仅在宽屏触发。
  const mentionOwnerColumn = isRelationList ? "relation_id" : "entity_id";
  const railEvidenceQuery = useQuery({
    queryKey: [
      "ontology",
      "objects",
      "graph_mention",
      "by-owner",
      activeType,
      railPk,
    ],
    queryFn: ({ signal }) =>
      fetchObjects("graph_mention", {
        filters: [
          { column: mentionOwnerColumn, op: "eq", value: railPk },
        ],
        limit: 5,
        signal,
      }),
    enabled:
      isWideRail &&
      (isGraphEntity || isRelationList) &&
      Boolean(railPk),
    staleTime: 5 * 60_000,
    retry: 0,
  });
  const railEvidence = railEvidenceQuery.data?.data ?? [];
  const railEvidenceTotal = railEvidenceQuery.data?.total ?? railEvidence.length;

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
          className="os-btn os-btn-primary os-btn-sm"
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
          className="os-btn os-btn-secondary os-btn-sm"
        >
          查看合并
        </button>
      );
    }
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setSelectedId(nodeId);
        }}
        className="os-btn os-btn-ghost os-btn-sm"
      >
        详情
      </button>
    );
  }

  return (
    <div className="h-full overflow-x-hidden overflow-y-auto">
      <div className="os-page">
        <PageHeader
          clause="03"
          icon={Database}
          title="实体库"
          description="检索并浏览已入图实体，右侧查看属性、关系与来源信息。"
          actions={
            <>
              {rowsQuery.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin text-[var(--main-600)]" />
              ) : null}
              <button
                type="button"
                className="os-btn os-btn-secondary"
                disabled
                title="导出功能规划中"
              >
                <Download />
                导出 CSV
              </button>
              <button
                type="button"
                className="os-btn os-btn-primary"
                onClick={() => {
                  window.location.hash = "resolve";
                }}
              >
                <Plus />
                新建 / 复核实体
              </button>
            </>
          }
        />

        <div className={cn("os-entity-layout", isWideRail && "is-wide")}>
        <Panel
          title="实体检索"
          subtitle={hasFilter ? "已过滤" : "全部实体"}
          className="os-entity-panel"
          actions={
            <span
              className="os-entity-api"
              title="数据源：GET /ontology/objects/{type}（q + filters 分页）"
            >
              GET /objects/{activeType ?? "…"}
            </span>
          }
        >
          <div className="os-entity-toolbar">
            <div className="os-entity-search">
              <Search />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setSearch(searchInput.trim());
                    resetPage();
                  }
                  if (e.key === "Escape") {
                    setSearchInput("");
                    setSearch("");
                    resetPage();
                  }
                }}
                placeholder="搜索实体名称 / 规范名 / 来源…"
                aria-label="搜索实体"
                title="回车检索 · Esc 清空"
                className="os-entity-search-input"
              />
              {searchInput || search ? (
                <button
                  type="button"
                  className="os-entity-search-clear"
                  aria-label="清空搜索"
                  onClick={() => {
                    setSearchInput("");
                    setSearch("");
                    resetPage();
                  }}
                >
                  <X />
                </button>
              ) : (
                <kbd className="os-entity-search-kbd">↵</kbd>
              )}
            </div>
            <div className="os-entity-filters">
              {isGraphEntity ? (
                <FilterSelect
                  label="域"
                  value={domainFilter}
                  onChange={(v) => {
                    setDomainFilter(v);
                    resetPage();
                  }}
                  active={Boolean(domainFilter && domainFilter !== "eia")}
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
              <button
                type="button"
                className="os-btn os-btn-secondary os-btn-sm os-entity-reset"
                onClick={resetFilters}
                disabled={!hasFilter}
                title="重置筛选"
              >
                <RotateCcw />
                重置
              </button>
            </div>
          </div>

          {isGraphEntity ? (
            <div className="os-entity-chip-row">
              <span className="os-entity-chip-label">状态</span>
              <button
                type="button"
                className={cn("os-chip", !statusFilter && "on")}
                onClick={() => {
                  setStatusFilter("");
                  resetPage();
                }}
              >
                全部
              </button>
              {STATUS_ENUM.map((status) => (
                <button
                  key={status}
                  type="button"
                  className={cn("os-chip", statusFilter === status && "on")}
                  onClick={() => {
                    setStatusFilter(status);
                    resetPage();
                  }}
                >
                  {STATUS_META[status].label}
                </button>
              ))}
            </div>
          ) : null}
          <div className="os-entity-table-wrap">
            <table
              className={cn(
                "os-table os-entity-table",
                isMentionList && "is-mention",
              )}
            >
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th
                      key={c.api}
                      className={cn(
                        (c.api === "confidence" || c.api === "__mentions") &&
                          "os-entity-th-num",
                        c.api === "__mentions" && "os-entity-mentions-col",
                        c.api === "updatedAt" && "os-entity-updated-col",
                        c.api === "quote" && "os-entity-quote-col",
                        c.api === "extractedAt" &&
                          "os-entity-mention-time-col",
                      )}
                    >
                      {c.label}
                    </th>
                  ))}
                  <th className="os-entity-action-col">操作</th>
                </tr>
              </thead>
              <tbody>
                {rowsQuery.isLoading ? (
                  <tr>
                    <td
                      colSpan={columns.length + 1}
                      className="os-entity-state"
                    >
                      <Loader2 className="mr-1.5 inline h-4 w-4 animate-spin" />
                      正在检索实体…
                    </td>
                  </tr>
                ) : rowsQuery.isError ? (
                  <tr>
                    <td
                      colSpan={columns.length + 1}
                      className="os-entity-state os-entity-state-error"
                    >
                      加载失败：{(rowsQuery.error as Error).message}
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length + 1}
                      className="os-entity-state"
                    >
                      <Database />
                      {hasFilter
                        ? "无匹配结果——试试放宽筛选条件"
                        : "该类型暂无实例"}
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
                        tabIndex={0}
                        aria-selected={selectedId === nodeId}
                        onClick={() => setSelectedId(nodeId)}
                        onKeyDown={(e) => {
                          if (e.target !== e.currentTarget) return;
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setSelectedId(nodeId);
                          }
                        }}
                        className={cn(
                          "os-entity-row",
                          selectedId === nodeId && "is-selected",
                        )}
                      >
                        {columns.map((c) => {
                          const value = row[c.api];
                          if (c.api === "canonicalName") {
                            const norm = String(row.normName ?? "");
                            const uri = String(row.uri ?? "");
                            const sub =
                              norm && norm !== String(value ?? "") ? norm : uri;
                            return (
                              <td key={c.api}>
                                <div className="os-entity-name">
                                  <div
                                    className="os-cell-main"
                                    title={String(value ?? "")}
                                  >
                                    {renderCell(value)}
                                  </div>
                                  {sub ? (
                                    <div className="os-cell-sub" title={sub}>
                                      {sub}
                                    </div>
                                  ) : null}
                                </div>
                              </td>
                            );
                          }
                          if (c.api === "etype") {
                            return (
                              <td key={c.api}>
                                {value ? (
                                  <span
                                    className={cn(
                                      "os-pill os-entity-type-pill",
                                      etypeTone(value),
                                    )}
                                  >
                                    {etypeLabel(value)}
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                            );
                          }
                          if (c.api === "domain") {
                            const raw = String(value ?? "");
                            return (
                              <td
                                key={c.api}
                                className="os-entity-muted"
                                title={raw}
                              >
                                {raw ? (domainAlias(raw) ?? raw) : "—"}
                              </td>
                            );
                          }
                          if (c.api === "normName") {
                            return (
                              <td key={c.api} className="os-entity-generic">
                                <span title={String(value ?? "")}>
                                  {renderCell(value)}
                                </span>
                              </td>
                            );
                          }
                          if (c.api === "confidence") {
                            const num =
                              value === null || value === undefined || value === ""
                                ? null
                                : Number(value);
                            const valid = num !== null && !Number.isNaN(num);
                            return (
                              <td key={c.api} className="os-entity-num">
                                {valid ? (
                                  <span
                                    className={cn(
                                      "os-entity-confidence",
                                      num >= 0.9
                                        ? "is-up"
                                        : num >= 0.8
                                          ? "is-mid"
                                          : "is-low",
                                    )}
                                  >
                                    {num.toFixed(2)}
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                            );
                          }
                          if (c.api === "status") {
                            return (
                              <td key={c.api}>
                                {meta ? (
                                  <Chip tone={meta.tone}>{meta.label}</Chip>
                                ) : (
                                  "—"
                                )}
                              </td>
                            );
                          }
                          if (c.api === "__mentions") {
                            const count = mentionCountById.get(
                              String(row.id ?? ""),
                            );
                            return (
                              <td
                                key={c.api}
                                className="os-entity-num os-entity-mentions-col"
                              >
                                {count ?? "—"}
                              </td>
                            );
                          }
                          if (isMentionList && c.api === "entityId") {
                            const pkText = String(value ?? "");
                            const label = pkText
                              ? mentionEntityNameIndexQuery.isLoading
                                ? "加载中…"
                                : (mentionEntityNameIndex.get(pkText) ?? "—")
                              : "—";
                            return (
                              <td key={c.api} className="os-entity-generic">
                                <span>{label}</span>
                              </td>
                            );
                          }
                          if (isMentionList && c.api === "relationId") {
                            const pkText = String(value ?? "");
                            const isLoading =
                              mentionRelationIndexQuery.isLoading ||
                              mentionEntityNameIndexQuery.isLoading ||
                              relationPredicateLabelsQuery.isLoading;
                            const label = pkText
                              ? isLoading
                                ? "加载中…"
                                : (mentionRelationNameIndex.get(pkText) ?? "—")
                              : "—";
                            return (
                              <td key={c.api} className="os-entity-generic">
                                <span
                                  title={
                                    label !== "—" && label !== "加载中…"
                                      ? label
                                      : undefined
                                  }
                                >
                                  {label}
                                </span>
                              </td>
                            );
                          }
                          if (isMentionList && c.api === "extractedAt") {
                            return (
                              <td
                                key={c.api}
                                className="os-entity-time os-entity-mention-time-col"
                              >
                                {fmtTime(value)}
                              </td>
                            );
                          }
                          if (c.api === "updatedAt") {
                            return (
                              <td
                                key={c.api}
                                className="os-entity-time os-entity-updated-col"
                              >
                                {fmtTime(value)}
                              </td>
                            );
                          }
                          if (c.api === "createdAt") {
                            return (
                              <td key={c.api} className="os-entity-time">
                                {fmtTime(value)}
                              </td>
                            );
                          }
                          if (
                            c.api === "subjectId" ||
                            c.api === "objectId"
                          ) {
                            const pkText = String(value ?? "");
                            const entityName =
                              relationNameIndex.get(pkText) ?? "";
                            const label =
                              entityName ||
                              (relationNameIndexQuery.isLoading
                                ? "加载中…"
                                : "—");
                            return (
                              <td
                                key={c.api}
                                className="os-entity-generic"
                              >
                                <span>{label}</span>
                              </td>
                            );
                          }
                          if (c.api === "predicate") {
                            const raw = String(value ?? "");
                            const label = raw
                              ? (relationPredicateLabels.get(raw) ??
                                CORE_PREDICATE_LABELS[raw] ??
                                localizePredicate(
                                  raw,
                                  relationPredicateLabels,
                                ))
                              : "—";
                            return (
                              <td
                                key={c.api}
                                className="os-entity-generic"
                              >
                                <span title={raw || undefined}>
                                  {label}
                                </span>
                              </td>
                            );
                          }
                          return (
                            <td
                              key={c.api}
                              className={cn(
                                "os-entity-generic",
                                c.api === "quote" && "os-entity-quote-col",
                              )}
                            >
                              <span title={String(value ?? "")}>
                                {renderCell(value)}
                              </span>
                            </td>
                          );
                        })}
                        <td className="os-entity-action-col">
                          <div className="flex items-center justify-end">
                            <RowAction status={status} nodeId={nodeId} />
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="os-entity-foot">
            <div className="os-entity-foot-left">
              <span>
                共 <b>{total.toLocaleString()}</b> 条
                {hasFilter ? " · 已过滤" : ""}
              </span>
              <span className="os-entity-foot-sep">·</span>
              <span>
                第 {page + 1}/{totalPages} 页
              </span>
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
                  className="h-7 w-auto gap-1 rounded-[6px] border-[var(--border)] bg-[var(--card)] px-2 text-[11.5px] font-normal text-[var(--muted-foreground)] shadow-none"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper" className="text-[12px]">
                  {PAGE_SIZES.map((size) => (
                    <SelectItem key={size} value={String(size)}>
                      {size} 条/页
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="os-entity-foot-right">
              <button
                type="button"
                disabled={page <= 0}
                onClick={() => {
                  setPage(0);
                  setSelectedId(null);
                }}
                className="os-pager-btn os-pager-edge"
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
                className="os-pager-btn"
              >
                <ChevronLeft />
              </button>
              {pageWindow.map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-label={`第 ${p + 1} 页`}
                  onClick={() => {
                    setPage(p);
                    setSelectedId(null);
                  }}
                  className={cn("os-pager-btn os-pager-num", p === page && "on")}
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
                className="os-pager-btn"
              >
                <ChevronRight />
              </button>
              <button
                type="button"
                disabled={page >= totalPages - 1}
                onClick={() => {
                  setPage(totalPages - 1);
                  setSelectedId(null);
                }}
                className="os-pager-btn os-pager-edge"
              >
                末页
              </button>
              <button
                type="button"
                disabled
                title="规划中（TODOS·批量摊销）"
                className="os-btn os-btn-secondary os-btn-sm os-entity-batch"
              >
                批量送审
              </button>
            </div>
          </div>
        </Panel>

        {isWideRail ? (
          <aside className="os-entity-rail" aria-label="实体详情栏">
            <section className="os-card">
              <div className="os-card-hd">
                <b>{isGraphEntity ? "实体详情" : "对象详情"}</b>
                {selectedRow && isGraphEntity && selectedRow.etype ? (
                  <div className="os-card-right">
                    <span
                      className={cn(
                        "os-pill",
                        etypeTone(selectedRow.etype),
                      )}
                    >
                      {etypeLabel(selectedRow.etype)}
                    </span>
                  </div>
                ) : null}
              </div>
              {selectedId ? (
                <>
                  {selectedRow &&
                  (isGraphEntity ||
                    selectedRow.canonicalName ||
                    selectedRow.name) ? (
                    <div className="os-entity-rail-title">
                      <h3>{railTitle}</h3>
                      <p>{railSub}</p>
                      {railStatusMeta ? (
                        <Chip tone={railStatusMeta.tone}>
                          {railStatusMeta.label}
                        </Chip>
                      ) : null}
                    </div>
                  ) : null}
                  <DetailPanel
                    nodeId={selectedId}
                    properties={selectedRow}
                    showHeader={false}
                    showPropertiesHeading={false}
                    showLinks={false}
                    showActions={false}
                  />
                </>
              ) : (
                <div className="os-entity-rail-empty">
                  <Database />
                  <b>选择一个对象</b>
                  <p>点击左侧列表中的对象，查看属性、关系与来源信息。</p>
                </div>
              )}
            </section>

            {selectedId ? (
              <>
                {!isRelationList ? (
                  <section className="os-card">
                    <div className="os-card-hd">
                      <b>关系</b>
                      <span className="os-card-sub">按链接类型实时加载</span>
                    </div>
                    <DetailPanel
                      nodeId={selectedId}
                      properties={selectedRow}
                      showHeader={false}
                      showProperties={false}
                      showLinksHeading={false}
                      showActions={false}
                      excludeLinkTypes={["mention_of_entity"]}
                    />
                  </section>
                ) : null}

                <section className="os-card">
                  <div className="os-card-hd">
                    <b>来源证据</b>
                    <span className="os-card-sub">
                      {railEvidenceQuery.isLoading
                        ? "加载中…"
                        : railEvidenceQuery.isError
                          ? "加载失败"
                          : `${railEvidenceTotal} 条引文`}
                    </span>
                  </div>
                  <div className="os-entity-rail-body">
                    {railEvidenceQuery.isLoading ? (
                      <div className="os-entity-evidence-state">
                        <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" />
                        正在加载引文…
                      </div>
                    ) : railEvidence.length === 0 ? (
                      <div className="os-entity-evidence-state">
                        {railEvidenceQuery.isError
                          ? "引文加载失败"
                          : "暂无引文证据"}
                      </div>
                    ) : (
                      <ul className="os-entity-quotes">
                        {railEvidence.map((row, index) => {
                          const quote = String(row.quote ?? "").trim();
                          const doc = String(
                            row.documentId ?? row.document_id ?? "",
                          ).trim();
                          return (
                            <li
                              key={String(row.id ?? index)}
                              className="os-entity-quote"
                            >
                              <p title={quote || undefined}>
                                {quote ? `「${quote}」` : "（无上下文引文）"}
                              </p>
                              {doc ? (
                                <span title={doc}>{doc}</span>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                    {railEvidenceTotal > railEvidence.length ? (
                      <div className="os-entity-evidence-more">
                        共 {railEvidenceTotal} 条，仅展示前 {railEvidence.length} 条
                      </div>
                    ) : null}

                    <div className="os-entity-rail-section">标识</div>
                    <dl className="os-entity-kv">
                      <div>
                        <dt>{isGraphEntity ? "实体 URI" : "对象 URI"}</dt>
                        <dd
                          title={
                            selectedRow?.uri
                              ? String(selectedRow.uri)
                              : undefined
                          }
                        >
                          {selectedRow?.uri ? String(selectedRow.uri) : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt>来源</dt>
                        <dd
                          title={
                            railSource ? String(railSource) : undefined
                          }
                        >
                          {railSource ? String(railSource) : "—"}
                        </dd>
                      </div>
                      {isGraphEntity ? (
                        <div>
                          <dt>提及</dt>
                          <dd>{railMentions ?? "—"}</dd>
                        </div>
                      ) : null}
                      <div>
                        <dt>{isGraphEntity ? "更新" : "创建"}</dt>
                        <dd>
                          {selectedRow
                            ? fmtTime(
                                isGraphEntity
                                  ? selectedRow.updatedAt
                                  : (selectedRow.createdAt ??
                                      selectedRow.updatedAt),
                              )
                            : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt>{isGraphEntity ? "实体 ID" : "对象 ID"}</dt>
                        <dd
                          className="os-entity-rail-id"
                          title={railId || undefined}
                        >
                          {railId || "—"}
                        </dd>
                      </div>
                    </dl>
                    <div className="os-entity-rail-actions">
                      <button
                        type="button"
                        className="os-btn os-btn-secondary os-btn-sm os-entity-rail-btn"
                        onClick={() => {
                          window.location.hash = "resolve";
                        }}
                      >
                        消解审核
                      </button>
                      <button
                        type="button"
                        className="os-btn os-btn-secondary os-btn-sm os-entity-rail-btn"
                        onClick={() => {
                          window.location.hash = "modeler";
                        }}
                      >
                        本体建模器
                      </button>
                    </div>
                  </div>
                </section>
              </>
            ) : null}
          </aside>
        ) : null}
        </div>
      </div>

      {/* 窄屏行详情抽屉（遮罩 + 右滑入）；宽屏由右侧常驻详情栏承载 */}
      {selectedId && !isWideRail ? (
        <>
          <div
            className="os-entity-scrim"
            onClick={() => setSelectedId(null)}
            data-testid="entities-drawer-scrim"
          />
          <aside
            className="os-entity-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="实体详情"
            data-testid="entities-drawer"
          >
            <div className="os-entity-drawer-hd">
              <div className="os-entity-drawer-title">
                <Database />
                实体详情
              </div>
              <button
                type="button"
                className="os-drawer-close"
                aria-label="关闭详情"
                onClick={() => setSelectedId(null)}
              >
                <X />
              </button>
            </div>
            <div className="os-entity-drawer-bd">
              <DetailPanel nodeId={selectedId} properties={selectedRow} />
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}
