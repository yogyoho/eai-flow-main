/**
 * 06 推理工作台（EAI-CUSTOM，2026-09-27 原型重构）：infer 真数据（闭包统计 + 规则表）
 * + 解释视图 / CQ 验收单（规划态展示，水印标注——已入 TODOS「推理白盒化」，触发条件驱动）。
 */
import { BrainCircuit } from "lucide-react";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { runFormalInfer } from "@/api/formal-api";
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

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

const QUESTIONS = [
  { verdict: "PASS", text: "矿井水处理站的悬浮物执行哪个标准？", answer: "GB 50383-2010 · 路径 monitored_by→has_limit⇒covered_by_standard" },
  { verdict: "PASS", text: "哪些设施受 GB 13223-2011 约束？", answer: "锅炉烟气排放系统 · 1 条治理链" },
  { verdict: "FAIL", text: "矸石山与水源保护区的最小距离要求？", answer: "无路径：located_in 链首缺实例（prp-spo2 静默零推断）· 建议补桑干河实体" },
  { verdict: "PASS", text: "投标人须具备哪些资质？", answer: "2 条 · 来自 bid_quote 域 qualification" },
] as const;

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

  return (
    /* 纵向滚动层（样式=全站 6px 细条）+ min-w 保底（同总览/实体库手法） */
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
      <PageHeader
        icon={ BrainCircuit }
        title="推理工作台"
        description="单引擎：owlrl 闭包（graph:entailment）+ SPARQL CONSTRUCT 派生（每规则独立 named graph，named graph 归属即触发轨迹）"
        actions={
          <>
            <button className="border-border bg-card hover:bg-accent h-9 rounded-md border px-4 text-sm font-medium shadow-xs" onClick={() => inferQuery.refetch()}>
              dry 运行规则
            </button>
            <button className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 rounded-md px-4 text-sm font-medium" onClick={() => inferQuery.refetch()}>
              {inferQuery.isFetching ? "推理中…" : "全量重算"}
            </button>
          </>
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
                  <tr key={rule.name} className="hover:bg-muted/50 cursor-pointer">
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
          <Panel title="规则预览" subtitle="bidder_qualified · Phase B 验收问题 #3">
            <div className="p-3">
              <pre className="bg-code-bg text-code-fg overflow-x-auto rounded-lg p-3.5 font-mono text-xs leading-relaxed">
                {SPARQL}
              </pre>
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
          actions={
            <span className="flex items-center gap-1.5">
              <DemoTag />
              <Chip tone="warning">规划中</Chip>
            </span>
          }
        >
          <div className="flex flex-col p-4">
            {QUESTIONS.map((question) => (
              <div
                key={question.text}
                className="border-border flex items-start gap-2.5 border-b py-2.5 last:border-b-0"
              >
                <span
                  className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold ${
                    question.verdict === "PASS"
                      ? "bg-primary/10 text-primary"
                      : "bg-destructive/10 text-destructive"
                  }`}
                >
                  {question.verdict}
                </span>
                <div className="min-w-0">
                  <div className="text-[12.5px]">{question.text}</div>
                  <div className="text-muted-foreground mt-0.5 font-mono text-xs">
                    → {question.answer}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      </div>
    </div>
  );
}
