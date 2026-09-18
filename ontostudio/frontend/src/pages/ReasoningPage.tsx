/**
 * 06 推理工作台骨架页（EAI-CUSTOM）：闭包统计 + CONSTRUCT 规则表 + SPARQL 预览
 * + Competency Questions 验收单（静态示例数据）。
 * 真实数据面待 kernel P3（owlrl 闭包 + named graph 派生）。
 */
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

const STATS = [
  { k: "entailment 物化", v: "18,642", m: "subclass 12,341 · 链 3,207 · sameAs 89" },
  { k: "CONSTRUCT 派生", v: "486", m: "9 条规则 · 上次全量 09:12" },
  { k: "闭包耗时", v: "1.8s", m: "5k 实体预算 < 3s ✓" },
];

const RULES = [
  { name: "org_in_ecosystem", desc: "组织沿承包链归入生态", pred: "org_in_ecosystem_of", graph: "graph:derived:org_eco", count: 214, live: true },
  { name: "bidder_qualified", desc: "投标资格预审（Phase B 试点）", pred: "bidder_qualified_for", graph: "graph:derived:qualified", count: 97, live: true },
  { name: "place_containment", desc: "地理包含传递", pred: "located_in", graph: "graph:derived:geo", count: 132, live: true },
  { name: "conflict_of_interest", desc: "关联关系预警", pred: "related_to", graph: "graph:derived:coi", count: 43, live: false },
];

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
  { tone: "primary", tag: "图谱可答", text: "横城煤矿项目的投标人是谁？" },
  { tone: "primary", tag: "图谱可答", text: "山西煤机集团持有什么资质？" },
  { tone: "warning", tag: "推理可答", text: "哪些投标人具备项目所需全部资质？" },
] as const;

export function ReasoningPage() {
  return (
    <div className="p-6">
      <PageHeader
        clause="06 · 推理"
        title="推理工作台"
        description="单引擎：owlrl 闭包（graph:entailment）+ SPARQL CONSTRUCT 派生（每规则独立 named graph，named graph 归属即触发轨迹）"
        actions={
          <>
            <button className="border-border bg-card hover:bg-accent h-8 rounded-lg border px-3 text-xs font-medium shadow-xs">
              dry 运行规则
            </button>
            <button className="bg-primary text-primary-foreground h-8 rounded-lg px-3 text-xs font-medium">
              全量重算
            </button>
          </>
        }
      />
      <div className="mb-3.5 grid grid-cols-3 gap-3.5">
        {STATS.map((stat) => (
          <Panel key={stat.k} className="px-4 py-3.5">
            <div className="text-muted-foreground text-xs font-medium">{stat.k}</div>
            <div className="font-display mt-0.5 text-3xl font-black tracking-tight">{stat.v}</div>
            <div className="text-muted-foreground mt-0.5 text-xs">{stat.m}</div>
          </Panel>
        ))}
      </div>
      <Panel
        title="CONSTRUCT 规则"
        subtitle="替代 Rete · join 型派生"
        actions={<button className="text-primary text-xs font-medium">新增规则</button>}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-border border-b">
                {["规则", "派生谓词", "named graph", "派生数", "状态"].map((head, index) => (
                  <th
                    key={head}
                    className={`text-muted-foreground px-3.5 py-2.5 text-xs font-medium whitespace-nowrap ${index === 3 ? "text-right" : "text-left"}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {RULES.map((rule) => (
                <tr key={rule.name} className="border-border/60 hover:bg-accent/60 cursor-pointer border-b">
                  <td className="px-3.5 py-2.5">
                    <b className="font-medium">{rule.name}</b>
                    <div className="text-muted-foreground text-[11.5px]">{rule.desc}</div>
                  </td>
                  <td className="text-muted-foreground px-3.5 py-2.5 font-mono text-xs">{rule.pred}</td>
                  <td className="text-muted-foreground px-3.5 py-2.5 font-mono text-xs">{rule.graph}</td>
                  <td className="px-3.5 py-2.5 text-right tabular-nums">{rule.count}</td>
                  <td className="px-3.5 py-2.5">
                    <Chip tone={rule.live ? "primary" : "warning"}>
                      {rule.live ? "现行" : "dry-run"}
                    </Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="mt-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-[1.4fr_1fr]">
        <Panel title="规则预览" subtitle="bidder_qualified · Phase B 验收问题 #3">
          <div className="p-3">
            <pre className="bg-code-bg text-code-fg overflow-x-auto rounded-lg p-3.5 font-mono text-[11.5px] leading-relaxed">
              <DemoTag className="mb-2 inline-block" />
              {"\n"}
              {SPARQL}
            </pre>
          </div>
        </Panel>
        <Panel title="验收问题（Competency Questions）">
          <div className="flex flex-col gap-2.5 p-4 text-[13px]">
            {QUESTIONS.map((question) => (
              <div key={question.text} className="flex items-center gap-2.5">
                <Chip tone={question.tone}>{question.tag}</Chip>
                {question.text}
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
