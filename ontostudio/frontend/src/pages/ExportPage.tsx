/**
 * 09 导出互操作（EAI-CUSTOM，2026-09-27 原型重构）——真实数据源：
 * GET /ontology/formal/export（Turtle all 图 / JSON-LD schema 图）+ POST /formal/load
 * （全量装载=对账，degraded 自愈执行者）。命名空间表静态；快照/导入为规划项。
 */
import { FileOutput, Loader2, PlayCircle } from "lucide-react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  downloadText,
  fetchFormalExportJsonld,
  fetchFormalExportText,
  runFormalLoad,
  type FormalLoadResult,
} from "@/api/formal-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";

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

  // 全量装载（对账）——人审闭环切片：行级 force_status 重写 DB 真相，degraded 自愈的执行者
  const queryClient = useQueryClient();
  const [loadResult, setLoadResult] = useState<FormalLoadResult | null>(null);
  const loadMutation = useMutation({
    mutationFn: () => runFormalLoad(),
    onSuccess: (data) => {
      setLoadResult(data);
      // 装载重写内核图 → 校验中心缓存失效
      void queryClient.invalidateQueries({ queryKey: ["formal", "validate"] });
    },
  });

  return (
    <div className="p-6">
      <PageHeader
        icon={ FileOutput }
        title="导出互操作"
        description="图真源 → 标准序列化 · 每日快照即国标 §5.3 交付物 · IRI 机械可逆可回导"
      />
      <div className="mb-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel className="overflow-hidden">
          <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 font-mono text-xs font-semibold">
              .ttl
            </span>
            <b className="text-sm font-semibold">Turtle</b>
            <span className="text-muted-foreground text-xs">
              {turtleQuery.data ? `${turtleQuery.data.length} 字符` : "加载中…"}
            </span>
            <span className="ml-auto flex gap-1.5">
              <Chip tone="primary">推荐</Chip>
              <button
                className="border-border hover:border-primary h-6 rounded-md border px-2 text-xs font-medium"
                disabled={!turtleQuery.data}
                onClick={() => turtleQuery.data && downloadText("ontostudio-all.ttl", turtleQuery.data, "text/turtle")}
              >
                下载
              </button>
            </span>
          </div>
          <div className="p-3">
            <pre className="bg-code text-code-fg max-h-72 overflow-auto rounded-lg p-3.5 font-mono text-xs leading-relaxed">
              {turtleQuery.error ? `导出失败：${(turtleQuery.error as Error).message}` : turtleQuery.data || "加载中…"}
            </pre>
          </div>
        </Panel>
        <Panel className="overflow-hidden">
          <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 font-mono text-xs font-semibold">
              .jsonld
            </span>
            <b className="text-sm font-semibold">JSON-LD 1.1</b>
            <span className="text-muted-foreground text-xs">schema 图</span>
            <span className="ml-auto flex gap-1.5">
              <Chip>互操作</Chip>
              <button
                className="border-border hover:border-primary h-6 rounded-md border px-2 text-xs font-medium"
                disabled={!jsonldText}
                onClick={() => jsonldText && downloadText("ontostudio-schema.jsonld", jsonldText, "application/ld+json")}
              >
                下载
              </button>
            </span>
          </div>
          <div className="p-3">
            <pre className="bg-code text-code-fg max-h-72 overflow-auto rounded-lg p-3.5 font-mono text-xs leading-relaxed">
              {jsonldQuery.error ? `导出失败：${(jsonldQuery.error as Error).message}` : jsonldText || "加载中…"}
            </pre>
          </div>
        </Panel>
      </div>
      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel
          title="装载与对账"
          subtitle="全量装载重写数据库真相——投影失败后重跑本操作即恢复一致"
        >
          <div className="p-4">
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                disabled={loadMutation.isPending}
                onClick={() => {
                  // G4 同款二次确认（与总览页全量装载一致，2026-10-02 审核补齐一致性）
                  if (window.confirm("全量装载将重写图数据全表（耗时数十秒），确认执行？")) {
                    loadMutation.mutate();
                  }
                }}
                className="flex items-center gap-1.5 whitespace-nowrap rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {loadMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <PlayCircle className="h-3.5 w-3.5" />
                )}
                全量装载（对账）
              </button>
              <span className="text-muted-foreground text-xs">
                装载即重写 DB 真相——投影失败（degraded）后重跑本操作即恢复一致，数据无损失
              </span>
            </div>
            {loadMutation.isError ? (
              <p className="text-destructive mt-3 text-sm">
                装载失败：{(loadMutation.error as Error).message}
              </p>
            ) : null}
            {loadResult ? (
              <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                {[
                  ["实体", loadResult.entities],
                  ["关系", loadResult.relations],
                  ["提及", loadResult.mentions],
                  ["去重", loadResult.deduped_entities],
                ].map(([k, v]) => (
                  <div key={k as string} className="bg-muted rounded-lg px-2 py-2">
                    <div className="text-foreground text-base font-semibold tabular-nums">
                      {v as number}
                    </div>
                    <div className="text-muted-foreground text-xs">{k as string}</div>
                  </div>
                ))}
              </div>
            ) : null}
            {loadResult && loadResult.skipped_entities.length > 0 ? (
              <p className="text-warning mt-2 text-xs">
                跳过 {loadResult.skipped_entities.length} 行（etype 未在 registry 声明，详见后端日志）
              </p>
            ) : null}
          </div>
        </Panel>
        <Panel title="快照历史" subtitle="规划：每日 06:00 快照调度">
          <div>
            {SNAPSHOTS.map((snapshot) => (
              <div
                key={snapshot.when}
                className="border-border flex items-center gap-3 border-b px-4 py-2.5 text-sm last:border-b-0"
              >
                <span className="text-muted-foreground w-36 flex-none font-mono">{snapshot.when}</span>
                <Chip tone="primary">计划中</Chip>
                <span className="text-muted-foreground ml-auto font-mono text-xs">{snapshot.size}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
