/**
 * 09 导出互操作骨架页（EAI-CUSTOM）：Turtle/JSON-LD 预览 + 命名空间映射 + 快照历史（静态示例）。
 * 真实数据面待 kernel P1/P5（export 序列化 + 快照调度）。
 */
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

const TURTLE = `# doc_graph 快照 2026-09-18
@prefix dg: <https://ontology.eai-flow.com/doc_graph#> .
dg:id/a1f3c9 a dg:Bidder ;
  dg:canonicalName "山西煤机集团" ;
  dg:holdsQualification dg:id/77b2e0 ;
  dg:bidderOf dg:id/9c21f7 .`;

const JSONLD = `{
  "@context": { "dg": "…/doc_graph#" },
  "@id": "dg:id/a1f3c9",
  "@type": "dg:Bidder",
  "dg:canonicalName": "山西煤机集团"
}`;

const SNAPSHOTS = [
  { when: "2026-09-18 06:00", size: "4.2 MB · 86,412 triples" },
  { when: "2026-09-17 06:00", size: "4.1 MB · 84,930 triples" },
  { when: "2026-09-16 06:00", size: "4.0 MB · 82,101 triples" },
];

export function ExportPage() {
  return (
    <div className="p-6">
      <PageHeader
        clause="09 · 导出"
        title="导出互操作"
        description="图真源 → 标准序列化 · 每日快照即国标 §5.3 交付物 · IRI 机械可逆可回导"
      />
      <div className="mb-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel className="overflow-hidden">
          <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold">
              .ttl
            </span>
            <b className="text-sm font-semibold">Turtle</b>
            <span className="ml-auto">
              <Chip tone="primary">推荐</Chip>
            </span>
          </div>
          <div className="p-3">
            <pre className="bg-code-bg text-code-fg overflow-x-auto rounded-lg p-3.5 font-mono text-[11.5px] leading-relaxed">
              <DemoTag className="mb-2 inline-block" />
              {"\n"}
              {TURTLE}
            </pre>
          </div>
        </Panel>
        <Panel className="overflow-hidden">
          <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold">
              .jsonld
            </span>
            <b className="text-sm font-semibold">JSON-LD 1.1</b>
            <span className="ml-auto">
              <Chip>互操作</Chip>
            </span>
          </div>
          <div className="p-3">
            <pre className="bg-code-bg text-code-fg overflow-x-auto rounded-lg p-3.5 font-mono text-[11.5px] leading-relaxed">
              <DemoTag className="mb-2 inline-block" />
              {"\n"}
              {JSONLD}
            </pre>
          </div>
        </Panel>
      </div>
      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel title="命名空间映射">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-border border-b">
                {["前缀", "命名空间", "域"].map((head) => (
                  <th key={head} className="text-muted-foreground px-3.5 py-2.5 text-left text-xs font-medium">
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-border/60 border-b">
                <td className="px-3.5 py-2.5 font-mono text-xs">dg</td>
                <td className="text-muted-foreground px-3.5 py-2.5 font-mono text-xs break-all">
                  https://ontology.eai-flow.com/doc_graph#
                </td>
                <td className="px-3.5 py-2.5">投标域</td>
              </tr>
              <tr className="border-border/60 border-b">
                <td className="px-3.5 py-2.5 font-mono text-xs">eia</td>
                <td className="text-muted-foreground px-3.5 py-2.5 font-mono text-xs break-all">
                  https://ontology.eai-flow.com/eia#
                </td>
                <td className="px-3.5 py-2.5">环评域</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2.5 font-mono text-xs">owl / sh / rdf</td>
                <td className="text-muted-foreground px-3.5 py-2.5 font-mono text-xs">W3C 标准</td>
                <td className="px-3.5 py-2.5">—</td>
              </tr>
            </tbody>
          </table>
        </Panel>
        <Panel title="快照历史" subtitle="每日 06:00 · 可恢复">
          <div>
            {SNAPSHOTS.map((snapshot) => (
              <div
                key={snapshot.when}
                className="border-border flex items-center gap-3 border-b px-4 py-2.5 text-xs last:border-b-0"
              >
                <span className="text-muted-foreground w-36 flex-none font-mono">{snapshot.when}</span>
                <Chip tone="primary">验讫</Chip>
                <span className="text-muted-foreground ml-auto font-mono tabular-nums">
                  {snapshot.size}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
