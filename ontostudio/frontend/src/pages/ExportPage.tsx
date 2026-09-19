/**
 * 09 导出互操作（EAI-CUSTOM）——真实数据源：GET /ontology/formal/export。
 * Turtle（all 图）/ JSON-LD（schema 图）预览 + 下载；命名空间表静态；
 * 快照列表为占位（快照调度属后续部署面，见 spec §4）。
 */
import { useQuery } from "@tanstack/react-query";

import {
  downloadText,
  fetchFormalExportJsonld,
  fetchFormalExportText,
} from "@/api/formal-api";
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

const SNAPSHOTS = [
  { when: "2026-09-20 06:00", size: "— 待快照调度" },
];

export function ExportPage() {
  const turtleQuery = useQuery({
    queryKey: ["formal", "export", "turtle", "all"],
    queryFn: () => fetchFormalExportText("turtle", "all"),
    staleTime: 60_000,
  });
  const jsonldQuery = useQuery({
    queryKey: ["formal", "export", "json-ld", "schema"],
    queryFn: () => fetchFormalExportJsonld("schema"),
    staleTime: 60_000,
  });
  const jsonldText = jsonldQuery.data
    ? JSON.stringify(jsonldQuery.data.document, null, 2)
    : "";

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
            <span className="text-muted-foreground text-[11px]">
              {turtleQuery.data ? `${turtleQuery.data.length} 字符` : "加载中…"}
            </span>
            <span className="ml-auto flex gap-1.5">
              <Chip tone="primary">推荐</Chip>
              <button
                className="border-border hover:border-primary h-6 rounded-md border px-2 text-[11px] font-medium"
                disabled={!turtleQuery.data}
                onClick={() => turtleQuery.data && downloadText("ontostudio-all.ttl", turtleQuery.data, "text/turtle")}
              >
                下载
              </button>
            </span>
          </div>
          <div className="p-3">
            <pre className="bg-code text-code-fg max-h-72 overflow-auto rounded-lg p-3.5 font-mono text-[11.5px] leading-relaxed">
              {turtleQuery.error ? `导出失败：${(turtleQuery.error as Error).message}` : turtleQuery.data || "加载中…"}
            </pre>
          </div>
        </Panel>
        <Panel className="overflow-hidden">
          <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold">
              .jsonld
            </span>
            <b className="text-sm font-semibold">JSON-LD 1.1</b>
            <span className="text-muted-foreground text-[11px]">schema 图</span>
            <span className="ml-auto flex gap-1.5">
              <Chip>互操作</Chip>
              <button
                className="border-border hover:border-primary h-6 rounded-md border px-2 text-[11px] font-medium"
                disabled={!jsonldText}
                onClick={() => jsonldText && downloadText("ontostudio-schema.jsonld", jsonldText, "application/ld+json")}
              >
                下载
              </button>
            </span>
          </div>
          <div className="p-3">
            <pre className="bg-code text-code-fg max-h-72 overflow-auto rounded-lg p-3.5 font-mono text-[11.5px] leading-relaxed">
              {jsonldQuery.error ? `导出失败：${(jsonldQuery.error as Error).message}` : jsonldText || "加载中…"}
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
                <Chip tone="primary">计划中</Chip>
                <span className="text-muted-foreground ml-auto font-mono text-[11.5px]">{snapshot.size}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
