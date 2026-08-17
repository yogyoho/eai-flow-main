"use client";

import {
  Library,
  Search,
  RefreshCw,
  Plus,
  BookOpen,
  FileText,
  ExternalLink,
  AlertCircle,
  CheckCircle,
  Clock,
  Loader2,
  Trash2,
} from "lucide-react";
import React, { useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
// Import components
import ImportLawModal from "@/extensions/knowledge-factory/components/ImportLawModal";
import LawDetailDrawer from "@/extensions/knowledge-factory/components/LawDetailDrawer";
import RAGFlowStatusPanel from "@/extensions/knowledge-factory/components/RAGFlowStatusPanel";
import { getCategoryColor } from "@/extensions/knowledge-factory/config/lawCategories";
import {
  LAW_CATEGORIES,
  LAW_TYPE_OPTIONS,
  getCategoryByCode,
} from "@/extensions/knowledge-factory/config/lawCategories";
import {
  useLawList,
  useLawStatistics,
  useRAGFlowStatus,
  useSyncAllLaws,
  useDeleteLaw,
} from "@/extensions/knowledge-factory/hooks/useLawLibrary";
import type { LawItem, LawType } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

export default function LawLibrary() {
  // Filter states
  const [filterType, setFilterType] = useState<LawType | "all">("all");
  const [filterStatus, setFilterStatus] = useState<string>("active");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [limit] = useState(20);

  // Modal states
  const [showImportModal, setShowImportModal] = useState(false);
  const [showRAGFlowStatus, setShowRAGFlowStatus] = useState(false);
  const [selectedLaw, setSelectedLaw] = useState<LawItem | null>(null);
  const [deletingLaw, setDeletingLaw] = useState<LawItem | null>(null);

  // Debounce keyword search
  const [searchKeyword, setSearchKeyword] = useState("");

  // Fetch data
  const { data, isLoading, error, refetch } = useLawList({
    law_type: filterType,
    status: filterStatus === "valid" ? "active" : filterStatus,
    keyword: searchKeyword || undefined,
    page,
    limit,
  });

  const { data: statistics } = useLawStatistics();
  const { data: ragflowStatus } = useRAGFlowStatus();

  // Mutations
  const syncAllMutation = useSyncAllLaws();
  const deleteMutation = useDeleteLaw();

  // Handle keyword search (debounced)
  const handleKeywordChange = (value: string) => {
    setKeyword(value);
    // Reset page when searching
    if (value !== searchKeyword) {
      setPage(1);
    }
  };

  // Debounce the actual search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setSearchKeyword(keyword);
    }, 300);
    return () => clearTimeout(timer);
  }, [keyword]);

  const totalCount = statistics?.total_count ?? data?.total ?? 0;
  const activeCount = statistics?.active_count ?? 0;
  const deprecatedCount = statistics?.deprecated_count ?? 0;

  // Check RAGFlow status for warnings
  const hasMissingKBs =
    ragflowStatus?.statuses?.some((s) => s.status === "missing") ?? false;

  // Handle import success
  const handleImportSuccess = () => {
    void refetch();
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-border bg-card flex shrink-0 items-center justify-between border-b p-4">
        <h2 className="text-foreground flex items-center gap-2 text-lg font-medium tracking-tight">
          <Library className="text-primary h-5 w-5" />
          法规标准库
          {hasMissingKBs && (
            <span className="bg-warning/10 text-warning flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
              <AlertCircle className="h-3 w-3" />
              未初始化
            </span>
          )}
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => setShowRAGFlowStatus(true)}
            className="text-muted-foreground hover:text-foreground flex items-center gap-2 px-3 py-2 text-sm transition-colors"
            title="RAGFlow状态"
          >
            {ragflowStatus ? (
              ragflowStatus.missing_kbs > 0 ? (
                <AlertCircle className="text-warning h-4 w-4" />
              ) : (
                <CheckCircle className="text-success h-4 w-4" />
              )
            ) : (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            <span className="hidden sm:inline">知识库状态</span>
          </button>
          <button
            onClick={() => syncAllMutation.mutate(undefined)}
            disabled={syncAllMutation.isPending}
            className="text-foreground bg-card border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium shadow-sm transition-colors disabled:opacity-50"
          >
            {syncAllMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            同步更新
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium shadow-sm transition-colors"
          >
            <Plus className="h-4 w-4" /> 导入新法规
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="bg-muted/30 min-h-0 flex-1 overflow-hidden">
        <LawListView
          data={data}
          isLoading={isLoading}
          error={error}
          refetch={refetch}
          statistics={statistics}
          totalCount={totalCount}
          activeCount={activeCount}
          deprecatedCount={deprecatedCount}
          filterType={filterType}
          setFilterType={setFilterType}
          filterStatus={filterStatus}
          setFilterStatus={setFilterStatus}
          keyword={keyword}
          handleKeywordChange={handleKeywordChange}
          page={page}
          setPage={setPage}
          limit={limit}
          selectedLaw={selectedLaw}
          setSelectedLaw={setSelectedLaw}
          setShowImportModal={setShowImportModal}
          onDeleteLaw={setDeletingLaw}
        />
      </div>

      {/* Modals */}
      {showImportModal && (
        <ImportLawModal
          onClose={() => setShowImportModal(false)}
          onSuccess={handleImportSuccess}
        />
      )}

      {showRAGFlowStatus && (
        <RAGFlowStatusPanel onClose={() => setShowRAGFlowStatus(false)} />
      )}

      {selectedLaw && (
        <LawDetailDrawer
          law={selectedLaw}
          onClose={() => setSelectedLaw(null)}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!deletingLaw}
        onOpenChange={(open) => {
          if (!open) setDeletingLaw(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除法规</DialogTitle>
            <DialogDescription>
              确定要删除以下法规吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <div className="flex items-start gap-2">
              <FileText className="text-muted-foreground mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <p className="text-foreground font-medium">
                  {deletingLaw?.title}
                </p>
                {deletingLaw?.law_number && (
                  <p className="text-muted-foreground text-sm">
                    标准号: {deletingLaw.law_number}
                  </p>
                )}
              </div>
            </div>
            {deletingLaw?.is_synced === "synced" && (
              <div className="text-warning flex items-start gap-2 text-sm">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  该法规已同步到 RAGFlow 知识库，将同时删除知识库中的文档。
                </span>
              </div>
            )}
            {deleteMutation.isError && (
              <div className="text-destructive flex items-start gap-2 text-sm">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  {deleteMutation.error instanceof Error
                    ? deleteMutation.error.message
                    : "删除失败"}
                </span>
              </div>
            )}
          </div>
          <DialogFooter>
            <button
              onClick={() => setDeletingLaw(null)}
              disabled={deleteMutation.isPending}
              className="text-muted-foreground hover:text-foreground px-4 py-2 text-sm transition-colors"
            >
              取消
            </button>
            <button
              onClick={() => {
                if (deletingLaw) {
                  deleteMutation.mutate(deletingLaw.id, {
                    onSuccess: () => {
                      setDeletingLaw(null);
                      void refetch();
                    },
                  });
                }
              }}
              disabled={deleteMutation.isPending}
              className="bg-destructive hover:bg-destructive/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-white transition-colors disabled:opacity-50"
            >
              {deleteMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" />
              )}
              确认删除
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Law List View Component
interface LawListViewProps {
  data?: {
    laws: LawItem[];
    total: number;
    by_type: Record<string, number>;
  };
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
  statistics?: {
    total_count: number;
    active_count: number;
    deprecated_count: number;
    synced_count: number;
    pending_sync_count: number;
    failed_sync_count: number;
  };
  totalCount: number;
  activeCount: number;
  deprecatedCount: number;
  filterType: LawType | "all";
  setFilterType: (type: LawType | "all") => void;
  filterStatus: string;
  setFilterStatus: (status: string) => void;
  keyword: string;
  handleKeywordChange: (value: string) => void;
  page: number;
  setPage: (page: number) => void;
  limit: number;
  selectedLaw: LawItem | null;
  setSelectedLaw: (law: LawItem | null) => void;
  setShowImportModal: (show: boolean) => void;
  onDeleteLaw: (law: LawItem) => void;
}

function LawListView({
  data,
  isLoading,
  error,
  refetch,
  statistics,
  totalCount,
  activeCount,
  deprecatedCount,
  filterType,
  setFilterType,
  filterStatus,
  setFilterStatus,
  keyword,
  handleKeywordChange,
  page,
  setPage,
  limit,
  setSelectedLaw,
  setShowImportModal,
  onDeleteLaw,
}: LawListViewProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-6">
        {/* Search & Filter */}
        <div className="from-card to-card/80 border-border/50 flex flex-wrap items-center gap-4 rounded-xl border bg-gradient-to-br p-4 shadow-sm">
          <div className="relative min-w-[300px] flex-1">
            <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
            <input
              type="text"
              placeholder="请输入法规名称/标准号/关键词..."
              value={keyword}
              onChange={(e) => handleKeywordChange(e.target.value)}
              className="bg-muted border-border focus:ring-primary/20 focus:border-primary w-full rounded-lg border py-2 pr-4 pl-10 text-sm transition-all outline-none focus:ring-2"
            />
          </div>
          <div className="flex gap-3">
            <AdminSelect
              value={filterType}
              onChange={(v) => {
                setFilterType(v as LawType | "all");
                setPage(1);
              }}
              options={[
                { value: "all", label: "全部类型" },
                ...LAW_TYPE_OPTIONS,
              ]}
              className="w-40"
            />
            <AdminSelect
              value={filterStatus}
              onChange={(v) => {
                setFilterStatus(v);
                setPage(1);
              }}
              options={[
                { value: "active", label: "现行有效" },
                { value: "deprecated", label: "已废止" },
                { value: "updating", label: "正在修订" },
                { value: "all", label: "全部状态" },
              ]}
              className="w-36"
            />
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="bg-destructive/10 border-destructive/20 flex items-center gap-3 rounded-lg border p-4">
            <AlertCircle className="text-destructive h-5 w-5 shrink-0" />
            <span className="text-destructive">{error.message}</span>
            <button
              onClick={() => refetch()}
              className="text-destructive ml-auto text-sm hover:underline"
            >
              重试
            </button>
          </div>
        )}

        {/* Category Grid */}
        <div className="space-y-3">
          <h3 className="text-md text-foreground flex items-center gap-2 font-semibold">
            <BookOpen className="text-primary h-5 w-5" /> 知识库分类
          </h3>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7">
            {LAW_CATEGORIES.map((cat) => {
              const count = data?.by_type?.[cat.code] ?? 0;
              const isActive = filterType === cat.code;
              return (
                <div
                  key={cat.code}
                  onClick={() => {
                    setFilterType(isActive ? "all" : cat.code);
                    setPage(1);
                  }}
                  className={cn(
                    "border-border/50 from-card to-card/80 flex cursor-pointer items-center gap-3 rounded-xl border border-l-[3px] bg-gradient-to-br p-5 shadow-sm transition-all hover:shadow-md",
                    isActive
                      ? "border-primary ring-primary/20 border-l-primary ring-2"
                      : "hover:border-primary/30 hover:border-l-primary/30 border-l-transparent",
                  )}
                >
                  <div
                    className={cn(
                      "flex size-12 shrink-0 items-center justify-center rounded-xl",
                      cat.bgColor,
                    )}
                  >
                    <cat.icon className={cn("size-6", cat.color)} aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-muted-foreground mb-1 truncate text-sm">
                      {cat.name}
                    </div>
                    <div
                      className={cn(
                        "flex flex-wrap items-baseline gap-x-1 tabular-nums",
                        cat.color,
                      )}
                    >
                      <span className="font-cyber text-2xl font-bold">
                        {count}
                      </span>
                      <span className="text-muted-foreground text-sm font-medium">
                        份
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Law List */}
        <div className="space-y-3">
          <h3 className="text-md text-foreground flex items-center gap-2 font-semibold">
            <FileText className="text-primary h-5 w-5" />
            {filterType !== "all"
              ? `${getCategoryByCode(filterType)?.name ?? filterType}列表`
              : "全部法规"}
            <span className="text-muted-foreground text-sm font-normal">
              ({data?.total ?? 0} 份)
            </span>
          </h3>

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="text-primary h-8 w-8 animate-spin" />
            </div>
          ) : data?.laws && data.laws.length > 0 ? (
            <div className="space-y-3">
              {data.laws.map((law) => (
                <LawListItem
                  key={law.id}
                  law={law}
                  onView={() => setSelectedLaw(law)}
                  onDelete={() => onDeleteLaw(law)}
                />
              ))}
            </div>
          ) : (
            <div className="bg-card border-border rounded-xl border p-8 text-center">
              <FileText className="text-muted-foreground/50 mx-auto mb-3 h-12 w-12" />
              <p className="text-muted-foreground">暂无法规数据</p>
              <button
                onClick={() => setShowImportModal(true)}
                className="text-primary mt-3 text-sm hover:underline"
              >
                导入第一份法规
              </button>
            </div>
          )}

          {/* Pagination */}
          {data && data.total > limit && (
            <div className="flex justify-center gap-2 pt-4">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="hover:bg-accent rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50"
              >
                上一页
              </button>
              <span className="px-3 py-1.5 text-sm">
                第 {page} / {Math.ceil(data.total / limit)} 页
              </span>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page >= Math.ceil(data.total / limit)}
                className="hover:bg-accent rounded-lg border px-3 py-1.5 text-sm disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="border-border bg-card/80 text-muted-foreground flex shrink-0 flex-wrap items-center justify-between gap-2 border-t px-6 py-3 text-sm backdrop-blur-sm">
        <span>
          共 {totalCount.toLocaleString()} 份法规标准 | 现行有效 {activeCount} |
          已废止 {deprecatedCount}
        </span>
        {statistics && (
          <span className="text-xs">
            已同步 {statistics.synced_count} | 待同步{" "}
            {statistics.pending_sync_count} | 同步失败{" "}
            {statistics.failed_sync_count}
          </span>
        )}
      </div>
    </div>
  );
}

// Law list item component
function LawListItem({
  law,
  onView,
  onDelete,
}: {
  law: LawItem;
  onView: () => void;
  onDelete: () => void;
}) {
  const { color, bgColor } = getCategoryColor(law.law_type);
  const category = getCategoryByCode(law.law_type);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return (
          <span className="bg-success/10 text-success inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
            <CheckCircle className="h-3 w-3" /> 现行
          </span>
        );
      case "deprecated":
        return (
          <span className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
            已废止
          </span>
        );
      case "updating":
        return (
          <span className="bg-warning/10 text-warning inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
            <Loader2 className="h-3 w-3" /> 修订中
          </span>
        );
      default:
        return null;
    }
  };

  const getSyncBadge = (isSynced: string) => {
    switch (isSynced) {
      case "synced":
        return (
          <span
            className="bg-info/10 text-info inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs"
            title="已同步到RAGFlow"
          >
            <CheckCircle className="h-3 w-3" /> 已同步
          </span>
        );
      case "pending":
        return (
          <span
            className="bg-warning/10 text-warning inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs"
            title="待同步"
          >
            <Clock className="h-3 w-3" /> 待同步
          </span>
        );
      case "failed":
        return (
          <span
            className="bg-destructive/10 text-destructive inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs"
            title="同步失败"
          >
            <AlertCircle className="h-3 w-3" /> 同步失败
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div
      className={cn(
        "bg-card border-border/50 hover:border-primary/30 rounded-xl border border-l-[3px] p-4 shadow-sm transition-all hover:shadow-md",
        color.replace("text-", "border-l-") + "/60",
      )}
    >
      <div className="flex items-start gap-4">
        {/* Category Icon */}
        <div
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            bgColor.replace("/10", "/20"),
          )}
        >
          {category && <category.icon className={cn("h-5 w-5", color)} />}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h4
                className="text-foreground hover:text-primary cursor-pointer font-medium transition-colors"
                onClick={onView}
              >
                {law.title}
              </h4>
              {getStatusBadge(law.status)}
              {getSyncBadge(law.is_synced)}
            </div>
            {law.law_number && (
              <p className="text-muted-foreground mt-0.5 text-sm">
                {law.law_number}
              </p>
            )}
          </div>

          <div className="text-muted-foreground mt-2 flex items-center gap-6 text-sm">
            {law.department && <span>发布: {law.department}</span>}
            {law.effective_date && (
              <span>
                生效: {new Date(law.effective_date).toLocaleDateString()}
              </span>
            )}
            {law.ref_count > 0 && (
              <span className="text-warning">引用 {law.ref_count} 次</span>
            )}
            {(law.view_count ?? 0) > 0 && <span>查看 {law.view_count} 次</span>}
          </div>

          {/* Keywords */}
          {law.keywords && law.keywords.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {law.keywords.slice(0, 5).map((kw, i) => (
                <span
                  key={i}
                  className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs"
                >
                  {kw}
                </span>
              ))}
              {law.keywords.length > 5 && (
                <span className="text-muted-foreground text-xs">
                  +{law.keywords.length - 5}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 gap-2">
          <button
            onClick={onView}
            className="text-primary hover:text-primary/70 flex items-center gap-1 text-sm transition-colors hover:underline"
          >
            详情 <ExternalLink className="h-3 w-3" />
          </button>
          <button
            onClick={onDelete}
            className="text-muted-foreground hover:text-destructive hover:bg-destructive/5 rounded-lg p-1.5 transition-colors"
            title="删除法规"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
