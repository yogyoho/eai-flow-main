"use client";

import {
  Search,
  Upload,
  FileText,
  MoreHorizontal,
  CheckCircle2,
  Clock,
  RefreshCw,
  Star,
  AlertCircle,
  Loader2,
} from "lucide-react";
import React, { Fragment, useState, useEffect, useCallback, useRef, useMemo } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import { kfApi, kbApi } from "@/extensions/api";
import type { SampleReport, KnowledgeBase } from "@/extensions/types";
import { isDocumentReady, DocumentStatus } from "@/extensions/types";

import AdvancedUploadModal from "@/extensions/knowledge-factory/components/AdvancedUploadModal";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: number) => void }) {
  return (
    <div className="fixed right-6 bottom-6 z-[100] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "flex items-center gap-3 rounded-xl border px-4 py-3 font-medium shadow-lg",
            t.type === "success" && "border-emerald-200 bg-emerald-50 text-emerald-800",
            t.type === "error" && "border-red-200 bg-red-50 text-red-800",
            t.type === "info" && "border-blue-200 bg-blue-50 text-blue-800"
          )}
        >
          {t.type === "success" && <CheckCircle2 className="h-4 w-4 shrink-0" />}
          {t.type === "error" && <AlertCircle className="h-4 w-4 shrink-0" />}
          {t.type === "info" && <Loader2 className="h-4 w-4 shrink-0" />}
          <span>{t.message}</span>
          <button
            onClick={() => onRemove(t.id)}
            className="ml-2 text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const show = useCallback((message: string, type: ToastType = "info") => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, show, remove };
}

export default function SampleReports() {
  const { toasts, show, remove } = useToast();

  const [reports, setReports] = useState<SampleReport[]>([]);
  const [kbList, setKbList] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);

  const [filterKb, setFilterKb] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [search, setSearch] = useState("");

  const [showUploadModal, setShowUploadModal] = useState(false);

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
        const res = await kfApi.listDocs(kbId, { skip: (page - 1) * pageSize, limit: pageSize });
        return {
          docs: res.documents.map((doc) => ({
            ...doc,
            knowledge_base_id: doc.knowledge_base_id,
            knowledge_base_name: kbName,
            parse_progress: doc.status === "parsing" ? 50 : isDocumentReady(doc.status) ? 100 : 0,
          })),
          total: res.total,
        };
      };

      if (filterKb !== "all") {
        const kb = kbList.find((k) => k.id === filterKb);
        const { docs, total } = await fetchKbDocs(filterKb, kb?.name || "");
        setReports(docs);
        setTotal(total);
        return;
      }

      // 未选择知识库时，并行获取所有库的文档并汇总
      const results = await Promise.allSettled(
        kbList.map((kb) => fetchKbDocs(kb.id, kb.name))
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
    } catch (e) {
      show("加载报告列表失败", "error");
    } finally {
      setLoading(false);
    }
  }, [filterKb, kbList, page, pageSize, show]);

  useEffect(() => {
    loadKbList();
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
    loadReports();
  }, [loadReports]);

  // 轮询解析中的报告状态
  useEffect(() => {
    const parsingReports = reports.filter(
      (r) => r.status === "parsing" || r.status === "uploading"
    );

    if (parsingReports.length > 0 && !pollRef.current) {
      pollRef.current = setInterval(() => {
        loadReports();
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

  // 处理删除
  const handleDelete = async (report: SampleReport) => {
    if (!confirm(`确定要删除 "${report.name}" 吗？`)) return;
    try {
      await kfApi.deleteDoc(report.knowledge_base_id, report.id);
      setReports((prev) => prev.filter((r) => r.id !== report.id));
      show("报告已删除", "success");
    } catch (e) {
      show("删除失败", "error");
    }
  };

  // 处理上传成功
  const handleUploadSuccess = (newReports: SampleReport[]) => {
    setReports((prev) => [...newReports, ...prev]);
    loadReports(); // 刷新列表
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
    if (search && !r.name.toLowerCase().includes(search.toLowerCase())) return false;
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
    parsing: reports.filter((r) => r.status === "parsing" || r.status === "uploading").length,
    pending: reports.filter((r) => !r.status || r.status === DocumentStatus.PENDING).length,
  };

  const statItems = [
    { label: "总数", value: stats.total, color: "text-zinc-900" },
    { label: "已完成", value: stats.completed, color: "text-emerald-600" },
    { label: "解析中", value: stats.parsing, color: "text-blue-600" },
    { label: "待处理", value: stats.pending, color: "text-amber-600" },
  ];

  // 只有搜索或状态筛选时才显示当前页条数（翻页本身不需要提示）
  const listFiltered =
    (search.trim() !== "" || filterStatus !== "all") && filteredReports.length !== reports.length;

  return (
    <div className="flex flex-col h-full">
      {/* 标题栏 */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-card p-4">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-5 w-5 shrink-0 text-primary" />
          <h2 className="truncate text-lg font-semibold tracking-tight text-foreground">样例报告库</h2>
        </div>
        <button
          type="button"
          onClick={() => setShowUploadModal(true)}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 sm:px-4"
        >
          <Upload className="h-4 w-4" />
          上传新报告
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 bg-card px-4 py-2.5">
        <div className="relative flex-1 min-w-[280px]">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 pointer-events-none text-zinc-400" />
          <input
            type="text"
            placeholder="搜索报告名称..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1.5 pl-8 text-sm text-zinc-900 placeholder:text-zinc-400 transition-all focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
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
          className="shrink-0 rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600"
          title="刷新"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {/* Report List — 与合规规则引擎等 tab 列表项垂直间距一致 (space-y-4) */}
      <div className="flex-1 overflow-y-auto space-y-4 bg-muted/30 p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>暂无报告</p>
            <button
              onClick={() => setShowUploadModal(true)}
              className="mt-4 text-primary hover:underline"
            >
              上传第一份报告
            </button>
          </div>
        ) : (
          filteredReports.map((report) => (
            <div
              key={report.id}
              className="group rounded-lg border border-border bg-card p-3 shadow-sm transition-all hover:shadow"
            >
              <div className="flex items-start gap-2.5">
                <div className="shrink-0 rounded-md bg-secondary p-2 text-primary">
                  <FileText className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="line-clamp-2 font-medium leading-snug text-foreground group-hover:text-primary transition-colors">
                      {report.name}
                    </h3>
                    <button
                      type="button"
                      className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs leading-tight text-muted-foreground md:grid-cols-4">
                    <div>上传时间: {formatDate(report.created_at)}</div>
                    <div>大小: {formatFileSize(report.file_size)}</div>
                    {report.knowledge_base_name && (
                      <div className="min-w-0 truncate">知识库: {report.knowledge_base_name}</div>
                    )}
                    <div className="flex flex-wrap items-center gap-1">
                      <span>状态:</span>
                      {isDocumentReady(report.status) ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">
                          <CheckCircle2 className="h-3 w-3 shrink-0" /> 已解析
                        </span>
                      ) : report.status === "parsing" || report.status === "uploading" ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[11px] font-medium text-blue-700">
                          <Clock className="h-3 w-3 shrink-0 animate-spin" /> 解析中
                          {report.parse_progress ? ` ${report.parse_progress}%` : ""}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full border border-zinc-300 bg-zinc-100 px-1.5 py-0.5 text-[11px] font-medium text-zinc-700">
                          <Clock className="h-3 w-3 shrink-0" /> 待处理
                        </span>
                      )}
                    </div>
                  </div>

                  {isDocumentReady(report.status) ? (
                    <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-1.5 text-xs">
                      {report.quality_score && (
                        <div className="flex items-center gap-1 text-muted-foreground">
                          质量评分:
                          <div className="flex items-center gap-0.5 text-amber-400">
                            {[...Array(5)].map((_, i) => (
                              <Star
                                key={i}
                                className={cn(
                                  "h-3 w-3 fill-current",
                                  i >= Math.floor(report.quality_score || 0) && "text-zinc-200"
                                )}
                              />
                            ))}
                          </div>
                          <span className="font-medium text-foreground">
                            {report.quality_score}/5
                          </span>
                        </div>
                      )}
                      {report.chapters && (
                        <div className="text-muted-foreground">
                          章节数: {report.chapters}
                        </div>
                      )}
                      {report.sections && (
                        <div className="text-muted-foreground">
                          节数: {report.sections}
                        </div>
                      )}
                      {report.template_version && (
                        <div className="text-primary font-medium">
                          模板: {report.template_version}
                        </div>
                      )}
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-x-2 gap-y-0.5 pt-1.5">
                    <button
                      type="button"
                      className="text-xs font-medium text-primary transition-colors hover:text-primary/80 hover:underline"
                    >
                      查看详情
                    </button>
                    {isDocumentReady(report.status) ? (
                      <>
                        <button
                          type="button"
                          className="text-xs text-muted-foreground transition-colors hover:text-foreground"
                        >
                          重新解析
                        </button>
                        <button
                          type="button"
                          className="text-xs text-muted-foreground transition-colors hover:text-foreground"
                        >
                          下载模板
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(report)}
                          className="text-xs text-destructive transition-colors hover:text-destructive/80"
                        >
                          删除
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="text-xs text-destructive transition-colors hover:text-destructive/80"
                      >
                        取消
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 底栏：统计 + 分页 */}
      <div className="flex flex-col gap-3 border-t border-border bg-card px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-6 sm:py-4">
        <div
          className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-1 text-[13px] text-muted-foreground sm:text-sm"
          aria-label="报告统计"
        >
          {statItems.map((s, i) => (
            <Fragment key={s.label}>
              {i > 0 && (
                <span className="mx-1.5 select-none text-zinc-300 sm:mx-2" aria-hidden>
                  ·
                </span>
              )}
              <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
                <span className="text-zinc-500">{s.label}</span>
                <span className={cn("font-semibold tabular-nums", s.color)}>{s.value}</span>
              </span>
            </Fragment>
          ))}
          {listFiltered && (
            <>
              <span className="mx-1.5 select-none text-zinc-300 sm:mx-2" aria-hidden>
                ·
              </span>
              <span className="text-zinc-500">
                当前页 <span className="font-semibold tabular-nums text-zinc-700">{reports.length}</span> 条
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page === 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="flex h-8 w-8 items-center justify-center rounded border border-border text-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          <span className="min-w-[4.5rem] text-center text-sm tabular-nums text-muted-foreground">
            {page} / {Math.max(1, Math.ceil(total / pageSize))}
          </span>

          <button
            type="button"
            disabled={page >= Math.ceil(total / pageSize) || loading}
            onClick={() => setPage((p) => p + 1)}
            className="flex h-8 w-8 items-center justify-center rounded border border-border text-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <AdvancedUploadModal
          businessType="sample_reports"
          onClose={() => setShowUploadModal(false)}
          onSuccess={handleUploadSuccess}
          onToast={show}
        />
      )}

      <ToastContainer toasts={toasts} onRemove={remove} />
    </div>
  );
}
