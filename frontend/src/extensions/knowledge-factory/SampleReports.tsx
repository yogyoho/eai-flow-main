"use client";

import {
  Search,
  Upload,
  FileText,
  CheckCircle2,
  Clock,
  RefreshCw,
  Loader2,
  Calendar,
  HardDrive,
  Database,
  Trash2,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import React, {
  Fragment,
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
} from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { kfApi, kbApi } from "@/extensions/api";
import AdvancedUploadModal from "@/extensions/knowledge-factory/components/AdvancedUploadModal";
import type { SampleReport, KnowledgeBase } from "@/extensions/types";
import { isDocumentReady, DocumentStatus } from "@/extensions/types";
import { cn } from "@/lib/utils";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(dateString: string): string {
  return new Date(dateString).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function SampleReports() {
  const router = useRouter();

  const [reports, setReports] = useState<SampleReport[]>([]);
  const [kbList, setKbList] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);

  const [filterKb, setFilterKb] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [search, setSearch] = useState("");

  const [showUploadModal, setShowUploadModal] = useState(false);

  type ConfirmAction = {
    type: "delete" | "cancel";
    report: SampleReport;
  } | null;
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);

  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [total, setTotal] = useState(0);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 加载知识库列表
  const loadKbList = useCallback(async () => {
    try {
      const res = await kbApi.list({ limit: 100 });
      setKbList(res.knowledge_bases);
    } catch (e) {
      console.error("加载知识库列表失败", e);
    }
  }, []);

  // 加载报告列表（分页）
  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const fetchKbDocs = async (kbId: string, kbName: string) => {
        const res = await kfApi.listDocs(kbId, {
          skip: (page - 1) * pageSize,
          limit: pageSize,
        });
        return {
          docs: res.documents.map((doc) => ({
            ...doc,
            knowledge_base_id: doc.knowledge_base_id,
            knowledge_base_name: kbName,
            parse_progress:
              doc.status === "parsing"
                ? 50
                : isDocumentReady(doc.status)
                  ? 100
                  : 0,
          })),
          total: res.total,
        };
      };

      if (filterKb !== "all") {
        const kb = kbList.find((k) => k.id === filterKb);
        const { docs, total } = await fetchKbDocs(filterKb, kb?.name ?? "");
        setReports(docs);
        setTotal(total);
        return;
      }

      // 未选择知识库时，并行获取所有库的文档并汇总
      const results = await Promise.allSettled(
        kbList.map((kb) => fetchKbDocs(kb.id, kb.name)),
      );
      const allDocs: SampleReport[] = [];
      let totalCount = 0;
      for (const result of results) {
        if (result.status === "fulfilled") {
          allDocs.push(...result.value.docs);
          totalCount += result.value.total;
        }
      }
      setReports(allDocs);
      setTotal(totalCount);
    } catch {
      toast.error("加载报告列表失败");
    } finally {
      setLoading(false);
    }
  }, [filterKb, kbList, page, pageSize]);

  useEffect(() => {
    void loadKbList();
  }, [loadKbList]);

  // 切换知识库或筛选状态时重置到第一页
  const handleFilterKbChange = (val: string) => {
    setFilterKb(val);
    setPage(1);
  };

  const handleFilterStatusChange = (val: string) => {
    setFilterStatus(val);
    setPage(1);
  };

  const handleSearchChange = (val: string) => {
    setSearch(val);
    setPage(1);
  };

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  // 轮询解析中的报告状态
  useEffect(() => {
    const parsingReports = reports.filter(
      (r) => r.status === "parsing" || r.status === "uploading",
    );

    if (parsingReports.length > 0 && !pollRef.current) {
      pollRef.current = setInterval(() => {
        void loadReports();
        // 检查是否还有解析中的报告
        if (!reports.some((r) => r.status === "parsing")) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      }, 5000);
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [reports, loadReports]);

  // 确认对话框 - 执行删除
  const executeConfirmAction = useCallback(async () => {
    if (!confirmAction) return;
    const { type, report } = confirmAction;
    setConfirmAction(null);
    try {
      await kfApi.deleteDoc(report.knowledge_base_id, report.id);
      setReports((prev) => prev.filter((r) => r.id !== report.id));
      toast.success(type === "delete" ? "报告已删除" : "已取消并删除");
    } catch {
      toast.error(type === "delete" ? "删除失败" : "取消失败");
    }
  }, [confirmAction]);

  // 处理上传成功
  const handleUploadSuccess = (newReports: SampleReport[]) => {
    setReports((prev) => [...newReports, ...prev]);
    void loadReports(); // 刷新列表
  };

  const kbFilterOptions = useMemo(
    () => [
      { value: "all", label: "全部知识库" },
      ...kbList.map((kb) => ({ value: kb.id, label: kb.name })),
    ],
    [kbList],
  );

  const statusFilterOptions = useMemo(
    () => [
      { value: "all", label: "全部状态" },
      { value: "success", label: "已完成" },
      { value: "parsing", label: "解析中" },
      { value: "pending", label: "待处理" },
    ],
    [],
  );

  // 筛选后的报告
  const filteredReports = reports.filter((r) => {
    if (search && !r.name.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (filterStatus !== "all") {
      const done = isDocumentReady(r.status);
      const busy = r.status === "parsing" || r.status === "uploading";
      if (filterStatus === "success" && !done) return false;
      if (filterStatus === "parsing" && !busy) return false;
      if (filterStatus === "pending" && (done || busy)) return false;
    }
    return true;
  });

  // 统计（total 来自服务端总数，其余为当前页数据）
  const stats = {
    total,
    completed: reports.filter((r) => isDocumentReady(r.status)).length,
    parsing: reports.filter(
      (r) => r.status === "parsing" || r.status === "uploading",
    ).length,
    pending: reports.filter(
      (r) => !r.status || r.status === DocumentStatus.PENDING,
    ).length,
  };

  const statItems = [
    { label: "总数", value: stats.total, color: "text-foreground" },
    { label: "已完成", value: stats.completed, color: "text-success" },
    { label: "解析中", value: stats.parsing, color: "text-primary" },
    { label: "待处理", value: stats.pending, color: "text-warning" },
  ];

  // 只有搜索或状态筛选时才显示当前页条数（翻页本身不需要提示）
  const listFiltered =
    (search.trim() !== "" || filterStatus !== "all") &&
    filteredReports.length !== reports.length;

  return (
    <div className="flex h-full flex-col">
      {/* 标题栏 */}
      <div className="border-border bg-card flex shrink-0 items-center justify-between gap-3 border-b px-8 py-6">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="text-primary h-5 w-5 shrink-0" />
          <h2 className="text-foreground truncate text-lg font-medium tracking-tight">
            样例报告库
          </h2>
        </div>
        <button
          type="button"
          onClick={() => setShowUploadModal(true)}
          className="bg-primary hover:bg-primary/90 flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white transition-colors sm:px-4"
        >
          <Upload className="h-4 w-4" />
          上传新报告
        </button>
      </div>

      {/* Filters */}
      <div className="border-border bg-card flex flex-wrap items-center gap-2 border-b px-8 py-4">
        <div className="relative min-w-[280px] flex-1">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2" />
          <input
            type="text"
            placeholder="搜索报告名称..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="border-border bg-muted text-foreground placeholder:text-muted-foreground focus:border-primary focus:bg-background focus:ring-primary/20 w-full rounded-md border px-3 py-1.5 pl-8 text-sm transition-all focus:ring-2 focus:outline-none"
          />
        </div>
        <AdminSelect
          value={filterKb}
          onChange={handleFilterKbChange}
          options={kbFilterOptions}
          placeholder="选择知识库"
          className="w-[min(100%,200px)] min-w-[160px]"
        />
        <AdminSelect
          value={filterStatus}
          onChange={handleFilterStatusChange}
          options={statusFilterOptions}
          placeholder="选择状态"
          className="w-[min(100%,140px)] min-w-[120px]"
        />
        <button
          type="button"
          onClick={loadReports}
          className="text-muted-foreground hover:bg-accent hover:text-primary shrink-0 rounded-md p-1.5 transition-colors"
          title="刷新"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {/* Report Cards Grid */}
      <div className="bg-muted/30 flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="border-border/60 bg-card flex flex-col rounded-xl border p-5 shadow-sm"
              >
                <div className="flex items-start gap-3">
                  <div className="bg-muted h-10 w-10 shrink-0 animate-pulse rounded-xl" />
                  <div className="flex-1 space-y-2">
                    <div className="bg-muted h-4 w-3/4 animate-pulse rounded" />
                    <div className="bg-muted h-3 w-1/2 animate-pulse rounded" />
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  <div className="bg-muted h-3 w-2/3 animate-pulse rounded" />
                  <div className="bg-muted h-3 w-1/3 animate-pulse rounded" />
                </div>
                <div className="border-border/60 mt-4 border-t pt-3">
                  <div className="bg-muted h-3 w-16 animate-pulse rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="bg-muted mb-5 rounded-2xl p-4">
              <FileText className="text-muted-foreground/60 h-10 w-10" />
            </div>
            <h3 className="text-foreground text-sm font-semibold">暂无报告</h3>
            <p className="text-muted-foreground mt-1 max-w-xs text-[13px]">
              上传样例文档后，系统将自动解析并生成结构化报告
            </p>
            <button
              onClick={() => setShowUploadModal(true)}
              className="bg-primary hover:bg-primary/90 mt-5 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors"
            >
              <Upload className="h-4 w-4" />
              上传第一份报告
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {filteredReports.map((report) => {
              const isReady = isDocumentReady(report.status);
              const isProcessing =
                report.status === "parsing" || report.status === "uploading";
              const progress =
                report.parse_progress ??
                (isReady ? 100 : isProcessing ? 50 : 0);
              return (
                <div
                  key={report.id}
                  className="group border-border/60 bg-card hover:border-primary/20 flex flex-col rounded-xl border p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
                >
                  {/* Header: Icon + Title + Status */}
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                        isReady || isProcessing
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      <FileText className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-foreground group-hover:text-primary line-clamp-2 text-sm leading-snug font-medium transition-colors duration-200">
                        {report.name}
                      </h3>
                      <div className="mt-1.5">
                        {isReady ? (
                          <span className="bg-success/10 text-success inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold">
                            <CheckCircle2 className="h-3 w-3" />
                            已解析
                          </span>
                        ) : isProcessing ? (
                          <span className="bg-primary/10 text-primary inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            解析中
                          </span>
                        ) : (
                          <span className="bg-warning/10 text-warning inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold">
                            <Clock className="h-3 w-3" />
                            待处理
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Progress bar for parsing items */}
                  {isProcessing && (
                    <div className="mt-3">
                      <div className="text-muted-foreground mb-1 flex items-center justify-between text-[11px]">
                        <span>解析进度</span>
                        <span className="font-medium tabular-nums">
                          {progress}%
                        </span>
                      </div>
                      <div className="bg-muted h-1.5 overflow-hidden rounded-full">
                        <div
                          className="bg-primary h-full rounded-full transition-all duration-500"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Metadata */}
                  <div className="text-muted-foreground mt-3 space-y-1.5 text-[12px]">
                    <div className="flex items-center gap-1.5">
                      <Calendar className="h-3.5 w-3.5 shrink-0 opacity-60" />
                      <span>{formatDateTime(report.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <HardDrive className="h-3.5 w-3.5 shrink-0 opacity-60" />
                      <span>{formatFileSize(report.file_size)}</span>
                    </div>
                    {report.knowledge_base_name && (
                      <div className="flex items-center gap-1.5">
                        <Database className="h-3.5 w-3.5 shrink-0 opacity-60" />
                        <button
                          type="button"
                          onClick={() =>
                            router.push(
                              `/knowledge?search=${encodeURIComponent(report.knowledge_base_name!)}`,
                            )
                          }
                          className="hover:text-primary truncate text-left transition-colors hover:underline"
                          title={`查看知识库: ${report.knowledge_base_name}`}
                        >
                          {report.knowledge_base_name}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Footer: actions */}
                  <div className="border-border/60 mt-auto flex items-center justify-between gap-2 border-t pt-3">
                    {isReady ? (
                      <>
                        <span className="text-success bg-success/10 border-success/20 inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium">
                          已就绪
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            setConfirmAction({ type: "delete", report })
                          }
                          className="text-destructive hover:bg-destructive/10 inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          删除
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() =>
                            setConfirmAction({ type: "cancel", report })
                          }
                          className="text-warning hover:bg-warning/10 inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition-colors"
                        >
                          <XCircle className="h-3.5 w-3.5" />
                          取消
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setConfirmAction({ type: "delete", report })
                          }
                          className="text-destructive hover:bg-destructive/10 inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          删除
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 底栏：统计 + 分页 */}
      <div className="border-border bg-card flex flex-col gap-3 border-t px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-3">
        <div
          className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-x-1 gap-y-1 text-[13px] sm:text-sm"
          aria-label="报告统计"
        >
          {statItems.map((s, i) => (
            <Fragment key={s.label}>
              {i > 0 && (
                <span
                  className="text-muted-foreground/40 mx-1.5 select-none sm:mx-2"
                  aria-hidden
                >
                  ·
                </span>
              )}
              <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
                <span className="text-muted-foreground">{s.label}</span>
                <span
                  className={cn(
                    "font-cyber font-semibold tabular-nums",
                    s.color,
                  )}
                >
                  {s.value}
                </span>
              </span>
            </Fragment>
          ))}
          {listFiltered && (
            <>
              <span
                className="text-muted-foreground/40 mx-1.5 select-none sm:mx-2"
                aria-hidden
              >
                ·
              </span>
              <span className="text-muted-foreground">
                当前页{" "}
                <span className="text-foreground font-semibold tabular-nums">
                  {reports.length}
                </span>{" "}
                条
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page === 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="border-border hover:bg-accent flex h-8 w-8 items-center justify-center rounded border text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg
              className="h-3.5 w-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 19l-7-7 7-7"
              />
            </svg>
          </button>

          <span className="text-muted-foreground min-w-[4.5rem] text-center text-sm tabular-nums">
            {page} / {Math.max(1, Math.ceil(total / pageSize))}
          </span>

          <button
            type="button"
            disabled={page >= Math.ceil(total / pageSize) || loading}
            onClick={() => setPage((p) => p + 1)}
            className="border-border hover:bg-accent flex h-8 w-8 items-center justify-center rounded border text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg
              className="h-3.5 w-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Confirm Dialog */}
      <Dialog
        open={confirmAction !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmAction(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <div className="bg-destructive/10 mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full">
              {confirmAction?.type === "cancel" ? (
                <AlertTriangle className="text-warning h-6 w-6" />
              ) : (
                <Trash2 className="text-destructive h-6 w-6" />
              )}
            </div>
            <DialogTitle className="text-center">
              {confirmAction?.type === "cancel" ? "取消上传" : "确认删除"}
            </DialogTitle>
            <DialogDescription className="text-center">
              {confirmAction?.type === "cancel"
                ? `确定要取消 "${confirmAction?.report.name}" 的上传吗？已处理的部分将丢失。`
                : `确定要删除 "${confirmAction?.report.name}" 吗？此操作不可撤销。`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center">
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              取消
            </Button>
            <Button
              variant={
                confirmAction?.type === "cancel" ? "default" : "destructive"
              }
              onClick={executeConfirmAction}
              className={
                confirmAction?.type === "cancel"
                  ? "bg-warning hover:bg-warning/90"
                  : ""
              }
            >
              {confirmAction?.type === "cancel" ? "确认取消" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Modal */}
      {showUploadModal && (
        <AdvancedUploadModal
          businessType="sample_reports"
          onClose={() => setShowUploadModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}
    </div>
  );
}
