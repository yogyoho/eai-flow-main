"use client";

import {
  BookOpen,
  Plus,
  Trash2,
  Edit3,
  Loader2,
  CheckCircle2,
  XCircle,
  GripVertical,
} from "lucide-react";
import React, { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { kfApi } from "@/extensions/api";
import type { ExtractionDomain, DictItemResponse } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

type CategoryKey = "domain" | "industry" | "report_type" | "region" | "rule_type" | "severity_level";

interface CategoryTab {
  key: CategoryKey;
  label: string;
}

const CATEGORY_TABS: CategoryTab[] = [
  { key: "domain", label: "报告大纲" },
  { key: "industry", label: "业务领域" },
  { key: "report_type", label: "报告类型" },
  { key: "region", label: "适用地区" },
  { key: "rule_type", label: "规则分类" },
  { key: "severity_level", label: "严重级别" },
];

// ============== Domain Edit Dialog ==============

interface ChapterItem {
  id: string;
  title: string;
  level?: number;
}

interface InferSection {
  id: string;
  title: string;
  level?: number;
  children?: InferSection[];
}

function flattenSections(sections: InferSection[], parentLevel = 0): ChapterItem[] {
  const result: ChapterItem[] = [];
  for (const s of sections) {
    const level = s.level ?? parentLevel + 1;
    result.push({ id: s.id, title: s.title, level });
    if (s.children?.length) result.push(...flattenSections(s.children, level));
  }
  return result;
}

function DomainEditDialog({
  domain,
  onClose,
  onSave,
}: {
  domain: ExtractionDomain | null;
  onClose: () => void;
  onSave: (data: { id?: string; name: string; description: string; standard_chapters: Record<string, unknown>; industry?: string; report_type?: string }) => void;
}) {
  const isEdit = !!domain;
  const [name, setName] = useState(domain?.name ?? "");
  const [description, setDescription] = useState(domain?.description ?? "");
  const [industry, setIndustry] = useState(domain?.industry ?? "");
  const [reportType, setReportType] = useState(domain?.report_type ?? "");
  const [industryOptions, setIndustryOptions] = useState<{ value: string; label: string }[]>([]);
  const [reportTypeOptions, setReportTypeOptions] = useState<{ value: string; label: string }[]>([]);
  const [chapters, setChapters] = useState<ChapterItem[]>(() => {
    const sections = (domain?.standard_chapters as { sections?: ChapterItem[] })?.sections ?? [];
    return sections.length > 0 ? sections : [];
  });
  const [newTitle, setNewTitle] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [maxDepth, setMaxDepth] = useState(3);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [indRes, rtRes] = await Promise.all([
          kfApi.listDictItems("industry"),
          kfApi.listDictItems("report_type"),
        ]);
        setIndustryOptions(indRes.items.filter((i) => i.enabled).map((i) => ({ value: i.id, label: i.label })));
        setReportTypeOptions(rtRes.items.filter((i) => i.enabled).map((i) => ({ value: i.id, label: i.label })));
      } catch { /* ignore */ }
    })();
  }, []);

  const addChapter = () => {
    if (!newTitle.trim()) return;
    const id = `sec_${String(chapters.length + 1).padStart(2, "0")}`;
    setChapters((prev) => [...prev, { id, title: newTitle.trim() }]);
    setNewTitle("");
  };

  const removeChapter = (idx: number) => {
    setChapters((prev) => prev.filter((_, i) => i !== idx));
  };

  const moveChapter = (idx: number, dir: -1 | 1) => {
    const target = idx + dir;
    if (target < 0 || target >= chapters.length) return;
    setChapters((prev) => {
      const next = [...prev];
      const temp = next[idx];
      next[idx] = next[target]!;
      next[target] = temp!;
      return next;
    });
  };

  const handleAiExtract = async (file: File) => {
    setAiLoading(true);
    try {
      const result = await kfApi.inferChapters(file, maxDepth);
      const items = flattenSections(result.sections as InferSection[]);
      if (items.length === 0) {
        toast.error("未能从文档中提取到章节结构");
        return;
      }
      setChapters(items);
      toast.success(`已提取 ${items.length} 个章节`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "AI 提取失败";
      toast.error(msg);
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b border-border">
          <h3 className="text-lg font-medium text-foreground">{isEdit ? "编辑报告大纲" : "新建报告大纲"}</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-accent rounded-lg transition-colors">
            <XCircle className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">大纲名称</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：环境影响评价报告"
              className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">描述</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简要描述该领域的适用范围"
              className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">业务领域</label>
              <AdminSelect
                value={industry}
                onChange={setIndustry}
                options={industryOptions}
                placeholder="选择业务领域"
                className="w-full"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">报告类型</label>
              <AdminSelect
                value={reportType}
                onChange={setReportType}
                options={reportTypeOptions}
                placeholder="选择报告类型"
                className="w-full"
              />
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">标准章节</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.txt,.md"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleAiExtract(file);
                  e.target.value = "";
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={aiLoading}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/10 rounded-md transition-colors disabled:opacity-50"
              >
                {aiLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3v2m0 14v2M5.636 5.636l1.414 1.414m9.9 9.9l1.414 1.414M3 12h2m14 0h2M5.636 18.364l1.414-1.414m9.9-9.9l1.414-1.414" />
                  </svg>
                )}
                {aiLoading ? "AI 分析中..." : "AI 提取章节"}
              </button>
              <div className="flex items-center gap-2 ml-2">
                <span className="text-xs text-muted-foreground whitespace-nowrap">层级</span>
                <div className="relative w-28 h-2 rounded-full bg-muted">
                  <div
                    className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-primary/80 to-primary transition-all duration-150"
                    style={{ width: `${((maxDepth - 1) / 5) * 100}%` }}
                  />
                  <input
                    type="range"
                    min={1}
                    max={6}
                    step={1}
                    value={maxDepth}
                    onChange={(e) => setMaxDepth(Number(e.target.value))}
                    disabled={aiLoading}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10 disabled:cursor-not-allowed"
                  />
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white border-2 border-primary shadow-md transition-all duration-150 pointer-events-none"
                    style={{ left: `calc(${((maxDepth - 1) / 5) * 100}% - 8px)` }}
                  />
                </div>
                <span className="text-xs font-semibold tabular-nums text-primary bg-primary/10 px-2 py-0.5 rounded-full min-w-[36px] text-center">
                  {maxDepth} 级
                </span>
              </div>
            </div>
            {aiLoading && (
              <div className="flex items-center gap-2 px-3 py-2 bg-primary/5 border border-primary/20 rounded-lg text-xs text-primary">
                <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                <span>正在分析文档结构，请稍候...</span>
              </div>
            )}
            <div className="space-y-2">
              {chapters.map((ch, idx) => (
                <div key={ch.id} className="flex items-center gap-2 group" style={{ paddingLeft: `${((ch.level ?? 1) - 1) * 20}px` }}>
                  <GripVertical className="w-4 h-4 text-muted-foreground/40 shrink-0" />
                  <span className="text-xs text-muted-foreground shrink-0 font-mono">{ch.id}</span>
                  <input
                    type="text"
                    value={ch.title}
                    onChange={(e) => {
                      const next = [...chapters];
                      next[idx] = { ...next[idx]!, title: e.target.value };
                      setChapters(next);
                    }}
                    className="flex-1 px-2 py-1.5 border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => moveChapter(idx, -1)} disabled={idx === 0} className="p-1 hover:bg-accent rounded disabled:opacity-30">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M18 15l-6-6-6 6" /></svg>
                    </button>
                    <button onClick={() => moveChapter(idx, 1)} disabled={idx === chapters.length - 1} className="p-1 hover:bg-accent rounded disabled:opacity-30">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M6 9l6 6 6-6" /></svg>
                    </button>
                    <button onClick={() => removeChapter(idx)} className="p-1 hover:bg-destructive/10 hover:text-destructive rounded">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addChapter()}
                  placeholder="输入章节标题后按回车添加"
                  className="flex-1 px-2 py-1.5 border border-dashed border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
                <button onClick={addChapter} disabled={!newTitle.trim()} className="px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-40">
                  添加
                </button>
              </div>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-border">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors">取消</button>
          <button
            disabled={!name.trim() || aiLoading}
            onClick={() => onSave({ name: name.trim(), description, standard_chapters: { sections: chapters }, industry: industry || undefined, report_type: reportType || undefined })}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {isEdit ? "保存" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============== Dict Item Edit Dialog ==============

function DictItemDialog({
  category,
  item,
  onClose,
  onSave,
}: {
  category: string;
  item: DictItemResponse | null;
  onClose: () => void;
  onSave: (data: { id?: string; category: string; label: string; sort_order: number; enabled: boolean }) => void;
}) {
  const isEdit = !!item;
  const [id, setId] = useState(item?.id ?? "");
  const [label, setLabel] = useState(item?.label ?? "");
  const [sortOrder, setSortOrder] = useState(item?.sort_order ?? 0);
  const [enabled, setEnabled] = useState(item?.enabled ?? true);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background rounded-2xl shadow-2xl w-full max-w-md flex flex-col">
        <div className="flex justify-between items-center px-6 py-4 border-b border-border">
          <h3 className="text-lg font-medium text-foreground">{isEdit ? "编辑" : "新建"}</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-accent rounded-lg transition-colors">
            <XCircle className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>
        <div className="flex-1 px-6 py-5 space-y-4">
          {!isEdit && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">ID</label>
              <input
                type="text"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="如：construction_project_eia"
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
          )}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">显示名称</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="如：建设项目环评"
              className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">排序</label>
              <input
                type="number"
                value={sortOrder}
                onChange={(e) => setSortOrder(parseInt(e.target.value) || 0)}
                className="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">状态</label>
              <button
                type="button"
                onClick={() => setEnabled(!enabled)}
                className={cn(
                  "w-full px-3 py-2 border rounded-lg text-sm font-medium transition-colors",
                  enabled ? "border-success/30 bg-success/10 text-success" : "border-border bg-muted text-muted-foreground"
                )}
              >
                {enabled ? "已启用" : "已禁用"}
              </button>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-border">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors">取消</button>
          <button
            disabled={!label.trim() || (!isEdit && !id.trim())}
            onClick={() => onSave({ id: isEdit ? undefined : id.trim(), category, label: label.trim(), sort_order: sortOrder, enabled })}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {isEdit ? "保存" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============== Main Component ==============

export default function BusinessDictionary() {
  const [activeCategory, setActiveCategory] = useState<CategoryKey>("domain");
  const [loading, setLoading] = useState(true);

  // Domain state
  const [domains, setDomains] = useState<ExtractionDomain[]>([]);
  const [editDomain, setEditDomain] = useState<ExtractionDomain | null>(null);
  const [showDomainDialog, setShowDomainDialog] = useState(false);

  // Dict item state
  const [dictItems, setDictItems] = useState<DictItemResponse[]>([]);
  const [dictTotal, setDictTotal] = useState(0);
  const [editItem, setEditItem] = useState<DictItemResponse | null>(null);
  const [showItemDialog, setShowItemDialog] = useState(false);

  // Delete confirmation state
  type DeleteTarget = { type: "domain"; data: ExtractionDomain } | { type: "item"; data: DictItemResponse } | null;
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);

  const loadDomains = useCallback(async () => {
    setLoading(true);
    try {
      const res = await kfApi.listDomains();
      setDomains(res.domains);
    } catch {
      toast.error("加载领域失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDictItems = useCallback(async (category: string) => {
    setLoading(true);
    try {
      const res = await kfApi.listDictItems(category, { limit: 200 });
      setDictItems(res.items);
      setDictTotal(res.total);
    } catch {
      toast.error("加载字典失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeCategory === "domain") {
      void loadDomains();
    } else {
      void loadDictItems(activeCategory);
    }
  }, [activeCategory, loadDomains, loadDictItems]);

  const handleCategoryChange = (key: CategoryKey) => {
    setActiveCategory(key);
  };

  // ============ Domain CRUD ============

  const handleSaveDomain = async (data: { id?: string; name: string; description: string; standard_chapters: Record<string, unknown>; industry?: string; report_type?: string }) => {
    try {
      if (editDomain) {
        await kfApi.updateDomain(editDomain.id, { name: data.name, description: data.description, standard_chapters: data.standard_chapters, industry: data.industry, report_type: data.report_type });
        toast.success("领域已更新");
      } else {
        await kfApi.createDomain({ id: data.name.toLowerCase().replace(/\s+/g, "_"), name: data.name, description: data.description, standard_chapters: data.standard_chapters, industry: data.industry, report_type: data.report_type });
        toast.success("领域已创建");
      }
      setShowDomainDialog(false);
      setEditDomain(null);
      void loadDomains();
    } catch {
      toast.error("操作失败");
    }
  };

  const handleDeleteDomain = async (domain: ExtractionDomain) => {
    setDeleteTarget({ type: "domain", data: domain });
  };

  // ============ Dict Item CRUD ============

  const handleSaveItem = async (data: { id?: string; category: string; label: string; sort_order: number; enabled: boolean }) => {
    try {
      if (editItem) {
        await kfApi.updateDictItem(editItem.id, { label: data.label, sort_order: data.sort_order, enabled: data.enabled });
        toast.success("已更新");
      } else {
        await kfApi.createDictItem({ id: data.id!, category: data.category, label: data.label, sort_order: data.sort_order, enabled: data.enabled });
        toast.success("已创建");
      }
      setShowItemDialog(false);
      setEditItem(null);
      void loadDictItems(activeCategory);
    } catch {
      toast.error("操作失败");
    }
  };

  const handleDeleteItem = async (item: DictItemResponse) => {
    setDeleteTarget({ type: "item", data: item });
  };

  const executeDelete = async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.type === "domain") {
        await kfApi.deleteDomain(deleteTarget.data.id);
        toast.success("已删除");
        void loadDomains();
      } else {
        await kfApi.deleteDictItem(deleteTarget.data.id);
        toast.success("已删除");
        void loadDictItems(activeCategory);
      }
    } catch {
      toast.error("删除失败");
    } finally {
      setDeleteTarget(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex justify-between items-center px-6 py-4 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3">
          <BookOpen className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-medium text-foreground">业务字典</h2>
        </div>
        <button
          onClick={() => {
            if (activeCategory === "domain") { setEditDomain(null); setShowDomainDialog(true); }
            else { setEditItem(null); setShowItemDialog(true); }
          }}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors shadow-sm font-medium text-sm"
        >
          <Plus className="w-4 h-4" />
          新增
        </button>
      </div>

      {/* Category tabs */}
      <div className="flex items-center gap-1 px-6 py-2.5 border-b border-border bg-card shrink-0">
        {CATEGORY_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleCategoryChange(tab.key)}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              activeCategory === tab.key
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 bg-muted/30">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> 加载中...
          </div>
        ) : activeCategory === "domain" ? (
          /* Domain list */
          domains.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <BookOpen className="w-12 h-12 mb-3 opacity-30" />
              <p>暂无业务领域</p>
              <button onClick={() => { setEditDomain(null); setShowDomainDialog(true); }} className="mt-3 text-primary hover:underline text-sm">
                创建第一个领域
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {domains.map((domain) => {
                const chapters = (domain.standard_chapters as { sections?: { id: string; title: string }[] })?.sections ?? [];
                return (
                  <div key={domain.id} className="bg-card rounded-xl border border-border/50 shadow-sm p-5 hover:shadow-md transition-shadow">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-medium text-foreground text-sm">{domain.name}</h3>
                          {domain.industry && (
                            <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] bg-primary/10 text-primary rounded">{CATEGORY_TABS.find(t => t.key === "industry")?.label}: {domain.industry}</span>
                          )}
                          {domain.report_type && (
                            <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] bg-success/10 text-success rounded">{CATEGORY_TABS.find(t => t.key === "report_type")?.label}: {domain.report_type}</span>
                          )}
                        </div>
                        {domain.description && (
                          <p className="text-xs text-muted-foreground mt-1">{domain.description}</p>
                        )}
                        {chapters.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {chapters.map((ch) => (
                              <span key={ch.id} className="inline-flex items-center px-2 py-0.5 text-[11px] bg-muted rounded-md text-muted-foreground">
                                {ch.title}
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="text-[11px] text-muted-foreground/50 mt-2 font-mono">ID: {domain.id}</p>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => { setEditDomain(domain); setShowDomainDialog(true); }}
                          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                          title="编辑"
                        >
                          <Edit3 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteDomain(domain)}
                          className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )
        ) : (
          /* Dict item list */
          dictItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <BookOpen className="w-12 h-12 mb-3 opacity-30" />
              <p>暂无数据</p>
              <button onClick={() => { setEditItem(null); setShowItemDialog(true); }} className="mt-3 text-primary hover:underline text-sm">
                添加第一条
              </button>
            </div>
          ) : (
            <div className="bg-card rounded-xl border border-border/50 shadow-sm overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-left">
                    <th className="py-3 px-4 font-medium text-xs">ID</th>
                    <th className="py-3 px-4 font-medium text-xs">名称</th>
                    <th className="py-3 px-4 font-medium text-xs">排序</th>
                    <th className="py-3 px-4 font-medium text-xs">状态</th>
                    <th className="py-3 px-4 font-medium text-xs text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {dictItems.map((item) => (
                    <tr key={item.id} className="hover:bg-muted/50 transition-colors">
                      <td className="py-3 px-4 text-xs font-mono text-muted-foreground">{item.id}</td>
                      <td className="py-3 px-4 text-sm text-foreground">{item.label}</td>
                      <td className="py-3 px-4 text-xs text-muted-foreground tabular-nums">{item.sort_order}</td>
                      <td className="py-3 px-4">
                        {item.enabled ? (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-500"><CheckCircle2 className="w-3.5 h-3.5" />启用</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><XCircle className="w-3.5 h-3.5" />禁用</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => { setEditItem(item); setShowItemDialog(true); }}
                            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
                            title="编辑"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteItem(item)}
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {/* Dialogs */}
      {showDomainDialog && (
        <DomainEditDialog
          domain={editDomain}
          onClose={() => { setShowDomainDialog(false); setEditDomain(null); }}
          onSave={handleSaveDomain}
        />
      )}
      {showItemDialog && (
        <DictItemDialog
          category={activeCategory}
          item={editItem}
          onClose={() => { setShowItemDialog(false); setEditItem(null); }}
          onSave={handleSaveItem}
        />
      )}

      {/* Delete Confirmation */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background rounded-2xl shadow-2xl w-full max-w-sm flex flex-col">
            <div className="px-6 py-5 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <Trash2 className="h-6 w-6 text-destructive" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-1">确认删除</h3>
              <p className="text-sm text-muted-foreground">
                确定删除"{deleteTarget.type === "domain" ? deleteTarget.data.name : deleteTarget.data.label}"吗？此操作不可撤销。
              </p>
            </div>
            <div className="flex justify-center gap-3 px-6 py-4 border-t border-border">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors"
              >
                取消
              </button>
              <button
                onClick={executeDelete}
                className="px-4 py-2 bg-destructive text-white rounded-lg text-sm font-medium hover:bg-destructive/90 transition-colors"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
