"use client";

import { GitCommitHorizontal, RefreshCw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { clearBizPipelineCache } from "@/extensions/biz-pipeline/api";
import { ChartCard } from "@/extensions/biz-pipeline/components/ChartCard";
import {
  AXIS,
  BLUE,
  CURSOR,
  GREEN,
  GRID,
  INK,
  INK_2,
  INK_3,
  PAGE_BG,
  RED,
  RED_55,
} from "@/extensions/biz-pipeline/components/chartTheme";
import { SectionCard } from "@/extensions/biz-pipeline/components/SectionCard";
import { Emph, StatCard } from "@/extensions/biz-pipeline/components/StatCard";
import { TechTooltip } from "@/extensions/biz-pipeline/components/TechTooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/biz-pipeline/components/ui/table";
import { useContractRecon, useMonthlyBids, usePipelineFunnel } from "@/extensions/biz-pipeline/hooks";

// Decimal/numeric 列经 JSON 序为 string;recharts 需 number → 统一转。
const toNum = (v: string | null | undefined): number => (v === null || v === undefined ? 0 : Number(v));
function wan(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}
// 合同号缩写(HT-2025-003 → HT-003),meta 行用
const shortNo = (no: string) => no.replace(/^HT-\d{4}-/, "HT-");
const pct = (a: number, b: number): number | null => (b > 0 ? Math.round((100 * a) / b) : null);

// 月度节奏 / 待开票对账图例:[名称, 色]
const BIDS_LEGEND: Array<[string, string]> = [
  ["投标", BLUE],
  ["中标", GREEN],
];
const RECON_LEGEND: Array<[string, string]> = [
  ["已开票", BLUE],
  ["待开票", RED_55],
];

// dataviz: 柱顶直接标值(tabular 对齐,次级墨色——文字穿文字 token 不穿系列色)
const LABEL_STYLE = { fontSize: 11, fontWeight: 600, fill: INK_2, fontVariantNumeric: "tabular-nums" } as const;

/** 自定义图例(①bid-quote 同构):8px 圆角色点 + 11px 名称。 */
function Legend({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="mt-1.5 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-[11px]" style={{ color: INK_2 }}>
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-[3px]" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

/**
 * 仪表盘 tab(2026-08-17 按原型重构,对齐 bid-quote DeepSeek usage 风):
 * ①转化怎么样? ②钱到账了多少? 原型 = docs/superpowers/specs/2026-08-17-biz-pipeline-dashboard-prototype.html。
 * EAI-CUSTOM: 不随暗色主题切换——本页走独立浅色 token(chartTheme),原型即验收标准。
 */
export function DashboardView() {
  const [tick, setTick] = useState(0);
  const refresh = () => {
    clearBizPipelineCache();
    setTick((t) => t + 1);
  };

  const funnelQ = usePipelineFunnel();
  const monthlyQ = useMonthlyBids();
  const reconQ = useContractRecon();

  const f = funnelQ.data?.[0];

  // 金额漏斗(投标→中标→合同→开票,单位万)—— 单色实心柱 + 柱顶直接标值;share=占投标总额(表格/tooltip 用)
  const bidAmt = f ? toNum(f.bid_amount_total) : 0;
  const funnelData = f
    ? [
        { stage: "投标总额", amount: bidAmt / 10000, amlabel: `${(bidAmt / 10000).toFixed(0)}万`, share: 100 },
        { stage: "中标总额", amount: toNum(f.won_amount_total) / 10000, amlabel: `${(toNum(f.won_amount_total) / 10000).toFixed(0)}万`, share: pct(toNum(f.won_amount_total), bidAmt) },
        { stage: "合同总额", amount: toNum(f.contract_total) / 10000, amlabel: `${(toNum(f.contract_total) / 10000).toFixed(0)}万`, share: pct(toNum(f.contract_total), bidAmt) },
        { stage: "已开票", amount: toNum(f.invoiced_total) / 10000, amlabel: `${(toNum(f.invoiced_total) / 10000).toFixed(0)}万`, share: pct(toNum(f.invoiced_total), bidAmt) },
      ]
    : [];
  // 中标率:保留 1 位小数(1000 倍后取整再除回,避开浮点)
  const winRate = f && f.bid_count > 0 ? Math.round((1000 * f.won_count) / f.bid_count) / 10 : null;
  // 漏斗各级转化(金额口径,meta 行)
  const winAmt = f ? pct(toNum(f.won_amount_total), toNum(f.bid_amount_total)) : null;
  const signRate = f ? pct(toNum(f.contract_total), toNum(f.won_amount_total)) : null;
  const invRate = f ? pct(toNum(f.invoiced_total), toNum(f.contract_total)) : null;
  // KPI 口径开票进度保留 1 位小数(原型 70.7%);图1 meta 维持整数口径
  const invRate1 = f && toNum(f.contract_total) > 0 ? Math.round((1000 * toNum(f.invoiced_total)) / toNum(f.contract_total)) / 10 : null;
  // 月度投标节奏(投标 vs 中标,次数)
  const monthlyData = (monthlyQ.data ?? []).map((r) => ({ ym: r.ym, 投标: r.bids, 中标: r.won }));
  const wonMonths = (monthlyQ.data ?? []).filter((r) => r.won > 0).map((r) => r.ym.slice(5));
  const year = monthlyData[0]?.ym.slice(0, 4);
  // 原型 meta 前缀:全年每月恰好 1 标时才声明
  const onePerMonth = monthlyData.length > 0 && monthlyData.every((d) => d.投标 === 1);
  // 全 1 数据下 allowDecimals 会把刻度撑到 4 → 小值域给显式整数刻度
  const bidsMax = monthlyData.reduce((m, d) => Math.max(m, d.投标, d.中标), 0);
  const bidsTicks = bidsMax > 0 && bidsMax <= 6 ? Array.from({ length: bidsMax + 1 }, (_, i) => i) : undefined;
  // 待开票对账(堆叠:已开票 + 待开票 = 合同额,万)—— 待开票直接编码为红色段,不再让读者心算差值
  const reconRows = reconQ.data ?? [];
  const dueRows = reconRows.filter((r) => toNum(r.uninvoiced) > 0);
  const reconData = reconRows.map((r) => {
    const due = toNum(r.uninvoiced) / 10000;
    return {
      contract_no: r.contract_no,
      customer: r.customer,
      amount: toNum(r.amount) / 10000,
      已开票: toNum(r.invoiced) / 10000,
      待开票: due,
      dueLabel: due > 0 ? `待开 ${due.toFixed(0)}万` : "",
      doneLabel: due > 0 ? "" : "已全额开票",
    };
  });
  const reconMeta: ReactNode = (
    <span>
      按待开票降序 ·{" "}
      {dueRows.length > 0 ? (
        dueRows.map((r, i) => (
          <span key={r.contract_no}>
            {i > 0 ? " · " : ""}
            <b className="font-semibold" style={{ color: INK_2 }}>
              {shortNo(r.contract_no)} 余 {(toNum(r.uninvoiced) / 10000).toFixed(0)}万
            </b>
          </span>
        ))
      ) : (
        "全部合同已全额开票"
      )}{" "}
      · 合计待开{" "}
      <b className="font-semibold" style={{ color: INK_2 }}>
        {f ? `${(toNum(f.uninvoiced_total) / 10000).toFixed(0)}万` : "—"}
      </b>{" "}
      · 红段即催办金额
    </span>
  );

  return (
    <div key={tick} className="space-y-6 p-6" style={{ background: PAGE_BG, minHeight: "100%" }}>
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GitCommitHorizontal className="h-5 w-5" style={{ color: BLUE }} />
          <h1 className="text-[22px] font-bold" style={{ color: INK }}>
            管线战情总览
          </h1>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={funnelQ.isFetching}>
          <RefreshCw className={funnelQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          刷新
        </Button>
      </div>

      {/* ── ① 转化怎么样? ─────────────────────────────── */}
      <SectionCard badge="①" title="转化怎么样?" sub="管线漏斗 · 投标 → 中标 → 合同 → 开票,金额逐级沉淀">
        {/* KPI 行(注脚=可从数据算出的口径) */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard label="投标总数" value={f?.bid_count ?? "—"} delta={f && year ? `${year} 年度 · ${f.bid_count} 个项目` : undefined} />
          <StatCard
            label="中标率"
            value={winRate !== null ? `${winRate}%` : "—"}
            delta={f ? <b className="font-semibold">{f.won_count} 中 / {f.bid_count} 投</b> : undefined}
          />
          <StatCard label="合同总额" value={f ? wan(f.contract_total) : "—"} delta={f ? `${f.contract_count} 份合同` : undefined} />
          <StatCard
            label="已开票总额"
            value={f ? wan(f.invoiced_total) : "—"}
            delta={invRate1 !== null ? <>开票进度 <Emph value={`${invRate1}%`} />(占合同额)</> : undefined}
          />
          <StatCard
            label="待开票总额"
            value={f ? wan(f.uninvoiced_total) : "—"}
            delta={dueRows.length > 0 ? <Emph value={`${dueRows.length} 份合同待催开`} neg /> : "全部已开票"}
          />
        </div>

        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {/* 图1:金额漏斗(单色蓝柱 + 柱顶标值;实线网格) */}
          <ChartCard
            title="金额漏斗 · 投标 → 中标 → 合同 → 开票(万)"
            meta={
              <span>
                金额口径:中标 <b className="font-semibold" style={{ color: INK_2 }}>{winAmt ?? "—"}%</b> · 签约{" "}
                <b className="font-semibold" style={{ color: INK_2 }}>{signRate ?? "—"}%</b> · 开票进度{" "}
                <b className="font-semibold" style={{ color: INK_2 }}>{invRate ?? "—"}%</b>
              </span>
            }
          >
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={funnelData} margin={{ top: 22, right: 8, left: -8, bottom: 0 }} barCategoryGap="32%">
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="stage" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} allowDecimals={false} />
                <Tooltip
                  cursor={CURSOR}
                  content={({ active, payload }) => {
                    const row = payload?.[0]?.payload as (typeof funnelData)[number] | undefined;
                    if (!active || !row) return null;
                    return (
                      <TechTooltip
                        active
                        label={row.stage}
                        payload={[
                          { name: "金额", value: `${row.amount.toFixed(0)} 万`, color: BLUE },
                          { name: "占投标总额", value: row.share !== null ? `${row.share}%` : "—", color: "#c6cdf6" },
                        ]}
                      />
                    );
                  }}
                />
                <Bar dataKey="amount" name="金额" fill={BLUE} radius={[4, 4, 0, 0]} maxBarSize={72} isAnimationActive={false}>
                  <LabelList dataKey="amlabel" position="top" style={LABEL_STYLE} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <details className="mt-3">
              <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
                数据表
              </summary>
              <Table className="text-xs">
                <TableHeader>
                  <TableRow>
                    <TableHead className="tracking-normal">阶段</TableHead>
                    <TableHead className="text-right tracking-normal">金额(万)</TableHead>
                    <TableHead className="text-right tracking-normal">占投标总额</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {funnelData.map((d) => (
                    <TableRow key={d.stage}>
                      <TableCell>{d.stage}</TableCell>
                      <TableCell className="text-right [font-variant-numeric:tabular-nums]">{d.amount.toFixed(0)}</TableCell>
                      <TableCell className="text-right [font-variant-numeric:tabular-nums]">{d.share !== null ? `${d.share}%` : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </details>
          </ChartCard>

          {/* 图2:月度投标节奏(投标蓝 vs 中标绿;整数刻度) */}
          <ChartCard
            title="月度投标节奏 · 投标 vs 中标"
            meta={
              wonMonths.length > 0 ? (
                <span>
                  {onePerMonth && year ? `${year} 年每月 1 标 · ` : ""}
                  中标集中在 <b className="font-semibold" style={{ color: INK_2 }}>{wonMonths.join(" / ")}</b> 月
                </span>
              ) : (
                "全年暂无中标"
              )
            }
          >
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={monthlyData} margin={{ top: 14, right: 8, left: -14, bottom: 0 }} barCategoryGap="20%">
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="ym" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
                <YAxis
                  tick={AXIS}
                  tickLine={false}
                  axisLine={false}
                  width={32}
                  allowDecimals={false}
                  ticks={bidsTicks}
                  label={{ value: "次", angle: 0, position: "top", offset: 10, style: { fontSize: 11, fill: INK_3 } }}
                />
                <Tooltip
                  cursor={CURSOR}
                  content={({ active, payload }) => {
                    const row = payload?.[0]?.payload as (typeof monthlyData)[number] | undefined;
                    if (!active || !row) return null;
                    return (
                      <TechTooltip
                        active
                        label={row.ym}
                        payload={[
                          { name: "投标", value: `${row.投标} 次`, color: BLUE },
                          { name: "中标", value: `${row.中标} 次`, color: GREEN },
                          { name: "状态", value: row.中标 > 0 ? "中标" : "未中", color: INK_3 },
                        ]}
                      />
                    );
                  }}
                />
                <Bar dataKey="投标" fill={BLUE} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="中标" fill={GREEN} radius={[3, 3, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
            <Legend items={BIDS_LEGEND} />
            <details className="mt-3">
              <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
                数据表
              </summary>
              <Table className="text-xs">
                <TableHeader>
                  <TableRow>
                    <TableHead className="tracking-normal">月份</TableHead>
                    <TableHead className="text-right tracking-normal">投标(次)</TableHead>
                    <TableHead className="text-right tracking-normal">中标(次)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {monthlyData.map((d) => (
                    <TableRow key={d.ym}>
                      <TableCell>{d.ym}</TableCell>
                      <TableCell className="text-right [font-variant-numeric:tabular-nums]">{d.投标}</TableCell>
                      <TableCell className="text-right [font-variant-numeric:tabular-nums]">{d.中标}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </details>
          </ChartCard>
        </div>
      </SectionCard>

      {/* ── ② 钱到账了多少? ───────────────────────────── */}
      <SectionCard badge="②" title="钱到账了多少?" sub="合同 × 开票对账 · 待开票即催办清单(降序)">
        {/* 图3:合同开票对账(堆叠 已开票蓝+待开票红,白描边做段间留白;待开金额红色直标) */}
        <ChartCard title="合同开票对账 · 已开票 + 待开票(万)" meta={reconMeta}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={reconData} margin={{ top: 20, right: 8, left: -8, bottom: 0 }} barCategoryGap="24%">
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="contract_no" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} allowDecimals={false} />
              <Tooltip
                cursor={CURSOR}
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as (typeof reconData)[number] | undefined;
                  if (!active || !row) return null;
                  return (
                    <TechTooltip
                      active
                      label={`${row.contract_no} · ${row.customer}`}
                      payload={[
                        { name: "合同额", value: `${row.amount.toFixed(0)} 万`, color: BLUE },
                        { name: "已开票", value: `${row.已开票.toFixed(0)} 万`, color: BLUE },
                        { name: "待开票", value: `${row.待开票.toFixed(0)} 万`, color: RED_55 },
                      ]}
                    />
                  );
                }}
              />
              <Bar dataKey="已开票" stackId="recon" fill={BLUE} maxBarSize={120} stroke="#fff" strokeWidth={2} isAnimationActive={false}>
                {/* 栈顶圆角只由栈顶段承担:有待开票段时底段方角;全额开票合同底段自担圆角(原型 topRound)。
                    recharts 3.10 Cell 类型未声明 radius(落入 React SVGAttributes 的 string|number),运行期经 cells[i].props 透传生效,故断言 */}
                {reconData.map((d) => (
                  <Cell key={d.contract_no} radius={(d.待开票 > 0 ? [0, 0, 0, 0] : [4, 4, 0, 0]) as unknown as number} />
                ))}
              </Bar>
              <Bar dataKey="待开票" stackId="recon" fill={RED_55} radius={[4, 4, 0, 0]} maxBarSize={120} stroke="#fff" strokeWidth={2} isAnimationActive={false}>
                {/* 双 LabelList:待开(红,600 字重)/ 已全额(弱灰),空串不渲染 → 每行恰一枚标签 */}
                <LabelList dataKey="dueLabel" position="top" style={{ fontSize: 11, fontWeight: 600, fill: RED, fontVariantNumeric: "tabular-nums" }} />
                <LabelList dataKey="doneLabel" position="top" style={{ fontSize: 10.5, fill: INK_3 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <Legend items={RECON_LEGEND} />
          <details className="mt-3">
            <summary className="cursor-pointer select-none text-xs" style={{ color: INK_3 }}>
              数据表
            </summary>
            <Table className="text-xs">
              <TableHeader>
                <TableRow>
                  <TableHead className="tracking-normal">合同</TableHead>
                  <TableHead className="tracking-normal">客户</TableHead>
                  <TableHead className="text-right tracking-normal">合同额(万)</TableHead>
                  <TableHead className="text-right tracking-normal">已开票(万)</TableHead>
                  <TableHead className="text-right tracking-normal">待开票(万)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reconRows.map((r) => (
                  <TableRow key={r.contract_no}>
                    <TableCell>{r.contract_no}</TableCell>
                    <TableCell>{r.customer}</TableCell>
                    <TableCell className="text-right [font-variant-numeric:tabular-nums]">{wan(r.amount)}</TableCell>
                    <TableCell className="text-right [font-variant-numeric:tabular-nums]">{wan(r.invoiced)}</TableCell>
                    <TableCell className="text-right [font-variant-numeric:tabular-nums]">{wan(r.uninvoiced)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
        </ChartCard>
      </SectionCard>
    </div>
  );
}
