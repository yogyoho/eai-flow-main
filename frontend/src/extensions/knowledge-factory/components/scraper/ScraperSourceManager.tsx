"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Database, Globe, Layers, Loader2, Pencil, Play, Plus, Power, PowerOff, Scale, Trash2, Zap } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { scraperApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

import { useScraperContext } from "./ScraperContext";

interface SourceFormData {
  name: string;
  url_pattern: string;
  description: string;
  category: string;
  default_schema: string;
  default_provider: string;
  is_enabled: boolean;
}

const EMPTY_FORM: SourceFormData = {
  name: "",
  url_pattern: "",
  description: "",
  category: "",
  default_schema: "",
  default_provider: "firecrawl",
  is_enabled: true,
};

const PROVIDER_OPTIONS = [
  { value: "firecrawl", label: "Firecrawl", desc: "Firecrawl API", icon: Zap },
  { value: "jina", label: "Jina", desc: "Jina Reader", icon: Globe },
] as const;

interface SchemaItem {
  name: string;
  display_name: string;
  category: string;
}

function SchemaDropdown({
  schemas,
  value,
  onChange,
}: {
  schemas: SchemaItem[];
  value: string | undefined;
  onChange: (v: string | undefined, category: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const lawSchemas = schemas.filter((s) => s.category === "法规标准");
  const generalSchemas = schemas.filter((s) => s.category !== "法规标准");
  const selected = schemas.find((s) => s.name === value);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  function pick(schema: SchemaItem | undefined) {
    onChange(schema?.name, schema?.category || "");
    setOpen(false);
  }

  const groups: { key: string; label: string; icon: React.ComponentType<{ className?: string }>; color: string; items: SchemaItem[] }[] = [];
  if (lawSchemas.length) groups.push({ key: "law", label: "法规标准", icon: Scale, color: "text-primary", items: lawSchemas });
  if (generalSchemas.length) groups.push({ key: "general", label: "通用模板", icon: Layers, color: "text-warning", items: generalSchemas });

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          "w-full flex items-center gap-2 px-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm text-left transition-all outline-none",
          open ? "border-primary ring-[3px] ring-primary/20" : "hover:border-primary/30 focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px]"
        )}
      >
        {selected ? (
          <>
            <span className="flex-1 truncate font-medium">{selected.display_name}</span>
            <span className="text-[10px] text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded-md font-medium">{selected.category}</span>
          </>
        ) : (
          <span className="flex-1 text-muted-foreground">无（通用提取）</span>
        )}
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground shrink-0 transition-transform duration-200", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute z-[60] top-full left-0 right-0 mt-1.5 bg-popover border rounded-xl shadow-lg overflow-hidden animate-in fade-in-0 slide-in-from-top-1 duration-150">
          <div className="max-h-72 overflow-auto py-1">
            <button
              onClick={() => pick(undefined)}
              className={cn("w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-left transition-colors", !value ? "bg-primary/8 text-primary font-medium" : "text-foreground hover:bg-muted/60")}
            >
              <div className="flex-1">通用提取（无模板）</div>
              {!value && <Check className="h-4 w-4 text-primary shrink-0" />}
            </button>
            {groups.map((group) => {
              const GroupIcon = group.icon;
              return (
                <div key={group.key}>
                  <div className="flex items-center gap-2 px-3 pt-2 pb-1">
                    <GroupIcon className={cn("h-3.5 w-3.5", group.color)} />
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{group.label}</span>
                    <span className="flex-1 border-b border-dashed border-border" />
                  </div>
                  {group.items.map((s) => {
                    const active = value === s.name;
                    return (
                      <button
                        key={s.name}
                        onClick={() => pick(s)}
                        className={cn("w-full flex items-center gap-2.5 pl-7 pr-3 py-2 text-sm text-left transition-colors", active ? "bg-primary/8 text-primary font-medium" : "text-foreground hover:bg-muted/60")}
                      >
                        <span className="flex-1 truncate">{s.display_name}</span>
                        {active && <Check className="h-4 w-4 text-primary shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const CATEGORY_COLORS: Record<string, string> = {
  "法规标准": "bg-primary/10 text-primary border-primary/20",
  "行业标准": "bg-info/10 text-info border-info/20",
  "技术规范": "bg-warning/10 text-warning border-warning/20",
};

export default function ScraperSourceManager() {
  const [page, setPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<SourceFormData>(EMPTY_FORM);
  const { openScrapeDialog } = useScraperContext();
  const queryClient = useQueryClient();
  const [schemas, setSchemas] = useState<SchemaItem[]>([]);

  // Load schemas once
  useEffect(() => {
    scraperApi.listSchemas().then((res) => setSchemas(res.schemas || [])).catch(() => {});
  }, []);

  const { data, isLoading } = useQuery({
    queryKey: ["scraper-sources", page],
    queryFn: () => scraperApi.listSources({ page, page_size: 20 }),
  });

  const createMutation = useMutation({
    mutationFn: (d: Record<string, unknown>) => scraperApi.createSource(d as Parameters<typeof scraperApi.createSource>[0]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scraper-sources"] });
      setShowForm(false);
      setForm(EMPTY_FORM);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => scraperApi.updateSource(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scraper-sources"] });
      setShowForm(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => scraperApi.deleteSource(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scraper-sources"] }),
  });

  const sources = data?.sources || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / 20);

  function openCreate() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(true);
  }

  function openEdit(source: { id: string; name: string; url_pattern: string; [key: string]: unknown }) {
    setForm({
      name: source.name,
      url_pattern: source.url_pattern,
      description: (source.description as string) || "",
      category: (source.category as string) || "",
      default_schema: (source.default_schema as string) || "",
      default_provider: (source.default_provider as string) || "firecrawl",
      is_enabled: (source.is_enabled as boolean) ?? true,
    });
    setEditingId(source.id);
    setShowForm(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload: Record<string, unknown> = { ...form };
    if (!payload.category) delete payload.category;
    if (!payload.default_schema) delete payload.default_schema;
    if (!payload.description) delete payload.description;

    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3 border-b shrink-0 bg-card/50">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">共 <span className="font-semibold text-foreground tabular-nums">{total}</span> 个数据源</span>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 shadow-sm transition-all duration-200 active:scale-[0.98]"
        >
          <Plus className="h-4 w-4" /> 新增数据源
        </button>
      </div>

      {/* Create/Edit dialog */}
      <Dialog open={showForm} onOpenChange={(open) => { if (!open) { setShowForm(false); setEditingId(null); } }}>
        <DialogContent className="sm:max-w-[560px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Database className="h-5 w-5 text-primary" />
              {editingId ? "编辑数据源" : "新增数据源"}
            </DialogTitle>
            <DialogDescription>
              {editingId ? "修改数据源配置信息" : "配置数据源以便快速发起抓取任务"}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-5 py-2">
            {/* Name + URL row */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-sm font-semibold tracking-tight">名称 <span className="text-destructive">*</span></label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                  className="w-full px-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px] outline-none transition-all"
                  placeholder="例：国家标准全文公开系统"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-semibold tracking-tight">URL 模式 <span className="text-destructive">*</span></label>
                <div className="relative">
                  <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={form.url_pattern}
                    onChange={(e) => setForm({ ...form, url_pattern: e.target.value })}
                    required
                    className="w-full pl-10 pr-3 py-2.5 border rounded-xl text-sm bg-background shadow-sm focus-visible:border-primary focus-visible:ring-primary/20 focus-visible:ring-[3px] outline-none transition-all"
                    placeholder="https://openstd.samr.gov.cn/*"
                  />
                </div>
              </div>
            </div>

            {/* Schema (category + template) dropdown */}
            <div className="space-y-1.5">
              <label className="text-sm font-semibold tracking-tight">提取模板</label>
              <SchemaDropdown
                schemas={schemas}
                value={form.default_schema || undefined}
                onChange={(name, category) => setForm({ ...form, default_schema: name || "", category })}
              />
            </div>

            {/* Provider card selector */}
            <div className="space-y-1.5">
              <label className="text-sm font-semibold tracking-tight">默认引擎</label>
              <div className="grid grid-cols-2 gap-2">
                {PROVIDER_OPTIONS.map((p) => {
                  const Icon = p.icon;
                  const active = form.default_provider === p.value;
                  return (
                    <button
                      key={p.value}
                      type="button"
                      onClick={() => setForm({ ...form, default_provider: p.value })}
                      className={cn(
                        "flex items-center gap-2.5 px-4 py-3 rounded-xl border text-left transition-all",
                        active ? "border-primary/30 bg-primary/5 shadow-sm" : "border-border hover:border-primary/20 hover:bg-muted/50"
                      )}
                    >
                      <Icon className={cn("h-4 w-4 shrink-0", active ? "text-primary" : "text-muted-foreground")} />
                      <div>
                        <span className={cn("text-sm font-medium block", active ? "text-foreground" : "text-muted-foreground")}>{p.label}</span>
                        <span className="text-xs text-muted-foreground">{p.desc}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3 pt-1">
              <button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:bg-primary/90 shadow-sm transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none active:scale-[0.98]"
              >
                {(createMutation.isPending || updateMutation.isPending) ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {editingId ? "保存修改" : "创建数据源"}
              </button>
              <button
                type="button"
                onClick={() => { setShowForm(false); setEditingId(null); }}
                className="px-5 py-2.5 border rounded-xl text-sm font-medium hover:bg-muted transition-colors shadow-sm"
              >
                取消
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Source list */}
      <div className="flex-1 overflow-auto p-3">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin mb-3 text-primary/60" />
            <p className="text-sm">加载数据源...</p>
          </div>
        ) : sources.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
            <div className="bg-muted/50 rounded-2xl p-6 mb-4">
              <Globe className="h-12 w-12 text-muted-foreground/30" />
            </div>
            <p className="text-sm font-medium mb-1">暂无数据源</p>
            <p className="text-xs text-muted-foreground/70 mb-4">添加数据源以便快速发起抓取任务</p>
            <button
              onClick={openCreate}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 shadow-sm transition-all"
            >
              <Plus className="h-3.5 w-3.5" /> 添加第一个数据源
            </button>
          </div>
        ) : (
          <div className="grid gap-2">
            {sources.map((source) => {
              const categoryColor = CATEGORY_COLORS[source.category || ""] || "bg-muted text-muted-foreground border-border";
              return (
                <div
                  key={source.id}
                  className={cn(
                    "group flex items-center gap-4 px-4 py-3.5 rounded-xl border transition-all duration-200",
                    source.is_enabled
                      ? "border-border bg-card shadow-sm hover:shadow-md hover:border-primary/20"
                      : "border-border/50 bg-muted/20 opacity-70"
                  )}
                >
                  {/* Enable/Disable indicator */}
                  <div className={cn("shrink-0", source.is_enabled ? "text-success" : "text-muted-foreground/40")}>
                    {source.is_enabled ? <Power className="h-4 w-4" /> : <PowerOff className="h-4 w-4" />}
                  </div>

                  {/* Name + URL */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{source.name}</p>
                      {!source.is_enabled && (
                        <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-md uppercase tracking-wider font-bold">已禁用</span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5 font-mono">{source.url_pattern}</p>
                  </div>

                  {/* Badges */}
                  {source.category && (
                    <span className={cn("px-2 py-0.5 rounded-lg text-xs font-medium border shrink-0", categoryColor)}>
                      {source.category}
                    </span>
                  )}
                  {source.default_schema && (
                    <span className="px-2 py-0.5 bg-primary/8 text-primary rounded-lg text-xs font-medium shrink-0 border border-primary/10">
                      {source.default_schema}
                    </span>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => { e.stopPropagation(); openScrapeDialog({
                        url: source.url_pattern,
                        provider: source.default_provider,
                        schema: source.default_schema,
                      }); }}
                      className="p-2 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                      title="立即抓取"
                    >
                      <Play className="h-4 w-4" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); openEdit(source); }}
                      className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      title="编辑"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); if (confirm("确定删除该数据源？")) deleteMutation.mutate(source.id); }}
                      className="p-2 rounded-lg hover:bg-destructive/5 text-muted-foreground hover:text-destructive transition-colors"
                      title="删除"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 px-4 py-3 border-t shrink-0 bg-card/50">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-4 py-1.5 text-sm rounded-lg border bg-card hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors shadow-sm"
          >
            上一页
          </button>
          <span className="text-sm text-muted-foreground font-medium tabular-nums">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="px-4 py-1.5 text-sm rounded-lg border bg-card hover:bg-muted disabled:opacity-40 disabled:pointer-events-none transition-colors shadow-sm"
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
