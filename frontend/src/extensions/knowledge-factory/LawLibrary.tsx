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
  Loader2,
  Globe,
} from "lucide-react";
import React, { useState } from "react";

import { AdminSelect } from "@/components/ui/admin-select";


// Import components
import ImportLawModal from "@/extensions/knowledge-factory/components/ImportLawModal";
import LawDetailDrawer from "@/extensions/knowledge-factory/components/LawDetailDrawer";
import LawScraperView from "@/extensions/knowledge-factory/components/LawScraperView";
import RAGFlowStatusPanel from "@/extensions/knowledge-factory/components/RAGFlowStatusPanel";
import { getCategoryColor } from "@/extensions/knowledge-factory/config/lawCategories";
import { LAW_CATEGORIES, LAW_TYPE_OPTIONS, getCategoryByCode } from "@/extensions/knowledge-factory/config/lawCategories";
import {
  useLawList,
  useLawStatistics,
  useRAGFlowStatus,
  useSyncAllLaws,
  useInitRAGFlow,
} from "@/extensions/knowledge-factory/hooks/useLawLibrary";
import type { LawItem, LawType, LawViewType } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

export default function LawLibrary() {
  // View state: list view or scraper view
  const [activeView, setActiveView] = useState<LawViewType>("list");

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
  const initRAGFlowMutation = useInitRAGFlow();

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

  // Get category counts from API
  const categoryCounts = data?.by_type || {};
  const totalCount = statistics?.total_count || data?.total || 0;
  const activeCount = statistics?.active_count || 0;
  const deprecatedCount = statistics?.deprecated_count || 0;

  // Check RAGFlow status for warnings
  const hasMissingKBs =
    ragflowStatus?.statuses?.some((s) => s.status === "missing") || false;

  // Handle import success
  const handleImportSuccess = () => {
    setActiveView("list");
    refetch();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center p-4 border-b border-border bg-card shrink-0">
        <h2 className="text-lg font-semibold flex items-center gap-2 text-foreground tracking-tight">
          <Library className="w-5 h-5 text-primary" />
          法规标准库
          {hasMissingKBs && (
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              未初始化
            </span>
          )}
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => setShowRAGFlowStatus(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            title="RAGFlow状态"
          >
            {ragflowStatus ? (
              ragflowStatus.missing_kbs > 0 ? (
                <AlertCircle className="w-4 h-4 text-amber-500" />
              ) : (
                <CheckCircle className="w-4 h-4 text-green-500" />
              )
            ) : (
              <Loader2 className="w-4 h-4 animate-spin" />
            )}
            <span className="hidden sm:inline">知识库状态</span>
          </button>
          <button
            onClick={() => syncAllMutation.mutate(undefined)}
            disabled={syncAllMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 text-foreground bg-card border border-border rounded-lg hover:bg-accent transition-colors shadow-sm font-medium text-sm disabled:opacity-50"
          >
            {syncAllMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            同步更新
          </button>
          <button
            onClick={() => setActiveView("scraper")}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-sm text-sm"
          >
            <Globe className="w-4 h-4" /> 爬取新法规
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors shadow-sm font-medium text-sm"
          >
            <Plus className="w-4 h-4" /> 导入新法规
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-h-0 overflow-hidden bg-muted/30">
        {activeView === "scraper" ? (
          <LawScraperView
            onBack={() => setActiveView("list")}
            onImportSuccess={handleImportSuccess}
          />
        ) : (
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
          />
        )}
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
        <LawDetailDrawer law={selectedLaw} onClose={() => setSelectedLaw(null)} />
      )}
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
  selectedLaw,
  setSelectedLaw,
  setShowImportModal,
}: LawListViewProps) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-6">
        {/* Search & Filter */}
        <div className="bg-card p-4 rounded-xl border border-border shadow-sm flex flex-wrap gap-4 items-center">
          <div className="relative flex-1 min-w-[300px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="请输入法规名称/标准号/关键词..."
              value={keyword}
              onChange={(e) => handleKeywordChange(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-muted border border-border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all text-sm"
            />
          </div>
          <div className="flex gap-3">
            <AdminSelect
              value={filterType}
              onChange={(v) => {
                setFilterType(v as LawType | "all");
                setPage(1);
              }}
              options={[{ value: "all", label: "全部类型" }, ...LAW_TYPE_OPTIONS]}
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
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
            <span className="text-red-700">{error.message}</span>
            <button
              onClick={() => refetch()}
              className="ml-auto text-sm text-red-600 hover:underline"
            >
              重试
            </button>
          </div>
        )}

        {/* Category Grid */}
        <div className="space-y-3">
          <h3 className="text-md font-semibold text-foreground flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary" /> 知识库分类
          </h3>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7">
            {LAW_CATEGORIES.map((cat) => {
              const count = data?.by_type?.[cat.code] || 0;
              const isActive = filterType === cat.code;
              return (
                <div
                  key={cat.code}
                  onClick={() => {
                    setFilterType(isActive ? "all" : cat.code);
                    setPage(1);
                  }}
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-xl border border-border bg-card p-5 shadow-sm transition-all hover:shadow-md",
                    isActive
                      ? "border-primary ring-2 ring-primary/20"
                      : "hover:border-primary/30"
                  )}
                >
                  <div
                    className={cn(
                      "flex size-12 shrink-0 items-center justify-center rounded-xl",
                      cat.bgColor
                    )}
                  >
                    <cat.icon className={cn("size-6", cat.color)} aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 truncate text-sm text-muted-foreground">{cat.name}</div>
                    <div className={cn("flex flex-wrap items-baseline gap-x-1 tabular-nums", cat.color)}>
                      <span className="text-2xl font-bold">{count}</span>
                      <span className="text-sm font-medium text-muted-foreground">份</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Law List */}
        <div className="space-y-3">
          <h3 className="text-md font-semibold text-foreground flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            {filterType !== "all"
              ? `${getCategoryByCode(filterType)?.name || filterType}列表`
              : "全部法规"}
            <span className="text-sm font-normal text-muted-foreground">
              ({data?.total || 0} 份)
            </span>
          </h3>

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          ) : data?.laws && data.laws.length > 0 ? (
            <div className="space-y-3">
              {data.laws.map((law) => (
                <LawListItem
                  key={law.id}
                  law={law}
                  onView={() => setSelectedLaw(law)}
                />
              ))}
            </div>
          ) : (
            <div className="bg-card rounded-xl border border-border p-8 text-center">
              <FileText className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
              <p className="text-muted-foreground">暂无法规数据</p>
              <button
                onClick={() => setShowImportModal(true)}
                className="mt-3 text-sm text-primary hover:underline"
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
                className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-50 hover:bg-accent"
              >
                上一页
              </button>
              <span className="px-3 py-1.5 text-sm">
                第 {page} / {Math.ceil(data.total / limit)} 页
              </span>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page >= Math.ceil(data.total / limit)}
                className="px-3 py-1.5 text-sm border rounded-lg disabled:opacity-50 hover:bg-accent"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="shrink-0 border-t border-border bg-card/80 backdrop-blur-sm px-6 py-3 text-sm text-muted-foreground flex flex-wrap items-center justify-between gap-2">
        <span>
          共 {totalCount.toLocaleString()} 份法规标准 | 现行有效 {activeCount} | 已废止{" "}
          {deprecatedCount}
        </span>
        {statistics && (
          <span className="text-xs">
            已同步 {statistics.synced_count} | 待同步 {statistics.pending_sync_count} | 同步失败{" "}
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
}: {
  law: LawItem;
  onView: () => void;
}) {
  const { color, bgColor } = getCategoryColor(law.law_type);
  const category = getCategoryByCode(law.law_type);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700">
            <CheckCircle className="w-3 h-3" /> 现行
          </span>
        );
      case "deprecated":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600">
            已废止
          </span>
        );
      case "updating":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700">
            <Loader2 className="w-3 h-3" /> 修订中
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
          <span className="text-xs text-green-600" title="已同步到RAGFlow">
            已同步
          </span>
        );
      case "pending":
        return (
          <span className="text-xs text-amber-600" title="待同步">
            待同步
          </span>
        );
      case "failed":
        return (
          <span className="text-xs text-red-600" title="同步失败">
            同步失败
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="bg-card p-4 rounded-xl border border-border shadow-sm hover:border-primary/30 hover:shadow-md transition-all">
      <div className="flex items-start gap-4">
        {/* Category Icon */}
        <div className={cn("w-10 h-10 shrink-0 rounded-lg flex items-center justify-center", bgColor)}>
          {category && <category.icon className={cn("w-5 h-5", color)} />}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h4
                className="font-medium text-foreground cursor-pointer hover:text-primary transition-colors"
                onClick={onView}
              >
                {law.title}
              </h4>
              {law.law_number && (
                <p className="text-sm text-muted-foreground mt-0.5">{law.law_number}</p>
              )}
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {getStatusBadge(law.status)}
              {getSyncBadge(law.is_synced)}
            </div>
          </div>

          <div className="flex items-center gap-6 text-sm text-muted-foreground mt-2">
            {law.department && <span>发布: {law.department}</span>}
            {law.effective_date && (
              <span>生效: {new Date(law.effective_date).toLocaleDateString()}</span>
            )}
            {law.ref_count > 0 && (
              <span className="text-amber-600">引用 {law.ref_count} 次</span>
            )}
            {(law.view_count ?? 0) > 0 && <span>查看 {law.view_count} 次</span>}
          </div>

          {/* Keywords */}
          {law.keywords && law.keywords.length > 0 && (
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              {law.keywords.slice(0, 5).map((kw, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 text-xs bg-muted text-muted-foreground rounded"
                >
                  {kw}
                </span>
              ))}
              {law.keywords.length > 5 && (
                <span className="text-xs text-muted-foreground">+{law.keywords.length - 5}</span>
              )}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2 shrink-0">
          <button
            onClick={onView}
            className="text-sm text-primary hover:text-primary/70 hover:underline flex items-center gap-1 transition-colors"
          >
            详情 <ExternalLink className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
