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
import { FileText, FileInput, FileUp, Loader2, Trash2, UploadCloud, X } from "lucide-react";
import { useMemo, useRef, useState, type DragEvent } from "react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  // G3 双通道模式切换
  const [taskMode, setTaskMode] = useState<"sample" | "upload">("sample");
  // G3 上传直连（拖拽区对齐知识工厂 ExtractionTaskModal B 模式：暂存文件，底部统一按钮提交）
  const [dragging, setDragging] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("force_review", "true");
      return fetch("/api/ontostudio/api/extensions/ingest-tasks/upload", {
        method: "POST",
        credentials: "include",
        body: fd,
      }).then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `上传失败(${res.status})`);
        }
        return res.json();
      });
    },
    onSuccess: (data) => {
      // 与样例路径同口径：关对话框 + 页面级成功消息（上传端点本身即创建任务）
      setCreateOpen(false);
      setUploadFile(null);
      setCreateMsg(`✓ 已上传并创建任务（直连抽取）——${data.file}`);
      void queryClient.invalidateQueries({ queryKey: ["ingest", "tasks"] });
    },
    onError: (e: Error) => setUploadMsg(`✗ ${e.message}`),
  });

  const handleFileSelect = (files: FileList | null) => {
    const file = files?.[0];
    setUploadFile(file ?? null);
    setUploadMsg(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    handleFileSelect(e.dataTransfer.files);
  };

  // 可建任务样例（新建表单选取源）+ 证据链引文的样例名解析——证据链需要, 常驻拉取
  const samplesQuery = useQuery({
    queryKey: ["ingest", "samples"],
    queryFn: ({ signal }) => fetchSamples(signal),
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
  // 引文人话化（2026-10-05 用户反馈）：doc:kf-sample:<uuid> → 样例标题；
  // extractedBy ingest-task:<uuid> → 「抽取任务 <短id>」；离线管线名原样
  const sampleTitleOf = (docId?: string) => {
    if (!docId) return null;
    const id = docId.split(":").pop() ?? "";
    return samplesQuery.data?.samples.find((s) => s.id === id)?.title ?? null;
  };
  const extractedByLabel = (by: string) =>
    by.startsWith("ingest-task:") ? `抽取任务 ${by.split(":")[1]?.slice(0, 8) ?? ""}` : by;

  return (
    <div className="h-full overflow-x-auto overflow-y-auto">
      <div className="min-w-[1080px] p-6">
        <PageHeader
          icon={FileInput}
          title="抽取导入"
          description="抽取任务队列（实时轮询）、置信度分布与证据链引文。任务双通道：样例有已提取产物 → 直接消费；仅有源文件 → 规则抽取补产物（直连）。开启强制人审的任务会全部进入消解审核。"
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
        </div>
        {loadMutation.isError ? (
          <p className="text-destructive mb-3 text-sm">{loadMsg}</p>
        ) : loadMsg ? (
          <p className="text-success mb-3 text-sm">{loadMsg}</p>
        ) : null}
        {createMsg ? <p className="text-success mb-3 text-sm">{createMsg}</p> : null}

        {/* 新建任务弹出对话框（结构对齐知识工厂 ExtractionTaskModal） */}
        {createOpen ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
            <div className="bg-background flex max-h-[90vh] w-full max-w-2xl flex-col overflow-y-auto rounded-2xl shadow-2xl">
              {/* Header */}
              <div className="border-border bg-background sticky top-0 z-10 flex shrink-0 items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">新建抽取任务</h3>
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="hover:bg-accent rounded-lg p-1.5 transition-colors"
                  aria-label="关闭"
                >
                  <X className="text-muted-foreground h-5 w-5" />
                </button>
              </div>

              {/* Body */}
              <div className="flex-1 space-y-5 px-6 py-5 text-sm">
                {/* 二选一切换（参照知识工厂 ExtractionTaskModal 卡片式模式切换） */}
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setTaskMode("sample")}
                    className={cn(
                      "flex items-start gap-2.5 rounded-lg border-2 p-3 text-left transition-all",
                      taskMode === "sample"
                        ? "border-primary bg-primary/5 shadow-sm"
                        : "border-border hover:border-primary/40 hover:bg-accent/50",
                    )}
                  >
                    <FileText
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        taskMode === "sample" ? "text-primary" : "text-muted-foreground",
                      )}
                    />
                    <div className="min-w-0">
                      <div className={cn("text-sm font-semibold", taskMode === "sample" ? "text-primary" : "text-foreground")}>
                        选择已有样例
                      </div>
                      <div className="text-muted-foreground text-[10px] leading-tight">消费已提取产物入图</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setTaskMode("upload")}
                    className={cn(
                      "flex items-start gap-2.5 rounded-lg border-2 p-3 text-left transition-all",
                      taskMode === "upload"
                        ? "border-primary bg-primary/5 shadow-sm"
                        : "border-border hover:border-primary/40 hover:bg-accent/50",
                    )}
                  >
                    <FileUp
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0",
                        taskMode === "upload" ? "text-primary" : "text-muted-foreground",
                      )}
                    />
                    <div className="min-w-0">
                      <div className={cn("text-sm font-semibold", taskMode === "upload" ? "text-primary" : "text-foreground")}>
                        上传新文件
                      </div>
                      <div className="text-muted-foreground text-[10px] leading-tight">直连规则抽取（txt/docx）</div>
                    </div>
                  </button>
                </div>

                {/* 路径①：选择已有样例 */}
                {taskMode === "sample" && (
                  <div className="flex flex-col gap-2">
                    <label className="text-muted-foreground text-[13px]">选择样例（消费已提取产物）</label>
                    <Select value={sampleId || undefined} onValueChange={(v) => setSampleId(v || "")}>
                      <SelectTrigger className="w-full max-w-xl">
                        <SelectValue placeholder="— 选择 —" />
                      </SelectTrigger>
                      <SelectContent position="popper" className="max-h-72">
                        {(samplesQuery.data?.samples ?? []).filter(s => s.entity_count > 0).map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.title}（{s.entity_count} 实体 · {s.status}）
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {/* 路径②：上传新文件直连抽取（拖拽区样式对齐知识工厂 ExtractionTaskModal B 模式） */}
                {taskMode === "upload" && (
                  <div className="flex flex-col gap-2">
                    <label className="text-foreground text-sm font-medium">
                      上传源文件
                      <span className="text-muted-foreground ml-2 text-xs">直接上传 txt/docx，规则抽取直连入图</span>
                    </label>
                    <div
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragging(true);
                      }}
                      onDragLeave={() => setDragging(false)}
                      onDrop={handleDrop}
                      onClick={() => !uploadMutation.isPending && fileInputRef.current?.click()}
                      className={cn(
                        "cursor-pointer rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
                        dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-accent/30",
                        uploadMutation.isPending && "cursor-wait opacity-80",
                      )}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".txt,.docx"
                        onChange={(e) => handleFileSelect(e.target.files)}
                        disabled={uploadMutation.isPending}
                        className="hidden"
                      />
                      {uploadMutation.isPending ? (
                        <div className="text-muted-foreground flex flex-col items-center gap-2">
                          <Loader2 className="h-7 w-7 animate-spin" />
                          <span className="text-sm">上传抽取中...</span>
                        </div>
                      ) : (
                        <div className="text-muted-foreground flex flex-col items-center gap-2">
                          <UploadCloud className="h-7 w-7" />
                          <span className="text-foreground text-sm font-medium">点击或拖拽 txt/docx 文件到此处</span>
                          <span className="text-xs">支持 .txt / .docx，单文件</span>
                        </div>
                      )}
                    </div>
                    {uploadFile ? (
                      <div className="flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2">
                        <FileText className="h-4 w-4 shrink-0 text-primary" />
                        <span className="min-w-0 flex-1 truncate text-xs font-medium">{uploadFile.name}</span>
                        <span className="text-muted-foreground flex-none text-xs">{(uploadFile.size / 1024).toFixed(0)} KB</span>
                        <button
                          type="button"
                          onClick={() => setUploadFile(null)}
                          className="text-muted-foreground hover:text-destructive ml-1 flex-none text-xs"
                          aria-label="移除文件"
                        >
                          ✕
                        </button>
                      </div>
                    ) : null}
                  </div>
                )}
                {uploadMsg ? <p className="text-destructive text-xs">{uploadMsg}</p> : null}

                <p className="text-muted-foreground text-xs">
                  force_review 默认开启：入库实体全量置待复核（D11/11A），消解审核逐条确认后入图。
                </p>
              </div>

              {/* Footer */}
              <div className="border-border bg-background sticky bottom-0 z-10 flex shrink-0 justify-end gap-3 border-t px-6 py-4">
                <button
                  type="button"
                  onClick={() => setCreateOpen(false)}
                  className="border-border bg-card hover:bg-accent rounded-lg border px-4 py-2 text-sm transition-colors"
                >
                  取消
                </button>
                <button
                  type="button"
                  disabled={
                    createMutation.isPending ||
                    uploadMutation.isPending ||
                    (taskMode === "sample" ? !sampleId : !uploadFile)
                  }
                  onClick={() => {
                    if (taskMode === "sample") createMutation.mutate();
                    else if (uploadFile) uploadMutation.mutate(uploadFile);
                  }}
                  className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createMutation.isPending || uploadMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> 创建中...
                    </>
                  ) : (
                    "创建并排队"
                  )}
                </button>
              </div>
            </div>
          </div>
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
                  {["来源", "创建时间", "域", "状态", "进度", "实体", "关系", "提及", "操作"].map((head, index) => (
                    <th
                      key={head}
                      className={cn(
                        "text-muted-foreground px-4 py-2 text-xs font-medium whitespace-nowrap",
                        index >= 4 && index <= 6 ? "text-right" : "text-left",
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
                    <td colSpan={9} className="text-muted-foreground px-4 py-6 text-center text-sm">
                      <Loader2 className="mr-1.5 inline h-3.5 w-3.5 animate-spin" />
                      加载任务队列…
                    </td>
                  </tr>
                ) : tasks.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-muted-foreground px-4 py-6 text-center text-sm">
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
                      {/* G6 进度列：loading 阶段实时百分比（独立连接写 stats），完成 ✓，其余 — */}
                      <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">
                        {isActiveStatus(task.status) && task.stats?.progress?.pct != null
                          ? `${task.stats.progress.pct}%`
                          : task.status === "done"
                            ? "✓"
                            : "—"}
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
                    <blockquote className="leading-relaxed">
                      {m.quote ? (
                        `"${m.quote}"`
                      ) : (
                        <span className="text-muted-foreground">（离线批量抽取产物未携带原文引文）</span>
                      )}
                    </blockquote>
                    <figcaption className="text-muted-foreground/80 mt-1 text-xs">
                      来源样例 {sampleTitleOf(m.documentId) ?? `doc:${(m.documentId || "").split(":").pop()?.slice(0, 8) || "—"}`}
                      {m.threadId ? ` · 会话 ${m.threadId.slice(0, 6)}` : ""}
                      {m.extractedBy ? ` · ${extractedByLabel(m.extractedBy)}` : ""}
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