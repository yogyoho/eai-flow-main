"use client";

import { Clock, Plane, RefreshCw, TrendingUp, Users, Wallet } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
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

// EAI-CUSTOM: 项目 chart CSS 变量为完整颜色(非 HSL 通道),故图表用字面 hex
const GRID = "rgba(100,116,139,0.22)";
const AXIS_FILL = "#94a3b8";
const AXIS = { fontSize: 11, fill: AXIS_FILL };
const CURSOR = { fill: "rgba(148,163,184,0.15)" };
const BLUE = "#3b82f6";
const AMBER = "#f6bd16";
const GREEN = "#10b981";
const RED = "#f43f5e";

const STATUS_LABEL: Record<string, string> = {
  approved: "已审批",
  pending: "待审批",
  rejected: "已驳回",
};
const STATUS_COLOR: Record<string, string> = {
  approved: GREEN,
  pending: AMBER,
  rejected: RED,
};

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
  // 部门差旅总额(万)
  const travelData = (travelQ.data ?? []).map((r) => ({
    department: r.department,
    金额: toNum(r.total_amount) / 10000,
  }));
  // 报销状态构成(笔数)
  const reimbData = (reimbQ.data ?? []).map((r) => ({
    name: STATUS_LABEL[r.reimburse_status] ?? r.reimburse_status,
    value: r.cnt,
    color: STATUS_COLOR[r.reimburse_status] ?? BLUE,
  }));

  return (
    <div key={tick} className="cyber-scope space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-sm border border-primary/30 bg-primary/10 p-1 text-primary">
            <Users className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold text-foreground text-shadow-glow">销售人员</h1>
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
        {/* 图1:各部门考勤构成(堆叠) */}
        <ChartCard title="各部门考勤构成 · 出勤/出差/请假/缺勤(天)" meta="团队纪律">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={attData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="department"
                tick={{ ...AXIS, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
                angle={-8}
                textAnchor="end"
                height={48}
              />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={36} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="出勤" stackId="a" fill={GREEN} isAnimationActive animationDuration={900} />
              <Bar dataKey="出差" stackId="a" fill={BLUE} isAnimationActive animationDuration={900} />
              <Bar dataKey="请假" stackId="a" fill={AMBER} isAnimationActive animationDuration={900} />
              <Bar dataKey="缺勤" stackId="a" fill={RED} radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图2:部门差旅总额(万) */}
        <ChartCard title="部门差旅总额(万)" meta="费用去向">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={travelData} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <defs>
                <linearGradient id="travelGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={BLUE} stopOpacity={0.95} />
                  <stop offset="100%" stopColor={BLUE} stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="department"
                tick={{ ...AXIS, fontSize: 10 }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                interval={0}
                angle={-8}
                textAnchor="end"
                height={48}
              />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={40} />
              <Tooltip content={<TechTooltip />} cursor={CURSOR} />
              <Bar
                dataKey="金额"
                name="金额(万)"
                fill="url(#travelGrad)"
                radius={[4, 4, 0, 0]}
                isAnimationActive
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图3:报销状态构成(饼) */}
        <ChartCard title="报销状态构成 · 笔数占比" meta="审批预警" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={reimbData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                innerRadius={48}
                isAnimationActive
                animationDuration={900}
              >
                {reimbData.map((d) => (
                  <Cell key={d.name} fill={d.color} />
                ))}
              </Pie>
              <Tooltip content={<TechTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
