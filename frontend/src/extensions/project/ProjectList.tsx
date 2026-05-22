"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Clock,
  FolderCheck,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { projectApi } from "@/extensions/project/api";
import type { CreateProjectRequest, ReportType } from "@/extensions/project/types";
import { REPORT_TYPE_LABELS, PROJECT_STATUS_LABELS } from "@/extensions/project/types";
import { cn } from "@/lib/utils";

import { ProjectCard } from "./components/ProjectCard";

// ─── Toast ─────────────────────────────────────────────────────────────────────

type ToastType = "success" | "error" | "info";
interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed right-6 bottom-6 z-[100] flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className={cn(
              "pointer-events-auto flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg backdrop-blur-sm",
              t.type === "success" && "border-green-200 bg-green-600 text-white",
              t.type === "error" && "border-red-200 bg-red-600 text-white",
              t.type === "info" && "border-blue-200 bg-blue-600 text-white",
            )}
          >
            {t.type === "success" && <CheckCircle2 className="h-4 w-4 shrink-0" />}
            {t.type === "error" && <AlertCircle className="h-4 w-4 shrink-0" />}
            {t.type === "info" && <RefreshCw className="h-4 w-4 shrink-0" />}
            <span>{t.message}</span>
            <button onClick={() => onRemove(t.id)} className="ml-1 opacity-60 transition-opacity hover:opacity-100">
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const show = useCallback((message: string, type: ToastType = "info") => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);
  const remove = useCallback((id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)), []);
  return { toasts, show, remove };
}

// ─── Custom Select ───────────────────────────────────────────────────────────────

interface SelectOption {
  value: string;
  label: string;
  icon?: React.ReactNode;
}

function CustomSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: SelectOption[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm",
          "border bg-background transition-all duration-150",
          open ? "border-primary shadow-sm ring-2 ring-ring/50" : "border-input hover:border-input hover:shadow-sm",
        )}
      >
        <span className={cn("flex min-w-0 items-center gap-2", selected ? "text-foreground" : "text-muted-foreground")}>
          {selected?.icon && <span className="shrink-0 text-muted-foreground">{selected.icon}</span>}
          <span className="truncate">{selected?.label ?? "请选择"}</span>
        </span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="absolute top-full right-0 left-0 z-50 mt-1.5 overflow-hidden rounded-xl border border-border bg-background shadow-lg shadow-black/5"
          >
            {options.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm transition-colors",
                  o.value === value ? "bg-primary/10 font-medium text-primary" : "text-foreground hover:bg-muted",
                )}
              >
                {o.icon && (
                  <span className={cn("shrink-0", o.value === value ? "text-primary" : "text-muted-foreground")}>
                    {o.icon}
                  </span>
                )}
                {o.label}
                {o.value === value && <CheckCircle2 className="ml-auto h-3.5 w-3.5 shrink-0 text-primary" />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Filter options ─────────────────────────────────────────────────────────────

const STATUS_FILTER_OPTIONS: SelectOption[] = [
  { value: "all", label: "所有状态", icon: <FolderCheck className="h-3.5 w-3.5" /> },
  ...Object.entries(PROJECT_STATUS_LABELS).map(([value, label]) => ({
    value,
    label,
    icon: <Clock className="h-3.5 w-3.5" />,
  })),
];

const TYPE_FILTER_OPTIONS: SelectOption[] = [
  { value: "all", label: "所有类型", icon: <Search className="h-3.5 w-3.5" /> },
  ...Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({
    value,
    label,
    icon: <FolderCheck className="h-3.5 w-3.5" />,
  })),
];

// ─── Create Modal ───────────────────────────────────────────────────────────────

function CreateProjectModal({
  onClose,
  onCreated,
  toast,
}: {
  onClose: () => void;
  onCreated: () => void;
  toast: (msg: string, type?: ToastType) => void;
}) {
  const [form, setForm] = useState<CreateProjectRequest>({
    name: "",
    reportType: "environmental_impact",
    client: "",
  });
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!form.name.trim() || !form.client.trim()) return;
    setCreating(true);
    try {
      await projectApi.create(form);
      toast("项目创建成功", "success");
      onCreated();
      onClose();
    } catch (e: any) {
      toast(e?.message ?? "创建失败", "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
      >
        <div className="flex items-center gap-3 border-b border-border bg-muted/50 px-6 py-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
            <FolderCheck className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold leading-tight text-foreground">新建项目</h3>
            <div className="text-xs text-muted-foreground">创建一个新的报告项目</div>
          </div>
        </div>
        <div className="space-y-5 p-6">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              项目名称 <span className="text-destructive">*</span>
            </label>
            <Input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full"
              placeholder="例如：XX建设项目环境影响评价"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              报告类型 <span className="text-destructive">*</span>
            </label>
            <CustomSelect
              value={form.reportType}
              onChange={(v) => setForm({ ...form, reportType: v as ReportType })}
              options={Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({
                value,
                label,
                icon: <FolderCheck className="h-3.5 w-3.5" />,
              }))}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              委托方 <span className="text-destructive">*</span>
            </label>
            <Input
              type="text"
              value={form.client}
              onChange={(e) => setForm({ ...form, client: e.target.value })}
              className="w-full"
              placeholder="例如：XX建设有限公司"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleCreate} disabled={!form.name.trim() || !form.client.trim() || creating}>
            {creating && <Loader2 className="h-4 w-4 animate-spin" />}
            创建
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

// ─── Main ProjectList ─────────────────────────────────────────────────────────

export function ProjectList() {
  const router = useRouter();
  const { toasts, show: toast, remove } = useToast();
  const [projects, setProjects] = useState<import("@/extensions/project/types").ReportProject[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const loadProjects = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await projectApi.list();
      setProjects(data);
    } catch (e: any) {
      toast(e?.message ?? "加载项目失败", "error");
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const filteredProjects = projects.filter((project) => {
    const matchesSearch = project.name.toLowerCase().includes(searchQuery.toLowerCase()) || project.client.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || project.status === statusFilter;
    const matchesType = typeFilter === "all" || project.reportType === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除该项目吗？此操作不可撤销。")) return;
    try {
      await projectApi.delete(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      toast("项目已删除", "success");
    } catch (e: any) {
      toast(e?.message ?? "删除失败", "error");
    }
  };

  const handleEdit = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    router.push(`/projects/${id}`);
  };

  const handleClick = (project: import("@/extensions/project/types").ReportProject) => {
    router.push(`/projects/${project.id}`);
  };

  return (
    <main className="flex-1 overflow-y-auto bg-muted/50 p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">项目管理</h1>
            <p className="mt-1 text-sm text-muted-foreground">管理报告项目，跟踪编写、审核和发布进度。</p>
          </div>
          <Button onClick={() => setIsCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            新建项目
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-col items-center justify-between gap-4 rounded-xl border border-border bg-background p-4 shadow-sm sm:flex-row">
          <div className="relative w-full sm:w-64">
            <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder="搜索项目名称或委托方..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-muted pl-9 pr-4"
            />
          </div>
          <div className="flex w-full gap-3 sm:w-auto">
            <div className="w-full sm:w-40">
              <CustomSelect value={statusFilter} onChange={setStatusFilter} options={STATUS_FILTER_OPTIONS} />
            </div>
            <div className="w-full sm:w-40">
              <CustomSelect value={typeFilter} onChange={setTypeFilter} options={TYPE_FILTER_OPTIONS} />
            </div>
          </div>
        </div>

        {/* Grid / Loading / Empty */}
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {filteredProjects.map((project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onClick={() => handleClick(project)}
                  onEdit={(e) => handleEdit(project.id, e)}
                  onDelete={(e) => handleDelete(project.id, e)}
                />
              ))}
            </AnimatePresence>

            {filteredProjects.length === 0 && (
              <div className="col-span-full rounded-xl border border-dashed border-border bg-background py-12 text-center">
                <FolderCheck className="mx-auto mb-3 h-12 w-12 text-muted-foreground/50" />
                <h3 className="text-sm font-medium text-foreground">未找到项目</h3>
                <p className="mt-1 text-sm text-muted-foreground">尝试调整搜索词或筛选条件</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>{isCreateOpen && <CreateProjectModal onClose={() => setIsCreateOpen(false)} onCreated={loadProjects} toast={toast} />}</AnimatePresence>

      {/* Toast Container */}
      <ToastContainer toasts={toasts} onRemove={remove} />
    </main>
  );
}
