"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 DocumentsView — bid-quote 原语体系
// (StatCard 统计头 / SectionCard 容器 / FilterBar 筛选条 / ui table),
// 信息架构与计划一致:report_id/文件/阶段/矿种/状态/脱敏摘要/操作 + 上传表单 + 动作按钮。
import { FileStack, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { geoSamplesApi } from "@/extensions/geo-samples/api";
import {
  AMBER,
  BLUE,
  GREEN,
  INK,
  INK_2,
  INK_3,
  PAGE_BG,
  RED,
} from "@/extensions/geo-samples/components/chartTheme";
import {
  FilterBar,
  MINERAL_OPTIONS,
  STAGE_OPTIONS,
  STATUS_OPTIONS,
  type GsbDocFilters,
} from "@/extensions/geo-samples/components/FilterBar";
import { SectionCard } from "@/extensions/geo-samples/components/SectionCard";
import { StatCard } from "@/extensions/geo-samples/components/StatCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/geo-samples/components/ui/table";
import {
  useGsbAction,
  useGsbCompile,
  useGsbDelete,
  useGsbDocuments,
  useGsbUpload,
} from "@/extensions/geo-samples/hooks";

// 未知状态兜底(Phase 2 后端先行加 compiled 等新值时):显示原文字符 + 中性灰,行不空白不崩溃
const STATUS_LABEL: Record<string, string> = Object.fromEntries(
  STATUS_OPTIONS.map((o) => [o.value, o.label]),
);
const STATUS_COLOR: Record<string, string> = {
  uploaded: INK_2,
  parsed: BLUE,
  redacted: AMBER,
  reviewed: GREEN,
  failed: RED,
  compiled: BLUE, // 编译终态(成功语义,与 reviewed GREEN 区分)
};
const STAGE_LABEL: Record<string, string> = Object.fromEntries(
  STAGE_OPTIONS.map((o) => [o.value, o.label]),
);
const MINERAL_LABEL: Record<string, string> = Object.fromEntries(
  MINERAL_OPTIONS.map((o) => [o.value, o.label]),
);

const ACT_BTN =
  "border-border text-foreground hover:border-foreground/40 cursor-pointer rounded border px-2 py-0.5 text-xs transition-colors";

const PAGE_BTN =
  "border-border text-foreground hover:border-foreground/40 cursor-pointer rounded border px-2 py-0.5 text-xs transition-colors disabled:cursor-default disabled:opacity-40";

/** mutate 失败兜底：TanStack 默认吞 rejection，409「任务已在跑」等后端 detail 不提示会变成死按钮。 */
const alertErr = (e: unknown) =>
  alert(e instanceof Error ? e.message : String(e));

export function DocumentsView() {
  const router = useRouter();
  const [filters, setFilters] = useState<GsbDocFilters>({
    stage: "",
    mineral: "",
    status: "",
  });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  // 统计头走全量(不随筛选/分页联动);limit=200=后端上限,避免默认 50 截断计数(聚合端点 Phase 3 再做);列表走筛选+分页
  const allQ = useGsbDocuments({ limit: 200 });
  const { data, isLoading } = useGsbDocuments({
    stage: filters.stage || undefined,
    mineral: filters.mineral || undefined,
    status: filters.status || undefined,
    skip: page * pageSize,
    limit: pageSize,
  });
  const upload = useGsbUpload();
  const action = useGsbAction();
  const del = useGsbDelete();
  const compile = useGsbCompile();
  const fileRef = useRef<HTMLInputElement>(null);
  const reportIdRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  // 操作结果确认对话框（替代原生 alert；编译分发 / 初始化切片库共用）
  const [resultDialog, setResultDialog] = useState<{
    title: string;
    message: string;
  } | null>(null);

  function onUpload() {
    const file = fileRef.current?.files?.[0];
    const reportId = reportIdRef.current?.value.trim();
    if (!file || !reportId) {
      alert("请填写 report_id（小写字母-数字）并选择 .docx/.pdf 文件");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("report_id", reportId);
    if (filters.stage) fd.append("stage", filters.stage);
    if (filters.mineral) fd.append("mineral", filters.mineral);
    upload.mutate(fd, {
      onSuccess: () => {
        if (fileRef.current) fileRef.current.value = "";
        if (reportIdRef.current) reportIdRef.current.value = "";
        setFileName("");
      },
      onError: (e) =>
        alert(`上传失败: ${e instanceof Error ? e.message : String(e)}`),
    });
  }

  function onCompileRow(reportId: string, id: string) {
    if (
      !confirm(
        `编译分发 ${reportId}？\n该样例切片将写入技能 references 并分发 RAGFlow（后台任务，进度见「运行记录」；已有编译在跑会 409）。`,
      )
    )
      return;
    compile.mutate(
      { document_id: id },
      {
        onSuccess: (r) =>
          setResultDialog({
            title: "编译已入队",
            message: `run ${r.run_id.slice(0, 8)}…，进度见「运行记录」tab`,
          }),
        onError: (e) =>
          setResultDialog({
            title: "编译触发失败",
            message: e instanceof Error ? e.message : String(e),
          }),
      },
    );
  }

  // 初始化切片库（幂等）：部署后点一次，编译分发按名生效；已存在时提示 aligned。
  async function onInitRagflow() {
    try {
      const r = await geoSamplesApi.initRagflow();
      setResultDialog({
        title: r.status === "created" ? "切片库已创建" : "切片库已就绪",
        message:
          r.status === "created"
            ? `RAGFlow 数据集 ${r.dataset_id?.slice(0, 8)}… 创建成功——编译分发即刻生效`
            : `RAGFlow 数据集 ${r.dataset_id?.slice(0, 8)}… 已存在且配置一致（aligned）`,
      });
    } catch (e) {
      setResultDialog({
        title: "初始化失败",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }

  const all = allQ.data?.items ?? [];
  const countBy = (s: string) => all.filter((d) => d.status === s).length;
  const docs = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div
      className="space-y-6 p-6"
      style={{ background: PAGE_BG, minHeight: "100%" }}
    >
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <FileStack className="h-5 w-5" style={{ color: BLUE }} />
        <h1 className="text-[22px] font-bold" style={{ color: INK }}>
          样例文档库
        </h1>
        <button
          type="button"
          onClick={onInitRagflow}
          title="创建/对齐 RAGFlow 切片数据集（编译分发的目标库）——部署后点一次即可，幂等"
          className="border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground ml-auto cursor-pointer rounded-md border px-2.5 py-1 text-xs transition-colors"
        >
          初始化切片库
        </button>
      </div>

      {/* 各状态计数(全量) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {STATUS_OPTIONS.map((o) => (
          <StatCard
            key={o.value}
            label={o.label}
            value={allQ.isPending ? "—" : countBy(o.value)}
            delta={
              o.value === "uploaded" && !allQ.isPending
                ? `共 ${all.length} 份`
                : undefined
            }
          />
        ))}
      </div>

      {/* ① 上传新样例 */}
      <SectionCard
        badge="①"
        title="上传新样例"
        sub="仅 .docx/.pdf；report_id 全库唯一，相同内容按哈希去重（409 拒绝）"
      >
        <div className="border-border bg-card flex flex-wrap items-center gap-3 rounded-xl border p-4">
          <input
            ref={reportIdRef}
            placeholder="report_id（如 2019-qianxi-gold-expl）"
            className="border-border bg-background placeholder:text-muted-foreground/60 focus:border-foreground/40 w-72 rounded-md border px-2.5 py-1.5 font-mono text-[13px] outline-none"
          />
          {/* 自动编码（batch-cli T7）：题名取所选文件名去扩展名，无文件退 report_id 框现值；
              低置信度结果照常回填但提示人工复核 */}
          <button
            type="button"
            onClick={async () => {
              const file = fileRef.current?.files?.[0];
              const title = (
                file?.name ??
                reportIdRef.current?.value ??
                ""
              ).replace(/\.(docx|pdf)$/i, "");
              if (!title) {
                alert("先选择文件或输入题名再自动编码");
                return;
              }
              try {
                const r = await geoSamplesApi.suggestId(title);
                if (reportIdRef.current)
                  reportIdRef.current.value = r.report_id;
                if (r.confidence === "needs-review") {
                  alert(
                    `已自动编码（低置信度，建议人工复核）：\n阶段=${r.stage ?? "?"} 矿种=${r.mineral ?? "?"} 地区=${r.region ?? "?"}`,
                  );
                }
              } catch (e) {
                alertErr(e);
              }
            }}
            className="border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground cursor-pointer rounded-md border px-2.5 py-1.5 text-[13px] transition-colors"
          >
            自动
          </button>
          <input
            ref={fileRef}
            id="gsb-upload-file"
            type="file"
            accept=".docx,.pdf"
            className="hidden"
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? "")}
          />
          <label
            htmlFor="gsb-upload-file"
            className="border-border bg-muted/40 hover:bg-muted text-foreground/80 cursor-pointer rounded-md border px-3 py-1.5 text-[13px] transition-colors"
          >
            选择文件
          </label>
          <span className="text-muted-foreground max-w-56 truncate text-[12px]">
            {fileName || "未选择文件"}
          </span>
          <button
            type="button"
            onClick={onUpload}
            disabled={upload.isPending}
            className="flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-[14px] font-medium text-white disabled:cursor-default disabled:opacity-50"
            style={{ background: BLUE }}
          >
            <Upload className="h-4 w-4" />
            {upload.isPending ? "上传中…" : "上传"}
          </button>
          <span className="text-[12px]" style={{ color: INK_3 }}>
            阶段/矿种取下方筛选条当前值（不选则用后端默认：勘探/铜）
          </span>
        </div>
      </SectionCard>

      {/* ② 样例文档列表 */}
      <SectionCard
        badge="②"
        title="样例文档列表"
        sub="解析 → 脱敏 → 抽审 状态流转，5 秒自动刷新"
      >
        <FilterBar
          filters={filters}
          onChange={(f) => {
            setFilters(f);
            setPage(0); // 筛选变更回第 1 页(防越界页)
          }}
        />
        <div className="border-border bg-card rounded-xl border p-4">
          {isLoading ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              加载中…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>report_id</TableHead>
                  <TableHead>文件</TableHead>
                  <TableHead>阶段</TableHead>
                  <TableHead>矿种</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>脱敏摘要</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {docs.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-mono text-xs">
                      {d.report_id}
                    </TableCell>
                    <TableCell className="text-[13px]">{d.file_name}</TableCell>
                    <TableCell className="text-[13px]">
                      {STAGE_LABEL[d.stage] ?? d.stage}
                    </TableCell>
                    <TableCell className="text-[13px]">
                      {MINERAL_LABEL[d.mineral] ?? d.mineral}
                    </TableCell>
                    <TableCell>
                      <span
                        className="text-[13px] font-medium"
                        style={{ color: STATUS_COLOR[d.status] ?? INK_2 }}
                      >
                        {STATUS_LABEL[d.status] ?? d.status}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-48 truncate text-xs">
                      {d.redaction_summary ?? "—"}
                    </TableCell>
                    <TableCell>
                      <span className="space-x-1 whitespace-nowrap">
                        {d.status === "uploaded" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            onClick={() =>
                              action.mutate(
                                { id: d.id, action: "parse" },
                                { onError: alertErr },
                              )
                            }
                          >
                            解析
                          </button>
                        )}
                        {d.status === "parsed" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            onClick={() =>
                              action.mutate(
                                { id: d.id, action: "redact" },
                                { onError: alertErr },
                              )
                            }
                          >
                            脱敏
                          </button>
                        )}
                        {d.status === "redacted" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            onClick={() => router.push("/geo-samples/review")}
                          >
                            抽审
                          </button>
                        )}
                        {d.status === "failed" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            style={{ color: RED }}
                            onClick={() =>
                              action.mutate(
                                { id: d.id, action: "parse" },
                                { onError: alertErr },
                              )
                            }
                          >
                            重试
                          </button>
                        )}
                        {/* 逐行编译分发（reviewed 首编 / compiled 幂等重编译） */}
                        {(d.status === "reviewed" ||
                          d.status === "compiled") && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            style={{ color: BLUE }}
                            disabled={compile.isPending}
                            onClick={() => onCompileRow(d.report_id, d.id)}
                          >
                            编译
                          </button>
                        )}
                        {d.status !== "compiled" && (
                          <button
                            type="button"
                            className="text-muted-foreground hover:text-foreground cursor-pointer text-xs hover:underline"
                            onClick={() => {
                              if (
                                confirm(
                                  `确认删除 ${d.report_id}？原始文件与解析/脱敏产物将一并删除，审计流水保留，不可恢复`,
                                )
                              ) {
                                del.mutate(
                                  { id: d.id },
                                  {
                                    onError: alertErr,
                                    onSuccess: () => {
                                      // 删完当前页仅剩 0 行且不在第 1 页 → 回退一页(防空白页)
                                      if (page > 0 && docs.length === 1)
                                        setPage(page - 1);
                                    },
                                  },
                                );
                              }
                            }}
                          >
                            删除
                          </button>
                        )}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
                {docs.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="text-muted-foreground py-6 text-center text-sm"
                    >
                      暂无样例
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
          {/* 分页行(表格下方):total 来自后端 count,同当前筛选;尾页按 total 精确判定,docs.length 兜底(翻页占位期间 total 瞬时滞后) */}
          <div className="border-border text-muted-foreground mt-3 flex flex-wrap items-center gap-4 border-t pt-3 text-xs">
            <span>共 {total} 条</span>
            <label className="flex items-center gap-1.5">
              <span>每页</span>
              <select
                value={pageSize}
                aria-label="每页条数"
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(0);
                }}
                className="border-border bg-background text-foreground cursor-pointer rounded border px-1.5 py-0.5 outline-none"
              >
                {[20, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span>条</span>
            </label>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                className={PAGE_BTN}
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </button>
              <span>第 {page + 1} 页</span>
              <button
                type="button"
                className={PAGE_BTN}
                disabled={(page + 1) * pageSize >= (data?.total ?? docs.length)}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      </SectionCard>

      {/* 操作结果确认对话框（编译分发 / 初始化切片库共用；替代原生 alert） */}
      <Dialog
        open={resultDialog != null}
        onOpenChange={(open) => {
          if (!open) setResultDialog(null);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{resultDialog?.title}</DialogTitle>
            <DialogDescription className="whitespace-pre-line">
              {resultDialog?.message}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button
              type="button"
              onClick={() => setResultDialog(null)}
              className="bg-primary text-primary-foreground hover:bg-primary/90 cursor-pointer rounded-lg px-4 py-2 text-sm font-medium shadow-sm transition-colors"
            >
              确定
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
