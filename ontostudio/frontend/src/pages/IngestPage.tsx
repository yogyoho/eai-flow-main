/**
 * 08 抽取导入（EAI-CUSTOM, 2026-09-28 审计升级；09-29 口径订正）——真数据区块：
 *
 * - 置信度分布：graph_entity objects → 客户端分桶计算（真数据）；
 * - 证据链引文：graph_mention objects → 按 extracted_at 倒序取最近 5 条（真数据）；
 * - 抽取任务队列：静态示例（DemoTag 标注——「任务」概念后端 TODOS）；
 * - 从主系统线程导入：POST /formal/load 真端点（dg_* 全量装载）。
 * 生产线口径：LLM 离线批量管线（extracted_by=eia-batch-v2-llm，etype/谓词与 eia.yaml v2 枚举严格同名，kernel loader 直读）。
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileInput, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

import { runFormalLoad } from "@/api/formal-api";
import { fetchObjects } from "@/api/ontology-graph-api";
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

/* 静态示例——「抽取任务」概念后端 TODOS，落地后替换为真 API。 */
interface Task {
  doc: string;
  domain: string;
  status: "完成" | "抽取中" | "排队中";
  progress?: string;
  e: string;
  r: string;
  m: string;
}

const STATUS_DOT: Record<Task["status"], string> = {
  完成: "bg-success",
  抽取中: "bg-primary",
  排队中: "bg-warning",
};

const TASKS: Task[] = [
  { doc: "环评报告-横城（送审稿）.docx", domain: "eia", status: "完成", e: "460", r: "205", m: "318" },
  { doc: "横城煤矿投标文件-2024-017.pdf", domain: "doc_graph", status: "抽取中", progress: "62%", e: "87", r: "104", m: "156" },
  { doc: "中标候选人公示-0912.pdf", domain: "bid_quote", status: "抽取中", progress: "31%", e: "22", r: "35", m: "48" },
  { doc: "GB 13223-2011 火电厂大气污染物排放标准.pdf", domain: "eia", status: "排队中", e: "—", r: "—", m: "—" },
];

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
  // 从主系统线程导入 = POST /formal/load（dg_* 全量装载，真端点）
  const [loadMsg, setLoadMsg] = useState<string | null>(null);
  const loadMutation = useMutation({
    mutationFn: () => runFormalLoad(),
    onSuccess: (data) =>
      setLoadMsg(`✓ 已装载 ${data.entities} 实体 / ${data.relations} 关系 / ${data.mentions} 提及——图已对账，可在消解审核处理待审、在导出互操作查看图面`),
    onError: (e) => setLoadMsg(`装载失败：${e instanceof Error ? e.message : String(e)}`),
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
          description="真数据区块：置信度分布（graph_entity 实时统计）+ 证据链引文（graph_mention 最近记录）。任务队列为静态示例（DemoTag——「任务」概念后端 TODOS）。"
        />

        {/* 顶部动作行 */}
        <div className="mb-3.5 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled
            title="规划中（任务 API）"
            className="bg-primary text-primary-foreground flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium opacity-60"
          >
            ＋ 新建抽取任务
            <span className="rounded bg-white/15 px-1 py-px font-mono text-[10px]">规划·任务API</span>
          </button>
          <button
            type="button"
            disabled={loadMutation.isPending}
            onClick={() => loadMutation.mutate()}
            className="border-border bg-card hover:bg-muted flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            {loadMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            从主系统线程导入
          </button>
          <span className="text-muted-foreground ml-auto max-w-[52ch] text-[11px] leading-relaxed">
            抽取来源 <span className="text-foreground font-mono">eia-batch-v2-llm</span>
            （LLM 离线批量管线，etype/谓词与 eia.yaml v2 枚举严格同名）· 在线任务 API 规划中 ·
            v1 历史参考：月儿湾全链路 460 实体 / 205 关系 / 318 提及 → 装载 → infer 1857 物化（该批 v1 数据已清除）
          </span>
        </div>
        {loadMutation.isError ? (
          <p className="text-destructive mb-3 text-xs">{loadMsg}</p>
        ) : loadMsg ? (
          <p className="text-success mb-3 text-xs">{loadMsg}</p>
        ) : null}

        {/* 抽取任务队列（静态示例——「任务」概念后端 TODOS） */}
        <Panel
          title="抽取任务"
          actions={
            <span className="flex items-center gap-1.5">
              <Chip tone="warning">2 进行中</Chip>
              <DemoTag />
            </span>
          }
          className="mb-3.5 overflow-hidden"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-border bg-muted/60 border-b">
                  {["来源", "域 profile", "状态", "实体", "关系", "提及", "操作"].map((head, index) => (
                    <th
                      key={head}
                      className={cn(
                        "text-muted-foreground px-4 py-2 text-[11.5px] font-medium whitespace-nowrap",
                        index >= 3 && index <= 5 ? "text-right" : "text-left",
                      )}
                    >
                      {head}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TASKS.map((task) => (
                  <tr key={task.doc} className="border-border hover:bg-muted/50 border-b last:border-b-0">
                    <td className="max-w-[20rem] truncate px-4 py-2.5 font-medium">{task.doc}</td>
                    <td className="text-muted-foreground px-4 py-2.5 font-mono text-xs">{task.domain}</td>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2 text-xs">
                        <span className={cn("inline-block h-2 w-2 flex-none rounded-full", STATUS_DOT[task.status])} />
                        {task.status}
                        {task.progress ? (
                          <span className="text-muted-foreground tabular-nums">{task.progress}</span>
                        ) : null}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{task.e}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{task.r}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{task.m}</td>
                    <td className="px-4 py-2.5 text-right">
                      {task.status === "完成" ? (
                        <button
                          type="button"
                          onClick={() => {
                            window.location.hash = "resolve";
                          }}
                          className="border-border bg-card hover:bg-muted rounded-md border px-2 py-1 text-[11px] font-medium"
                        >
                          送审待复核
                        </button>
                      ) : task.status === "排队中" ? (
                        <button
                          type="button"
                          disabled
                          title="任务 API 规划中"
                          className="border-border bg-card rounded-md border px-2 py-1 text-[11px] opacity-50"
                        >
                          ↑ 提前
                        </button>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">等待完成</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* 置信度分布（真数据） + 证据链引文（真数据） */}
        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
          <Panel title="置信度分布" subtitle="graph_entity 实时统计">
            <div className="flex flex-col gap-2 p-4">
              {entitiesQuery.isLoading ? (
                <div className="text-muted-foreground flex items-center justify-center gap-2 py-4 text-xs">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  加载实体…
                </div>
              ) : (
                histogram.map((bar) => (
                  <div key={bar.label} className="flex items-center gap-2.5 text-[11.5px]">
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
              <p className="text-muted-foreground mt-1 text-[11px]">
                低置信段（&lt;.7）优先进入人审队列；高置信段规划供方案 C（agent 预审）自动确认（后端规划中）。
              </p>
            </div>
          </Panel>

          <Panel title="证据链引文" subtitle="mention 永不删">
            <div className="flex flex-col gap-2.5 p-4">
              {mentionsQuery.isLoading ? (
                <div className="text-muted-foreground flex items-center justify-center gap-2 py-4 text-xs">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  加载最近引文…
                </div>
              ) : recentMentions.length === 0 ? (
                <div className="text-muted-foreground px-2 py-6 text-center text-xs">
                  暂无提及记录——抽取导入后证据链在此展示
                </div>
              ) : (
                recentMentions.map((m) => (
                  <figure
                    key={m.id}
                    className="border-border bg-muted rounded-lg border px-3 py-2.5 text-xs"
                  >
                    <blockquote>{m.quote ? `"${m.quote}"` : "—"}</blockquote>
                    <figcaption className="text-muted-foreground/80 mt-1 font-mono text-[10.5px]">
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