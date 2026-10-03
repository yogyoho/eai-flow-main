/**
 * 09 导出互操作（EAI-CUSTOM，2026-09-27 原型重构；2026-10-03 D8 快照/回导落地）——
 * GET /ontology/formal/export（Turtle all / 含派生档 / JSON-LD schema）+ POST /formal/load
 * （全量装载=对账）+ 快照：TriG 全图（含派生）落盘 / 清单 / 恢复（自动回滚点）/ 删除。
 * 「IRI 机械可逆可回导」由 TriG 快照成真（Turtle 交付物仍是压平三元组形态）。
 */
import { FileOutput, Loader2, PlayCircle } from "lucide-react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  downloadText,
  fetchFormalExportJsonld,
  fetchFormalExportText,
  fetchSnapshots,
  createSnapshot,
  restoreSnapshot,
  deleteSnapshot,
  runFormalLoad,
  type FormalLoadResult,
} from "@/api/formal-api";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

export function ExportPage() {
  // D9：交付物默认不含派生（可重算）——「含派生图」勾选切换 all+derived 档
  const [withDerived, setWithDerived] = useState(false);
  const turtleQuery = useQuery({
    queryKey: ["formal", "export", "turtle", withDerived ? "all+derived" : "all"],
    queryFn: () => fetchFormalExportText("turtle", withDerived ? "all+derived" : "all"),
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

  // D8 快照：TriG 全图落盘 / 清单 / 恢复（自动回滚点）/ 删除
  const [restoreMsg, setRestoreMsg] = useState<string | null>(null);
  const snapshotsQuery = useQuery({
    queryKey: ["formal", "snapshots"],
    queryFn: fetchSnapshots,
  });
  const createSnapMutation = useMutation({
    mutationFn: createSnapshot,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["formal", "snapshots"] }),
  });
  const restoreMutation = useMutation({
    mutationFn: (v: { file: string }) => restoreSnapshot(v.file),
    onSuccess: (r) => {
      const total = Object.values(r.restored).reduce((a, b) => a + b, 0);
      setRestoreMsg(
        `已恢复 ${total.toLocaleString()} 三元组（回滚点 ${r.pre_restore}）——建议到推理工作台全量重算刷新派生`,
      );
      void queryClient.invalidateQueries({ queryKey: ["formal"] });
    },
    onError: (e: Error) => setRestoreMsg(`恢复失败：${e.message}`),
  });
  const deleteSnapMutation = useMutation({
    mutationFn: deleteSnapshot,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["formal", "snapshots"] }),
  });

  return (
    <div className="p-6">
      <PageHeader
        icon={ FileOutput }
        title="导出互操作"
        description="图真源 → 标准序列化 · TriG 快照可回导（国标 §5.3）· 每日调度为规划项"
      />
      <div className="mb-3.5 grid grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel className="overflow-hidden">
          <div className="border-border flex items-center gap-2.5 border-b px-4 py-3">
            <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 font-mono text-xs font-semibold">
              .ttl
            </span>
            <b className="text-sm font-semibold">Turtle</b>
            <label className="text-muted-foreground flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={withDerived}
                onChange={(e) => setWithDerived(e.target.checked)}
                className="h-3 w-3"
                title="派生结论可随时重算——交付物默认不含（D9 口径）"
              />
              含派生图
            </label>
            <span className="text-muted-foreground text-xs">
              {turtleQuery.data ? `${turtleQuery.data.length} 字符` : "加载中…"}
            </span>
            <span className="ml-auto flex gap-1.5">
              <Chip tone="primary">推荐</Chip>
              <button
                className="border-border hover:border-primary h-6 rounded-md border px-2 text-xs font-medium"
                disabled={!turtleQuery.data}
                onClick={() =>
                  turtleQuery.data &&
                  downloadText(
                    withDerived ? "ontostudio-all-plus-derived.ttl" : "ontostudio-all.ttl",
                    turtleQuery.data,
                    "text/turtle",
                  )
                }
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
        <Panel
          title="快照与恢复"
          subtitle="TriG 全图（含派生）落盘内核卷 · 恢复前自动生成回滚点"
          actions={
            <button
              type="button"
              onClick={() => createSnapMutation.mutate()}
              disabled={createSnapMutation.isPending}
              className="border-border bg-card hover:bg-muted rounded-md border px-2.5 py-1 text-xs font-medium disabled:opacity-50"
            >
              {createSnapMutation.isPending ? "生成中…" : "生成快照"}
            </button>
          }
        >
          <div className="p-4">
            {restoreMsg ? (
              <p
                className={cn(
                  "mb-2 rounded-md border px-2.5 py-1.5 text-xs",
                  restoreMsg.startsWith("已恢复")
                    ? "border-primary/30 bg-primary/5 text-foreground"
                    : "border-destructive/40 bg-destructive/10 text-destructive",
                )}
              >
                {restoreMsg}
              </p>
            ) : null}
            {snapshotsQuery.isLoading ? (
              <p className="text-muted-foreground text-sm">加载快照…</p>
            ) : (snapshotsQuery.data?.snapshots.length ?? 0) === 0 ? (
              <p className="text-muted-foreground text-sm">暂无快照——点「生成快照」把当前内核全图（含派生）落盘。</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-border bg-muted/50 border-b">
                      {["文件", "大小", "时间", "操作"].map((head) => (
                        <th key={head} className="text-muted-foreground px-3 py-2 text-left text-xs font-medium">
                          {head}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-border divide-y">
                    {snapshotsQuery.data!.snapshots.map((snap) => (
                      <tr key={snap.file} className="hover:bg-muted/50">
                        <td className="px-3 py-2 font-mono text-xs">{snap.file}</td>
                        <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                          {(snap.bytes / 1024).toFixed(0)} KB
                        </td>
                        <td className="text-muted-foreground whitespace-nowrap px-3 py-2 text-xs">
                          {new Date(snap.mtime).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              disabled={restoreMutation.isPending}
                              title="清空当前内核全部图并从该快照回灌（恢复前自动生成回滚点）"
                              onClick={() => {
                                if (!window.confirm(`恢复 ${snap.file} 将覆盖当前内核全部图（恢复前自动生成回滚点），确认？`)) return;
                                setRestoreMsg(null);
                                restoreMutation.mutate({ file: snap.file });
                              }}
                              className="text-primary text-xs font-medium hover:underline disabled:opacity-50"
                            >
                              恢复
                            </button>
                            <button
                              type="button"
                              disabled={deleteSnapMutation.isPending}
                              onClick={() => {
                                if (!window.confirm(`删除快照 ${snap.file}？`)) return;
                                deleteSnapMutation.mutate(snap.file);
                              }}
                              className="text-muted-foreground text-xs hover:text-destructive disabled:opacity-50"
                            >
                              删除
                            </button>
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
