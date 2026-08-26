"use client";

import { ChevronDown, RefreshCw, Users } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { clearSalesCache } from "@/extensions/sales-personnel/api";
import { ChartCard } from "@/extensions/sales-personnel/components/ChartCard";
import {
  ACCENT_SOFT,
  AMBER,
  AXIS,
  AXIS_FILL,
  BLUE,
  CARD,
  CARD_BORDER,
  CURSOR,
  GRID,
  INK,
  INK_2,
  INK_3,
  LEAVE,
  ORANGE,
  PAGE_BG,
  RED,
} from "@/extensions/sales-personnel/components/chartTheme";
import { SectionCard } from "@/extensions/sales-personnel/components/SectionCard";
import { Emph, StatCard } from "@/extensions/sales-personnel/components/StatCard";
import { TechTooltip } from "@/extensions/sales-personnel/components/TechTooltip";
import {
  useAttendanceSummary,
  useDeptTravel,
  useEmployeeDetail,
  useReimburseDept,
} from "@/extensions/sales-personnel/hooks";
import { cn } from "@/lib/utils";

// EAI-CUSTOM · dataviz: 2026-08-18 人员总览仪表盘重构(原型即验收标准:
// docs/superpowers/specs/2026-08-18-sales-personnel-dashboard-prototype.html)。
// 浅色单主题不随暗色切换;部门单选筛选全页联动(KPI/图/表客户端重算,61 行量级无需服务端分页)。
// 调色:出勤蓝/出差橙/请假中性蓝灰(低彩度,靠图例+tooltip+数据表兜底)/缺勤红;
// 待审批用琥珀非橙(橙+红对 CVD 不可分)。house 组件克隆自 biz-pipeline,不跨模块 import。
// ponytail: 图表标记用 light 模式字面 hex,与 bid-quote/biz-pipeline 一致。

const DEPT_ORDER = [
  "销售一部",
  "销售二部",
  "技术支持部",
  "市场部",
  "研发部",
  "生产部",
  "采购部",
  "产品部",
  "质量部",
  "行政部",
  "人力资源部",
  "财务部",
];
const FLAT_DEPTS = DEPT_ORDER.slice(0, 5); // 业务线部门平铺
const MORE_DEPTS = DEPT_ORDER.slice(5); // 职能部门收进「更多」下拉

/** 考勤四段(固定顺序,色随身份不随筛选重绘)。 */
const ATT_SEGS = [
  { key: "present_days", name: "出勤", color: BLUE },
  { key: "trip_days", name: "出差", color: ORANGE },
  { key: "leave_days", name: "请假", color: LEAVE },
  { key: "absent_days", name: "缺勤", color: RED },
] as const;

const STATUS_META: Record<"approved" | "pending" | "rejected", { label: string; color: string }> = {
  approved: { label: "已审批", color: BLUE },
  pending: { label: "待审批", color: AMBER },
  rejected: { label: "已驳回", color: RED },
};

// Decimal/numeric 列经 JSON 序列化为 string;recharts 需 number → 统一转。
const toNum = (v: string | null | undefined): number => (v === null || v === undefined ? 0 : Number(v));
const fmt1 = (n: number) => n.toFixed(1);
const fmt2 = (n: number) => n.toFixed(2);
const LABEL_STYLE = { fontSize: 11, fontWeight: 600, fill: INK_2, fontVariantNumeric: "tabular-nums" } as const;

type RateRow = { department: string; rate: number; emp: number };

/** 点图标记:蓝点白描边 + 右侧直标率值(文本用次级墨色,色不承载文字)。 */
const dotShape = (p: { cx?: number; cy?: number; payload?: RateRow }) => {
  const cx = p.cx ?? 0;
  const cy = p.cy ?? 0;
  return (
    <g>
      <circle cx={cx} cy={cy} r={5.5} fill={BLUE} stroke="#fff" strokeWidth={2} />
      <text x={cx + 11} y={cy + 3.5} fontSize={11} fontWeight={600} fill={INK_2} style={{ fontVariantNumeric: "tabular-nums" }}>
        {fmt1(p.payload?.rate ?? 0)}%
      </text>
    </g>
  );
};

/** 筛选 chip(选中 = 主蓝浅底 + 600 字重)。 */
function Chip({ on, onClick, children }: { on?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg border px-2.5 py-1 text-[12.5px] whitespace-nowrap transition-colors",
        !on && "hover:border-black/20 hover:text-[#1b1c1d]",
      )}
      style={{
        background: on ? ACCENT_SOFT : CARD,
        borderColor: on ? "transparent" : CARD_BORDER,
        color: on ? BLUE : INK_2,
        fontWeight: on ? 600 : 400,
      }}
    >
      {children}
    </button>
  );
}

function PagerBtn({
  children,
  on,
  disabled,
  onClick,
}: {
  children: ReactNode;
  on?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "h-[26px] min-w-[26px] rounded-[7px] border px-1.5 text-xs [font-variant-numeric:tabular-nums] transition-colors",
        disabled ? "cursor-default opacity-35" : "hover:border-black/20",
      )}
      style={{
        background: on ? ACCENT_SOFT : CARD,
        borderColor: on ? "transparent" : CARD_BORDER,
        color: on ? BLUE : INK_2,
        fontWeight: on ? 600 : 400,
      }}
    >
      {children}
    </button>
  );
}

interface PagedCell {
  v: ReactNode;
  red?: boolean;
}

/** 分页表格(dataviz 表格孪生;行数 ≤ 百级,组件内 state 分页)。 */
function PagedTable({ head, rows, pageSize }: { head: string[]; rows: PagedCell[][]; pageSize: number }) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const cur = Math.min(page, pages); // 筛选切走后页码钳回有效区间
  const slice = rows.slice((cur - 1) * pageSize, cur * pageSize);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs tracking-normal [font-variant-numeric:tabular-nums]">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th
                key={h}
                className={cn("border-b px-2 py-[5px] font-medium whitespace-nowrap", i === 0 ? "text-left" : "text-right")}
                style={{ color: INK_3, borderColor: GRID }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slice.map((r, ri) => (
            <tr key={ri}>
              {r.map((c, ci) => (
                <td
                  key={ci}
                  className={cn("border-b px-2 py-[5px] whitespace-nowrap", ci === 0 ? "text-left" : "text-right")}
                  style={{ color: c.red ? RED : INK_2, borderColor: GRID, fontWeight: c.red ? 500 : undefined }}
                >
                  {c.v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pages > 1 ? (
        <div className="mt-2 flex items-center justify-between gap-3 text-xs" style={{ color: INK_3 }}>
          <span>
            共 {rows.length} 条 · {cur}/{pages} 页
          </span>
          <span className="flex gap-1">
            <PagerBtn disabled={cur === 1} onClick={() => setPage(cur - 1)}>
              ‹
            </PagerBtn>
            {Array.from({ length: pages }, (_, i) => (
              <PagerBtn key={i + 1} on={i + 1 === cur} onClick={() => setPage(i + 1)}>
                {i + 1}
              </PagerBtn>
            ))}
            <PagerBtn disabled={cur === pages} onClick={() => setPage(cur + 1)}>
              ›
            </PagerBtn>
          </span>
        </div>
      ) : (
        <p className="mt-2 text-xs" style={{ color: INK_3 }}>
          共 {rows.length} 条
        </p>
      )}
    </div>
  );
}

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const [dept, setDept] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);

  const att = useAttendanceSummary();
  const trav = useDeptTravel();
  const reimb = useReimburseDept();
  const emp = useEmployeeDetail();

  const refresh = () => {
    clearSalesCache();
    setTick((t) => t + 1); // key 变更整树重挂,分页状态一并复位
  };

  // —— 筛选(部门单选;null=全部)。KPI/图/表全部客户端重算,量级 ≤ 百行。 ——
  const attRows = useMemo(() => {
    const rows = (att.data ?? []).filter((r) => !dept || r.department === dept);
    return [...rows].sort((a, b) => DEPT_ORDER.indexOf(a.department) - DEPT_ORDER.indexOf(b.department));
  }, [att.data, dept]);
  const empRows = useMemo(() => (emp.data ?? []).filter((r) => !dept || r.department === dept), [emp.data, dept]);
  const travRows = useMemo(() => (trav.data ?? []).filter((r) => !dept || r.department === dept), [trav.data, dept]);
  const reimbRows = useMemo(() => (reimb.data ?? []).filter((r) => !dept || r.department === dept), [reimb.data, dept]);

  // —— KPI 聚合(全选 = 全公司;选中部门 = 单部门重算)。 ——
  const S = useMemo(() => {
    const n = empRows.length;
    const resigned = empRows.filter((r) => r.status !== "active").length;
    const pre = empRows.reduce((a, r) => a + r.present_days, 0);
    const days = empRows.reduce((a, r) => a + r.present_days + r.trip_days + r.leave_days + r.absent_days, 0);
    const rate = days > 0 ? Math.round((1000 * pre) / days) / 10 : 0;
    const amt = travRows.reduce((a, r) => a + toNum(r.total_amount), 0);
    const trips = travRows.reduce((a, r) => a + r.trip_count, 0);
    const tc = travRows.reduce((a, r) => a + r.traveler_count, 0);
    return { n, resigned, rate, amt, trips, tc };
  }, [empRows, travRows]);

  const R = useMemo(() => {
    const g = { approved: { cnt: 0, amt: 0 }, pending: { cnt: 0, amt: 0 }, rejected: { cnt: 0, amt: 0 } };
    for (const r of reimbRows) {
      const s = g[r.reimburse_status];
      if (s) {
        s.cnt += r.cnt;
        s.amt += toNum(r.total_amount);
      }
    }
    const total = g.approved.amt + g.pending.amt + g.rejected.amt;
    const cnt = g.approved.cnt + g.pending.cnt + g.rejected.cnt;
    return { g, total, cnt };
  }, [reimbRows]);

  const reimbAgg = useMemo(
    () =>
      (["approved", "pending", "rejected"] as const).map((st) => ({
        id: st,
        name: STATUS_META[st].label,
        color: STATUS_META[st].color,
        cnt: R.g[st].cnt,
        amt: R.g[st].amt,
        value: R.g[st].amt / 10000,
        pct: R.total > 0 ? Math.round((1000 * R.g[st].amt) / R.total) / 10 : 0,
      })),
    [R],
  );

  // —— 图数据。 ——
  const attData = useMemo(
    () =>
      attRows.map((r) => {
        const total = r.present_days + r.trip_days + r.leave_days + r.absent_days;
        const p = (v: number) => (total > 0 ? Math.round((1000 * v) / total) / 10 : 0);
        return {
          ...r,
          label: `${r.department} ·${r.emp_count}人`,
          pp: p(r.present_days),
          tp: p(r.trip_days),
          lp: p(r.leave_days),
          ap: p(r.absent_days),
          rateLabel: `${fmt1(toNum(r.attendance_rate))}%`,
        };
      }),
    [attRows],
  );

  const rateData = useMemo(
    () =>
      [...attRows]
        .sort((a, b) => toNum(b.attendance_rate) - toNum(a.attendance_rate))
        .map((r) => ({ department: r.department, rate: toNum(r.attendance_rate), emp: r.emp_count })),
    // 降序 → recharts category 轴首项沉底 → 最低(最需关注)置顶,同原型
    [attRows],
  );

  const travelData = useMemo(
    () =>
      [...travRows]
        .sort((a, b) => toNum(b.total_amount) - toNum(a.total_amount))
        .map((r) => {
          const amt = toNum(r.total_amount);
          return {
            department: r.department,
            amt,
            wan: amt / 10000,
            amlabel: `${fmt1(amt / 10000)}万`,
            trips: r.trip_count,
            travelers: r.traveler_count,
            per: amt / Math.max(1, r.traveler_count),
          };
        }),
    [travRows],
  );

  const error = att.error ?? trav.error ?? reimb.error ?? emp.error;
  const loading = att.isLoading || trav.isLoading || reimb.isLoading || emp.isLoading;
  if (error) {
    return (
      <div className="p-6 text-sm" style={{ background: PAGE_BG, minHeight: "100%", color: RED }}>
        数据加载失败:{error instanceof Error ? error.message : String(error)}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="p-6 text-sm" style={{ background: PAGE_BG, minHeight: "100%", color: INK_3 }}>
        加载中…
      </div>
    );
  }

  // —— 元信息行(<b> 强调次级墨色,红色仅用于未达标)。 ——
  const b = (v: ReactNode) => <b className="font-semibold [font-variant-numeric:tabular-nums]" style={{ color: INK_2 }}>{v}</b>;
  const bRed = (v: ReactNode) => <b className="font-semibold [font-variant-numeric:tabular-nums]" style={{ color: RED }}>{v}</b>;

  const sortedAsc = [...attRows].sort((a, b2) => toNum(a.attendance_rate) - toNum(b2.attendance_rate));
  const low = sortedAsc[0]; // noUncheckedIndexedAccess → 可能 undefined
  const above = attRows.filter((r) => toNum(r.attendance_rate) >= 90).length;
  const m2: ReactNode = !low
    ? "按出勤率升序 · 最需关注者置顶"
    : attRows.length > 1
      ? (
          <>
            最低 {bRed(`${low.department} ${fmt1(toNum(low.attendance_rate))}%`)}({fmt1(toNum(low.attendance_rate) - 90)}pp)· 达标 {b(`${above}/${attRows.length}`)} 部门
          </>
        )
      : (
          <>
            本部门 {b(`${fmt1(toNum(low.attendance_rate))}%`)} · 距目标 {fmt1(toNum(low.attendance_rate) - 90)}pp
          </>
        );

  const top = travelData[0];
  const m3: ReactNode = !top
    ? "按金额降序"
    : travelData.length > 1
      ? (
          <>
            按金额降序 · 人均最高 {b(`${top.department} ${fmt2(top.per / 10000)} 万`)} · 合计 {b(`${fmt1(S.amt / 10000)} 万 / ${S.trips} 趟`)}
          </>
        )
      : (
          <>
            本部门合计 {b(`${fmt1(S.amt / 10000)} 万 / ${S.trips} 趟`)} · 人均 {b(`${fmt2(S.amt / Math.max(1, S.tc) / 10000)} 万`)}
          </>
        );

  const m4: ReactNode = (
    <>
      待审批 {b(`${R.g.pending.cnt} 笔 / ${fmt2(R.g.pending.amt / 10000)}万`)} · 已驳回 {b(`${R.g.rejected.cnt} 笔 / ${fmt2(R.g.rejected.amt / 10000)}万`)} 需重新提交
    </>
  );
  const approvedPct = R.total > 0 ? Math.round((1000 * R.g.approved.amt) / R.total) / 10 : 0;

  // —— 数据表行。 ——
  const t1Rows = attRows.map((r) => [
    { v: r.department },
    { v: r.emp_count },
    { v: r.present_days },
    { v: r.trip_days },
    { v: r.leave_days },
    { v: r.absent_days },
    { v: `${fmt1(toNum(r.attendance_rate))}%`, red: toNum(r.attendance_rate) < 90 },
  ]);
  const t2Rows = sortedAsc.map((r) => [
    { v: r.department },
    { v: `${fmt1(toNum(r.attendance_rate))}%`, red: toNum(r.attendance_rate) < 90 },
    { v: `${fmt1(toNum(r.attendance_rate) - 90)}pp`, red: toNum(r.attendance_rate) < 90 },
  ]);
  const t3Rows = travelData.map((d) => [
    { v: d.department },
    { v: d.trips },
    { v: fmt2(d.wan) },
    { v: d.travelers },
    { v: fmt2(d.per / 10000) },
  ]);
  const t4Rows = reimbAgg.map((s) => [
    { v: s.name },
    { v: s.cnt },
    { v: fmt2(s.amt / 10000) },
    { v: `${fmt1(s.pct)}%` },
  ]);
  const empCells = empRows.map((r) => {
    const amt = toNum(r.travel_amount);
    const rate = toNum(r.attendance_rate);
    const resigned = r.status !== "active";
    return [
      { v: r.employee_id },
      { v: r.name },
      { v: r.department },
      { v: r.present_days },
      { v: r.trip_days },
      { v: r.leave_days },
      { v: r.absent_days },
      { v: `${fmt1(rate)}%`, red: rate < 90 },
      { v: amt > 0 ? fmt2(amt / 10000) : "—" },
      { v: resigned ? "离职" : "在岗", red: resigned },
    ];
  });

  const deptInMore = dept ? MORE_DEPTS.includes(dept) : false;

  return (
    <div key={tick} className="space-y-6 p-6" style={{ background: PAGE_BG, minHeight: "100%" }}>
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <Users className="h-5 w-5" style={{ color: BLUE }} />
        <h1 className="text-[22px] font-bold tracking-tight" style={{ color: INK }}>
          人员总览
        </h1>
        <Button variant="outline" size="sm" className="ml-auto h-8 gap-1.5 text-xs" onClick={refresh}>
          <RefreshCw className="h-3.5 w-3.5" />
          刷新
        </Button>
      </div>

      {/* 筛选栏:业务部门平铺 + 职能部门收「更多」 */}
      <div
        className="flex flex-wrap items-center gap-x-[18px] gap-y-2 rounded-[14px] px-[18px] py-3 text-[13px]"
        style={{ background: CARD, border: `1px solid ${CARD_BORDER}` }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12.5px]" style={{ color: INK_2 }}>
            部门
          </span>
          <Chip on={!dept} onClick={() => setDept(null)}>
            全部
          </Chip>
          {FLAT_DEPTS.map((d) => (
            <Chip key={d} on={dept === d} onClick={() => setDept(dept === d ? null : d)}>
              {d}
            </Chip>
          ))}
          <Popover open={moreOpen} onOpenChange={setMoreOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className={cn(
                  "flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[12.5px] whitespace-nowrap transition-colors",
                  !deptInMore && "hover:border-black/20 hover:text-[#1b1c1d]",
                )}
                style={{
                  background: deptInMore ? ACCENT_SOFT : CARD,
                  borderColor: deptInMore ? "transparent" : CARD_BORDER,
                  color: deptInMore ? BLUE : INK_2,
                  fontWeight: deptInMore ? 600 : 400,
                }}
              >
                {deptInMore ? dept : "更多部门"}
                <ChevronDown className="h-3.5 w-3.5" style={{ color: INK_3 }} />
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-[210px] p-1.5" style={{ background: CARD, borderColor: "rgba(0,0,0,0.08)" }}>
              <p className="px-2.5 pb-1 pt-0.5 text-[11px]" style={{ color: INK_3 }}>
                职能部门
              </p>
              {MORE_DEPTS.map((d) => {
                const n = att.data?.find((r) => r.department === d)?.emp_count;
                const on = dept === d;
                return (
                  <button
                    key={d}
                    type="button"
                    onClick={() => {
                      setDept(on ? null : d);
                      setMoreOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center justify-between rounded-[7px] px-2.5 py-[7px] text-[12.5px] transition-colors",
                      !on && "hover:bg-[#eef1ff]",
                    )}
                    style={{ background: on ? ACCENT_SOFT : undefined, color: on ? BLUE : INK_2, fontWeight: on ? 600 : 400 }}
                  >
                    <span>{d}</span>
                    <span className="text-[11.5px] [font-variant-numeric:tabular-nums]" style={{ color: INK_3 }}>
                      {n !== undefined ? `${n} 人` : ""}
                    </span>
                  </button>
                );
              })}
            </PopoverContent>
          </Popover>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-[11px]" style={{ color: INK_3 }}>
            统计窗口 2025 Q4(10~12 月)· mock 数据
          </span>
          {dept ? (
            <button
              type="button"
              onClick={() => setDept(null)}
              className="text-[12.5px] transition-colors hover:text-[#1b1c1d]"
              style={{ color: INK_3 }}
            >
              重置
            </button>
          ) : null}
        </div>
      </div>

      {/* KPI 五卡 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="在岗员工"
          value={String(S.n - S.resigned)}
          delta={
            <>
              总数 {S.n} · 离职 {S.resigned}
            </>
          }
        />
        <StatCard
          label="全员出勤率"
          value={`${fmt1(S.rate)}%`}
          delta={
            <span className="flex items-center gap-1.5">
              <Emph value={S.rate >= 90 ? "达到" : "低于"} neg={S.rate < 90} /> 90% 目标线 ·(出勤天数口径)
            </span>
          }
        />
        <StatCard
          label="差旅总额"
          value={`${fmt1(S.amt / 10000)}万`}
          delta={
            <>
              {S.trips} 趟 · {S.tc} 人有出差
            </>
          }
        />
        <StatCard
          label="待审批笔数"
          value={String(R.g.pending.cnt)}
          delta={<>占累计报销 {R.cnt > 0 ? fmt1((100 * R.g.pending.cnt) / R.cnt) : "0.0"}%</>}
        />
        <StatCard
          label="待审批金额"
          value={`${fmt1(R.g.pending.amt / 10000)}万`}
          delta={
            <span className="flex items-center gap-1.5">
              <Emph value={`占差旅总额 ${S.amt > 0 ? fmt1((100 * R.g.pending.amt) / S.amt) : "0.0"}%`} neg />
            </span>
          }
        />
      </div>

      {/* ① 人怎么样:考勤构成 + 出勤率 vs 目标 + 员工明细 */}
      <SectionCard
        badge="①"
        title="人怎么样?"
        sub={dept ? `${dept} · 考勤四态与出勤率(基准 90% 目标线)` : "全公司 · 考勤四态与出勤率(基准 90% 目标线)"}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="考勤构成 · 出勤 / 出差 / 请假 / 缺勤(100% 堆叠)" meta="天数占比 · 缺勤为红色段直读 · 部门人数见行标">
            <div style={{ height: Math.max(200, attData.length * 24 + 40) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={attData} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid horizontal={false} stroke={GRID} />
                  <XAxis
                    type="number"
                    domain={[0, 100]}
                    ticks={[0, 25, 50, 75, 100]}
                    tickFormatter={(t: number) => (t === 100 ? "100%" : String(t))}
                    tick={AXIS}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 11, fill: INK_2 }} tickLine={false} axisLine={false} />
                  <Tooltip
                    cursor={{ fill: CURSOR.fill }}
                    content={({ active, payload }) => {
                      const row = payload?.[0]?.payload as (typeof attData)[number] | undefined;
                      if (!active || !row) return null;
                      return (
                        <TechTooltip
                          active
                          label={row.label}
                          payload={[
                            ...ATT_SEGS.map((s) => ({ name: s.name, value: `${row[s.key]} 天`, color: s.color })),
                            { name: "出勤率", value: row.rateLabel, color: "#c6cdf6" },
                          ]}
                        />
                      );
                    }}
                  />
                  <Bar dataKey="pp" stackId="att" fill={BLUE} stroke="#fff" strokeWidth={1.5} isAnimationActive={false}>
                    <LabelList
                      dataKey="rateLabel"
                      position="center"
                      style={{ fontSize: 10.5, fontWeight: 600, fill: "#fff", fontVariantNumeric: "tabular-nums" }}
                    />
                  </Bar>
                  <Bar dataKey="tp" stackId="att" fill={ORANGE} stroke="#fff" strokeWidth={1.5} isAnimationActive={false} />
                  <Bar dataKey="lp" stackId="att" fill={LEAVE} stroke="#fff" strokeWidth={1.5} isAnimationActive={false} />
                  <Bar dataKey="ap" stackId="att" fill={RED} stroke="#fff" strokeWidth={1.5} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-[11px]" style={{ color: INK_2 }}>
              {ATT_SEGS.map((s) => (
                <span key={s.name} className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-[3px]" style={{ background: s.color }} />
                  {s.name}
                </span>
              ))}
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
                数据表(分页)
              </summary>
              <div className="mt-2">
                <PagedTable head={["部门", "人数", "出勤(天)", "出差(天)", "请假(天)", "缺勤(天)", "出勤率"]} rows={t1Rows} pageSize={8} />
              </div>
            </details>
          </ChartCard>

          <ChartCard title="部门出勤率 vs 目标线" meta={m2}>
            <div style={{ height: Math.max(200, rateData.length * 24 + 36) }}>
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 18, right: 34, bottom: 0, left: 0 }}>
                  <CartesianGrid horizontal={false} stroke={GRID} />
                  <XAxis type="number" dataKey="rate" domain={[82, 94]} ticks={[82, 86, 90, 94]} tick={AXIS} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="department" width={88} tick={{ fontSize: 11, fill: INK_2 }} tickLine={false} axisLine={false} />
                  <ReferenceLine
                    x={90}
                    stroke={RED}
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    label={{ value: "目标 90%", position: "top", fill: RED, fontSize: 10.5, fontWeight: 600 }}
                  />
                  <Tooltip
                    cursor={{ strokeDasharray: "3 3" }}
                    content={({ active, payload }) => {
                      const row = payload?.[0]?.payload as RateRow | undefined;
                      if (!active || !row) return null;
                      return (
                        <TechTooltip
                          active
                          label={row.department}
                          payload={[
                            { name: "出勤率", value: `${fmt1(row.rate)}%`, color: BLUE },
                            { name: "距目标", value: `${fmt1(row.rate - 90)}pp`, color: RED },
                            { name: "人数", value: `${row.emp} 人`, color: "#c6cdf6" },
                          ]}
                        />
                      );
                    }}
                  />
                  <Scatter data={rateData} fill={BLUE} shape={dotShape} isAnimationActive={false} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
                数据表(分页)
              </summary>
              <div className="mt-2">
                <PagedTable head={["部门", "出勤率", "距目标"]} rows={t2Rows} pageSize={8} />
              </div>
            </details>
          </ChartCard>
        </div>

        <ChartCard
          title="员工明细 · 考勤与差旅"
          meta={`${empRows.length} 人 · 在岗 ${empRows.length - S.resigned} · 每页 10 条 · 出勤率低于 90% 标红`}
        >
          <PagedTable
            head={["工号", "姓名", "部门", "出勤(天)", "出差(天)", "请假(天)", "缺勤(天)", "出勤率", "差旅(万)", "状态"]}
            rows={empCells}
            pageSize={10}
          />
        </ChartCard>
      </SectionCard>

      {/* ② 差旅花在哪儿 */}
      <SectionCard
        badge="②"
        title="差旅花在哪儿?"
        sub={dept ? `${dept} 差旅金额与人均` : `部门差旅金额与人均 · 合计 ${fmt1(S.amt / 10000)} 万 / ${S.trips} 趟 / ${S.tc} 人`}
      >
        <ChartCard title="部门差旅金额(万)" meta={m3}>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={travelData} margin={{ top: 22, right: 8, bottom: 0, left: -8 }}>
                <CartesianGrid vertical={false} stroke={GRID} />
                <XAxis dataKey="department" interval={0} tick={{ fontSize: 10.5, fill: AXIS_FILL }} tickLine={false} axisLine={false} />
                <YAxis
                  ticks={[0, 2, 4, 6]}
                  width={44}
                  tick={AXIS}
                  tickLine={false}
                  axisLine={false}
                  label={{ value: "万", angle: 0, position: "top", offset: 10, style: { fontSize: 10.5, fill: AXIS_FILL } }}
                />
                <Tooltip
                  cursor={CURSOR}
                  content={({ active, payload }) => {
                    const row = payload?.[0]?.payload as (typeof travelData)[number] | undefined;
                    if (!active || !row) return null;
                    return (
                      <TechTooltip
                        active
                        label={row.department}
                        payload={[
                          { name: "金额", value: `${fmt2(row.wan)} 万`, color: BLUE },
                          { name: "趟数", value: `${row.trips} 趟`, color: "#c6cdf6" },
                          { name: "出差人数", value: `${row.travelers} 人`, color: "#c6cdf6" },
                          { name: "人均", value: `${fmt2(row.per / 10000)} 万`, color: "#c6cdf6" },
                        ]}
                      />
                    );
                  }}
                />
                <Bar dataKey="wan" fill={BLUE} radius={[4, 4, 0, 0]} maxBarSize={64} isAnimationActive={false}>
                  <LabelList dataKey="amlabel" position="top" style={LABEL_STYLE} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
              数据表(分页)
            </summary>
            <div className="mt-2">
              <PagedTable head={["部门", "趟数", "金额(万)", "出差人数", "人均(万)"]} rows={t3Rows} pageSize={8} />
            </div>
          </details>
        </ChartCard>
      </SectionCard>

      {/* ③ 报销批到哪儿 */}
      <SectionCard badge="③" title="报销批到哪儿?" sub="报销状态构成 · 金额口径,笔数 × 金额双维">
        <ChartCard title="报销状态构成(按金额)" meta={m4}>
          <div className="flex flex-wrap items-center gap-9">
            <div className="relative w-[320px] max-w-full">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={reimbAgg}
                    dataKey="value"
                    nameKey="name"
                    startAngle={90}
                    endAngle={-270}
                    innerRadius={60}
                    outerRadius={94}
                    stroke="#fff"
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {reimbAgg.map((s) => (
                      <Cell key={s.id} fill={s.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      const row = payload?.[0]?.payload as (typeof reimbAgg)[number] | undefined;
                      if (!active || !row) return null;
                      return (
                        <TechTooltip
                          active
                          label={row.name}
                          payload={[
                            { name: "金额", value: `${fmt2(row.amt / 10000)} 万`, color: row.color },
                            { name: "笔数", value: `${row.cnt} 笔`, color: "#c6cdf6" },
                            { name: "金额占比", value: `${fmt1(row.pct)}%`, color: "#c6cdf6" },
                          ]}
                        />
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                <p className="text-[20px] font-[650] [font-variant-numeric:tabular-nums]" style={{ color: INK }}>
                  {fmt1(R.total / 10000)}万
                </p>
                <p className="mt-1 text-[11px]" style={{ color: INK_3 }}>
                  合计 · {R.cnt} 笔
                </p>
              </div>
            </div>
            <div className="flex min-w-[280px] flex-1 flex-col gap-2.5">
              {reimbAgg.map((s) => (
                <div
                  key={s.id}
                  className="flex items-baseline gap-2.5 text-[12.5px] [font-variant-numeric:tabular-nums]"
                  style={{ color: INK_2 }}
                >
                  <span className="inline-block h-[9px] w-[9px] shrink-0 self-center rounded-[3px]" style={{ background: s.color }} />
                  <span className="min-w-[52px] font-semibold" style={{ color: INK }}>
                    {s.name}
                  </span>
                  <span>{s.cnt} 笔</span>
                  <span className="ml-auto font-semibold" style={{ color: INK }}>
                    {fmt2(s.amt / 10000)}万
                  </span>
                  <span className="min-w-[44px] text-right" style={{ color: INK_3 }}>
                    {fmt1(s.pct)}%
                  </span>
                </div>
              ))}
              <p className="mt-1 text-xs [font-variant-numeric:tabular-nums]" style={{ color: INK_3 }}>
                金额合计 {b(`${fmt2(R.total / 10000)}万`)} = 差旅合计(对账一致)· 待审批 + 已驳回占 {b(`${fmt1(100 - approvedPct)}%`)} 流向未决
              </p>
            </div>
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
              数据表(分页)
            </summary>
            <div className="mt-2">
              <PagedTable head={["状态", "笔数", "金额(万)", "金额占比"]} rows={t4Rows} pageSize={8} />
            </div>
          </details>
        </ChartCard>
      </SectionCard>
    </div>
  );
}
