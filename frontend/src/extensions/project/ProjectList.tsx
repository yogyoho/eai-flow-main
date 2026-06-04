"use client";

import {
  Calendar,
  ChevronRight,
  Edit,
  FileText,
  FolderKanban,
  LayoutGrid,
  List,
  Loader2,
  MessageSquare,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { kfApi } from "@/extensions/api";
import { FilterPills } from "@/extensions/project/components/FilterPills";
import { useAuth } from "@/extensions/hooks/useAuth";
import { projectApi } from "@/extensions/project/api";
import type { ProjectListItem } from "@/extensions/project/types";
import { PROJECT_STATUS_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";

// ─── Color palette for dynamic types (cycles by index) ────────────────────────

const TYPE_PALETTE = [
  "bg-green-500/10 text-green-600",
  "bg-amber-500/10 text-amber-600",
  "bg-blue-500/10 text-blue-600",
  "bg-red-500/10 text-red-600",
  "bg-purple-500/10 text-purple-600",
  "bg-cyan-500/10 text-cyan-600",
  "bg-rose-500/10 text-rose-600",
  "bg-teal-500/10 text-teal-600",
  "bg-indigo-500/10 text-indigo-600",
  "bg-orange-500/10 text-orange-600",
];

const DEFAULT_TYPE_COLOR = "bg-primary/10 text-primary";

// ─── Status colors for badges ─────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  setup: "bg-slate-500/10 text-slate-600",
  outline: "bg-blue-500/10 text-blue-600",
  writing: "bg-violet-500/10 text-violet-600",
  editing: "bg-amber-500/10 text-amber-600",
  approval: "bg-orange-500/10 text-orange-600",
  active: "bg-primary/10 text-primary",
  completed: "bg-emerald-500/10 text-emerald-600",
  archived: "bg-gray-500/10 text-gray-500",
};

// ─── Stat card data ────────────────────────────────────────────────────────────

interface StatCard {
  icon: React.ReactNode;
  label: string;
  count: number;
  iconBg: string;
  iconColor: string;
}

function computeStats(projects: ProjectListItem[]): StatCard[] {
  const inProgress = projects.filter((p) => ["active", "outline", "writing", "editing", "approval"].includes(p.status)).length;
  return [
    {
      icon: <FolderKanban className="h-5 w-5" />,
      label: "全部项目",
      count: projects.length,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
    },
    {
      icon: <Edit className="h-5 w-5" />,
      label: "进行中",
      count: inProgress,
      iconBg: "bg-blue-500/10",
      iconColor: "text-[#3B82F6]",
    },
    {
      icon: <Loader2 className="h-5 w-5" />,
      label: "审批中",
      count: projects.filter((p) => p.status === "approval").length,
      iconBg: "bg-orange-500/10",
      iconColor: "text-orange-600",
    },
    {
      icon: <FolderKanban className="h-5 w-5" />,
      label: "已完成",
      count: projects.filter((p) => p.status === "completed").length,
      iconBg: "bg-emerald-500/10",
      iconColor: "text-emerald-600",
    },
  ];
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(dateString: string | null): string {
  if (!dateString) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
    .format(new Date(dateString))
    .replace(/\//g, "/");
}

// ─── Main ProjectList ─────────────────────────────────────────────────────────

export function ProjectList() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // ── URL-persisted filter state ───────────────────────────────────────────
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const [searchQuery, setSearchQuery] = useState(searchParams.get("q") ?? "");
  const [typeFilter, setTypeFilter] = useState(searchParams.get("type") ?? "all");
  const [viewMode, setViewMode] = useState<"grid" | "list">(
    (searchParams.get("view") as "grid" | "list") ?? "grid",
  );

  // Sync filter changes to URL (debounced for search)
  const syncToUrl = useCallback(
    (q: string, type: string, view: string) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (type && type !== "all") params.set("type", type);
      if (view !== "grid") params.set("view", view);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchQuery(value);
      syncToUrl(value, typeFilter, viewMode);
    },
    [typeFilter, viewMode, syncToUrl],
  );

  const handleTypeChange = useCallback(
    (value: string) => {
      setTypeFilter(value);
      syncToUrl(searchQuery, value, viewMode);
    },
    [searchQuery, viewMode, syncToUrl],
  );

  const handleViewChange = useCallback(
    (value: "grid" | "list") => {
      setViewMode(value);
      syncToUrl(searchQuery, typeFilter, value);
    },
    [searchQuery, typeFilter, syncToUrl],
  );

  // ── Auth: permission check ─────────────────────────────────────────────────
  const { user: currentUser } = useAuth();
  const canCreateProject = useMemo(() => {
    if (!currentUser) return false;
    if (currentUser.is_admin) return true;
    return currentUser.permissions?.includes("project:create") ?? false;
  }, [currentUser]);

  // ── Dictionary: load industry types from business dictionary ──────────────

  const [industryDict, setIndustryDict] = useState<{ id: string; label: string }[]>([]);
  const [dictLoaded, setDictLoaded] = useState(false);

  // Build lookup: id → label
  const industryLookup = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of industryDict) {
      map.set(item.id, item.label);
    }
    return map;
  }, [industryDict]);

  // Build color/icon lookup by index
  const industryStyleLookup = useMemo(() => {
    const colorMap = new Map<string, string>();
    const iconMap = new Map<string, string>();
    industryDict.forEach((item, idx) => {
      colorMap.set(item.id, TYPE_PALETTE[idx % TYPE_PALETTE.length] ?? DEFAULT_TYPE_COLOR);
      iconMap.set(item.id, item.label.charAt(0));
    });
    return { colorMap, iconMap };
  }, [industryDict]);

  // Filter pills: "全部" + all enabled industry items
  const filterPills = useMemo(() => {
    return [
      { value: "all", label: "全部" },
      ...industryDict.map((item) => ({ value: item.id, label: item.label })),
    ];
  }, [industryDict]);

  // ── Data loading ───────────────────────────────────────────────────────────

  const loadProjects = useCallback(async () => {
    setIsLoading(true);
    try {
      const { items } = await projectApi.list();
      setProjects(items);
    } catch (e: any) {
      if (e?.status !== 404) {
        toast.error(e?.message ?? "加载项目失败");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadIndustryDict = useCallback(async () => {
    try {
      const res = await kfApi.listDictItems("industry", { limit: 200 });
      setIndustryDict(res.items.filter((i) => i.enabled).map((i) => ({ id: i.id, label: i.label })));
    } catch {
      // Fallback: empty dict — cards will show raw reportType
    } finally {
      setDictLoaded(true);
    }
  }, []);

  useEffect(() => {
    loadProjects();
    loadIndustryDict();
  }, [loadProjects, loadIndustryDict]);

  // ── Filtering ──────────────────────────────────────────────────────────────

  const filteredProjects = projects.filter((project) => {
    const matchesSearch = project.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === "all" || project.reportType === typeFilter;
    return matchesSearch && matchesType;
  });

  const stats = computeStats(projects);

  // ── Helpers for card rendering ─────────────────────────────────────────────

  const getTypeColor = (reportType: string) =>
    industryStyleLookup.colorMap.get(reportType) ?? DEFAULT_TYPE_COLOR;

  const getTypeIcon = (reportType: string) =>
    industryStyleLookup.iconMap.get(reportType) ?? "项";

  const getTypeLabel = (reportType: string) =>
    industryLookup.get(reportType) ?? reportType;

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("确定要删除该项目吗？此操作不可撤销。")) return;
    try {
      await projectApi.delete(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      toast.success("项目已删除");
    } catch (e: any) {
      toast.error(e?.message ?? "删除失败");
    }
  };

  const handleEdit = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    router.push(`/projects/${id}`);
  };

  const handleClick = (project: ProjectListItem) => {
    router.push(`/projects/${project.id}`);
  };

  const handleEnterChat = async (project: ProjectListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const { threadId } = await projectApi.enter(project.id);
      router.push(`/workspace/chats/${threadId}?from=project&projectId=${project.id}&projectName=${encodeURIComponent(project.name)}`);
    } catch {
      toast.error("进入对话失败，请确认你是项目成员");
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <main className="flex-1 overflow-y-auto bg-background">
      {/* Header */}
      <div className="flex h-14 items-center gap-4 border-b border-border bg-card px-7">
        <h1 className="text-lg font-bold text-foreground">项目管理</h1>
        <div className="flex-1" />
        <div className="relative">
          <Search className="absolute top-1/2 left-2.5 h-[15px] w-[15px] -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="搜索项目..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="h-[34px] w-[220px] rounded-[8px] border-border bg-card pl-8 pr-3 text-[13px] text-foreground placeholder:text-muted-foreground"
          />
        </div>
        {canCreateProject && (
          <Button
            onClick={() => router.push("/projects/new")}
            className="h-[34px] rounded-[8px] bg-primary px-3.5 text-[13px] font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-[15px] w-[15px]" />
            新建项目
          </Button>
        )}
      </div>

      {/* Stat cards row */}
      <div className="grid grid-cols-4 gap-3 px-7 pt-5">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="flex items-center gap-3.5 rounded-[8px] border border-border bg-card p-4"
          >
            <div className={cn("flex h-10 w-10 items-center justify-center rounded-[10px]", stat.iconBg, stat.iconColor)}>
              {stat.icon}
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[14px] text-muted-foreground">{stat.label}</span>
              <span className="text-[22px] font-bold leading-tight text-foreground">{stat.count}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Filter pills + view toggle */}
      <div className="flex items-center gap-2 px-7 pt-4">
        <FilterPills pills={filterPills} value={typeFilter} onChange={handleTypeChange} />
        <div className="flex-1" />
        <div className="flex h-[30px] items-center overflow-hidden rounded-[6px] border border-border bg-card">
          <button
            onClick={() => handleViewChange("grid")}
            className={cn(
              "flex h-[30px] w-[30px] items-center justify-center transition-colors",
              viewMode === "grid" ? "text-muted-foreground" : "text-foreground",
            )}
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <button
            onClick={() => handleViewChange("list")}
            className={cn(
              "flex h-[30px] w-[30px] items-center justify-center transition-colors",
              viewMode === "list" ? "text-muted-foreground" : "text-foreground",
            )}
          >
            <List className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading && dictLoaded ? (
        <></>
      ) : null}
      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          加载中...
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="mx-7 mt-5 flex flex-col items-center justify-center rounded-[8px] border border-dashed border-border bg-card py-16">
          <FolderKanban className="mb-3 h-12 w-12 text-muted-foreground/50" />
          <h3 className="text-sm font-medium text-foreground">未找到项目</h3>
          <p className="mt-1 text-sm text-muted-foreground">尝试调整搜索词或筛选条件</p>
        </div>
      ) : (
        <div
          className={cn(
            "px-7 pb-5 pt-4",
            viewMode === "grid"
              ? "grid grid-cols-1 gap-[14px] md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
              : "flex flex-col gap-[14px]",
          )}
        >
          {filteredProjects.map((project) => {
            const typeColor = getTypeColor(project.reportType);
            const typeIcon = getTypeIcon(project.reportType);
            const typeLabel = getTypeLabel(project.reportType);
            const statusColor = STATUS_COLORS[project.status] ?? "bg-muted text-muted-foreground";
            const statusLabel = PROJECT_STATUS_LABELS[project.status as keyof typeof PROJECT_STATUS_LABELS] ?? project.status;

            if (viewMode === "list") {
              return (
                <div
                  key={project.id}
                  onClick={() => handleClick(project)}
                  className="group flex cursor-pointer items-center gap-4 rounded-[8px] border border-border bg-card px-4 py-3 transition-shadow hover:shadow-sm"
                >
                  <div
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] text-sm font-bold",
                      typeColor,
                    )}
                  >
                    {typeIcon}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="truncate text-[14px] font-semibold text-foreground">{project.name}</h3>
                      <span
                        className={cn("shrink-0 rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold", statusColor)}
                      >
                        {statusLabel}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span>{typeLabel}</span>
                      <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {project.chapterCount}章
                      </span>
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {project.memberCount}人
                      </span>
                      <span>{formatDate(project.createdAt)}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleEnterChat(project, e)}
                      className="h-7 gap-1 px-2 text-xs text-primary hover:bg-primary/10"
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                      对话
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleEdit(project.id, e)}
                      className="h-7 w-7 text-muted-foreground hover:text-foreground"
                    >
                      <Edit className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleDelete(project.id, e)}
                      className="h-7 w-7 text-muted-foreground hover:text-red-500"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
              );
            }

            return (
              <div
                key={project.id}
                onClick={() => handleClick(project)}
                className="group flex cursor-pointer flex-col overflow-hidden rounded-[10px] border border-border bg-card transition-all hover:shadow-md hover:border-primary/20"
              >
                {/* Header: type icon + project name + status */}
                <div className="px-4 pt-4 pb-2">
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold",
                        typeColor,
                      )}
                    >
                      {typeIcon}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="line-clamp-1 flex-1 text-sm font-semibold text-foreground">{project.name}</h3>
                        <span className={cn("shrink-0 rounded-[4px] px-1.5 py-0.5 text-[10px] font-semibold", statusColor)}>
                          {statusLabel}
                        </span>
                      </div>
                      <span className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                        {typeLabel}{project.templateName && project.templateName !== typeLabel ? ` · ${project.templateName}` : ""}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Info grid: creator, dept, time, chapters */}
                <div className="flex-1 px-4 py-2">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                    {project.createdByName && (
                      <div className="flex items-center gap-1.5">
                        <Users className="h-3 w-3 shrink-0 text-muted-foreground/60" />
                        <span className="truncate text-[11px] text-muted-foreground">
                          {project.createdByName}
                        </span>
                      </div>
                    )}
                    {project.createdByDept && (
                      <div className="flex items-center gap-1.5">
                        <FolderKanban className="h-3 w-3 shrink-0 text-muted-foreground/60" />
                        <span className="truncate text-[11px] text-muted-foreground">
                          {project.createdByDept}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center gap-1.5">
                      <Calendar className="h-3 w-3 shrink-0 text-muted-foreground/60" />
                      <span className="text-[11px] text-muted-foreground">{formatDate(project.createdAt)}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <FileText className="h-3 w-3 shrink-0 text-muted-foreground/60" />
                      <span className="text-[11px] text-muted-foreground">
                        {project.chapterCount} 章节
                      </span>
                    </div>
                  </div>
                </div>

                {/* Footer: member count + actions */}
                <div className="flex items-center justify-between border-t border-border/60 bg-muted/20 px-4 py-2">
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Users className="h-3 w-3" />
                    {project.memberCount} 名成员
                  </span>
                  <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleEnterChat(project, e)}
                      className="h-6 gap-1 rounded-[6px] px-2 text-[11px] text-primary hover:bg-primary/10"
                    >
                      <MessageSquare className="h-3 w-3" />
                      对话
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleEdit(project.id, e)}
                      className="h-6 w-6 text-muted-foreground hover:text-foreground"
                    >
                      <Edit className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleDelete(project.id, e)}
                      className="h-6 w-6 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
