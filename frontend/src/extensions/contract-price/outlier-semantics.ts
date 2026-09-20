/**
 * EAI-CUSTOM F3a 离群语义分层 —— 整文档成片判定(纯函数,零 React 依赖)。
 *
 * 背景: is_outlier 是簇内 1.5×IQR 统计离群,但当「整份合同的基线就高于/低于
 * 全库」时,该合同同名簇里几乎全部行都会被标红——那是跨合同基线差异,不是
 * 单点价格异常。本模块在前端把这类「整文档成片红」降级为琥珀色(amber)
 * 「跨合同基线差异」语义;不满足成片条件的真散点行保持红色异常不变。
 *
 * 判定输入是后端预取的簇统计(cpa_items 行上的 cluster_median / deviation_pct /
 * cluster_doc_count,见 backend crud._attach_cluster_stats);本模块只读视图内
 * 已加载的行(分页近似),按 document_id 分组逐文档判定。阈值常量全部导出。
 */

import type { CpaItem } from "@/extensions/contract-price/types";

/** CpaItem → 判定行适配(ItemsView / ClustersView 共用)。 */
export function itemToStatRow(it: CpaItem): OutlierStatRow {
  return {
    id: it.id,
    documentId: it.document_id,
    isOutlier: it.is_outlier,
    unitPrice: it.unit_price,
    clusterMedian: it.cluster_median,
    deviationPct: it.deviation_pct,
    clusterId: it.cluster_id,
    contractNo: it.source_contract_no,
    clusterDocCount: it.cluster_doc_count,
  };
}

/** 规则一: 同文档 is_outlier 行占比 >= 该比例 → 整文档成片(0.6 = 60%)。 */
export const OUTLIER_DOC_RATIO_THRESHOLD = 0.6;

/** 规则二: 文档内 outlier 行单价中位相对簇中位的有符号偏离 >= 该比率 → 成片(0.1 = 10%)。 */
export const OUTLIER_DOC_DEVIATION_THRESHOLD = 0.1;

/** 成片佐证下限: 两条规则都要求文档内至少有这么多行离群佐证。
 * 单行离群(单行文档/散点高偏行)是散点异常,绝不是"片",必须保持红色。 */
export const OUTLIER_DOC_MIN_OUTLIERS = 2;

/** 行级离群语义: 红色异常散点 / 琥珀跨合同基线差异 / 正常。 */
export type OutlierTier = "outlier" | "baseline-shift" | "normal";

/** 判定输入行(组件行与后端明细行均按此形状适配)。 */
export interface OutlierStatRow {
  /** 行唯一键(ItemOut.id / goods_analysis 明细 id)。 */
  id: string;
  /** 所属文档 id——成片按文档分组判定。 */
  documentId: string;
  isOutlier: boolean;
  unitPrice: number | null;
  /** 后端预取的簇中位(ok/corrected 单价);无簇/缺失为 null。 */
  clusterMedian: number | null;
  /** 后端预取的有符号偏离比率;缺省时由 unitPrice/clusterMedian 现算。 */
  deviationPct?: number | null;
  /** 簇 id——tooltip 的「各文档基线概览」按同簇分桶。 */
  clusterId?: string | null;
  /** 合同编号——tooltip 概览展示用。 */
  contractNo?: string | null;
  /** 后端预取的簇内文档数(簇横跨几份合同)。 */
  clusterDocCount?: number | null;
}

/** 单文档成片判定画像(诊断/单测可见的中间量)。 */
export interface DocOutlierProfile {
  /** 该文档在当前视图内的总行数。 */
  totalRows: number;
  /** 其中 is_outlier 行数。 */
  outlierCount: number;
  /** outlier 行占比(总行数为 0 时为 0)。 */
  outlierRatio: number;
  /** outlier 行偏离比率的中位(有符号;无可算偏离时为 null)。 */
  deviationMedian: number | null;
  /** 参与偏离中位的样本行数。 */
  deviationSamples: number;
  /** 整文档成片(两规则任一命中)。 */
  isBaselineShift: boolean;
}

/** 数值中位(升序取中;偶数取中间两数均值)。空数组返回 null。 */
export function medianOf(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  const hi = s[mid] ?? 0;
  const lo = s[mid - 1] ?? 0;
  return s.length % 2 === 1 ? hi : (lo + hi) / 2;
}

/** 单行有符号偏离比率: 优先后端 deviation_pct,否则由单价/簇中位现算;
 * 两者都不可得(无价/无簇中位/中位为 0)返回 null。 */
export function rowDeviationPct(row: OutlierStatRow): number | null {
  if (row.deviationPct != null) return row.deviationPct;
  if (row.unitPrice == null || row.clusterMedian == null || row.clusterMedian === 0) return null;
  return (row.unitPrice - row.clusterMedian) / row.clusterMedian;
}

/**
 * 单文档成片判定(规则任一命中即成片):
 *  规则一  ratio:  outlier 行数 >= MIN_OUTLIERS 且 占比 >= 0.60;
 *  规则二  deviation: outlier 行偏离比率样本 >= MIN_OUTLIERS 且 中位绝对值 >= 0.10。
 * 规则二对「outlier 行单位价中位 vs 簇中位」的严格读法在单簇场景下与
 * 「逐行偏离取中位」等价(单调变换),跨簇时按各自簇中位归一再取中位,更稳。
 */
export function docOutlierProfile(docRows: OutlierStatRow[]): DocOutlierProfile {
  const totalRows = docRows.length;
  const outlierRows = docRows.filter((r) => r.isOutlier);
  const outlierCount = outlierRows.length;
  const outlierRatio = totalRows > 0 ? outlierCount / totalRows : 0;
  const deviations = outlierRows
    .map(rowDeviationPct)
    .filter((v): v is number => v != null);
  const deviationMedian = medianOf(deviations);

  const ratioTrigger =
    outlierCount >= OUTLIER_DOC_MIN_OUTLIERS && outlierRatio >= OUTLIER_DOC_RATIO_THRESHOLD;
  const deviationTrigger =
    deviations.length >= OUTLIER_DOC_MIN_OUTLIERS &&
    deviationMedian != null &&
    Math.abs(deviationMedian) >= OUTLIER_DOC_DEVIATION_THRESHOLD;

  return {
    totalRows,
    outlierCount,
    outlierRatio,
    deviationMedian,
    deviationSamples: deviations.length,
    isBaselineShift: ratioTrigger || deviationTrigger,
  };
}

/** 对一批行按文档分组成片判定,返回判定为「跨合同基线差异」的 document_id 集合。 */
export function baselineShiftDocIds(rows: OutlierStatRow[]): Set<string> {
  const byDoc = new Map<string, OutlierStatRow[]>();
  for (const r of rows) {
    const bucket = byDoc.get(r.documentId);
    if (bucket) bucket.push(r);
    else byDoc.set(r.documentId, [r]);
  }
  const hits = new Set<string>();
  for (const [docId, docRows] of byDoc) {
    if (docOutlierProfile(docRows).isBaselineShift) hits.add(docId);
  }
  return hits;
}

/** 单行离群语义分层: 非离群=normal;离群且其文档成片=baseline-shift;否则=outlier(红)。 */
export function rowOutlierTier(
  row: Pick<OutlierStatRow, "documentId" | "isOutlier"> | Pick<CpaItem, "document_id" | "is_outlier">,
  baselineDocs: Set<string>,
): OutlierTier {
  const docId = "documentId" in row ? row.documentId : row.document_id;
  const outlier = "documentId" in row ? !!row.isOutlier : !!row.is_outlier;
  if (!outlier) return "normal";
  return baselineDocs.has(docId) ? "baseline-shift" : "outlier";
}

function formatSignedPct(v: number): string {
  const pct = v * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

/**
 * 为视图内全部「成片文档的离群行」生成行 id → tooltip 文案 的映射。
 * 文案(任务 F3a 规定): 该合同基线高于/低于全库同名录簇中位 X%,簇内含 N 份
 * 合同: [各文档基线概览]。概览 = 同簇各文档(视图内)相对簇中位的偏离中位。
 * 非成片文档不产生 tooltip(保持红色异常,无降级说明)。
 */
export function buildBaselineTooltips(rows: OutlierStatRow[]): Map<string, string> {
  const byDoc = new Map<string, OutlierStatRow[]>();
  for (const r of rows) {
    const bucket = byDoc.get(r.documentId);
    if (bucket) bucket.push(r);
    else byDoc.set(r.documentId, [r]);
  }

  const out = new Map<string, string>();
  for (const [docId, docRows] of byDoc) {
    const profile = docOutlierProfile(docRows);
    if (!profile.isBaselineShift) continue;

    // 目标簇 = 该文档离群行里第一个可用的簇 id(单簇常态;跨簇取主导簇近似)。
    const targetCluster = docRows.find((r) => r.isOutlier && r.clusterId)?.clusterId ?? null;

    // N = 后端预取的簇内文档数;缺失时回退为视图内同簇文档数。
    const backendDocCount = docRows.find(
      (r) => r.isOutlier && r.clusterDocCount != null,
    )?.clusterDocCount;

    // 各文档基线概览: 同簇(视图内)每文档「全部行偏离中位」(无可算偏离的行跳过)。
    const clusterRows = targetCluster ? rows.filter((r) => r.clusterId === targetCluster) : [];
    const docsInCluster = new Set(clusterRows.map((r) => r.documentId));
    const overview: string[] = [];
    for (const cid of docsInCluster) {
      const docAll = clusterRows.filter((r) => r.documentId === cid);
      const devs = docAll.map(rowDeviationPct).filter((v): v is number => v != null);
      if (devs.length === 0) continue;
      const med = medianOf(devs) as number;
      const label = docAll[0]?.contractNo || `${cid.slice(0, 8)}…`;
      overview.push(`${label} ${formatSignedPct(med)}`);
    }

    const dev = profile.deviationMedian;
    const head =
      dev != null
        ? `该合同基线${dev > 0 ? "高于" : "低于"}全库同名录簇中位 ${Math.abs(dev * 100).toFixed(1)}%`
        : `该合同同名簇存在整批基线差异`;
    const n = backendDocCount ?? docsInCluster.size;
    const parts = [head, `簇内含 ${n} 份合同`];
    if (overview.length > 0) parts.push(overview.join("、"));
    const tooltip = `跨合同基线差异: ${parts.join(", ")}`;

    for (const r of docRows) {
      if (r.isOutlier) out.set(r.id, tooltip);
    }
  }
  return out;
}
