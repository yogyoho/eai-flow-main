/* 复制自 frontend/src/extensions/ontology/explorerDataSource.ts（S2 Task 1）——仅 import 路径改本地，内容零改动。 */
/**
 * Explorer 取数接缝实现 (EAI-CUSTOM, quality-review Fix 1, plan 2026-09-12 ontology-ui).
 *
 * 把本系统 /graph/* 端点（T1 契约 {id,type,label,properties} / {source,target,type,label}）
 * 映射为 Explorer 的 ApiNode/ApiEdge（explorer/types.ts:275-294），并包装成
 * useLoadGraph 的注入式接缝签名（UseLoadGraphOptions.fetchNodes/fetchEdges，
 * explorer/useLoadGraph.ts 的 ExplorerFetchNodes/ExplorerFetchEdges）。
 *
 * 映射决策：
 * - ApiNode.content ← T1 label（Explorer 以 content 做节点标签与实体形状分类）。
 * - ApiEdge.id ← `${source}->${target}#${type}`——确定性 id，跨页 dedup 安全；
 *   同一对节点的不同链接类型经 type 后缀保持相异；同类型同对边按 Explorer 语义视为同边合并。
 * - ApiEdge.familyId ← type（family 计数按链接类型聚合）。
 * - ApiEdge.weight ← 1（T1 无权重；log1p(1) 走 Explorer 默认视觉基线）。
 * - ApiEdge.properties ← { label }（保留 display_name 供详情展示）。
 * - ApiNode.valid_from/valid_until 不设（本系统无时间界 → Explorer 时间徽章恒灭）。
 *
 * EAI-CUSTOM(2026-09-30 关系折叠边): fetchEdges 改走 mode=flat 折叠投影——关系行由后端
 * 直接折叠为 实体—谓词—实体 带标签连线，画布上关系是连线不是圆点（旧 default 双轨投影
 * 的悬挂边在关系节点不在窗口时全部不可见）。映射沿用同一 ApiEdge 形状：
 * - ApiEdge.type/familyId ← 谓词值（family 计数即"按谓词聚合"，正是关系类型维度语义）；
 *   同一实体对同谓词的平行关系行按确定性 id 合并为一条（Explorer 既有语义）。
 * - ApiEdge.label 显示谓词值（英文，如 bidder_of_project）。注册表端点不吐谓词值级中文
 *   标注（/registry 仅计数指纹、/object-types 仅属性名清单），按任务口径回退英文谓词名，
 *   不硬编码中文对照表。
 * - relation_pk（关系行 id）透传进 properties，供溯源/详情延伸（DetailPanel 对 relation
 *   的懒加载仍走 /objects 通道，不受折叠影响）。
 */
import {
  fetchEdges as fetchEdgesPage,
  fetchNodes as fetchNodesPage,
} from "./api/ontology-graph-api";
import type { GraphEdge, GraphNode } from "./api/ontology-graph-api";
import { fetchRegistryContent } from "./api/registry-api";
import { createGraphLoadProgress } from "./explorer/graphLoading";
import type { ApiEdge, ApiNode, GraphLoadProgress } from "./explorer/types";
// type-only：接缝类型定义在 vendored useLoadGraph（仅取类型，不拉运行时模块图）
import type {
  ExplorerFetchEdges,
  ExplorerFetchNodes,
} from "./explorer/useLoadGraph";

export function toExplorerNode(node: GraphNode): ApiNode {
  // EAI-CUSTOM(2026-10-01 domain_pattern 节点可读化): B 库规律行（dg_entities.etype=
  // "domain_pattern"）经 graph_entity 透镜投影，label=canonicalName（唯一 searchable 列），
  // 而蒸馏管道写入的 pattern_name 偶有截断/测试残留（_clip 拼 pattern_id、"bl230" 式样例名），
  // 画布上不可读。可读短语在 attrs JSONB 里（pattern_type/subject_name/object_name/pattern_desc），
  // 在取数接缝处改写 content 即可生效（useLoadGraph hydration: label ← node.content）——
  // 零后端改动、零 vendored 改动，画布/检索/详情三处同源受益。
  return {
    id: node.id,
    type: node.type,
    content: domainPatternLabel(node.properties) ?? node.label,
    properties: node.properties,
  };
}

// ── EAI-CUSTOM(2026-10-01 domain_pattern 节点可读化) ─────────────────────────

/**
 * attrs 宽容归一：现行投影里 attrs 已是解析后的对象（/graph/nodes 实测 2026-10-01），
 * 兼容历史字符串形态（旧 asyncpg 无 codec 时 jsonb 以文本透出）。非对象/解析失败 → null。
 */
export function normalizePatternAttrs(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value === "string" && value) {
    try {
      const parsed: unknown = JSON.parse(value);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // 非法 JSON：按无 attrs 处理，回退后端 label
    }
  }
  return null;
}

function patternAttrText(attrs: Record<string, unknown>, key: string): string {
  const value = attrs[key];
  return typeof value === "string" ? value.trim() : "";
}

function patternAttrCount(attrs: Record<string, unknown>, key: string): number | null {
  const value = attrs[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** domain_pattern 节点的画布可读标签（Subject→Object 中文短语优先，pattern_desc 截断兜底）。
 *
 * 组装序：`{pattern_type}：{subject_name}→{object_name}` → pattern_desc 前 32 字 → null。
 * 返回 null（非规律节点 / attrs 缺失 / 端点与描述全缺）时调用方保持后端 label 原样——
 * 后端 label = canonicalName，ingest 对规律行 canonical_name=norm_name 同值写入，即任务
 * 口径的 "fallback norm_name"。
 */
export function domainPatternLabel(
  properties: Record<string, unknown> | undefined | null,
): string | null {
  if (!properties || properties.etype !== "domain_pattern") {
    return null;
  }
  const attrs = normalizePatternAttrs(properties.attrs);
  if (!attrs) {
    return null;
  }
  const subject = patternAttrText(attrs, "subject_name");
  const object = patternAttrText(attrs, "object_name");
  const type = patternAttrText(attrs, "pattern_type");
  if (subject && object) {
    return `${type ? `${type}：` : ""}${subject}→${object}`;
  }
  const desc = patternAttrText(attrs, "pattern_desc");
  if (desc) {
    return desc.length > 32 ? `${desc.slice(0, 31)}…` : desc;
  }
  return null;
}

/** 结构化卡片取字段（DetailPanel 与标签组装共用同一形状认知）。 */
export function patternAttr(
  attrs: Record<string, unknown>,
  key: string,
): { text: string; count: number | null } {
  return { text: patternAttrText(attrs, key), count: patternAttrCount(attrs, key) };
}

export function toExplorerEdge(edge: GraphEdge): ApiEdge {
  return {
    id: `${edge.source}->${edge.target}#${edge.type}`,
    familyId: edge.type,
    source: edge.source,
    target: edge.target,
    type: edge.type,
    // EAI-CUSTOM(2026-09-30): 权重 25 → 边宽 sqrt(25)*0.2+0.22 ≈ 1.22px——语义关系边必须肉眼可见
    weight: 25,
    properties: {
      label: edge.label,
      // EAI-CUSTOM(2026-09-30 关系折叠边): flat 边携带关系行 id 供溯源；default 边无此字段
      ...(edge.relation_pk != null ? { relation_pk: edge.relation_pk } : {}),
    },
  };
}

function yieldToMain(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

// EAI-CUSTOM(2026-09-30 谓词中文标注): eia.yaml 的 "# 谓词中文标注: xxx=中文" 注释块是
// 唯一真源（与后端 llm_extract.load_enums 同源解析），用户规则=本体英文必有对应中文。
// 边标签优先中文，标注缺失/接口不可达时回退英文谓词值；模块级缓存一次。
// EAI-CUSTOM(2026-10-01): DetailPanel 规律卡片复用（导出）——谓词/实体类型中文标注同源。
let predicateLabelCache: Map<string, string> | null = null;
export async function getPredicateLabels(): Promise<Map<string, string>> {
  if (predicateLabelCache) {
    return predicateLabelCache;
  }
  const map = new Map<string, string>();
  try {
    const content = await fetchRegistryContent("eia.yaml");
    for (const m of (content.raw ?? "").matchAll(/# 谓词中文标注: (.+)/g)) {
      const line = m[1];
      if (!line) {
        continue;
      }
      for (const pair of line.trim().split(/\s+/)) {
        const eq = pair.indexOf("=");
        if (eq > 0) {
          map.set(pair.slice(0, eq), pair.slice(eq + 1));
        }
      }
    }
  } catch {
    // 标注不可达：保持空表，回退英文谓词值
  }
  predicateLabelCache = map;
  return map;
}

/** EAI-CUSTOM(2026-10-01 domain_pattern): 复合谓词值 → 中文标注串——按 +/、 拆段逐段映射，
 *  未命中段保持原文（不猜）。如 "emitted_as+treated_by" → "排放污染物+经治理"。 */
export function localizePredicate(value: string, labels: Map<string, string>): string {
  const segments = value
    .split(/[+、]/)
    .map((segment) => segment.trim())
    .filter(Boolean);
  if (!segments.length) {
    return value;
  }
  return segments.map((segment) => labels.get(segment) ?? segment).join("+");
}

/** EAI-CUSTOM(2026-10-01 domain_pattern): eia 域 etype → 中文类目标注（结构化真源 =
 *  registry-content summary 的 classes[].etypes/label，同 eia.yaml；不解析注释块）。
 *  规律卡片 subject_etype/object_etype 显示用。 */
export async function fetchEiaEtypeLabels(): Promise<Map<string, string>> {
  const content = await fetchRegistryContent("eia.yaml");
  const map = new Map<string, string>();
  for (const cls of content.summary?.domains?.eia?.classes ?? []) {
    for (const etype of cls.etypes ?? []) {
      map.set(etype, cls.label);
    }
  }
  return map;
}

/** EAI-CUSTOM(2026-10-02 谓词中文标注, 建模器 P1): registry YAML「# 谓词中文标注: k=v …」
 *  注释块 → 标签 map。标注维护在 YAML 注释（eia.yaml 全量 37 谓词），无结构化字段——正则抽取。 */
export async function fetchPredicateLabels(file: string): Promise<Map<string, string>> {
  const content = await fetchRegistryContent(file);
  const map = new Map<string, string>();
  for (const m of content.raw.matchAll(/谓词中文标注[：:](.+)/g)) {
    for (const pair of (m[1] ?? "").trim().split(/\s+/)) {
      const eq = pair.indexOf("=");
      if (eq > 0) map.set(pair.slice(0, eq), pair.slice(eq + 1));
    }
  }
  return map;
}

/** EAI-CUSTOM(2026-09-29 图谱投影域过滤): domain 非空 → /graph/* 带 domain= 服务端过滤；
 *  取数器随域重建（调用方 useMemo 依赖域），切域即换一组 fetchers。 */
export function makeExplorerFetchers(domain = ""): {
  fetchNodes: ExplorerFetchNodes;
  fetchEdges: ExplorerFetchEdges;
} {
  const fetchNodes: ExplorerFetchNodes = async (signal, onProgress) => {
    let cursor: string | null = null;
    const collected: ApiNode[] = [];

    while (true) {
      const page = await fetchNodesPage(cursor, { signal, domain: domain || undefined });
      if (!page.nodes.length) {
        break;
      }
      collected.push(...page.nodes.map(toExplorerNode));
      onProgress?.(progressNodes(collected.length));
      if (!page.next_cursor) {
        break;
      }
      cursor = page.next_cursor;
      await yieldToMain();
    }

    return collected;
  };

  const fetchEdges: ExplorerFetchEdges = async (
    signal,
    nodeIds,
    nodeProgress,
    onProgress,
  ) => {
    let cursor: string | null = null;
    const collected: ApiEdge[] = [];
    const seenEdgeIds = new Set<string>();
    const predicateLabels = await getPredicateLabels();

    while (true) {
      // EAI-CUSTOM(2026-09-30 关系折叠边): mode=flat —— 关系折叠为实体间带谓词标签的连线
      const page = await fetchEdgesPage(cursor, { signal, domain: domain || undefined, mode: "flat" });
      if (!page.edges.length) {
        break;
      }
      for (const edge of page.edges) {
        const mapped = toExplorerEdge(edge);
        // EAI-CUSTOM(2026-09-30): 边标签优先谓词中文（标注真源=eia.yaml 注释块），回退英文谓词值
        const zh = predicateLabels.get(edge.type);
        if (zh) {
          mapped.properties.label = zh;
        }
        if (!nodeIds.has(mapped.source) || !nodeIds.has(mapped.target)) {
          continue;
        }
        if (seenEdgeIds.has(mapped.id)) {
          continue;
        }
        seenEdgeIds.add(mapped.id);
        collected.push(mapped);
      }
      onProgress?.(progressEdges(seenEdgeIds.size, nodeProgress));
      if (!page.next_cursor) {
        break;
      }
      cursor = page.next_cursor;
      await yieldToMain();
    }

    return collected;
  };

  return { fetchNodes, fetchEdges };
}

function progressNodes(loaded: number): GraphLoadProgress {
  return createGraphLoadProgress({
    phase: "fetching_nodes",
    progressKind: "indeterminate",
    loaded,
    total: null,
    nodesLoaded: loaded,
    nodesTotal: null,
    edgesLoaded: 0,
    edgesTotal: null,
    message: `Loading nodes ${loaded.toLocaleString()}`,
  });
}

function progressEdges(
  loaded: number,
  nodeProgress: { loaded: number; total: number | null },
): GraphLoadProgress {
  return createGraphLoadProgress({
    phase: "fetching_edges",
    progressKind: "indeterminate",
    loaded,
    total: null,
    nodesLoaded: nodeProgress.loaded,
    nodesTotal: nodeProgress.total,
    edgesLoaded: loaded,
    edgesTotal: null,
    message: `Loading edges ${loaded.toLocaleString()}`,
  });
}
