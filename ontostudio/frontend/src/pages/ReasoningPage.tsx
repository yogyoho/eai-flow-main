/**
 * 06 推理工作台（EAI-CUSTOM，2026-09-27 原型重构）：infer 真数据（闭包统计 + 规则表）
 * + 解释视图 / CQ 验收单（规划态展示，水印标注——已入 TODOS「推理白盒化」，触发条件驱动）。
 */
import { BrainCircuit } from "lucide-react";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { runCqs, runFormalInfer } from "@/api/formal-api";
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

const SPARQL = `# 投标人具备项目所需全部资质 → bidder_qualified_for
CONSTRUCT { ?b a :QualifiedBidder ; :qualifiedFor ?p }
WHERE {
  ?b a :Bidder ; :bidderOf ?p .
  ?p :requiresQualification ?q .
  ?b :holdsQualification ?q .
  FILTER NOT EXISTS { ?p :requiresQualification ?q2 .
                      FILTER NOT EXISTS { ?b :holdsQualification ?q2 } }
}`;

export function ReasoningPage() {
  const inferQuery = useQuery({
    queryKey: ["formal", "infer"],
    queryFn: () => runFormalInfer(),
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
          /* G-A（2026-10-02 深审）：原「dry 运行规则」按钮与全量重算同调 refetch，
           * 后端 /infer 无 dry 模式（一律清空重写 entailment）——语义谎言按钮删除；
           * dry 试算归「推理白盒化」（TODOS，触发条件驱动）。 */
          <button className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium" onClick={() => inferQuery.refetch()}>
            {inferQuery.isFetching ? "推理中…" : "全量重算"}
          </button>
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
                    <td className="px-4 py-3 text-right tabular-nums">{rule.count}</td>
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
          >
            <div className="p-3">
              {selectedRule?.name === "qualified_bidder" ? (
                <pre className="bg-code-bg text-code-fg overflow-x-auto rounded-lg p-3.5 font-mono text-xs leading-relaxed">
                  {SPARQL}
                </pre>
              ) : selectedRule ? (
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
                    规则源码在内核（rules.yaml / eia formal 链生成器），在线查看为规划项。
                  </p>
                </div>
              ) : (
                <p className="text-muted-foreground p-1 text-sm">暂无规则——先点右上「全量重算」。</p>
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
