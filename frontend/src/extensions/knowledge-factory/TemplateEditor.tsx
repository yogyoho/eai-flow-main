"use client";

import {
  Edit3,
  Save,
  Send,
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  Plus,
  Trash2,
  Link,
  ShieldCheck,
  Info,
  FileJson,
  X,
  Check,
  Loader2,
  RefreshCw,
  AlertCircle,
  FileText,
  Download,
  History,
  Undo2,
  Clock,
  User,
  Eye,
  Database,
  Settings2,
  Sparkles,
} from "lucide-react";
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { kfApi } from "@/extensions/api";
import type { EditorSection, EditorTemplate, TemplateVersionResponse, ExtractionDomain } from "@/extensions/knowledge-factory/types";
import type { RAGSourceConfig } from "@/extensions/knowledge-factory/types";
import { RETRIEVAL_STRATEGIES } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

import { useTemplateList, useTemplateEditor } from "./hooks";

// ============== Template Selector ==============

interface TemplateSelectorProps {
  templates: EditorTemplate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  loading: boolean;
}

function TemplateSelector({
  templates,
  selectedId,
  onSelect,
  onRefresh,
  loading,
}: TemplateSelectorProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const selected = templates.find((t) => t.id === selectedId);

  return (
    <div className="relative">
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="flex items-center gap-2 px-3 py-1.5 bg-secondary hover:bg-accent rounded-lg transition-colors text-sm"
      >
        <FileText className="w-4 h-4 text-muted-foreground" />
        <span className="font-medium text-foreground max-w-[200px] truncate">
          {selected?.name || "选择模板"}
        </span>
        {selected && (
          <span className="text-xs text-muted-foreground">{selected.version}</span>
        )}
        <ChevronDown className="w-4 h-4 text-muted-foreground" />
      </button>

      {showDropdown && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowDropdown(false)}
          />
          <div className="absolute top-full left-0 mt-2 w-72 bg-background rounded-xl border border-border shadow-lg z-20 overflow-hidden">
            <div className="p-3 border-b border-border flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                选择模板
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRefresh();
                }}
                className="p-1 hover:bg-accent rounded transition-colors"
                disabled={loading}
              >
                <RefreshCw
                  className={cn("w-3.5 h-3.5 text-muted-foreground", loading && "animate-spin")}
                />
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {templates.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">
                  暂无可用模板
                </div>
              ) : (
                templates.map((template) => (
                  <button
                    key={template.id}
                    onClick={() => {
                      onSelect(template.id);
                      setShowDropdown(false);
                    }}
                    className={cn(
                      "w-full text-left px-4 py-3 hover:bg-accent transition-colors border-b border-border last:border-0",
                      selectedId === template.id && "bg-accent"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm text-foreground">
                        {template.name}
                      </span>
                      {selectedId === template.id && (
                        <Check className="w-4 h-4 text-primary" />
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-muted-foreground">
                        {template.version}
                      </span>
                      <span
                        className={cn(
                          "text-xs px-1.5 py-0.5 rounded-full",
                          template.status === "published"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : template.status === "draft"
                            ? "bg-amber-500/10 text-amber-500"
                            : "bg-muted text-muted-foreground"
                        )}
                      >
                        {template.status === "published"
                          ? "已发布"
                          : template.status === "draft"
                          ? "草稿"
                          : "已废弃"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {template.completenessScore}% 完整
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============== Section Tree ==============

interface SectionTreeProps {
  sections: EditorSection[];
  selectedId: string | null;
  expandedIds: Set<string>;
  onSelect: (id: string) => void;
  onToggleExpand: (id: string) => void;
  onAdd: (parentId: string | null, level: number) => void;
  onDelete: (id: string) => void;
  templateStatus: string;
}

function SectionTree({
  sections,
  selectedId,
  expandedIds,
  onSelect,
  onToggleExpand,
  onAdd,
  onDelete,
  templateStatus,
}: SectionTreeProps) {
  const renderSection = (section: EditorSection, depth = 0) => {
    const hasChildren = section.children && section.children.length > 0;
    const isExpanded = expandedIds.has(section.id);
    const isSelected = selectedId === section.id;
    const canDelete = templateStatus !== "published";

    return (
      <div key={section.id}>
        <div
          className={cn(
            "group flex items-center gap-1 px-2 py-1.5 rounded-lg cursor-pointer transition-colors text-sm",
            isSelected
              ? "bg-primary/10 text-primary font-medium"
              : "hover:bg-accent text-foreground"
          )}
          style={{ marginLeft: depth * 16 }}
          onClick={() => onSelect(section.id)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (hasChildren) onToggleExpand(section.id);
            }}
            className="p-0.5 hover:bg-accent rounded transition-colors"
          >
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )
            ) : (
              <div className="w-4" />
            )}
          </button>
          <span className="flex-1 truncate">{section.title}</span>
          {section.required && (
            <span className="text-[10px] text-red-500">必</span>
          )}
          {canDelete && (
            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onAdd(section.id, section.level + 1);
                }}
                className="p-1 hover:bg-accent rounded transition-colors"
                title="添加子章节"
              >
                <Plus className="w-3 h-3 text-primary" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(section.id);
                }}
                className="p-1 hover:bg-red-500/10 rounded transition-colors"
                title="删除章节"
              >
                <Trash2 className="w-3 h-3 text-red-500" />
              </button>
            </div>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div className="border-l border-border ml-2 mt-1">
            {section.children!.map((child) => renderSection(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-1">
      {sections.length === 0 ? (
        <div className="text-center py-8 text-sm text-muted-foreground">
          暂无章节
        </div>
      ) : (
        sections.map((section) => renderSection(section))
      )}
    </div>
  );
}

// ============== RAG Source Selector ==============

interface RAGSourceSelectorProps {
  selected: RAGSourceConfig[];
  onUpdate: (newSources: RAGSourceConfig[]) => void;
  isReadOnly: boolean;
}

interface KnowledgeBaseItem {
  id: string;
  name: string;
  description?: string;
  ragflow_dataset_id?: string;
}

function RAGSourceSelector({ selected, onUpdate, isReadOnly }: RAGSourceSelectorProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseItem[]>([]);
  const [loadingKbs, setLoadingKbs] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  useEffect(() => {
    setLoadingKbs(true);
    kfApi.listKnowledgeBases({ limit: 200 })
      .then((res) => {
        setKnowledgeBases(
          (res.knowledge_bases || []).map((kb) => ({
            id: kb.id,
            name: kb.name,
            description: kb.description,
            ragflow_dataset_id: kb.ragflow_dataset_id,
          }))
        );
      })
      .catch(() => {})
      .finally(() => setLoadingKbs(false));
  }, []);

  const selectedKbIds = new Set(selected.filter((s) => s.kb_id).map((s) => s.kb_id));

  const filteredKbs = knowledgeBases.filter(
    (kb) =>
      !selectedKbIds.has(kb.id) &&
      (kb.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (kb.description ?? "").toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const handleAddKb = (kb: KnowledgeBaseItem) => {
    onUpdate([
      ...selected,
      {
        kb_id: kb.id,
        kb_name: kb.name,
        ragflow_dataset_id: kb.ragflow_dataset_id,
        retrieval_strategy: "hybrid",
        top_k: 5,
        similarity_threshold: 0.2,
        vector_similarity_weight: 0.3,
      },
    ]);
    setShowDropdown(false);
    setSearchQuery("");
  };

  const handleRemove = (index: number) => {
    onUpdate(selected.filter((_, i) => i !== index));
  };

  const handleUpdateSource = (index: number, changes: Partial<RAGSourceConfig>) => {
    onUpdate(selected.map((s, i) => (i === index ? { ...s, ...changes } : s)));
  };

  const strategyBadge = (strategy: string) => {
    const labels: Record<string, { text: string; cls: string }> = {
      semantic: { text: "语义", cls: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
      keyword: { text: "关键词", cls: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
      hybrid: { text: "混合", cls: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" },
    };
    const badge = labels[strategy] ?? labels.hybrid!;
    return (
      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${badge.cls}`}>
        {badge.text}
      </span>
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {selected.map((source, index) => {
          const isLegacy = !source.kb_id;
          return (
            <div key={`${source.kb_id || source.kb_name}-${index}`} className="relative group">
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer ${
                  isLegacy
                    ? "bg-muted/50 text-muted-foreground border border-dashed border-border"
                    : "bg-amber-500/10 text-amber-500 dark:bg-amber-500/20 border border-amber-500/20 dark:border-amber-500/30"
                }`}
                onClick={() => !isReadOnly && setEditingIndex(editingIndex === index ? null : index)}
              >
                {isLegacy ? (
                  <AlertCircle className="w-3 h-3 text-muted-foreground" />
                ) : (
                  <Database className="w-3 h-3" />
                )}
                {source.kb_name}
                {strategyBadge(source.retrieval_strategy)}
                {!isReadOnly && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemove(index);
                    }}
                    className="hover:text-red-500 transition-colors ml-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </span>

              {/* Inline edit popover */}
              {editingIndex === index && !isReadOnly && (
                <div className="absolute top-full left-0 mt-1 w-64 bg-background rounded-xl border border-border shadow-lg z-30 p-3 space-y-3">
                  <div className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                    <Settings2 className="w-3 h-3" /> 检索参数
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs text-foreground">检索策略</label>
                    <select
                      value={source.retrieval_strategy}
                      onChange={(e) => handleUpdateSource(index, { retrieval_strategy: e.target.value as RAGSourceConfig["retrieval_strategy"] })}
                      className="w-full px-2 py-1.5 text-xs bg-background border border-border rounded-lg focus:outline-none focus:border-primary"
                    >
                      {RETRIEVAL_STRATEGIES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label} — {s.description}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-foreground">Top K</label>
                      <input
                        type="number"
                        value={source.top_k}
                        onChange={(e) => handleUpdateSource(index, { top_k: parseInt(e.target.value) || 5 })}
                        min={1}
                        max={50}
                        className="w-full px-2 py-1.5 text-xs bg-background border border-border rounded-lg focus:outline-none focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-foreground">相似度阈值</label>
                      <input
                        type="number"
                        value={source.similarity_threshold}
                        onChange={(e) => handleUpdateSource(index, { similarity_threshold: parseFloat(e.target.value) || 0.2 })}
                        min={0}
                        max={1}
                        step={0.05}
                        className="w-full px-2 py-1.5 text-xs bg-background border border-border rounded-lg focus:outline-none focus:border-primary"
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => setEditingIndex(null)}
                    className="w-full text-xs text-primary hover:underline"
                  >
                    关闭
                  </button>
                </div>
              )}

              {isLegacy && (
                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-amber-500 rounded-full flex items-center justify-center">
                  <AlertCircle className="w-2 h-2 text-white" />
                </span>
              )}
            </div>
          );
        })}

        {!isReadOnly && (
          <div className="relative">
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="w-8 h-8 rounded-full border border-dashed border-amber-500/40 flex items-center justify-center text-amber-500 hover:bg-amber-500/10 transition-colors"
              title="关联知识库"
            >
              {loadingKbs ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            </button>

            {showDropdown && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowDropdown(false)} />
                <div className="absolute top-full left-0 mt-2 w-80 bg-background rounded-xl border border-border shadow-lg z-20 overflow-hidden">
                  <div className="p-3 border-b border-border">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="搜索知识库..."
                      className="w-full px-3 py-2 text-sm bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                      autoFocus
                    />
                  </div>
                  <div className="max-h-56 overflow-y-auto">
                    {knowledgeBases.length === 0 && loadingKbs ? (
                      <div className="p-4 text-center text-sm text-muted-foreground">
                        <Loader2 className="w-4 h-4 animate-spin inline mr-2" />加载中...
                      </div>
                    ) : filteredKbs.length === 0 ? (
                      <div className="p-4 text-center text-sm text-muted-foreground">
                        {knowledgeBases.length === 0 ? "暂无知识库，请先创建知识库并上传文档" : "没有匹配的知识库"}
                      </div>
                    ) : (
                      filteredKbs.map((kb) => (
                        <button
                          key={kb.id}
                          onClick={() => handleAddKb(kb)}
                          className="w-full text-left px-4 py-3 hover:bg-accent transition-colors border-b border-border last:border-0"
                        >
                          <div className="font-medium text-sm text-foreground flex items-center gap-2">
                            <Database className="w-3.5 h-3.5 text-amber-500" />
                            {kb.name}
                          </div>
                          {kb.description && (
                            <div className="text-xs text-muted-foreground mt-0.5 ml-5.5">
                              {kb.description}
                            </div>
                          )}
                          {kb.ragflow_dataset_id ? (
                            <div className="text-[10px] text-emerald-500 mt-0.5 ml-5.5">已连接 RAGFlow</div>
                          ) : (
                            <div className="text-[10px] text-muted-foreground mt-0.5 ml-5.5">未连接 RAGFlow</div>
                          )}
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {selected.length === 0 && (
        <p className="text-xs text-muted-foreground">
          提示：关联知识库后，AI 生成内容时会从这些知识库检索相关参考资料。点击已关联的知识库可调整检索参数。
        </p>
      )}
    </div>
  );
}

// ============== Compliance Rule Templates ==============

interface ComplianceRuleTemplatesProps {
  onSelect: (rule: string) => void;
}

const COMPLIANCE_RULE_TEMPLATES = [
  { id: "env-law-7", name: "《建设项目环境保护管理条例》第七条", rule: "需引用《建设项目环境保护管理条例》第七条关于环境影响评价的规定" },
  { id: "soil-law-87", name: "《土壤污染防治法》第八十七条", rule: "需符合《土壤污染防治法》第八十七条关于土壤污染风险管控的规定" },
  { id: "air-law-40", name: "《大气污染防治法》第四十条", rule: "需符合《大气污染防治法》第四十条关于挥发性有机物控制的要求" },
  { id: "EIA-guideline", name: "环评编制技术导则", rule: "应符合《建设项目环境影响评价技术导则》的相关要求" },
  { id: "emission-standard", name: "排放标准符合性", rule: "排放浓度和排放量需满足相应行业污染物排放标准的要求" },
];

function ComplianceRuleTemplates({ onSelect }: ComplianceRuleTemplatesProps) {
  const [showTemplates, setShowTemplates] = useState(false);

  return (
    <div>
      <button
        onClick={() => setShowTemplates(!showTemplates)}
        className="text-xs text-primary hover:text-primary/80 hover:underline transition-colors"
      >
        从模板选择...
      </button>

      {showTemplates && (
        <div className="mt-2 p-3 bg-muted/50 rounded-lg border border-border max-h-48 overflow-y-auto">
          {COMPLIANCE_RULE_TEMPLATES.map((template) => (
            <button
              key={template.id}
              onClick={() => {
                onSelect(template.rule);
                setShowTemplates(false);
              }}
              className="w-full text-left p-2 hover:bg-accent rounded transition-colors mb-1 last:mb-0"
            >
              <div className="text-xs font-medium text-foreground">{template.name}</div>
              <div className="text-xs text-primary mt-0.5">{template.rule}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ============== Version History Modal ==============

interface VersionHistoryModalProps {
  templateId: string;
  templateName: string;
  currentVersion: string;
  onClose: () => void;
}

function VersionHistoryModal({
  templateId,
  templateName,
  currentVersion,
  onClose,
}: VersionHistoryModalProps) {
  const [versions, setVersions] = useState<TemplateVersionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVersion, setSelectedVersion] = useState<TemplateVersionResponse | null>(null);

  useEffect(() => {
    const fetchVersions = async () => {
      try {
        const data = await kfApi.getTemplateVersions(templateId);
        setVersions(data);
        if (data.length > 0) {
          setSelectedVersion(data.at(0) ?? null);
        }
      } catch (e) {
        console.error("获取版本历史失败:", e);
      } finally {
        setLoading(false);
      }
    };
    fetchVersions();
  }, [templateId]);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-background rounded-2xl shadow-2xl w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <History className="w-5 h-5 text-primary" />
            <div>
              <h2 className="text-lg font-medium text-foreground">版本历史</h2>
              <p className="text-sm text-muted-foreground">{templateName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex">
          <div className="w-64 border-r border-border overflow-y-auto p-4 shrink-0">
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
              </div>
            ) : versions.length === 0 ? (
              <div className="text-center py-8 text-sm text-muted-foreground">暂无版本历史</div>
            ) : (
              <div className="space-y-2">
                {versions.map((version) => (
                  <button
                    key={version.id}
                    onClick={() => setSelectedVersion(version)}
                    className={cn(
                      "w-full text-left p-3 rounded-lg border transition-all",
                      selectedVersion?.id === version.id
                        ? "bg-primary/5 border-primary/20"
                        : "bg-card border-border hover:border-primary/30"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-foreground">{version.version}</span>
                      {version.version === currentVersion && (
                        <span className="text-xs px-1.5 py-0.5 bg-primary/10 text-primary rounded">
                          当前
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">{formatDate(version.published_at)}</div>
                    {version.published_by && (
                      <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                        <User className="w-3 h-3" />
                        {version.published_by}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {selectedVersion ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-bold text-foreground">
                    版本 {selectedVersion.version}
                  </h3>
                  {selectedVersion.version === currentVersion && (
                    <span className="text-sm text-primary font-medium">当前使用中</span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-muted/50 rounded-lg border border-border">
                    <div className="text-xs text-muted-foreground mb-1">发布时间</div>
                    <div className="text-sm font-medium text-foreground">
                      {formatDate(selectedVersion.published_at)}
                    </div>
                  </div>
                  {selectedVersion.published_by && (
                    <div className="p-4 bg-muted/50 rounded-lg border border-border">
                      <div className="text-xs text-muted-foreground mb-1">发布者</div>
                      <div className="text-sm font-medium text-foreground flex items-center gap-1">
                        <User className="w-4 h-4" />
                        {selectedVersion.published_by}
                      </div>
                    </div>
                  )}
                </div>

                {selectedVersion.changelog && (
                  <div className="p-4 bg-muted/50 rounded-lg border border-border">
                    <div className="text-xs text-muted-foreground mb-2">更新说明</div>
                    <div className="text-sm text-foreground whitespace-pre-wrap">
                      {selectedVersion.changelog}
                    </div>
                  </div>
                )}

                <button className="flex items-center gap-2 px-4 py-2 text-sm text-primary hover:bg-primary/10 rounded-lg transition-colors">
                  <Eye className="w-4 h-4" />
                  预览此版本
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                选择一个版本查看详情
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============== Section Editor ==============

interface SectionEditorProps {
  section: EditorSection | null;
  templateStatus: string;
  onUpdate: (changes: Partial<EditorSection>) => void;
  onAddKeyElement: (element: string) => void;
  onRemoveKeyElement: (index: number) => void;
  onAddForbiddenPhrase: (phrase: string) => void;
  onRemoveForbiddenPhrase: (index: number) => void;
}

function SectionEditor({
  section,
  templateStatus,
  onUpdate,
  onAddKeyElement,
  onRemoveKeyElement,
  onAddForbiddenPhrase,
  onRemoveForbiddenPhrase,
}: SectionEditorProps) {
  const [newKeyElement, setNewKeyElement] = useState("");
  const [newForbiddenPhrase, setNewForbiddenPhrase] = useState("");
  const [newComplianceRule, setNewComplianceRule] = useState("");
  const [structureType, setStructureType] = useState<string>(
    section?.contentContract?.structureType || "narrative_text"
  );
  const [sectionLevel, setSectionLevel] = useState<string>(
    String(section?.level || 1)
  );

  useEffect(() => {
    if (section) {
      setStructureType(section.contentContract?.structureType || "narrative_text");
      setSectionLevel(String(section.level));
    }
  }, [section]);

  const isReadOnly = templateStatus === "published";

  const handleAddKeyElement = () => {
    if (newKeyElement.trim()) {
      onAddKeyElement(newKeyElement.trim());
      setNewKeyElement("");
    }
  };

  const handleAddForbiddenPhrase = () => {
    if (newForbiddenPhrase.trim()) {
      onAddForbiddenPhrase(newForbiddenPhrase.trim());
      setNewForbiddenPhrase("");
    }
  };

  if (!section) {
    return (
              <div className="flex items-center justify-center h-64 text-muted-foreground">
                <div className="text-center">
                  <FileJson className="w-12 h-12 mx-auto mb-3 text-muted opacity-50" />
                  <p className="text-sm">请从左侧选择一个章节进行编辑</p>
                </div>
              </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Basic Info */}
      <div className="bg-card p-6 rounded-xl border border-border shadow-sm space-y-6">
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              章节ID
            </label>
            <input
              type="text"
              value={section.id}
              readOnly
              className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-muted-foreground text-sm"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              章节标题 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={section.title}
              onChange={(e) => onUpdate({ title: e.target.value })}
              disabled={isReadOnly}
              className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm transition-all disabled:bg-muted disabled:text-muted-foreground"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">层级</label>
            <AdminSelect
              value={sectionLevel}
              onValueChange={(v) => {
                setSectionLevel(v);
                onUpdate({ level: parseInt(v) });
              }}
              options={[
                { value: "1", label: "第1级" },
                { value: "2", label: "第2级" },
                { value: "3", label: "第3级" },
              ]}
              disabled={isReadOnly}
              className="w-full"
            />
          </div>
          <div className="flex items-center gap-2 pt-6">
            <label className="relative flex items-center gap-2.5 cursor-pointer select-none group">
              <div className="relative">
                <input
                  type="checkbox"
                  checked={section.required}
                  onChange={(e) => onUpdate({ required: e.target.checked })}
                  disabled={isReadOnly}
                  className="peer sr-only"
                />
                <div className={cn(
                  "w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all duration-200",
                  "peer-checked:bg-primary peer-checked:border-primary",
                  "peer-focus-visible:ring-2 peer-focus-visible:ring-primary/30 peer-focus-visible:ring-offset-2",
                  "group-hover:border-primary/60",
                  isReadOnly
                    ? "border-muted bg-muted cursor-not-allowed opacity-50"
                    : section.required
                      ? "border-primary bg-primary"
                      : "border-input bg-background"
                )}>
                  <Check className={cn(
                    "w-3.5 h-3.5 text-primary-foreground transition-all duration-200",
                    section.required ? "scale-100 opacity-100" : "scale-0 opacity-0"
                  )} />
                </div>
              </div>
              <span className="text-sm font-medium text-foreground">必选章节</span>
            </label>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">编写目的</label>
          <textarea
            value={section.purpose || ""}
            onChange={(e) => onUpdate({ purpose: e.target.value })}
            disabled={isReadOnly}
            rows={2}
            placeholder="描述本章的编写目的和主要内容..."
            className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm resize-y transition-all disabled:bg-muted"
          />
        </div>
      </div>

      {/* Content Contract */}
      <div className="bg-card p-6 rounded-xl border border-border shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-primary border-b border-border pb-2">
          <Info className="w-4 h-4" />
          <h4 className="font-bold text-sm uppercase tracking-wider">内容契约</h4>
        </div>

        {/* Key Elements */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            关键要素 (每行一个)
          </label>
          <div className="border border-border rounded-lg p-3 space-y-2">
            {(section.contentContract?.keyElements || []).map((item, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-muted/50 px-3 py-1.5 rounded border border-border text-sm"
              >
                <span className="text-foreground">• {item}</span>
                <button
                  onClick={() => onRemoveKeyElement(i)}
                  disabled={isReadOnly}
                  className="text-muted-foreground hover:text-red-500 transition-colors disabled:opacity-50"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            <div className="flex gap-2">
              <input
                type="text"
                value={newKeyElement}
                onChange={(e) => setNewKeyElement(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddKeyElement()}
                disabled={isReadOnly}
                placeholder="输入后按回车添加"
                className="flex-1 px-2 py-1.5 text-sm border border-dashed border-border rounded focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
              />
              <button
                onClick={handleAddKeyElement}
                disabled={isReadOnly || !newKeyElement.trim()}
                className="px-3 py-1.5 bg-primary/10 text-primary rounded border border-dashed border-primary/30 text-xs font-medium hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>

        {/* Structure Type & Min Word Count */}
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">结构类型</label>
            <AdminSelect
              value={structureType}
              onValueChange={(v) => {
                setStructureType(v);
                onUpdate({
                  contentContract: {
                    ...section.contentContract,
                    structureType: v as "narrative_text" | "table" | "formula" | "diagram" | "mixed",
                  } as EditorSection["contentContract"],
                });
              }}
              options={[
                { value: "narrative_text", label: "叙述文本" },
                { value: "table", label: "表格数据" },
                { value: "formula", label: "公式计算" },
                { value: "diagram", label: "流程图/示意图" },
                { value: "mixed", label: "混合类型" },
              ]}
              disabled={isReadOnly}
              className="w-full"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">最小字数</label>
            <input
              type="number"
              value={section.contentContract?.minWordCount || 0}
              onChange={(e) =>
                onUpdate({
                  contentContract: {
                    ...section.contentContract,
                    minWordCount: parseInt(e.target.value) || 0,
                  } as EditorSection["contentContract"],
                })
              }
              disabled={isReadOnly}
              min={0}
              className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm transition-all disabled:bg-muted"
            />
          </div>
        </div>

        {/* Style Rules */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">编写规范</label>
          <textarea
            value={section.contentContract?.styleRules || ""}
            onChange={(e) =>
              onUpdate({
                contentContract: {
                  ...section.contentContract,
                  styleRules: e.target.value,
                } as EditorSection["contentContract"],
              })
            }
            disabled={isReadOnly}
            rows={2}
            placeholder="描述本章的编写风格要求，如：使用被动语态、客观陈述..."
            className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm resize-y transition-all disabled:bg-muted"
          />
        </div>

        {/* Forbidden Phrases */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            禁用短语 (检测到会警告)
          </label>
          <div className="flex flex-wrap gap-2">
            {(section.contentContract?.forbiddenPhrases || []).map((phrase, i) => (
              <span
                key={i}
                className="bg-red-500/10 text-red-500 px-2 py-1 rounded border border-red-500/20 text-xs flex items-center gap-1"
              >
                {phrase}
                <button
                  onClick={() => onRemoveForbiddenPhrase(i)}
                  disabled={isReadOnly}
                  className="hover:text-red-500 transition-colors disabled:opacity-50"
                >
                  <X className="w-3 h-3 cursor-pointer" />
                </button>
              </span>
            ))}
            <div className="flex gap-2 items-center">
              <input
                type="text"
                value={newForbiddenPhrase}
                onChange={(e) => setNewForbiddenPhrase(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && handleAddForbiddenPhrase()
                }
                disabled={isReadOnly}
                placeholder="添加禁用短语"
                className="w-32 px-2 py-1 text-xs border border-dashed border-border rounded focus:outline-none focus:border-red-500 transition-colors disabled:opacity-50"
              />
              <button
                onClick={handleAddForbiddenPhrase}
                disabled={isReadOnly || !newForbiddenPhrase.trim()}
                className="text-xs text-primary hover:text-primary/80 hover:underline transition-colors disabled:opacity-50"
              >
                + 添加
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Compliance Rules */}
      <div className="bg-card p-6 rounded-xl border border-border shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-primary border-b border-border pb-2">
          <ShieldCheck className="w-4 h-4" />
          <h4 className="font-bold text-sm uppercase tracking-wider">合规规则</h4>
        </div>
        <div className="space-y-2">
          {(section.complianceRules || []).map((rule, i) => (
            <div
              key={i}
              className="flex items-center justify-between bg-primary/5 p-3 rounded-lg border border-primary/10 text-sm"
            >
              <span className="text-foreground">{rule}</span>
              <button
                onClick={() => {
                  const newRules = [...(section.complianceRules || [])];
                  newRules.splice(i, 1);
                  onUpdate({ complianceRules: newRules });
                }}
                disabled={isReadOnly}
                className="text-muted-foreground hover:text-red-500 transition-colors disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          <div className="flex gap-2">
            <input
              type="text"
              value={newComplianceRule}
              onChange={(e) => setNewComplianceRule(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newComplianceRule.trim()) {
                  onUpdate({
                    complianceRules: [
                      ...(section.complianceRules || []),
                      newComplianceRule.trim(),
                    ],
                  });
                  setNewComplianceRule("");
                }
              }}
              disabled={isReadOnly}
              placeholder="添加合规规则，如：必须引用XX法规第X条"
              className="flex-1 px-3 py-2 text-sm border border-dashed border-border rounded-lg focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
            />
            <button
              onClick={() => {
                if (newComplianceRule.trim()) {
                  onUpdate({
                    complianceRules: [
                      ...(section.complianceRules || []),
                      newComplianceRule.trim(),
                    ],
                  });
                  setNewComplianceRule("");
                }
              }}
              disabled={isReadOnly || !newComplianceRule.trim()}
              className="px-4 py-2 bg-primary/10 text-primary rounded-lg border border-dashed border-primary/30 text-xs font-medium hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* RAG Sources */}
      <div className="bg-card p-6 rounded-xl border border-border shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-primary border-b border-border pb-2">
          <Link className="w-4 h-4" />
          <h4 className="font-bold text-sm uppercase tracking-wider">RAG 数据源</h4>
          <span className="text-xs text-muted-foreground font-normal ml-auto">报告生成时的检索知识库</span>
        </div>
        
        {/* 可用的 RAG 数据源 */}
        <RAGSourceSelector
          selected={section.ragSources || []}
          onUpdate={(newSources) => onUpdate({ ragSources: newSources })}
          isReadOnly={isReadOnly}
        />
      </div>

      {/* Generation Hint & Example */}
      <div className="bg-card p-6 rounded-xl border border-border shadow-sm space-y-4">
        <h4 className="font-bold text-sm text-foreground uppercase tracking-wider">
          生成辅助
        </h4>
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">生成提示</label>
          <textarea
            value={section.generationHint || ""}
            onChange={(e) => onUpdate({ generationHint: e.target.value })}
            disabled={isReadOnly}
            rows={2}
            placeholder="AI 生成时的参考提示..."
            className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm resize-y transition-all disabled:bg-muted"
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">示例片段</label>
          <textarea
            value={section.exampleSnippet || ""}
            onChange={(e) => onUpdate({ exampleSnippet: e.target.value })}
            disabled={isReadOnly}
            rows={3}
            placeholder="本章的参考示例文本..."
            className="w-full px-3 py-2 bg-background border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm resize-y transition-all disabled:bg-muted"
          />
        </div>
      </div>
    </div>
  );
}

// ============== Main TemplateEditor Component ==============

export default function TemplateEditor() {
  const {
    templates,
    loading: listLoading,
    fetchTemplates,
  } = useTemplateList();

  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [confirmAction, setConfirmAction] = useState<{ action: () => Promise<void>; title: string; message: string } | null>(null);

  // 版本历史弹窗状态
  const [showVersionHistory, setShowVersionHistory] = useState(false);

  // 新建模板弹窗
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTemplateName, setNewTemplateName] = useState("");
  const [newTemplateDomain, setNewTemplateDomain] = useState("");
  const [domains, setDomains] = useState<ExtractionDomain[]>([]);
  const [creating, setCreating] = useState(false);

  // 加载领域列表（用于新建模板）
  useEffect(() => {
    kfApi.listDomains().then((res) => {
      if (res.domains.length > 0) {
        setDomains(res.domains);
        setNewTemplateDomain(res.domains[0]!.id);
      }
    }).catch(() => {});
  }, []);

  // 创建新模板
  const handleCreateTemplate = async () => {
    if (!newTemplateName.trim()) {
      toast.error("请输入模板名称");
      return;
    }
    setCreating(true);
    try {
      const res = await kfApi.createTemplate({
        name: newTemplateName.trim(),
        domain: newTemplateDomain,
      });
      setShowCreateDialog(false);
      setNewTemplateName("");
      await fetchTemplates({ status: "draft,published", limit: 50 });
      setSelectedTemplateId(res.template_id);
      toast.success("模板创建成功");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  // 撤销功能 - 保存原始状态的快照
  const [originalSnapshot, setOriginalSnapshot] = useState<EditorTemplate | null>(null);

  const {
    template,
    setTemplate,
    loading: templateLoading,
    saving,
    error,
    updateSection,
    addSection,
    deleteSection,
    addKeyElement,
    removeKeyElement,
    addForbiddenPhrase,
    removeForbiddenPhrase,
    saveDraft,
    publishTemplate,
    getSection,
    loadTemplate,
  } = useTemplateEditor(selectedTemplateId);

  // 加载模板列表
  useEffect(() => {
    fetchTemplates({ status: "draft,published", limit: 50 });
  }, [fetchTemplates]);

  // 将列表项转换为 EditorTemplate 用于选择器
  const editorTemplates: EditorTemplate[] = templates.map((t) => ({
    id: t.id,
    name: t.name,
    version: t.version,
    domain: t.domain,
    status: t.status,
    completenessScore: t.completeness_score,
    sections: [],
    isDirty: false,
  }));

  // 选中模板后自动选中第一个章节
  useEffect(() => {
    if (template?.sections?.length) {
      const firstSection = findFirstSection(template.sections);
      if (firstSection) {
        setSelectedSectionId(firstSection.id);
        setExpandedIds((prev) => new Set([...prev, firstSection.id]));
      }
    } else {
      setSelectedSectionId(null);
    }
  }, [template?.sections]);

  // 查找第一个章节
  const findFirstSection = (sections: EditorSection[]): EditorSection | null => {
    for (const section of sections) {
      return section;
    }
    return null;
  };

  // 展开/折叠
  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // 添加章节
  const handleAddSection = useCallback(
    (parentId: string | null, level: number) => {
      const newTitle = `新章节 ${Date.now().toString().slice(-4)}`;
      addSection(parentId, level, newTitle);
      setExpandedIds((prev) => {
        if (parentId) {
          const next = new Set(prev);
          next.add(parentId);
          return next;
        }
        return prev;
      });
    },
    [addSection]
  );

  // 删除章节
  const handleDeleteSection = useCallback(
    (id: string) => {
      if (selectedSectionId === id) {
        setSelectedSectionId(null);
      }
      deleteSection(id);
    },
    [deleteSection, selectedSectionId]
  );

  // 保存草稿
  const handleSaveDraft = async () => {
    try {
      await saveDraft();
      toast.success("草稿保存成功");
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : "保存失败"
      );
    }
  };

  // 发布模板
  const handlePublish = () => {
    if (!template) return;
    setConfirmAction({
      title: "确认发布",
      message: `确定要发布模板「${template.name}」吗？发布后将无法直接修改。`,
      action: async () => {
        try {
          await publishTemplate();
          toast.success("模板发布成功");
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "发布失败");
        }
      },
    });
  };

  // 导出模板
  const handleExport = useCallback(() => {
    if (!template || !selectedTemplateId) return;

    const exportUrl = kfApi.exportTemplate(selectedTemplateId);
    const link = document.createElement("a");
    link.href = exportUrl;
    link.download = `${template.name}_${template.version}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("模板导出成功");
  }, [template, selectedTemplateId]);

  // 删除模板
  const handleDeleteTemplate = () => {
    if (!template || !selectedTemplateId) return;
    setConfirmAction({
      title: "确认删除",
      message: `确定要删除模板「${template.name}」吗？此操作不可撤销。`,
      action: async () => {
        try {
          await kfApi.deleteTemplate(selectedTemplateId);
          setSelectedTemplateId("");
          await fetchTemplates({ status: "draft,published", limit: 50 });
          toast.success("模板已删除");
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "删除失败");
        }
      },
    });
  };

  // 撤销更改 - 使用快照恢复
  const handleRevert = useCallback(() => {
    if (!originalSnapshot) return;
    
    if (!window.confirm("确定要撤销所有未保存的更改吗？")) {
      return;
    }
    
    // 恢复原始状态
    setTemplate(originalSnapshot);
    toast.success("已撤销所有更改");
  }, [originalSnapshot, setTemplate]);

  // 当模板加载或保存后，更新快照
  useEffect(() => {
    if (template && !template.isDirty) {
      setOriginalSnapshot(JSON.parse(JSON.stringify(template)));
    }
  }, [template?.id, template?.isDirty]);

  // 章节导航
  const allSections = useMemo(() => {
    if (!template?.sections) return [];
    const result: EditorSection[] = [];
    const traverse = (sections: EditorSection[]) => {
      for (const s of sections) {
        result.push(s);
        if (s.children) traverse(s.children);
      }
    };
    traverse(template.sections);
    return result;
  }, [template?.sections]);

  const currentSectionIndex = selectedSectionId
    ? allSections.findIndex((s) => s.id === selectedSectionId)
    : -1;

  const goToPrevSection = useCallback(() => {
    if (currentSectionIndex > 0) {
      setSelectedSectionId(allSections.at(currentSectionIndex - 1)?.id ?? null);
    }
  }, [currentSectionIndex, allSections]);

  const goToNextSection = useCallback(() => {
    if (currentSectionIndex < allSections.length - 1) {
      setSelectedSectionId(allSections.at(currentSectionIndex + 1)?.id ?? null);
    }
  }, [currentSectionIndex, allSections]);

  const selectedSection = selectedSectionId
    ? getSection(selectedSectionId)
    : null;

  const isPublished = template?.status === "published";

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="sticky top-0 z-10 p-4 border-b border-border bg-background flex justify-between items-center shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Edit3 className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-medium text-foreground tracking-tight">
              模板编辑器
            </h2>
          </div>
          <TemplateSelector
            templates={editorTemplates}
            selectedId={selectedTemplateId}
            onSelect={setSelectedTemplateId}
            onRefresh={() => fetchTemplates({ status: "draft,published", limit: 50 })}
            loading={listLoading}
          />
          <button
            onClick={() => setShowCreateDialog(true)}
            className="px-3 py-1.5 text-sm font-medium text-primary bg-primary/10 border border-dashed border-primary/30 rounded-lg hover:bg-primary/20 transition-colors flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            新建模板
          </button>
          {template?.isDirty && (
            <span className="text-xs text-amber-500 bg-amber-500/10 px-2 py-1 rounded-full">
              有未保存的更改
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {/* 版本历史 */}
          <button
            onClick={() => setShowVersionHistory(true)}
            disabled={!template}
            className="px-3 py-2 text-foreground bg-card border border-border rounded-lg flex items-center gap-2 hover:bg-accent transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <History className="w-4 h-4" />
            版本历史
          </button>
          
          {/* 导出 */}
          <button
            onClick={handleExport}
            disabled={!template}
            className="px-3 py-2 text-foreground bg-card border border-border rounded-lg flex items-center gap-2 hover:bg-accent transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-4 h-4" />
            导出
          </button>

          {/* 删除 */}
          <button
            onClick={handleDeleteTemplate}
            disabled={!template}
            className="px-3 py-2 text-destructive bg-card border border-border rounded-lg flex items-center gap-2 hover:bg-destructive/10 transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Trash2 className="w-4 h-4" />
            删除
          </button>
          
          <button
            onClick={handleSaveDraft}
            disabled={saving || !template || !template.isDirty || isPublished}
            className="px-4 py-2 text-foreground bg-card border border-border rounded-lg flex items-center gap-2 hover:bg-accent transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            保存草稿
          </button>
          <button
            onClick={handlePublish}
            disabled={saving || !template || isPublished}
            className="px-4 py-2 bg-primary text-white rounded-lg flex items-center gap-2 hover:bg-primary/90 transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            发布
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background rounded-2xl shadow-2xl w-full max-w-sm flex flex-col">
            <div className="px-6 py-5 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                <AlertCircle className="h-6 w-6 text-destructive" />
              </div>
              <h3 className="text-base font-medium text-foreground mb-1">{confirmAction.title}</h3>
              <p className="text-sm text-muted-foreground">{confirmAction.message}</p>
            </div>
            <div className="flex justify-center gap-3 px-6 py-4 border-t border-border">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors"
              >
                取消
              </button>
              <button
                onClick={async () => {
                  const action = confirmAction.action;
                  setConfirmAction(null);
                  await action();
                }}
                className="px-4 py-2 bg-destructive text-white rounded-lg text-sm font-medium hover:bg-destructive/90 transition-colors"
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {showVersionHistory && template && (
        <VersionHistoryModal
          templateId={template.id}
          templateName={template.name}
          currentVersion={template.version}
          onClose={() => setShowVersionHistory(false)}
        />
      )}

      {/* Create Template Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-5">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-foreground">新建模板</h3>
              <button
                onClick={() => setShowCreateDialog(false)}
                className="p-1.5 hover:bg-accent rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-muted-foreground" />
              </button>
            </div>
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">模板名称</label>
                <input
                  type="text"
                  value={newTemplateName}
                  onChange={(e) => setNewTemplateName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateTemplate()}
                  placeholder="例如：消防设计专篇标准模板"
                  className="w-full px-3 py-2 border border-input rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">业务领域</label>
                {domains.length > 0 ? (
                  <AdminSelect
                    value={newTemplateDomain}
                    onValueChange={setNewTemplateDomain}
                    options={domains.map((d) => ({ value: d.id, label: d.name }))}
                    placeholder="选择领域"
                  />
                ) : (
                  <input
                    type="text"
                    value={newTemplateDomain}
                    onChange={(e) => setNewTemplateDomain(e.target.value)}
                    placeholder="输入领域标识"
                    className="w-full px-3 py-2 border border-input rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                )}
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowCreateDialog(false)}
                className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-accent transition-colors"
              >
                取消
              </button>
              <button
                disabled={creating || !newTemplateName.trim()}
                onClick={handleCreateTemplate}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {creating ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> 创建中...</>
                ) : (
                  "创建"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {templateLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <AlertCircle className="w-12 h-12 mx-auto mb-3 text-red-500" />
              <p className="text-red-500">{error}</p>
            </div>
          </div>
        ) : !template ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center">
              <FileJson className="w-16 h-16 text-muted-foreground/20 mb-4" />
              <p className="text-foreground font-medium mb-1">请从上方选择一个模板进行编辑</p>
              <button
                onClick={() => fetchTemplates({ status: "draft,published", limit: 50 })}
                className="text-sm text-primary hover:text-primary/80 hover:underline"
              >
                刷新模板列表
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Sidebar Tree */}
            <div className="w-72 border-r border-border bg-muted/50 overflow-y-auto p-4 shrink-0">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                  <FileJson className="w-3 h-3" /> 章节树
                </h3>
                {!isPublished && (
                  <button
                    onClick={() => handleAddSection(null, 1)}
                    className="p-1.5 hover:bg-accent rounded-lg text-muted-foreground hover:text-primary transition-colors"
                    title="添加一级章节"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                )}
              </div>
              <SectionTree
                sections={template.sections}
                selectedId={selectedSectionId}
                expandedIds={expandedIds}
                onSelect={setSelectedSectionId}
                onToggleExpand={toggleExpand}
                onAdd={handleAddSection}
                onDelete={handleDeleteSection}
                templateStatus={template.status}
              />
            </div>

            {/* Editor Area */}
            <div className="flex-1 overflow-y-auto bg-muted/30 p-8">
              <div className="max-w-4xl mx-auto">
                {/* Section Navigation */}
                <div className="flex items-center justify-between mb-4 bg-card rounded-lg border border-border px-4 py-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={goToPrevSection}
                      disabled={currentSectionIndex <= 0}
                      className="p-1.5 hover:bg-accent rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title="上一章节"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <span className="text-sm text-muted-foreground">
                      第 {currentSectionIndex + 1} / {allSections.length} 章节
                    </span>
                    <button
                      onClick={goToNextSection}
                      disabled={currentSectionIndex >= allSections.length - 1}
                      className="p-1.5 hover:bg-accent rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title="下一章节"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    {template?.isDirty && (
                      <button
                        onClick={handleRevert}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-amber-500 hover:bg-amber-500/10 rounded transition-colors"
                      >
                        <Undo2 className="w-3 h-3" />
                        撤销更改
                      </button>
                    )}
                    {selectedSection && (
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        最后修改: {template.lastSaved ? new Date(template.lastSaved).toLocaleTimeString() : '未保存'}
                      </span>
                    )}
                  </div>
                </div>

                <SectionEditor
                  section={selectedSection}
                  templateStatus={template.status}
                  onUpdate={(changes) => {
                    if (selectedSectionId) {
                      updateSection(selectedSectionId, changes);
                    }
                  }}
                  onAddKeyElement={(element) => {
                    if (selectedSectionId) {
                      addKeyElement(selectedSectionId, element);
                    }
                  }}
                  onRemoveKeyElement={(index) => {
                    if (selectedSectionId) {
                      removeKeyElement(selectedSectionId, index);
                    }
                  }}
                  onAddForbiddenPhrase={(phrase) => {
                    if (selectedSectionId) {
                      addForbiddenPhrase(selectedSectionId, phrase);
                    }
                  }}
                  onRemoveForbiddenPhrase={(index) => {
                    if (selectedSectionId) {
                      removeForbiddenPhrase(selectedSectionId, index);
                    }
                  }}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
