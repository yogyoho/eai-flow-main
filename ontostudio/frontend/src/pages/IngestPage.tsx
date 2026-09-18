/**
 * 08 抽取导入骨架页（EAI-CUSTOM）：投放区 + 置信度直方图 + 抽取任务表 + 证据链引文（静态示例）。
 * 真实数据面待 kernel P2（ingest 管线级幂等 + mentions API）。
 */
import { Chip, DemoTag, PageHeader, Panel } from "@/pages/shared";

const HISTO: Array<{ count: number; bucket: string }> = [
  { count: 38, bucket: "<.6" },
  { count: 72, bucket: ".6+" },
  { count: 118, bucket: ".7+" },
  { count: 161, bucket: ".8+" },
  { count: 244, bucket: ".9+" },
  { count: 205, bucket: "1.0" },
];

const TASKS = [
  { doc: "横城煤矿投标文件-2024-017.pdf", domain: "doc_graph", status: "完成", done: true, e: "142", r: "231", m: "318" },
  { doc: "环评报告-横城（送审稿）.docx", domain: "eia", status: "抽取中 62%", done: false, e: "87…", r: "104…", m: "156…" },
  { doc: "中标候选人公示-0912.pdf", domain: "doc_graph", status: "抽取中 31%", done: false, e: "22…", r: "35…", m: "48…" },
  { doc: "GB 13223-2011 火电厂大气污染物排放标准.pdf", domain: "eia", status: "排队中", done: true, e: "—", r: "—", m: "—" },
];

const QUOTES = [
  {
    text: "投标人须同时具备环保工程专业承包一级资质与煤矿设备安装一级资质。",
    src: "doc:标书-2024-017 · thread:2f8a… · extracted_by: llm/v3",
  },
  {
    text: "锅炉烟气采用双碱法脱硫后经 45m 烟囱排放，执行 GB 13223-2011 规定限值。",
    src: "doc:环评报告-横城 · thread:9d11… · extracted_by: llm/v3",
  },
];

const MAX = Math.max(...HISTO.map((bar) => bar.count));

export function IngestPage() {
  return (
    <div className="p-6">
      <PageHeader
        clause="08 · 抽取"
        title="抽取导入"
        description="文档 → LLM 类型化抽取 → mentions 证据落图 · 幂等管线（自然键去重）· 低置信度仅存证"
      />
      <div className="grid grid-cols-1 gap-3.5 xl:grid-cols-[1fr_1.6fr]">
        <div className="flex flex-col gap-3.5">
          <div className="border-primary/30 bg-muted hover:border-primary/60 rounded-lg border-[1.5px] border-dashed p-6 text-center transition-colors">
            <div className="text-[15px] font-semibold">投放待抽取文档</div>
            <div className="text-muted-foreground mt-0.5 text-xs">
              支持 PDF / DOCX / MD · 自动识别域与文档类型 · 幂等可重投
            </div>
            <button className="bg-primary text-primary-foreground mt-3 h-8 rounded-lg px-3.5 text-xs font-medium">
              选择文件
            </button>
          </div>
          <Panel title="置信度分布" subtitle="最近 30 天实体">
            <div className="flex h-[110px] items-end gap-1.5 px-4 pt-5 pb-6">
              {HISTO.map((bar) => (
                <div
                  key={bar.bucket}
                  className="bg-primary/85 hover:bg-primary relative min-w-3.5 flex-1 rounded-t"
                  style={{ height: `${(bar.count / MAX) * 100}%` }}
                  title={`${bar.bucket}：${bar.count}`}
                >
                  <b className="text-muted-foreground absolute -top-4 left-1/2 -translate-x-1/2 text-[10px] font-medium tabular-nums">
                    {bar.count}
                  </b>
                  <span className="text-muted-foreground absolute -bottom-5.5 left-1/2 -translate-x-1/2 font-mono text-[10px]">
                    {bar.bucket}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
        <Panel
          title="抽取任务"
          actions={<Chip tone="primary">3 运行中</Chip>}
          className="self-start"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-border border-b">
                  {["文档", "域", "状态", "实体", "关系", "证据"].map((head, index) => (
                    <th
                      key={head}
                      className={`text-muted-foreground px-3.5 py-2.5 text-xs font-medium whitespace-nowrap ${index >= 3 ? "text-right" : "text-left"}`}
                    >
                      {head}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TASKS.map((task) => (
                  <tr key={task.doc} className="border-border/60 hover:bg-accent/60 border-b">
                    <td className="px-3.5 py-2.5 font-medium">{task.doc}</td>
                    <td className="text-muted-foreground px-3.5 py-2.5 font-mono text-xs">{task.domain}</td>
                    <td className="px-3.5 py-2.5">
                      <Chip tone={task.status === "完成" ? "primary" : task.status === "排队中" ? "gray" : "warning"}>
                        {task.status}
                      </Chip>
                    </td>
                    <td className="px-3.5 py-2.5 text-right tabular-nums">{task.e}</td>
                    <td className="px-3.5 py-2.5 text-right tabular-nums">{task.r}</td>
                    <td className="px-3.5 py-2.5 text-right tabular-nums">{task.m}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-border flex items-center gap-2.5 border-t px-4 py-3">
            <b className="text-sm font-semibold">最新证据链片段</b>
            <DemoTag className="ml-auto" />
          </div>
          <div className="flex flex-col gap-2 p-4 pt-0">
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
  );
}
