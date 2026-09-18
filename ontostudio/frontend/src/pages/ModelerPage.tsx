/**
 * 05 本体建模器骨架页（EAI-CUSTOM）：类层次树 + 类详情（GB/T 48000.3 附录 A 八项）
 * + 公理列表 + registry formal 段 YAML 预览（静态示例数据）。
 * 真实建模面读写待 kernel P5（registry v2 formal 段落地后接 REST）。
 */
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

const TREE: Array<[string, string[]?]> = [
  ["Activity 活动", ["Project 项目", "Bid 投标行为", "Evaluation 评价活动"]],
  ["Agent 主体", ["Org 机构", "Bidder 投标人", "Person 个人"]],
  ["Resource 资源", ["Goods 货物", "Qualification 资质"]],
  ["Place 地点"],
  ["Mention 证据"],
];

const AXIOMS: Array<{ tag: string; body: string; note?: string }> = [
  { tag: "propertyChain", body: "org_compiles_project → project_owned_by → org_parent_of ⇒ org_in_ecosystem_of" },
  { tag: "transitive", body: "part_of", note: "传递闭包，用于组织与地理归属" },
  { tag: "inverse", body: "replaces ⇄ isReplacedBy" },
  { tag: "disjoint", body: "NormativeElement, InformativeElement" },
  { tag: "hasKey", body: "Org { norm_name }", note: "全局唯一标识" },
];

const YAML = `# registry v2 · formal 段
namespaces:
  dg: "https://ontology.eai-flow.com/doc_graph#"
object_types:
  - api_name: graph_entity
    etype_classes:
      project: { class: Project, subClassOf: [Activity] }
      mine:    { class: Mine,    subClassOf: [Place] }
formal:
  property_chains:
    - { derived: org_in_ecosystem_of,
        chain: [org_compiles_project,
               project_owned_by, org_parent_of] }
  transitive: [part_of]
  inverse: [{ pair: [replaces, isReplacedBy] }]`;

export function ModelerPage() {
  return (
    <div className="p-6">
      <PageHeader
        clause="05 · 建模"
        title="本体建模器"
        description="元数据描述项对齐 GB/T 48000.3 附录 A · 公理以 OWL 2 RL 表达 · 保存后 SHA 热重载"
        actions={
          <>
            <button className="border-border bg-card hover:bg-accent h-8 rounded-lg border px-3 text-xs font-medium shadow-xs">
              校验建模面
            </button>
            <button className="bg-primary text-primary-foreground h-8 rounded-lg px-3 text-xs font-medium">
              保存并热重载
            </button>
          </>
        }
      />
      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[250px_1fr_330px]">
        <Panel title="类层次" subtitle="subClassOf">
          <ul className="p-2 text-[13px]">
            {TREE.map(([label, children]) => (
              <li key={label}>
                <button
                  type="button"
                  className="hover:bg-accent flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left"
                >
                  <span className="text-primary font-mono text-[10px]">▾</span>
                  {label}
                  {children ? (
                    <span className="border-border text-muted-foreground bg-card ml-auto rounded border px-1 font-mono text-[10px]">
                      {children.length} 子类
                    </span>
                  ) : null}
                </button>
                {children ? (
                  <ul className="border-border/60 ml-4 list-none border-l border-dashed pl-4">
                    {children.map((child) => (
                      <li key={child}>
                        <button
                          type="button"
                          className="text-muted-foreground hover:bg-accent hover:text-foreground flex w-full items-center rounded-md px-2.5 py-1 text-left"
                        >
                          {child}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </Panel>

        <div className="flex flex-col gap-3.5">
          <Panel
            title="Activity 活动"
            actions={
              <div className="flex gap-1.5">
                <Chip tone="primary">owl:Class</Chip>
                <Chip>行为主体：竞标/评价/承包</Chip>
              </div>
            }
          >
            <dl className="grid grid-cols-[110px_1fr] gap-y-2 gap-x-4 px-4 py-3.5 text-[12.5px]">
              {(
                [
                  ["标识符 IRI", "…/doc_graph#Activity"],
                  ["名称 Name", "Activity"],
                  ["标签 Label", "活动"],
                  ["定义", "消耗资源并产生状态变化的业务行为，是项目、投标与评价行为的父类。"],
                  ["属性集", "name, startTime, endTime, status"],
                  ["父类", "—（根类）"],
                  ["子类", "Project, Bid, Evaluation"],
                  ["等价类", "—"],
                ] as Array<[string, string]>
              ).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground whitespace-nowrap">{key}</dt>
                  <dd className="min-w-0 break-words font-mono text-xs">{value}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          <Panel
            title="公理"
            subtitle="OWL 2 RL · 23 条"
            actions={<button className="text-primary text-xs font-medium">新增公理</button>}
          >
            <div className="flex flex-col gap-2 p-4">
              {AXIOMS.map((axiom) => (
                <div
                  key={axiom.tag + axiom.body}
                  className="border-border bg-muted flex flex-wrap items-center gap-2.5 rounded-lg border px-3 py-2 text-[12.5px]"
                >
                  <span className="text-primary bg-primary/10 rounded px-1.5 py-px font-mono text-[10.5px] font-semibold">
                    {axiom.tag}
                  </span>
                  <code className="font-mono text-xs">{axiom.body}</code>
                  {axiom.note ? (
                    <span className="text-muted-foreground text-xs">· {axiom.note}</span>
                  ) : null}
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel title="doc_graph.yaml" subtitle="formal 段预览" className="self-start">
          <div className="p-3">
            <pre className="bg-code-bg text-code-fg overflow-x-auto rounded-lg p-3.5 font-mono text-[11.5px] leading-relaxed">
              <DemoTag className="mb-2 inline-block" />
              {"\n"}
              {YAML}
            </pre>
          </div>
        </Panel>
      </div>
    </div>
  );
}
