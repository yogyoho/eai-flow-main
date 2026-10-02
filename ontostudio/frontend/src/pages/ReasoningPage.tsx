/**
 * 06 推理工作台（EAI-CUSTOM，2026-09-27 原型重构）：infer 真数据（闭包统计 + 规则表）
 * + 解释视图 / CQ 验收单（规划态展示，水印标注——已入 TODOS「推理白盒化」，触发条件驱动）。
 */
import { BrainCircuit } from "lucide-react";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  fetchFormalRules,
  fetchRuleDerivations,
  fetchRuleExplainMiss,
  fetchRuleTrace,
  runCqs,
  runFormalInfer,
  type DerivationRow,
  type InferStats,
} from "@/api/formal-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

/**
 * 已知规则的中文描述与派生谓词（对照 rules.yaml / eia formal 链生成器）。
 * 规则表行本身从 /formal/infer 响应的 rule_counts 键驱动（v2 起后端 8 条，前端
 * 硬编码会漏新规则——2026-09-29 抽查修复）；未知键回退通用描述 + 谓词 = 键名去
 * chain_ 前缀 + NAMED GRAPH = graph:derived:<键>。
 */
export const RULE_META: Record<string, { desc: string; pred?: string }> = {
  org_in_ecosystem: { desc: "组织沿承包链归入生态（rules.yaml）", pred: "org_in_ecosystem_of" },
  qualified_bidder: { desc: "投标资格预审（Phase B 试点，CQ#3）", pred: "bidder_qualified_for" },
  chain_covered_by_standard: { desc: "环评治理合规链：设施→监测→限值→标准（eia formal 自动生成）", pred: "covered_by_standard" },
  chain_covered_by_monitoring: { desc: "环评治理合规链 3 段（eia formal 自动生成）", pred: "covered_by_monitoring" },
  chain_impact_to: { desc: "环评影响传导链：impact_to（eia formal 自动生成）", pred: "impact_to" },
  chain_impact_on_receptor: { desc: "环评影响传导链：受体影响（eia formal 自动生成）", pred: "impact_on_receptor" },
  chain_aquifer_impact: { desc: "环评含水层影响链（eia formal 自动生成）", pred: "aquifer_impact" },
  sameas_propagation: { desc: "sameAs 候选等价传播（内置）", pred: "*" },
};

export interface RuleRow {
  name: string;
  desc: string;
  pred: string;
  graph: string;
  count: number;
}

/** rule_counts → 规则行（已知键按 META 顺序在前、未知键按响应顺序附后，渲染稳定）。 */
export function ruleRows(ruleCounts: Record<string, number>): RuleRow[] {
  const keys = Object.keys(ruleCounts);
  const known = keys.filter((key) => key in RULE_META);
  const unknown = keys.filter((key) => !(key in RULE_META));
  return [...known, ...unknown].map((name) => {
    const meta = RULE_META[name];
    return {
      name,
      desc: meta?.desc ?? "eia formal 自动生成链规则",
      pred: meta?.pred ?? name.replace(/^chain_/, ""),
      graph: `graph:derived:${name}`,
      count: ruleCounts[name] ?? 0,
    };
  });
}

/** IRI → 局部名（# 或最后一个 / 之后）——F2 下钻列表的紧凑显示。 */
function iriLocal(iri: string): string {
  const i = Math.max(iri.lastIndexOf("#"), iri.lastIndexOf("/"));
  return i >= 0 ? iri.slice(i + 1) : iri;
}

export function ReasoningPage() {
  // F7 门限可调（2026-10-02 一期）：仅作用于下一次全量重算；页面展示的始终是已落盘
  // 的当前物化——缓存 key 不含门限，与总览治理合规链共享同一份「最新落盘」数据。
  const [minConf, setMinConf] = useState(0.7);
  const inferQuery = useQuery({
    queryKey: ["formal", "infer"],
    queryFn: () => runFormalInfer(minConf),
    staleTime: 30_000,
  });
  const derivedTotal = inferQuery.data
    ? Object.values(inferQuery.data.rule_counts).reduce((sum, n) => sum + n, 0)
    : 0;
  const rules = useMemo(
    () => (inferQuery.data ? ruleRows(inferQuery.data.rule_counts) : []),
    [inferQuery.data],
  );
  // G-B（2026-10-02 深审）：规则行此前 cursor-pointer 无 onClick，预览写死
  // bidder_qualified——选中态驱动预览；缺省落 qualified_bidder（唯一有 SPARQL 源码）。
  const [selectedRuleName, setSelectedRuleName] = useState<string | null>(null);
  const selectedRule =
    rules.find((r) => r.name === selectedRuleName) ??
    rules.find((r) => r.name === "qualified_bidder") ??
    rules[0] ??
    null;

  // F1 规则源码 + F2 派生下钻（2026-10-02 一期）：预览面板三视图（信息/源码/派生）。
  const [previewView, setPreviewView] = useState<"meta" | "source" | "derivations">("meta");
  const rulesSourceQuery = useQuery({
    queryKey: ["formal", "rules"],
    queryFn: fetchFormalRules,
    staleTime: 5 * 60_000,
  });
  const sourceMap = useMemo(
    () => new Map((rulesSourceQuery.data?.rules ?? []).map((r) => [r.name, r])),
    [rulesSourceQuery.data],
  );
  const derivationsQuery = useQuery({
    queryKey: ["formal", "derivations", selectedRule?.name],
    queryFn: () => fetchRuleDerivations(selectedRule!.name),
    enabled: previewView === "derivations" && !!selectedRule,
  });
  // F3 溯源：点击派生行的「溯源」→ 查触发该结论的基础事实链
  const [traceTarget, setTraceTarget] = useState<DerivationRow | null>(null);
  const traceQuery = useQuery({
    queryKey: ["formal", "trace", selectedRule?.name, traceTarget?.s, traceTarget?.p, traceTarget?.o],
    queryFn: () => fetchRuleTrace(selectedRule!.name, traceTarget!.s, traceTarget!.p, traceTarget!.o),
    enabled: !!traceTarget && !!selectedRule,
  });
  // F4 反事实：期望派生 (主体, *, 客体) 未出现时逐段定位断裂
  const [missS, setMissS] = useState("");
  const [missO, setMissO] = useState("");
  const missQuery = useQuery({
    queryKey: ["formal", "explain-miss", selectedRule?.name, missS, missO],
    queryFn: () => fetchRuleExplainMiss(selectedRule!.name, missS, missO),
    enabled: false,
  });
  // F6 dry 试算：闭包只算不写，与当前落盘对比
  const [dry, setDry] = useState<{ loading: boolean; stats: InferStats | null; minConf: number | null; error: string | null }>({
    loading: false,
    stats: null,
    minConf: null,
    error: null,
  });
  const runDry = () => {
    setDry({ loading: true, stats: null, minConf, error: null });
    runFormalInfer(minConf, true)
      .then((stats) => setDry({ loading: false, stats, minConf, error: null }))
      .catch((e: Error) => setDry({ loading: false, stats: null, minConf, error: e.message }));
  };

  // F5 CQ 验收自动化（2026-10-02）：ASK 真跑于内核（取代静态演示判定）；
  // 结果基于上次全量重算，面板内可手动重跑。
  const cqQuery = useQuery({
    queryKey: ["formal", "cq"],
    queryFn: runCqs,
    staleTime: 30_000,
  });
  const cqResults = cqQuery.data?.results ?? [];
  const cqFailed = cqResults.filter((r) => !r.passed).length;

  return (
    /* 纵向滚动层（样式=全站 6px 细条）+ min-w 保底（同总览/实体库手法） */
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
      <PageHeader
        icon={ BrainCircuit }
        title="推理工作台"
        description="单引擎：owlrl 闭包（graph:entailment）+ SPARQL CONSTRUCT 派生（每规则独立 named graph，named graph 归属即触发轨迹）"
        actions={
          /* G-A：dry 按钮已删（后端无 dry 模式）；F7 门限输入作用于下一次全量重算 */
          <span className="flex items-center gap-2">
            <label className="text-muted-foreground flex items-center gap-1.5 text-xs">
              置信度门限
              <input
                type="number"
                min={0.5}
                max={1}
                step={0.05}
                value={minConf}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (!Number.isNaN(v)) setMinConf(Math.min(1, Math.max(0.5, v)));
                }}
                title="低于此抽取置信度的实体不参与推理；点全量重算时生效"
                className="border-input focus:border-primary h-8 w-20 rounded-md border px-2 font-mono text-sm outline-none"
              />
            </label>
            <button
              className="border-border bg-card hover:bg-muted h-9 rounded-md border px-4 text-sm font-medium disabled:opacity-50"
              onClick={runDry}
              disabled={dry.loading}
              title="F6 试算：闭包只算不写，与当前落盘对比"
            >
              {dry.loading ? "试算中…" : "试算"}
            </button>
            <button
              className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium"
              onClick={() => {
                void inferQuery.refetch().then(() => cqQuery.refetch());
              }}
            >
              {inferQuery.isFetching ? "推理中…" : "全量重算"}
            </button>
          </span>
        }
      />
      <div className="mb-3.5 grid grid-cols-3 gap-3.5">
        <Panel className="px-4 py-3.5">
          <div className="text-muted-foreground text-sm font-medium">entailment 物化</div>
          <div className="mt-0.5 text-3xl font-black tracking-tight">
            {inferQuery.data ? inferQuery.data.entailment_triples.toLocaleString() : "—"}
          </div>
          <div className="text-muted-foreground mt-0.5 text-xs">
            输入 {inferQuery.data ? inferQuery.data.input_triples.toLocaleString() : "—"} · 门限过滤{" "}
            {inferQuery.data?.filtered_low_confidence ?? 0}
          </div>
        </Panel>
        <Panel className="px-4 py-3.5">
          <div className="text-muted-foreground text-sm font-medium">CONSTRUCT 派生</div>
          <div className="mt-0.5 text-3xl font-black tracking-tight">{derivedTotal}</div>
          <div className="text-muted-foreground mt-0.5 text-xs">
            {inferQuery.data ? `${rules.length} 条规则` : "— 条规则"} · 上次全量{" "}
            {inferQuery.dataUpdatedAt
              ? new Date(inferQuery.dataUpdatedAt).toLocaleString("zh-CN", { hour12: false })
              : "—"}
          </div>
        </Panel>
        <Panel className="px-4 py-3.5">
          <div className="text-muted-foreground text-sm font-medium">闭包耗时</div>
          <div className="mt-0.5 text-3xl font-black tracking-tight">
            {inferQuery.data ? `${inferQuery.data.duration_ms}ms` : "—"}
          </div>
          <div className="text-muted-foreground mt-0.5 text-xs">
            5k 实体校准门限 ≤ 15s
            {inferQuery.data ? (inferQuery.data.duration_ms <= 15_000 ? " ✓" : " · 本次超限") : ""}
          </div>
        </Panel>
      </div>
      {dry.stats || dry.error ? (
        <div
          className={cn(
            "mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border px-4 py-2.5 text-xs",
            dry.error
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "border-primary/30 bg-primary/5 text-muted-foreground",
          )}
        >
          {dry.error ? (
            <span>试算失败：{dry.error}</span>
          ) : (
            <>
              <b className="text-foreground">试算（未落盘）</b>
              <span>门限 {dry.minConf}</span>
              <span>
                物化 <b className="text-foreground">{dry.stats!.entailment_triples.toLocaleString()}</b> vs 落盘{" "}
                {(inferQuery.data?.entailment_triples ?? 0).toLocaleString()}
              </span>
              <span>
                派生合计{" "}
                <b className="text-foreground">
                  {Object.values(dry.stats!.rule_counts).reduce((a, b) => a + b, 0).toLocaleString()}
                </b>{" "}
                vs 落盘 {Object.values(inferQuery.data?.rule_counts ?? {}).reduce((a, b) => a + b, 0).toLocaleString()}
              </span>
              <span>{dry.stats!.duration_ms}ms</span>
              <button
                type="button"
                onClick={() => setDry({ loading: false, stats: null, minConf: null, error: null })}
                className="ml-auto hover:text-foreground"
              >
                清除
              </button>
            </>
          )}
        </div>
      ) : null}
      <Panel
        title="CONSTRUCT 规则"
        subtitle="替代 Rete · join 型派生"
        actions={
          <button
            type="button"
            disabled
            title="规则集由 eia formal 链生成器与 rules.yaml 静态定义——在线新增规则为规划项"
            className="text-primary text-sm font-medium opacity-60"
          >
            新增规则 <span className="text-warning font-mono text-xs">规划</span>
          </button>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-border bg-muted/50 border-b">
                {["规则", "派生谓词", "named graph", "派生数", "状态"].map((head, index) => (
                  <th
                    key={head}
                    className={`text-muted-foreground px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap ${index === 3 ? "text-right" : "text-left"}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {rules.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-muted-foreground px-4 py-8 text-center text-sm">
                    {inferQuery.isPending ? "推理计算中…" : "暂无规则计数"}
                  </td>
                </tr>
              ) : (
                rules.map((rule) => (
                  <tr
                    key={rule.name}
                    onClick={() => setSelectedRuleName(rule.name)}
                    className={cn(
                      "cursor-pointer",
                      rule.name === selectedRule?.name ? "bg-primary/5" : "hover:bg-muted/50",
                    )}
                  >
                    <td className="px-4 py-3">
                      <b className="font-medium">{rule.name}</b>
                      <div className="text-muted-foreground text-xs">{rule.desc}</div>
                    </td>
                    <td className="text-muted-foreground px-4 py-3 font-mono text-sm">{rule.pred}</td>
                    <td className="text-muted-foreground px-4 py-3 font-mono text-sm">{rule.graph}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {/* F2：派生数可点 → 下钻该规则派生三元组 */}
                      {rule.count > 0 ? (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedRuleName(rule.name);
                            setPreviewView("derivations");
                            setTraceTarget(null);
                          }}
                          title="查看该规则的派生三元组"
                          className="text-primary hover:underline"
                        >
                          {rule.count}
                        </button>
                      ) : (
                        rule.count
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Chip tone="primary">现行</Chip>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-[1.4fr_1fr]">
        <div className="flex flex-col gap-3.5">
          <Panel
            title={selectedRule ? `规则预览 · ${selectedRule.name}` : "规则预览"}
            subtitle={selectedRule?.desc ?? "点击上方规则行切换"}
            actions={
              selectedRule ? (
                <span className="flex items-center gap-1">
                  {(
                    [
                      ["meta", "信息"],
                      ["source", "源码"],
                      ["derivations", "派生"],
                    ] as const
                  ).map(([v, label]) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setPreviewView(v)}
                      className={cn(
                        "rounded-md border px-2 py-0.5 text-xs font-medium",
                        previewView === v
                          ? "border-primary/40 bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </span>
              ) : null
            }
          >
            <div className="p-3">
              {!selectedRule ? (
                <p className="text-muted-foreground p-1 text-sm">暂无规则——先点右上「全量重算」。</p>
              ) : previewView === "source" ? (
                sourceMap.get(selectedRule.name) ? (
                  <pre className="bg-code-bg text-code-fg max-h-72 overflow-auto rounded-lg p-3.5 font-mono text-xs leading-relaxed">
                    {sourceMap.get(selectedRule.name)!.construct}
                  </pre>
                ) : (
                  <p className="text-muted-foreground p-1 text-xs">
                    规则源码加载中或不可得（rules.yaml / 链生成器）。
                  </p>
                )
              ) : previewView === "derivations" ? (
                derivationsQuery.isLoading ? (
                  <p className="text-muted-foreground p-1 text-sm">加载派生…</p>
                ) : derivationsQuery.isError ? (
                  <p className="text-destructive p-1 text-xs">{(derivationsQuery.error as Error).message}</p>
                ) : (derivationsQuery.data?.rows.length ?? 0) === 0 ? (
                  <p className="text-muted-foreground p-1 text-sm">
                    该规则暂无派生——前置关系数据不足（缺口可见即 CQ FAIL 的根源）。
                  </p>
                ) : (
                  <div className="flex flex-col gap-1">
                    <p className="text-muted-foreground text-xs">
                      共 {derivationsQuery.data!.total.toLocaleString()} 条（显示前 {derivationsQuery.data!.rows.length} 条）· 点「溯源」查触发事实链
                    </p>
                    {traceTarget ? (
                      <div className="border-primary/30 bg-primary/5 rounded-lg border p-2.5">
                        <div className="mb-1.5 flex items-center gap-2">
                          <b className="text-xs">溯源结果</b>
                          {traceQuery.data ? (
                            <Chip tone={traceQuery.data.satisfied ? "primary" : "warning"}>
                              {traceQuery.data.satisfied ? "触发事实链完整" : "断言图中未找到完整链"}
                            </Chip>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => setTraceTarget(null)}
                            className="text-muted-foreground hover:text-foreground ml-auto text-xs"
                          >
                            收起
                          </button>
                        </div>
                        {traceQuery.isLoading ? (
                          <p className="text-muted-foreground text-xs">追溯触发事实…</p>
                        ) : traceQuery.isError ? (
                          <p className="text-destructive text-xs">{(traceQuery.error as Error).message}</p>
                        ) : traceQuery.data ? (
                          <>
                            <div className="flex flex-col gap-1">
                              {traceQuery.data.evidence.map((ev, i) => (
                                <div
                                  key={i}
                                  className="bg-background rounded-md border px-2.5 py-1.5 font-mono text-xs"
                                >
                                  {iriLocal(ev.s)}{" "}
                                  <span className="text-primary font-semibold">{iriLocal(ev.p)}</span>{" "}
                                  {iriLocal(ev.o)}
                                </div>
                              ))}
                            </div>
                            {traceQuery.data.details ? (
                              <div className="mt-1.5 flex flex-col gap-0.5">
                                {traceQuery.data.details.map((d) => (
                                  <span key={d.qualification} className="text-xs">
                                    {d.held ? "✓" : "✗"} 资质 {iriLocal(d.qualification)}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </>
                        ) : null}
                      </div>
                    ) : null}
                    {/* F4 反事实表单：为什么没推出来？ */}
                    <div className="border-border mt-1.5 flex flex-wrap items-center gap-1.5 rounded-md border border-dashed p-2">
                      <span className="text-muted-foreground text-xs">反事实：为什么没推出来？</span>
                      <input
                        value={missS}
                        onChange={(e) => setMissS(e.target.value)}
                        placeholder="主体 IRI（从派生列表或图谱复制）"
                        className="border-input focus:border-primary h-6 w-56 rounded border px-1.5 font-mono text-xs outline-none"
                      />
                      <input
                        value={missO}
                        onChange={(e) => setMissO(e.target.value)}
                        placeholder="客体 IRI"
                        className="border-input focus:border-primary h-6 w-56 rounded border px-1.5 font-mono text-xs outline-none"
                      />
                      <button
                        type="button"
                        disabled={!missS || !missO || missQuery.isFetching}
                        onClick={() => void missQuery.refetch()}
                        className="border-border bg-card hover:bg-muted rounded border px-2 py-0.5 text-xs font-medium disabled:opacity-50"
                      >
                        {missQuery.isFetching ? "分析中…" : "分析"}
                      </button>
                    </div>
                    {missQuery.data ? (
                      <div
                        className={cn(
                          "rounded-md border p-2.5 text-xs",
                          missQuery.data.satisfied
                            ? "border-primary/30 bg-primary/5"
                            : "border-warning/40 bg-warning/5",
                        )}
                      >
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <b>{missQuery.data.satisfied ? "路径存在——应可派生" : "链条断裂"}</b>
                          <span className="text-muted-foreground">{missQuery.data.hint}</span>
                        </div>
                        {(missQuery.data.evidence ?? []).length > 0 ? (
                          <div className="flex flex-col gap-0.5">
                            {(missQuery.data.evidence ?? []).map((ev, i) => (
                              <div key={i} className="font-mono">
                                {iriLocal(ev.s)}{" "}
                                <span className="text-primary font-semibold">{iriLocal(ev.p)}</span>{" "}
                                {iriLocal(ev.o)}
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {missQuery.data.missing_pred ? (
                          <div className="text-muted-foreground mt-1">
                            断裂于第 {(missQuery.data.missing_at ?? 0) + 1} 段{" "}
                            <span className="font-mono">{iriLocal(missQuery.data.missing_pred)}</span>
                            {missQuery.data.reached
                              ? `（到达 ${iriLocal(missQuery.data.reached)}）`
                              : ""}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    {derivationsQuery.data!.rows.map((row, i) => (
                      <div
                        key={`${row.s}-${row.p}-${row.o}-${i}`}
                        className="bg-muted/60 flex items-center gap-2 rounded-md px-2.5 py-1.5 font-mono text-xs"
                      >
                        <span className="min-w-0 flex-1">
                          {iriLocal(row.s)}{" "}
                          <span className="text-primary font-semibold">{iriLocal(row.p)}</span>{" "}
                          {iriLocal(row.o)}
                        </span>
                        <button
                          type="button"
                          onClick={() => setTraceTarget(row)}
                          title="追溯触发该结论的基础事实链"
                          className="text-primary flex-none hover:underline"
                        >
                          溯源
                        </button>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                <div className="flex flex-col gap-1.5 p-1 text-[13px]">
                  <div className="flex justify-between gap-3">
                    <span className="text-muted-foreground">派生谓词</span>
                    <span className="font-mono text-xs">{selectedRule.pred}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-muted-foreground">named graph</span>
                    <span className="font-mono text-xs">{selectedRule.graph}</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-muted-foreground">派生数</span>
                    <span className="font-mono text-xs tabular-nums">{selectedRule.count}</span>
                  </div>
                  <p className="text-muted-foreground mt-1.5 text-xs">
                    规则 SPARQL 见「源码」页；逐条派生结论见「派生」页。
                  </p>
                </div>
              )}
            </div>
          </Panel>
          <Panel
            title="解释视图 · covered_by_standard 推导链示例"
            subtitle="named graph 归属即触发轨迹"
          >
            <ol className="flex flex-col gap-3 p-4 text-[13px]">
              <li className="border-primary/20 border-l-2 pl-3">
                <b className="text-[12.5px]">① 基础事实（确认入图）</b>
                <div className="text-muted-foreground font-mono text-xs">
                  monitored_by(矿井水处理站, 悬浮物浓度) · 源: 环评报告-横城 §4.2
                </div>
              </li>
              <li className="border-primary/20 border-l-2 pl-3">
                <b className="text-[12.5px]">② 基础事实（确认入图）</b>
                <div className="text-muted-foreground font-mono text-xs">
                  has_limit(悬浮物浓度, GB 50383-2010/表2) · 源: 条款抽取
                </div>
              </li>
              <li className="border-primary/20 border-l-2 pl-3">
                <b className="text-[12.5px]">
                  ③ 属性链推导 <Chip tone="primary">prp-spo2</Chip>
                </b>
                <div className="text-muted-foreground font-mono text-xs">
                  monitored_by∘has_limit ⇒ covered_by_standard · graph: rules/eia/chain-1
                </div>
              </li>
              <li className="border-primary/20 border-l-2 pl-3">
                <b className="text-[12.5px]">
                  ④ sameas 传播 <Chip tone="primary">sameas_propagation</Chip>
                </b>
                <div className="text-muted-foreground font-mono text-xs">
                  同义设施（回用水车间）继承同一治理关系
                </div>
              </li>
            </ol>
            <p className="text-muted-foreground border-border border-t px-4 py-2.5 text-xs">
              白盒化（逐条物化可下钻 + 反事实「为什么没推出来」）已入 TODOS「推理白盒化」，触发条件驱动开工。
            </p>
          </Panel>
        </div>
        <Panel
          title="验收问题（Competency Questions）"
          subtitle="ASK 真跑于内核 · 结果基于上次全量重算"
          actions={
            <span className="flex items-center gap-1.5">
              {cqResults.length > 0 ? (
                <Chip tone={cqFailed > 0 ? "warning" : "primary"}>
                  {cqFailed > 0 ? `${cqFailed} 未过` : `${cqResults.length} 全过`}
                </Chip>
              ) : null}
              <button
                type="button"
                onClick={() => cqQuery.refetch()}
                disabled={cqQuery.isFetching}
                className="border-border bg-card hover:bg-muted rounded-md border px-2 py-0.5 text-xs font-medium disabled:opacity-50"
              >
                {cqQuery.isFetching ? "运行中…" : "重跑"}
              </button>
            </span>
          }
        >
          <div className="flex flex-col p-4">
            {cqQuery.isLoading ? (
              <p className="text-muted-foreground py-2 text-sm">运行 CQ 验收…</p>
            ) : cqQuery.isError ? (
              <p className="text-destructive py-2 text-sm">
                CQ 验收失败：{(cqQuery.error as Error).message}
              </p>
            ) : cqResults.length === 0 ? (
              <p className="text-muted-foreground py-2 text-sm">暂无验收问题（kernel/cq.yaml）。</p>
            ) : (
              cqResults.map((cq) => (
                <div
                  key={cq.id}
                  className="border-border flex items-start gap-2.5 border-b py-2.5 last:border-b-0"
                >
                  <span
                    className={cn(
                      "shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold",
                      cq.passed
                        ? "bg-primary/10 text-primary"
                        : "bg-destructive/10 text-destructive",
                    )}
                  >
                    {cq.passed ? "PASS" : "FAIL"}
                  </span>
                  <div className="min-w-0">
                    <div className="text-[12.5px]">{cq.question}</div>
                    <div className="text-muted-foreground mt-0.5 font-mono text-xs">
                      → 预期 {cq.expected ? "真" : "假"} · 实际 {cq.actual ? "真" : "假"}
                      {cq.error ? ` · ${cq.error}` : ""}
                    </div>
                    {!cq.passed ? (
                      <div className="text-muted-foreground/70 mt-0.5 text-xs">
                        反事实解释（为什么没推出来）归白盒化三期（explain-miss）。
                      </div>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
      </div>
    </div>
  );
}
