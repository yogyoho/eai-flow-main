"use client";

// Collab Workspace 首页 — 项目列表
// EAI-CUSTOM: 全新模块。UI 样式对齐项目管理页 (extensions/project/ProjectList)

import {
  Boxes,
  CheckCircle2,
  ChevronRight,
  Clock,
  Edit3,
  FileText,
  FolderKanban,
  LayoutGrid,
  List,
  Loader2,
  Plus,
  Search,
  Send,
  Trash2,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FilterPills } from "@/extensions/project/components/FilterPills";
import { cn } from "@/lib/utils";

import { workspaceApi } from "./api";
import type { CollabProject, ProjectKind, ProjectStatus } from "./types";

// ─── Labels ────────────────────────────────────────────────────────────────────

const KIND_LABELS: Record<ProjectKind, string> = {
  quickdoc: "快速文档",
  report: "多章节报告",
};

const KIND_STYLE: Record<
  ProjectKind,
  { color: string; icon: React.ElementType }
> = {
  quickdoc: { color: "bg-info/10 text-info", icon: FileText },
  report: { color: "bg-primary/10 text-primary", icon: FolderKanban },
};

const STATUS_LABELS: Record<ProjectStatus, string> = {
  active: "进行中",
  submitted_for_release: "待发布",
  released: "已发布",
  archived: "已归档",
};

const STATUS_COLORS: Record<ProjectStatus, string> = {
  active: "bg-primary/10 text-primary",
  submitted_for_release: "bg-warning/10 text-warning",
  released: "bg-success/10 text-success",
  archived: "bg-muted text-muted-foreground",
};

// ─── Stat cards ─────────────────────────────────────────────────────────────────

interface StatCard {
  icon: React.ReactNode;
  label: string;
  count: number;
  iconBg: string;
  iconColor: string;
}

function computeStats(projects: CollabProject[]): StatCard[] {
  return [
    {
      icon: <FolderKanban className="h-5 w-5" />,
      label: "全部项目",
      count: projects.length,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
    },
    {
      icon: <Edit3 className="h-5 w-5" />,
      label: "进行中",
      count: projects.filter((p) => p.status === "active").length,
      iconBg: "bg-primary/10",
      iconColor: "text-primary",
    },
    {
      icon: <Clock className="h-5 w-5" />,
      label: "待发布",
      count: projects.filter((p) => p.status === "submitted_for_release")
        .length,
      iconBg: "bg-warning/10",
      iconColor: "text-warning",
    },
    {
      icon: <CheckCircle2 className="h-5 w-5" />,
      label: "已发布",
      count: projects.filter((p) => p.status === "released").length,
      iconBg: "bg-success/10",
      iconColor: "text-success",
    },
  ];
}

// ─── Helpers ────────────────────────────────────────────────────────────────────

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
  { value: "quickdoc", label: "快速文档" },
  { value: "report", label: "多章节报告" },
];

// ─── Main WorkspaceHome ─────────────────────────────────────────────────────────

export function WorkspaceHome() {
  const router = useRouter();
  const [projects, setProjects] = useState<CollabProject[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // ── Create state ────────────────────────────────────────────────────────────
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ProjectKind>("quickdoc");
  const [creating, setCreating] = useState(false);

  // ── Data loading ─────────────────────────────────────────────────────────────
  const load = async () => {
    try {
      const data = await workspaceApi.listProjects();
      setProjects(data);
    } catch {
      toast.error("加载项目失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error("请输入项目名称");
      return;
    }
    setCreating(true);
    try {
      const p = await workspaceApi.createProject(name.trim(), kind);
      toast.success("项目已创建");
      setShowCreate(false);
      setName("");
      router.push(`/agentspace/${p.id}`);
    } catch {
      toast.error("创建失败");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("确定要删除该项目吗？此操作不可撤销。")) return;
    try {
      await workspaceApi.deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      toast.success("项目已删除");
    } catch (e: unknown) {
      toast.error((e as { message?: string })?.message ?? "删除失败");
    }
  };

  const handleOpen = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    router.push(`/agentspace/${id}`);
  };

  // ── Filtering ────────────────────────────────────────────────────────────────
  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      const matchesSearch = project.name
        .toLowerCase()
        .includes(searchQuery.toLowerCase());
      const matchesKind = kindFilter === "all" || project.kind === kindFilter;
      return matchesSearch && matchesKind;
    });
  }, [projects, searchQuery, kindFilter]);

  const stats = computeStats(projects);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <main className="bg-background flex-1 overflow-y-auto">
      {/* Header */}
      <div className="border-border bg-card flex h-14 items-center gap-4 border-b px-7">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border border-violet-200 bg-violet-50 text-violet-600 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300">
          <Boxes className="h-4 w-4" />
        </div>
        <h1 className="text-foreground text-lg font-bold">协作工作台</h1>
        <div className="flex-1" />
        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 h-[15px] w-[15px] -translate-y-1/2" />
          <Input
            type="text"
            placeholder="搜索项目..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="border-border bg-card text-foreground placeholder:text-muted-foreground h-[34px] w-[220px] rounded-md pr-3 pl-8 text-sm"
          />
        </div>
        <Button
          onClick={() => setShowCreate((v) => !v)}
          className="bg-primary text-primary-foreground hover:bg-primary/90 h-[34px] rounded-md px-3.5 text-sm font-semibold"
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
            className="border-border bg-card flex items-center gap-3.5 rounded-md border p-4"
          >
            <div
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-[10px]",
                stat.iconBg,
                stat.iconColor,
              )}
            >
              {stat.icon}
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-muted-foreground text-sm">
                {stat.label}
              </span>
              <span className="text-foreground text-[22px] leading-tight font-bold">
                {stat.count}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Create panel (inline) */}
      {showCreate && (
        <div className="border-border bg-card mx-7 mt-5 flex flex-col gap-3 rounded-md border p-4 md:max-w-md">
          <Input
            placeholder="项目名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="border-border bg-background h-9 rounded-md text-sm"
          />
          <div className="flex gap-2">
            {(Object.keys(KIND_LABELS) as ProjectKind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={cn(
                  "flex-1 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors",
                  kind === k
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {KIND_LABELS[k]}
              </button>
            ))}
          </div>
          <Button
            onClick={handleCreate}
            disabled={creating}
            className="h-9 w-full"
          >
            {creating ? "创建中..." : "创建"}
          </Button>
        </div>
      )}

      {/* Filter pills + view toggle */}
      <div className="flex items-center gap-2 px-7 pt-4">
        <FilterPills
          pills={FILTER_PILLS}
          value={kindFilter}
          onChange={setKindFilter}
        />
        <div className="flex-1" />
        <div className="border-border bg-card flex h-[30px] items-center overflow-hidden rounded-sm border">
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
        <div className="text-muted-foreground flex items-center justify-center gap-2 py-16 text-sm">
          <Loader2 className="h-5 w-5 animate-spin" />
          加载中...
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="border-border bg-card mx-7 mt-5 flex flex-col items-center justify-center rounded-md border border-dashed py-16">
          <FolderKanban className="text-muted-foreground/50 mb-3 h-12 w-12" />
          <h3 className="text-foreground text-sm font-medium">
            {projects.length === 0 ? "还没有项目" : "未找到项目"}
          </h3>
          <p className="text-muted-foreground mt-1 text-sm">
            {projects.length === 0
              ? "新建一个快速文档或报告项目开始"
              : "尝试调整搜索词或筛选条件"}
          </p>
        </div>
      ) : (
        <div
          className={cn(
            "px-7 pt-4 pb-5",
            viewMode === "grid"
              ? "grid grid-cols-1 gap-[14px] md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
              : "flex flex-col gap-[14px]",
          )}
        >
          {filteredProjects.map((project) => {
            const style = KIND_STYLE[project.kind];
            const KindIcon = style.icon;
            const statusColor =
              STATUS_COLORS[project.status] ?? "bg-muted text-muted-foreground";
            const statusLabel = STATUS_LABELS[project.status] ?? project.status;

            if (viewMode === "list") {
              return (
                <div
                  key={project.id}
                  onClick={() => handleOpen(project.id)}
                  className="group border-border bg-card flex cursor-pointer items-center gap-4 rounded-md border px-4 py-3 transition-shadow hover:shadow-sm"
                >
                  <div
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px]",
                      style.color,
                    )}
                  >
                    <KindIcon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-foreground truncate text-sm font-semibold">
                        {project.name}
                      </h3>
                      <span
                        className={cn(
                          "shrink-0 rounded-[4px] px-1.5 py-0.5 text-xs font-semibold",
                          statusColor,
                        )}
                      >
                        {statusLabel}
                      </span>
                    </div>
                    <div className="text-muted-foreground mt-1 flex items-center gap-3 text-xs">
                      <span>{KIND_LABELS[project.kind]}</span>
                      <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {project.kind === "quickdoc"
                          ? "单文档"
                          : `${project.sectionCount}章`}
                      </span>
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {project.memberCount}人
                      </span>
                      <span>{formatDate(project.updatedAt)}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleOpen(project.id, e)}
                      className="text-primary hover:bg-primary/10 h-7 gap-1 px-2 text-xs"
                    >
                      <Send className="h-3.5 w-3.5" />
                      进入
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleDelete(project.id, e)}
                      className="text-muted-foreground hover:text-destructive h-7 w-7"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <ChevronRight className="text-muted-foreground h-4 w-4 shrink-0" />
                </div>
              );
            }

            return (
              <div
                key={project.id}
                onClick={() => handleOpen(project.id)}
                className="group border-border bg-card hover:border-primary/20 flex cursor-pointer flex-col overflow-hidden rounded-[10px] border transition-all hover:shadow-md"
              >
                {/* Header: kind icon + name + status */}
                <div className="px-4 pt-4 pb-2">
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                        style.color,
                      )}
                    >
                      <KindIcon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-foreground line-clamp-1 flex-1 text-sm font-semibold">
                          {project.name}
                        </h3>
                        <span
                          className={cn(
                            "shrink-0 rounded-[4px] px-1.5 py-0.5 text-[10px] font-semibold",
                            statusColor,
                          )}
                        >
                          {statusLabel}
                        </span>
                      </div>
                      <span className="text-muted-foreground mt-0.5 line-clamp-1 text-xs">
                        {KIND_LABELS[project.kind]}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Info grid: sections, tasks, members, time */}
                <div className="flex-1 px-4 py-2">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                    <div className="flex items-center gap-1.5">
                      <FileText className="text-muted-foreground/60 h-3 w-3 shrink-0" />
                      <span className="text-muted-foreground text-xs">
                        {project.kind === "quickdoc"
                          ? "单文档"
                          : `${project.sectionCount} 章节`}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <FolderKanban className="text-muted-foreground/60 h-3 w-3 shrink-0" />
                      <span className="text-muted-foreground text-xs">
                        {project.taskCount} 任务
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Users className="text-muted-foreground/60 h-3 w-3 shrink-0" />
                      <span className="text-muted-foreground text-xs">
                        {project.memberCount} 成员
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Clock className="text-muted-foreground/60 h-3 w-3 shrink-0" />
                      <span className="text-muted-foreground text-xs">
                        {formatDate(project.updatedAt)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Footer: actions */}
                <div className="border-border/60 bg-muted/20 flex items-center justify-between border-t px-4 py-2">
                  <span className="text-muted-foreground text-xs">
                    {project.kind === "quickdoc" ? "快速文档" : "多章节报告"}
                  </span>
                  <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleOpen(project.id, e)}
                      className="text-primary hover:bg-primary/10 h-6 gap-1 rounded-[6px] px-2 text-xs"
                    >
                      <Send className="h-3 w-3" />
                      进入
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleDelete(project.id, e)}
                      className="text-muted-foreground hover:text-destructive h-6 w-6"
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
