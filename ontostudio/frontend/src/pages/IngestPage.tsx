/**
 * 08 抽取导入（EAI-CUSTOM, 2026-09-28 审计升级；2026-10-01 T6 队列接真）——真数据区块：
 *
 * - 抽取任务队列：GET /ingest-tasks 真数据 + 2s 轮询（阶段枚举文案，无百分比——后端无进度生产者）；
 * - 新建抽取任务：POST /ingest-tasks（sample 选自 kf_samples 已提取产物）；
 * - 置信度分布：graph_entity objects → 客户端分桶计算（真数据）；
 * - 证据链引文：graph_mention objects → 按 extracted_at 倒序取最近 5 条（真数据）；
 * - 从主系统线程导入：POST /formal/load 真端点（dg_* 全量装载）。
 * 生产线口径：LLM 离线批量管线（extracted_by=eia-batch-v2-llm，etype/谓词与 eia.yaml v2 枚举严格同名，kernel loader 直读）。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileInput, Loader2, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import {
  createTask,
  deleteTask,
  fetchSamples,
  fetchTasks,
  isActiveStatus,
  STATUS_DOT,
  STATUS_LABEL,
  type IngestTask,
  type TaskStatus,
} from "@/api/ingest-tasks-api";
import { runFormalLoad } from "@/api/formal-api";
import { fetchObjects } from "@/api/ontology-graph-api";
import { domainAlias } from "@/lib/terms";
import { Chip, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

/* 置信度分桶定义 */
const BUCKETS = [
  { label: "<.6", min: 0, max: 0.6 },
  { label: ".6+", min: 0.6, max: 0.7 },
  { label: ".7+", min: 0.7, max: 0.8 },
  { label: ".8+", min: 0.8, max: 0.9 },
  { label: ".9+", min: 0.9, max: 1.0 },
  { label: "1.0", min: 1.0, max: 1.01 },
] as const;

interface Mention {
  id: string;
  quote?: string;
  documentId?: string;
  threadId?: string;
  extractedBy?: string;
}

export function IngestPage() {
  const queryClient = useQueryClient();
  // 从主系统线程导入 = POST /formal/load（dg_* 全量装载，真端点）
  const [loadMsg, setLoadMsg] = useState<string | null>(null);
  const loadMutation = useMutation({
    mutationFn: () => runFormalLoad(),
    onSuccess: (data) => {
      setLoadMsg(`✓ 已装载 ${data.entities} 实体 / ${data.relations} 关系 / ${data.mentions} 提及——图已对账，可在消解审核处理待审、在导出互操作查看图面`);
      // 装载重写内核图 → 校验中心缓存失效
      void queryClient.invalidateQueries({ queryKey: ["formal", "validate"] });
    },
    onError: (e) => setLoadMsg(`装载失败：${e instanceof Error ? e.message : String(e)}`),
  });

  // 抽取任务队列（真数据，2s 轮询——T6；有活动任务才轮也行，v1 恒轮代价可忽略）
  const tasksQuery = useQuery({
    queryKey: ["ingest", "tasks"],
    queryFn: ({ signal }) => fetchTasks(signal),
    refetchInterval: 2000,
  });
  const tasks: IngestTask[] = tasksQuery.data?.tasks ?? [];
  const activeCount = tasks.filter((t) => isActiveStatus(t.status)).length;

  // 新建任务（内联表单）
  const [createOpen, setCreateOpen] = useState(false);
  const [sampleId, setSampleId] = useState("");
  const [createMsg, setCreateMsg] = useState<string | null>(null);

  // 可建任务样例（新建表单选取源）
  const samplesQuery = useQuery({
    queryKey: ["ingest", "samples"],
    queryFn: ({ signal }) => fetchSamples(signal),
    enabled: createOpen,
    staleTime: 30_000,
  });
  const createMutation = useMutation({
    mutationFn: () => createTask({ sample_id: sampleId, force_review: true }),
    onSuccess: () => {
      setCreateOpen(false);
      setSampleId("");
      setCreateMsg("✓ 任务已排队——队列将实时推进，完成后可送审待复核");
      queryClient.invalidateQueries({ queryKey: ["ingest", "tasks"] });
    },
    onError: (e) => setCreateMsg(`创建失败：${e instanceof Error ? e.message : String(e)}`),
  });

  // 删除/中止任务
  const deleteMutation = useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ingest", "tasks"] }),
  });

  // 置信度分布（真数据）：graph_entity objects → 客户端分桶计算
  const entitiesQuery = useQuery({
    queryKey: ["ontology", "objects", "graph_entity", "confidence-dist"],
    queryFn: ({ signal }) => fetchObjects("graph_entity", { limit: 200, signal }),
    staleTime: 60_000,
  });

  // 证据链引文（真数据）：最近 mentions 按 extracted_at 倒序
  const mentionsQuery = useQuery({
    queryKey: ["ontology", "mentions", "recent"],
    queryFn: ({ signal }) =>
      fetchObjects("graph_mention", { order: "extracted_at", desc: true, limit: 5, signal }),
    staleTime: 60_000,
  });

  // 客户端置信度分桶
  const histogram = useMemo(() => {
    const counts = BUCKETS.map((b) => ({ ...b, count: 0 }));
    for (const row of entitiesQuery.data?.data ?? []) {
      const conf = Number(row.confidence);
      if (isNaN(conf)) continue;
      for (const bucket of counts) {
        if (conf >= bucket.min && conf < bucket.max) {
          bucket.count++;
          break;
        }
      }
    }
    return counts;
  }, [entitiesQuery.data]);
  const histoMax = Math.max(...histogram.map((h) => h.count), 1);

  // 真实提及 → 证据链引文
  const recentMentions = (mentionsQuery.data?.data ?? []).slice(0, 5) as Array<{
    id: string;
    quote?: string;
    documentId?: string;
    threadId?: string;
    extractedBy?: string;
  }>;

  return (
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
        <PageHeader
          icon={FileInput}
          title="抽取导入"
          description="抽取任务队列（实时轮询）、置信度分布与证据链引文。任务=把样例库已提取产物转换并批量写入图谱；开启强制人审的任务会全部进入消解审核。"
        />

        {/* 顶部动作行 */}
        <div className="mb-3.5 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setCreateOpen((v) => !v)}
            className="bg-primary text-primary-foreground flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium hover:opacity-90"
          >
            ＋ 新建抽取任务
          </button>
          <button
            type="button"
            disabled={loadMutation.isPending}
            onClick={() => {
              // G4 同款（与总览页全量装载一致，2026-10-02 审核补齐一致性）：重操作二次确认
              if (window.confirm("全量装载将重写图数据全表（耗时数十秒），确认执行？")) {
                loadMutation.mutate();
              }
            }}
            className="border-border bg-card hover:bg-muted flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            {loadMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            从主系统线程导入
          </button>
          <span className="text-muted-foreground ml-auto max-w-[52ch] text-xs leading-relaxed">
            抽取来源 <span className="text-foreground font-mono">eia-batch-v2-llm</span>
            （LLM 离线批量管线）· 在线任务 = 消费已提取产物入图（v1）·
            v1 历史参考：月儿湾全链路 460 实体 / 205 关系 / 318 提及 → 装载 → infer 1857 物化（该批 v1 数据已清除）
          </span>
        </div>
        {loadMutation.isError ? (
          <p className="text-destructive mb-3 text-sm">{loadMsg}</p>
        ) : loadMsg ? (
          <p className="text-success mb-3 text-sm">{loadMsg}</p>
        ) : null}
        {createMsg ? <p className="text-success mb-3 text-sm">{createMsg}</p> : null}

        {/* 新建任务内联表单 */}
        {createOpen ? (
          <Panel title="新建抽取任务" className="mb-3.5">
            <div className="flex flex-col gap-2 p-4 text-sm">
              <label className="text-muted-foreground text-[13px]">
                选择样例（已提取产物）：
                <select
                  value={sampleId}
                  onChange={(e) => setSampleId(e.target.value)}
                  className="border-input bg-card mt-1 w-full max-w-xl rounded-md border px-2.5 py-1.5 text-sm"
                >
                  <option value="">— 选择 —</option>
                  {(samplesQuery.data?.samples ?? []).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}（{s.entity_count} 实体 · {s.status}）
                    </option>
                  ))}
                </select>
              </label>
              <p className="text-muted-foreground text-xs">
                force_review 默认开启：入库实体全量置待复核（D11/11A），消解审核逐条确认后入图。
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={!sampleId || createMutation.isPending}
                  onClick={() => createMutation.mutate()}
                  className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  {createMutation.isPending ? <Loader2 className="inline h-3.5 w-3.5 animate-spin" /> : null}
                  创建并排队
                </button>
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="border-border bg-card rounded-md border px-3 py-1.5 text-sm"
                >
                  取消
                </button>
                {createMutation.isError ? (
                  <span className="text-destructive text-xs">{createMsg}</span>
                ) : null}
              </div>
            </div>
          </Panel>
        ) : null}

        {/* 抽取任务队列（真数据，2s 轮询） */}
        <Panel
          title="抽取任务"
          actions={
            activeCount > 0 ? (
              <Chip tone="warning">{activeCount} 进行中</Chip>
            ) : (
              <span className="text-muted-foreground text-xs">空闲</span>
            )
          }
          className="mb-3.5 overflow-hidden"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-border bg-muted/60 border-b">
                  {["来源", "创建时间", "域", "状态", "实体", "关系", "提及", "操作"].map((head, index) => (
                    <th
                      key={head}
                      className={cn(
                        "text-muted-foreground px-4 py-2 text-xs font-medium whitespace-nowrap",
                        index >= 3 && index <= 5 ? "text-right" : "text-left",
                      )}
                    >
                      {head}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tasksQuery.isLoading ? (
                  <tr>
                    <td colSpan={8} className="text-muted-foreground px-4 py-6 text-center text-sm">
                      <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" />
                      加载任务队列…
                    </td>
                  </tr>
                ) : tasks.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-muted-foreground px-4 py-6 text-center text-sm">
                      队列为空——点「＋ 新建抽取任务」从已提取样例创建
                    </td>
                  </tr>
                ) : (
                  tasks.map((task: IngestTask) => (
                    <tr key={task.id} className="border-border hover:bg-muted/50 border-b last:border-b-0">
                      <td className="max-w-[20rem] truncate px-4 py-2.5 font-medium" title={task.error || task.sample_title || task.document_id}>
                        {task.sample_title || task.document_id}
                        {task.error ? <span className="text-destructive ml-1.5 text-xs">⚠</span> : null}
                      </td>
                      <td className="text-muted-foreground whitespace-nowrap px-4 py-2.5 text-xs tabular-nums">
                        {task.created_at
                          ? new Date(task.created_at).toLocaleString("zh-CN", {
                              month: "2-digit",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                      {/* 域：v1 任务通道仅 eia（IngestTask 无 domain 字段）——多域任务落地后改 task.domain 数据驱动 */}
                      <td className="text-muted-foreground px-4 py-2.5 font-mono text-sm" title={domainAlias("eia") ?? "eia"}>
                        eia
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="flex items-center gap-2 font-medium">
                          <span className={cn("inline-block h-2 w-2 flex-none rounded-full", STATUS_DOT[task.status])} />
                          {STATUS_LABEL[task.status]}
                          {isActiveStatus(task.status) ? (
                            <Loader2 className="text-muted-foreground h-3 w-3 animate-spin" />
                          ) : null}
                        </span>
                        {task.error ? (
                          <span className="text-destructive mt-0.5 block max-w-[24rem] truncate text-xs" title={task.error}>
                            {task.error}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{task.stats?.entities_upserted ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{task.stats?.relations ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{task.stats?.mentions ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right">
                        {task.status === "done" ? (
                          <button
                            type="button"
                            onClick={() => {
                              window.location.hash = "resolve";
                            }}
                            title={`本任务 ${task.stats?.entities_upserted ?? "—"} 条实体已入待审队列；队列按置信度升序排列，force_review 批次（0.85+）位于列表后段——用搜索或逐条确认处理`}
                            className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-xs font-medium"
                          >
                            查看待审队列
                          </button>
                        ) : isActiveStatus(task.status) ? (
                          <button
                            type="button"
                            disabled={deleteMutation.isPending}
                            onClick={() => deleteMutation.mutate(task.id)}
                            title="中止任务（运行中=置已中止标记，不强杀进程）"
                            className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-xs font-medium disabled:opacity-50"
                          >
                            <Trash2 className="inline h-3 w-3" /> 中止
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={deleteMutation.isPending}
                            onClick={() => deleteMutation.mutate(task.id)}
                            title="从队列移除该任务行"
                            className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-xs font-medium disabled:opacity-50"
                          >
                            移除
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* 置信度分布（真数据） + 证据链引文（真数据） */}
        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
          <Panel title="置信度分布" subtitle="graph_entity 最新 200 行抽样">
            <div className="flex flex-col gap-2 p-4">
              {entitiesQuery.isLoading ? (
                <div className="text-muted-foreground flex items-center justify-center gap-2 py-4 text-sm">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  加载实体…
                </div>
              ) : (
                histogram.map((bar) => (
                  <div key={bar.label} className="flex items-center gap-2.5 text-xs">
                    <span className="text-muted-foreground w-9 flex-none font-mono">{bar.label}</span>
                    <div className="bg-muted h-3.5 min-w-0 flex-1 overflow-hidden rounded">
                      <div
                        className="bg-primary/85 h-full rounded"
                        style={{ width: `${(bar.count / histoMax) * 100}%` }}
                      />
                    </div>
                    <span className="w-9 flex-none text-right font-mono tabular-nums">{bar.count}</span>
                  </div>
                ))
              )}
              <p className="text-muted-foreground mt-1 text-xs">
                低置信段（&lt;.7）优先进入人审队列；高置信段规划供方案 C（agent 预审）自动确认（后端规划中）。
              </p>
            </div>
          </Panel>

          <Panel title="证据链引文" subtitle="mention 永不删">
            <div className="flex flex-col gap-2.5 p-4">
              {mentionsQuery.isLoading ? (
                <div className="text-muted-foreground flex items-center justify-center gap-2 py-4 text-sm">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  加载最近引文…
                </div>
              ) : recentMentions.length === 0 ? (
                <div className="text-muted-foreground px-2 py-6 text-center text-sm">
                  暂无提及记录——抽取导入后证据链在此展示
                </div>
              ) : (
                recentMentions.map((m) => (
                  <figure
                    key={m.id}
                    className="border-border bg-muted rounded-lg border px-3 py-2.5 text-sm"
                  >
                    <blockquote>{m.quote ? `"${m.quote}"` : <span className="text-muted-foreground">（无上下文引文——产物消费路径不含句子级 quote）</span>}</blockquote>
                    <figcaption className="text-muted-foreground/80 mt-1 font-mono text-xs">
                      doc:{m.documentId || "—"} · thread:{m.threadId?.slice(0, 6) || "—"}
                      {m.extractedBy ? ` · ${m.extractedBy}` : ""}
                    </figcaption>
                  </figure>
                ))
              )}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}