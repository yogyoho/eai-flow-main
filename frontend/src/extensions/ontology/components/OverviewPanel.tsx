"use client";

/**
 * 语义地图概览面板 (EAI-CUSTOM, plan semantic-map v2 Task 3 Step 3.4).
 *
 * bid-quote 仪表盘风格（浅色定版——PAGE_BG 区块底 + 白卡，不随暗色主题，
 * 对照 bid-quote DashboardView 先例，原型即验收标准）。统计全部来自传入的
 * 图快照（stats.ts 纯函数），本组件不做取数；待复核实体计数由页面查询后
 * 以 pendingCount 传入（null → 显示 "—"）。
 */
import { Network } from "lucide-react";
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import {
  AXIS,
  BLUE,
  CARD,
  CARD_BORDER,
  CURSOR,
  GRID,
  INK,
  INK_3,
  PAGE_BG,
  truncateLabel,
} from "@/extensions/bid-quote/components/chartTheme";
import { StatCard } from "@/extensions/bid-quote/components/StatCard";
import {
  PENDING_REVIEW_LIMIT,
  type GraphEdge,
  type GraphNode,
} from "@/extensions/ontology/api/ontology-graph-api";
import {
  communitySizes,
  degreeTop,
  typeDistribution,
} from "@/extensions/ontology/stats";

const HUB_TOP_N = 10;
const HUB_LABEL_MAX = 12;

function shortLabel(label: string): string {
  return label.length > HUB_LABEL_MAX
    ? `${label.slice(0, HUB_LABEL_MAX)}…`
    : label;
}

interface OverviewPanelProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** status=pending_review 实体数；null = 查询不可用/失败（显示 "—"）。 */
  pendingCount: number | null;
  onGoResolution: () => void;
}

export function OverviewPanel({
  nodes,
  edges,
  pendingCount,
  onGoResolution,
}: OverviewPanelProps) {
  const typeDist = useMemo(() => typeDistribution(nodes), [nodes]);
  const hubs = useMemo(
    () => degreeTop(nodes, edges, HUB_TOP_N),
    [nodes, edges],
  );
  const communities = useMemo(
    () => communitySizes(nodes, edges),
    [nodes, edges],
  );

  if (nodes.length === 0 && edges.length === 0) {
    return (
      <div
        className="flex h-full items-center justify-center overflow-y-auto"
        data-testid="ontology-overview-panel"
        style={{ background: PAGE_BG }}
      >
        <div
          className="flex flex-col items-center gap-2"
          data-testid="overview-loading"
        >
          <Network className="h-6 w-6 animate-pulse" style={{ color: INK_3 }} />
          <p className="text-sm" style={{ color: INK_3 }}>
            图加载中，统计将在就绪后显示
          </p>
        </div>
      </div>
    );
  }

  const avgDegree = nodes.length > 0 ? (2 * edges.length) / nodes.length : 0;
  const hubData = hubs.map((entry) => ({
    name: shortLabel(entry.label),
    title: entry.label,
    value: entry.degree,
  }));
  const communityData = communities.map((entry) => ({
    name: `#${entry.community}`,
    title: `社区 #${entry.community}`,
    value: entry.size,
  }));

  return (
    <div
      className="h-full overflow-y-auto"
      data-testid="ontology-overview-panel"
    >
      <div
        className="space-y-6 p-6"
        style={{ background: PAGE_BG, minHeight: "100%" }}
      >
        {/* 页头 */}
        <div className="flex items-center gap-3">
          <Network className="h-5 w-5" style={{ color: BLUE }} />
          <h1 className="text-[22px] font-bold" style={{ color: INK }}>
            语义地图概览
          </h1>
        </div>

        {/* KPI 行 */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div data-testid="kpi-nodes">
            <StatCard
              label="节点总数"
              value={nodes.length}
              delta={`${typeDist.length} 种对象类型`}
            />
          </div>
          <div data-testid="kpi-edges">
            <StatCard
              label="边总数"
              value={edges.length}
              delta={`平均 ${avgDegree.toFixed(1)} 度/节点`}
            />
          </div>
          <div data-testid="kpi-communities">
            <StatCard
              label="社区数"
              value={communities.length}
              delta={`最大社区 ${communities[0]?.size ?? 0} 实体`}
            />
          </div>
          <button
            type="button"
            onClick={onGoResolution}
            title="前往实体消解"
            data-testid="kpi-pending"
            className="w-full cursor-pointer text-left transition-opacity hover:opacity-90"
          >
            <StatCard
              label="待复核实体"
              value={pendingCount ?? "—"}
              delta={
                pendingCount !== null && pendingCount >= PENDING_REVIEW_LIMIT
                  ? `已达拉取上限 ${PENDING_REVIEW_LIMIT}`
                  : undefined
              }
            />
          </button>
        </div>

        {/* 图表网格 */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <ChartCard
            title="对象类型分布"
            meta={`${typeDist.length} 种对象类型`}
          >
            <div data-testid="chart-type-distribution">
              <ResponsiveContainer width="100%" height={250}>
                <BarChart
                  data={typeDist}
                  margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
                >
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={AXIS}
                    tickLine={false}
                    axisLine={{ stroke: GRID }}
                    tickFormatter={truncateLabel}
                  />
                  <YAxis
                    tick={AXIS}
                    tickLine={false}
                    axisLine={false}
                    width={40}
                    allowDecimals={false}
                  />
                  <Tooltip
                    content={<CountTooltip unit="实体" />}
                    cursor={CURSOR}
                  />
                  <Bar
                    dataKey="count"
                    name="实体数"
                    fill={BLUE}
                    radius={[4, 4, 0, 0]}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          <ChartCard title="Hub 实体 Top 10" meta="按关联边数（入度 + 出度）">
            <div
              data-testid="chart-hub-top"
              className="max-h-[280px] overflow-y-auto pr-1"
            >
              <ResponsiveContainer
                width="100%"
                height={Math.max(hubData.length * 26 + 26, 120)}
              >
                <BarChart
                  data={hubData}
                  layout="vertical"
                  margin={{ top: 4, right: 12, left: 0, bottom: 0 }}
                >
                  <CartesianGrid stroke={GRID} horizontal={false} />
                  <XAxis
                    type="number"
                    tick={AXIS}
                    tickLine={false}
                    axisLine={{ stroke: GRID }}
                    allowDecimals={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ ...AXIS, fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={130}
                  />
                  <Tooltip
                    content={<CountTooltip unit="条边" />}
                    cursor={CURSOR}
                  />
                  <Bar
                    dataKey="value"
                    name="度数"
                    fill={BLUE}
                    radius={[0, 3, 3, 0]}
                    barSize={10}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>

          <ChartCard
            title="社区规模分布"
            meta={`Louvain 无向投影 · ${communities.length} 个社区`}
            className="xl:col-span-2"
          >
            <div data-testid="chart-community-size">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={communityData}
                  margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
                >
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={AXIS}
                    tickLine={false}
                    axisLine={{ stroke: GRID }}
                  />
                  <YAxis
                    tick={AXIS}
                    tickLine={false}
                    axisLine={false}
                    width={40}
                    allowDecimals={false}
                  />
                  <Tooltip
                    content={<CountTooltip unit="实体" />}
                    cursor={CURSOR}
                  />
                  <Bar
                    dataKey="value"
                    name="规模"
                    fill={BLUE}
                    radius={[4, 4, 0, 0]}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>
        </div>
      </div>
    </div>
  );
}

/** 通用计数 tooltip：title 全名（轴上截断的补全）+ 计数。 */
function CountTooltip(props: {
  active?: boolean;
  unit?: string;
  payload?: Array<{
    payload?: { title?: string; value?: number };
  }>;
}) {
  const data = props.payload?.[0]?.payload;
  if (!props.active || !data) return null;
  return (
    <div
      className="rounded-[10px] px-3 py-2 text-xs shadow-[0_4px_16px_rgba(0,0,0,0.08)]"
      style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
    >
      <p
        className="mb-1 max-w-[240px] leading-snug font-semibold"
        style={{ color: INK }}
      >
        {data.title}
      </p>
      <p className="[font-variant-numeric:tabular-nums]" style={{ color: INK }}>
        <b>{data.value?.toLocaleString()}</b> {props.unit ?? ""}
      </p>
    </div>
  );
}
