/**
 * 08 抽取导入（EAI-CUSTOM, 2026-09-27 原型移植）——完全对照
 * docs/designs/designs/ontostudio-frontend-redesign-20260926.html#ingest：
 *
 * - 顶部动作行：新建抽取任务（规划·任务API）/ 从主系统线程导入（真端点
 *   POST /formal/load——dg_* 全量装载）+ 生产线口径注（regex/v1）；
 * - 抽取任务队列（静态示例，DemoTag 标注——「任务」概念后端 TODOS，见 TODOS.md）；
 * - 置信度分布（横向条）+ 证据链引文（mention 永不删）。
 * 生产线口径：regex/v1 确定性正则（etype/谓词与 eia.yaml 枚举严格同名，kernel loader 直读）。
 */
import { useMutation } from "@tanstack/react-query";
import { FileInput, Loader2 } from "lucide-react";
import { useState } from "react";

import { runFormalLoad } from "@/api/formal-api";
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";
import { cn } from "@/lib/utils";

const HISTO: Array<{ count: number; bucket: string }> = [
  { count: 38, bucket: "<.6" },
  { count: 72, bucket: ".6+" },
  { count: 118, bucket: ".7+" },
  { count: 161, bucket: ".8+" },
  { count: 244, bucket: ".9+" },
  { count: 205, bucket: "1.0" },
];
const HISTO_MAX = Math.max(...HISTO.map((bar) => bar.count));

type TaskStatus = "完成" | "抽取中" | "排队中";
const STATUS_DOT: Record<TaskStatus, string> = {
  完成: "bg-success",
  抽取中: "bg-primary",
  排队中: "bg-warning",
};

interface Task {
  doc: string;
  domain: string;
  status: TaskStatus;
  progress?: string;
  e: string;
  r: string;
  m: string;
}

const TASKS: Task[] = [
  { doc: "环评报告-横城（送审稿）.docx", domain: "eia", status: "完成", e: "460", r: "205", m: "318" },
  { doc: "横城煤矿投标文件-2024-017.pdf", domain: "doc_graph", status: "抽取中", progress: "62%", e: "87", r: "104", m: "156" },
  { doc: "中标候选人公示-0912.pdf", domain: "bid_quote", status: "抽取中", progress: "31%", e: "22", r: "35", m: "48" },
  { doc: "GB 13223-2011 火电厂大气污染物排放标准.pdf", domain: "eia", status: "排队中", e: "—", r: "—", m: "—" },
];

const QUOTES = [
  {
    text: "投标人须同时具备环保工程专业承包一级资质与煤矿设备安装一级资质。",
    src: "doc:标书-2024-017 · thread:2f8a… · extracted_by: regex/v1",
  },
  {
    text: "锅炉烟气采用双碱法脱硫后经 45m 烟囱排放，执行 GB 13223-2011 规定限值。",
    src: "doc:环评报告-横城 · thread:9d11… · extracted_by: regex/v1",
  },
];

export function IngestPage() {
  // 从主系统线程导入 = POST /formal/load（dg_* 全量装载，真端点）
  const [loadMsg, setLoadMsg] = useState<string | null>(null);
  const loadMutation = useMutation({
    mutationFn: () => runFormalLoad(),
    onSuccess: (data) =>
      setLoadMsg(`✓ 已装载 ${data.entities} 实体 / ${data.relations} 关系 / ${data.mentions} 提及——图已对账，可在消解审核处理待审、在导出互操作查看图面`),
    onError: (e) => setLoadMsg(`装载失败：${e instanceof Error ? e.message : String(e)}`),
  });

  return (
    /* 纵向滚动层（样式=全站 6px 细条）+ min-w 保底（同总览/实体库手法） */
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
        <PageHeader
          icon={FileInput}
          title="抽取导入"
          description="重构点：旧版纯静态。真数据化需要后端补「抽取任务」概念（TODOS 关联）——任务队列、进度、置信度直方图、证据链引文均挂在新任务实体上。"
        />

        {/* 顶部动作行（原型） */}
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
            生产线 <span className="text-foreground font-mono">regex/v1</span>
            （确定性正则，etype/谓词与 eia.yaml 枚举严格同名）· LLM 辅助精标规划中 ·
            月儿湾全链路：抽取 460 实体 / 205 关系 / 318 提及 → 装载 → infer 1857 物化
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

        {/* 置信度分布 + 证据链引文 */}
        <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-2">
          <Panel title="置信度分布" subtitle="月儿湾实体（示例数据）" actions={<DemoTag />}>
            <div className="flex flex-col gap-2 p-4">
              {HISTO.map((bar) => (
                <div key={bar.bucket} className="flex items-center gap-2.5 text-[11.5px]">
                  <span className="text-muted-foreground w-9 flex-none font-mono">{bar.bucket}</span>
                  <div className="bg-muted h-3.5 min-w-0 flex-1 overflow-hidden rounded">
                    <div
                      className="bg-primary/85 h-full rounded"
                      style={{ width: `${(bar.count / HISTO_MAX) * 100}%` }}
                    />
                  </div>
                  <span className="w-9 flex-none text-right font-mono tabular-nums">{bar.count}</span>
                </div>
              ))}
              <p className="text-muted-foreground mt-1 text-[11px]">
                低置信段（&lt;.7）优先进入人审队列；高置信段供方案 C（agent 预审）自动确认。
              </p>
            </div>
          </Panel>

          <Panel
            title="证据链引文"
            subtitle="mention 永不删"
            actions={<DemoTag />}
          >
            <div className="flex flex-col gap-2.5 p-4">
              {QUOTES.map((quote) => (
                <figure
                  key={quote.text}
                  className="border-border bg-muted rounded-lg border px-3 py-2.5 text-xs"
                >
                  <blockquote>"{quote.text}"</blockquote>
                  <figcaption className="text-muted-foreground/80 mt-1 font-mono text-[10.5px]">
                    {quote.src}
                  </figcaption>
                </figure>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
