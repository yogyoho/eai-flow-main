"use client";

import { Clock, Plane, RefreshCw, TrendingUp, Users, Wallet } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { clearSalesCache } from "@/extensions/sales-personnel/api";
import { ChartCard } from "@/extensions/sales-personnel/components/ChartCard";
import { StatCard } from "@/extensions/sales-personnel/components/StatCard";
import { TechTooltip } from "@/extensions/sales-personnel/components/TechTooltip";
import { useAttendanceSummary, useDeptTravel, useHrKpi, useReimburseStatus } from "@/extensions/sales-personnel/hooks";

// EAI-CUSTOM · dataviz: 调色板经 scripts/validate_palette.js 校验(CVD ΔE≥8),非凭眼选。
// ponytail: chart 标记用 light 模式字面 hex,不随 data-theme 切换(与 bid-quote/biz-pipeline 一致)。
// 分类色板 slots 1-4(出勤/出差/请假/缺勤)—— PASS light+dark。
const C_BLUE = "#2a78d6"; // slot1 出勤 / 差旅总额
const C_ORANGE = "#eb6834"; // slot2 出差
const C_AQUA = "#1baf7a"; // slot3 请假
const C_YELLOW = "#eda100"; // slot4 缺勤
// 报销状态 = status 语义(非分类):good/warning/critical。配直接标签满足 relief。
const S_GOOD = "#0ca30c"; // approved
const S_WARN = "#fab219"; // pending
const S_CRIT = "#d03b3b"; // rejected

// dataviz chrome:后退的网格/轴线(弱化到次要),数值用 tabular-nums 对齐。
const GRID = "rgba(11,11,11,0.06)";
const AXIS_FILL = "#898781";
const TICK = { fontSize: 11, fill: AXIS_FILL, fontFamily: "inherit" } as const;
const TABULAR = { fontVariantNumeric: "tabular-nums" } as const;
const CURSOR = { fill: "rgba(42,120,214,0.08)" } as const;

const STATUS_META: Record<string, { label: string; color: string }> = {
  approved: { label: "已审批", color: S_GOOD },
  pending: { label: "待审批", color: S_WARN },
  rejected: { label: "已驳回", color: S_CRIT },
};

// 考勤构成图例(分类色板 slots1-4,固定顺序):[名称, 色]
const ATT_LEGEND: Array<[string, string]> = [
  ["出勤", C_BLUE],
  ["出差", C_ORANGE],
  ["请假", C_AQUA],
  ["缺勤", C_YELLOW],
];

// Decimal/numeric 列经 JSON 序为 string;recharts 需 number → 统一转。
const toNum = (v: string | null | undefined): number => (v === null || v === undefined ? 0 : Number(v));
function wan(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const refresh = () => {
    clearSalesCache();
    setTick((t) => t + 1);
  };

  const kpiQ = useHrKpi();
  const attQ = useAttendanceSummary();
  const travelQ = useDeptTravel();
  const reimbQ = useReimburseStatus();

  const k = kpiQ.data?.[0];

  // 各部门考勤构成(堆叠 出勤/出差/请假/缺勤,单位天)
  const attData = (attQ.data ?? []).map((r) => ({
    department: r.department,
    出勤: r.present_days,
    出差: r.trip_days,
    请假: r.leave_days,
    缺勤: r.absent_days,
  }));
  // 部门差旅总额(万)—— 单色实心柱,柱顶直接标值
  const travelData = (travelQ.data ?? []).map((r) => {
    const w = (toNum(r.total_amount) / 10000).toFixed(1);
    return { department: r.department, 金额: Number(w), 金额label: `${w}万` };
  });
  // 报销状态构成(笔数)+ 总笔数 / 占比
  const reimbRows = reimbQ.data ?? [];
  const reimbTotal = reimbRows.reduce((s, r) => s + r.cnt, 0);
  const reimbData = reimbRows.map((r) => {
    const meta = STATUS_META[r.reimburse_status] ?? { label: r.reimburse_status, color: C_BLUE };
    return {
      id: r.reimburse_status,
      name: meta.label,
      value: r.cnt,
      color: meta.color,
      pct: reimbTotal > 0 ? (r.cnt / reimbTotal) * 100 : 0,
    };
  });

  return (
    <div key={tick} className="space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-lg border border-primary/30 bg-primary/10 p-1 text-primary">
            <Users className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">销售人员</h1>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={kpiQ.isFetching}>
          <RefreshCw className={kpiQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          刷新
        </Button>
      </div>

      {/* KPI 行(5 卡) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard
          label="在岗员工"
          value={k?.active_count ?? "—"}
          hint={`共 ${k?.employee_total ?? "—"} 人 · 离职 ${k?.resigned_count ?? "—"}`}
          icon={Users}
          color="primary"
        />
        <StatCard label="全员出勤率" value={k ? `${k.attendance_rate}%` : "—"} icon={TrendingUp} color="chart3" />
        <StatCard label="差旅总额" value={k ? wan(k.travel_total) : "—"} icon={Plane} color="chart2" />
        <StatCard label="待审批笔数" value={k?.pending_count ?? "—"} icon={Clock} color="chart5" />
        <StatCard label="待审批金额" value={k ? wan(k.pending_amount) : "—"} icon={Wallet} color="destructive" />
      </div>

      {/* 图表 3 张 */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {/* 图1:各部门考勤构成(堆叠,分类色板 slots1-4) */}
        <ChartCard title="各部门考勤构成 · 出勤/出差/请假/缺勤(天)" meta="团队纪律">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={attData} margin={{ top: 10, right: 12, left: -12, bottom: 0 }} barCategoryGap="28%">
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="department"
                tick={{ ...TICK, fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
              />
              <YAxis tick={{ ...TICK, ...TABULAR }} tickLine={false} axisLine={false} width={36} />
              <Tooltip content={<TechTooltip unit="天" />} cursor={CURSOR} />
              <Bar dataKey="出勤" stackId="a" fill={C_BLUE} isAnimationActive animationDuration={700} />
              <Bar dataKey="出差" stackId="a" fill={C_ORANGE} isAnimationActive animationDuration={700} />
              <Bar dataKey="请假" stackId="a" fill={C_AQUA} isAnimationActive animationDuration={700} />
              <Bar dataKey="缺勤" stackId="a" fill={C_YELLOW} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} />
            </BarChart>
          </ResponsiveContainer>
          {/* 自定义图例:色点 + 名称(分类色板,色随身份不随取值) */}
          <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
            {ATT_LEGEND.map(([label, color]) => (
              <span key={label} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </ChartCard>

        {/* 图2:部门差旅总额(万)—— 单色实心柱,柱顶直接标值 */}
        <ChartCard title="部门差旅总额(万)" meta="费用去向">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={travelData} margin={{ top: 18, right: 12, left: -12, bottom: 0 }} barCategoryGap="32%">
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="department" tick={{ ...TICK, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
              <YAxis tick={{ ...TICK, ...TABULAR }} tickLine={false} axisLine={false} width={40} />
              <Tooltip content={<TechTooltip unit="万" />} cursor={CURSOR} />
              <Bar dataKey="金额" name="金额(万)" fill={C_BLUE} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={700} maxBarSize={64}>
                <LabelList
                  dataKey="金额label"
                  position="top"
                  style={{ ...TICK, ...TABULAR, fontSize: 11, fontWeight: 600, fill: AXIS_FILL }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图3:报销状态构成(饼)—— status 色 + 中心总数 + 侧栏直接标签(pen/count/%) */}
        <ChartCard title="报销状态构成 · 笔数占比" meta="审批预警" className="xl:col-span-2">
          <div className="flex flex-col items-center gap-6 py-2 sm:flex-row sm:justify-center sm:gap-10">
            {/* donut + 中心总数 */}
            <div className="relative h-[230px] w-[230px] shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={reimbData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={98}
                    innerRadius={66}
                    paddingAngle={2}
                    stroke="none"
                    isAnimationActive
                    animationDuration={700}
                  >
                    {reimbData.map((d) => (
                      <Cell key={d.id} fill={d.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<TechTooltip unit="笔" />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold tabular-nums text-foreground">{reimbTotal}</span>
                <span className="mt-0.5 text-xs text-muted-foreground">报销单 · 笔</span>
              </div>
            </div>
            {/* 侧栏直接标签:status 色点 + 名称 + 笔数 + 占比条(relief:status 色从不单独承载含义) */}
            <div className="w-full max-w-xs space-y-3">
              {reimbData.map((d) => (
                <div key={d.id}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 text-foreground">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: d.color }} />
                      {d.name}
                    </span>
                    <span className="tabular-nums text-muted-foreground">
                      {d.value} 笔 · {d.pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full" style={{ width: `${d.pct}%`, background: d.color }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
