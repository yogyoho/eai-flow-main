"use client";

import {
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
  Settings,
  Trash2,
  Users,
} from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FilterPills } from "@/extensions/project/components/FilterPills";
import { projectApi } from "@/extensions/project/api";
import type { ProjectListItem } from "@/extensions/project/types";
import { REPORT_TYPE_LABELS, PROJECT_STATUS_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";

// ─── Report type colors for card icon circles ─────────────────────────────────

const REPORT_TYPE_COLORS: Record<string, string> = {
  environmental_impact: "bg-green-500/10 text-green-600",
  geological_survey: "bg-amber-500/10 text-amber-600",
  feasibility_study: "bg-blue-500/10 text-blue-600",
  safety_assessment: "bg-red-500/10 text-red-600",
  energy_assessment: "bg-purple-500/10 text-purple-600",
  other: "bg-[#0746FF]/10 text-[#0746FF]",
};

const REPORT_TYPE_ICONS: Record<string, string> = {
  environmental_impact: "环",
  geological_survey: "地",
  feasibility_study: "可",
  safety_assessment: "安",
  energy_assessment: "节",
  other: "报",
};

// ─── Status colors for badges ─────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  setup: "bg-primary/10 text-primary",
  outline: "bg-primary/10 text-primary",
  writing: "bg-purple-500/10 text-purple-600",
  editing: "bg-primary/10 text-primary",
  approval: "bg-warning/10 text-warning",
  published: "bg-success/10 text-success",
  archived: "bg-success/10 text-success",
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
      count: projects.filter((p) => p.status === "active").length,
      iconBg: "bg-blue-500/10",
      iconColor: "text-[#3B82F6]",
    },
    {
      icon: <Loader2 className="h-5 w-5" />,
      label: "审核中",
      count: projects.filter((p) => p.status === "active").length,
      iconBg: "bg-warning/10",
      iconColor: "text-warning",
    },
    {
      icon: <FolderKanban className="h-5 w-5" />,
      label: "已完成",
      count: projects.filter((p) => p.status === "completed").length,
      iconBg: "bg-success/10",
      iconColor: "text-success",
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

const FILTER_PILLS = [
  { value: "all", label: "全部" },
  ...Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({ value, label })),
];

// ─── Main ProjectList ─────────────────────────────────────────────────────────

export function ProjectList() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

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

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // ── Filtering ──────────────────────────────────────────────────────────────

  const filteredProjects = projects.filter((project) => {
    const matchesSearch = project.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === "all" || project.reportType === typeFilter;
    return matchesSearch && matchesType;
  });

  const stats = computeStats(projects);

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
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-[34px] w-[220px] rounded-[8px] border-border bg-card pl-8 pr-3 text-[13px] text-foreground placeholder:text-muted-foreground"
          />
        </div>
        <Button
          variant="outline"
          onClick={() => router.push("/projects/approval-settings")}
          className="h-[34px] rounded-[8px] border-border px-3.5 text-[13px] font-semibold text-foreground hover:bg-accent"
        >
          <Settings className="h-[15px] w-[15px]" />
          审批流程设置
        </Button>
        <Button
          onClick={() => router.push("/projects/new")}
          className="h-[34px] rounded-[8px] bg-primary px-3.5 text-[13px] font-semibold text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-[15px] w-[15px]" />
          新建项目
        </Button>
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
        <FilterPills pills={FILTER_PILLS} value={typeFilter} onChange={setTypeFilter} />
        <div className="flex-1" />
        <div className="flex h-[30px] items-center overflow-hidden rounded-[6px] border border-border bg-card">
          <button
            onClick={() => setViewMode("grid")}
            className={cn(
              "flex h-[30px] w-[30px] items-center justify-center transition-colors",
              viewMode === "grid" ? "text-muted-foreground" : "text-foreground",
            )}
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <button
            onClick={() => setViewMode("list")}
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
            const typeColor = REPORT_TYPE_COLORS[project.reportType] ?? REPORT_TYPE_COLORS.other;
            const typeIcon = REPORT_TYPE_ICONS[project.reportType] ?? REPORT_TYPE_ICONS.other;
            const typeLabel = REPORT_TYPE_LABELS[project.reportType] ?? project.reportType;
            const statusColor = STATUS_COLORS[project.status] ?? "bg-muted text-muted-foreground";
            const statusLabel = PROJECT_STATUS_LABELS[project.status] ?? project.status;

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
                className="group flex cursor-pointer flex-col overflow-hidden rounded-[8px] border border-border bg-card transition-shadow hover:shadow-sm"
              >
                {/* Top: type badge + status badge */}
                <div className="flex items-center gap-2 px-4 pt-3.5 pb-2">
                  <span className="rounded-[4px] bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary">
                    {typeLabel}
                  </span>
                  <div className="flex-1" />
                  <span className={cn("rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold", statusColor)}>
                    {statusLabel}
                  </span>
                </div>

                {/* Title + template */}
                <div className="flex flex-col gap-1.5 px-4 pb-3">
                  <h3 className="line-clamp-2 font-semibold leading-snug text-foreground">{project.name}</h3>
                  <span className="truncate text-xs text-muted-foreground">
                    {project.templateName ?? typeLabel}
                  </span>
                </div>

                {/* Metadata row */}
                <div className="flex items-center gap-3 border-t border-border px-4 py-2.5">
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <FileText className="h-[13px] w-[13px]" />
                    {project.chapterCount}章
                  </span>
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Users className="h-[13px] w-[13px]" />
                    {project.memberCount}人
                  </span>
                  <div className="flex-1" />
                  <span className="text-[11px] text-muted-foreground">{formatDate(project.createdAt)}</span>
                </div>
                {/* Enter chat action */}
                <div className="border-t border-border px-4 py-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => handleEnterChat(project, e)}
                    className="h-7 gap-1 px-2 text-xs text-primary hover:bg-primary/10"
                  >
                    <MessageSquare className="h-3.5 w-3.5" />
                    进入对话
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
