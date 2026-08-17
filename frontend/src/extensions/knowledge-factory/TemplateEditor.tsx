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
} from "lucide-react";
import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { kfApi } from "@/extensions/api";
import type {
  EditorSection,
  EditorTemplate,
  TemplateVersionResponse,
  ExtractionDomain,
} from "@/extensions/knowledge-factory/types";
import type { RAGSourceConfig } from "@/extensions/knowledge-factory/types";
import { RETRIEVAL_STRATEGIES } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

import { useTemplateList, useTemplateEditor } from "./hooks";
import { RichMetadataEditor } from "./RichMetadataEditor";

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
        className="bg-secondary hover:bg-accent flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors"
      >
        <FileText className="text-muted-foreground h-4 w-4" />
        <span className="text-foreground max-w-[200px] truncate font-medium">
          {selected?.name ?? "选择模板"}
        </span>
        {selected && (
          <span className="text-muted-foreground text-xs">
            {selected.version}
          </span>
        )}
        <ChevronDown className="text-muted-foreground h-4 w-4" />
      </button>

      {showDropdown && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowDropdown(false)}
          />
          <div className="bg-background border-border absolute top-full left-0 z-20 mt-2 w-72 overflow-hidden rounded-xl border shadow-lg">
            <div className="border-border flex items-center justify-between border-b p-3">
              <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                选择模板
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRefresh();
                }}
                className="hover:bg-accent rounded p-1 transition-colors"
                disabled={loading}
              >
                <RefreshCw
                  className={cn(
                    "text-muted-foreground h-3.5 w-3.5",
                    loading && "animate-spin",
                  )}
                />
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {templates.length === 0 ? (
                <div className="text-muted-foreground p-4 text-center text-sm">
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
                      "hover:bg-accent border-border w-full border-b px-4 py-3 text-left transition-colors last:border-0",
                      selectedId === template.id && "bg-accent",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-foreground text-sm font-medium">
                        {template.name}
                      </span>
                      {selectedId === template.id && (
                        <Check className="text-primary h-4 w-4" />
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-muted-foreground text-xs">
                        {template.version}
                      </span>
                      <span
                        className={cn(
                          "rounded-full px-1.5 py-0.5 text-xs",
                          template.status === "published"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : template.status === "draft"
                              ? "bg-amber-500/10 text-amber-500"
                              : "bg-muted text-muted-foreground",
                        )}
                      >
                        {template.status === "published"
                          ? "已发布"
                          : template.status === "draft"
                            ? "草稿"
                            : "已废弃"}
                      </span>
                      <span className="text-muted-foreground text-xs">
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
            "group flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors",
            isSelected
              ? "bg-primary/10 text-primary font-medium"
              : "hover:bg-accent text-foreground",
          )}
          style={{ marginLeft: depth * 16 }}
          onClick={() => onSelect(section.id)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (hasChildren) onToggleExpand(section.id);
            }}
            className="hover:bg-accent rounded p-0.5 transition-colors"
          >
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown className="text-muted-foreground h-4 w-4" />
              ) : (
                <ChevronRight className="text-muted-foreground h-4 w-4" />
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
            <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onAdd(section.id, section.level + 1);
                }}
                className="hover:bg-accent rounded p-1 transition-colors"
                title="添加子章节"
              >
                <Plus className="text-primary h-3 w-3" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(section.id);
                }}
                className="rounded p-1 transition-colors hover:bg-red-500/10"
                title="删除章节"
              >
                <Trash2 className="h-3 w-3 text-red-500" />
              </button>
            </div>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div className="border-border mt-1 ml-2 border-l">
            {section.children!.map((child) => renderSection(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-1">
      {sections.length === 0 ? (
        <div className="text-muted-foreground py-8 text-center text-sm">
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

function RAGSourceSelector({
  selected,
  onUpdate,
  isReadOnly,
}: RAGSourceSelectorProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseItem[]>([]);
  const [loadingKbs, setLoadingKbs] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  useEffect(() => {
    setLoadingKbs(true);
    kfApi
      .listKnowledgeBases({ limit: 200 })
      .then((res) => {
        setKnowledgeBases(
          (res.knowledge_bases || []).map((kb) => ({
            id: kb.id,
            name: kb.name,
            description: kb.description,
            ragflow_dataset_id: kb.ragflow_dataset_id,
          })),
        );
      })
      .catch(() => {
        // intentional no-op: KB list load failure keeps previous list
      })
      .finally(() => setLoadingKbs(false));
  }, []);

  const selectedKbIds = new Set(
    selected.filter((s) => s.kb_id).map((s) => s.kb_id),
  );

  const filteredKbs = knowledgeBases.filter(
    (kb) =>
      !selectedKbIds.has(kb.id) &&
      (kb.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (kb.description ?? "")
          .toLowerCase()
          .includes(searchQuery.toLowerCase())),
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

  const handleUpdateSource = (
    index: number,
    changes: Partial<RAGSourceConfig>,
  ) => {
    onUpdate(selected.map((s, i) => (i === index ? { ...s, ...changes } : s)));
  };

  const strategyBadge = (strategy: string) => {
    const labels: Record<string, { text: string; cls: string }> = {
      semantic: {
        text: "语义",
        cls: "bg-blue-500/10 text-blue-500 border-blue-500/20",
      },
      keyword: {
        text: "关键词",
        cls: "bg-purple-500/10 text-purple-500 border-purple-500/20",
      },
      hybrid: {
        text: "混合",
        cls: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
      },
    };
    const badge = labels[strategy] ?? labels.hybrid!;
    return (
      <span
        className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${badge.cls}`}
      >
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
            <div
              key={`${source.kb_id || source.kb_name}-${index}`}
              className="group relative"
            >
              <span
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
                  isLegacy
                    ? "bg-muted/50 text-muted-foreground border-border border border-dashed"
                    : "border border-amber-500/20 bg-amber-500/10 text-amber-500 dark:border-amber-500/30 dark:bg-amber-500/20"
                }`}
                onClick={() =>
                  !isReadOnly &&
                  setEditingIndex(editingIndex === index ? null : index)
                }
              >
                {isLegacy ? (
                  <AlertCircle className="text-muted-foreground h-3 w-3" />
                ) : (
                  <Database className="h-3 w-3" />
                )}
                {source.kb_name}
                {strategyBadge(source.retrieval_strategy)}
                {!isReadOnly && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemove(index);
                    }}
                    className="ml-0.5 transition-colors hover:text-red-500"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </span>

              {/* Inline edit popover */}
              {editingIndex === index && !isReadOnly && (
                <div className="bg-background border-border absolute top-full left-0 z-30 mt-1 w-64 space-y-3 rounded-xl border p-3 shadow-lg">
                  <div className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
                    <Settings2 className="h-3 w-3" /> 检索参数
                  </div>
                  <div className="space-y-2">
                    <label className="text-foreground text-xs">检索策略</label>
                    <select
                      value={source.retrieval_strategy}
                      onChange={(e) =>
                        handleUpdateSource(index, {
                          retrieval_strategy: e.target
                            .value as RAGSourceConfig["retrieval_strategy"],
                        })
                      }
                      className="bg-background border-border focus:border-primary w-full rounded-lg border px-2 py-1.5 text-xs focus:outline-none"
                    >
                      {RETRIEVAL_STRATEGIES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label} — {s.description}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-foreground text-xs">Top K</label>
                      <input
                        type="number"
                        value={source.top_k}
                        onChange={(e) =>
                          handleUpdateSource(index, {
                            top_k: parseInt(e.target.value) || 5,
                          })
                        }
                        min={1}
                        max={50}
                        className="bg-background border-border focus:border-primary w-full rounded-lg border px-2 py-1.5 text-xs focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-foreground text-xs">
                        相似度阈值
                      </label>
                      <input
                        type="number"
                        value={source.similarity_threshold}
                        onChange={(e) =>
                          handleUpdateSource(index, {
                            similarity_threshold:
                              parseFloat(e.target.value) || 0.2,
                          })
                        }
                        min={0}
                        max={1}
                        step={0.05}
                        className="bg-background border-border focus:border-primary w-full rounded-lg border px-2 py-1.5 text-xs focus:outline-none"
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => setEditingIndex(null)}
                    className="text-primary w-full text-xs hover:underline"
                  >
                    关闭
                  </button>
                </div>
              )}

              {isLegacy && (
                <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-amber-500">
                  <AlertCircle className="h-2 w-2 text-white" />
                </span>
              )}
            </div>
          );
        })}

        {!isReadOnly && (
          <div className="relative">
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-dashed border-amber-500/40 text-amber-500 transition-colors hover:bg-amber-500/10"
              title="关联知识库"
            >
              {loadingKbs ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
            </button>

            {showDropdown && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowDropdown(false)}
                />
                <div className="bg-background border-border absolute top-full left-0 z-20 mt-2 w-80 overflow-hidden rounded-xl border shadow-lg">
                  <div className="border-border border-b p-3">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="搜索知识库..."
                      className="bg-muted border-border focus:ring-primary/30 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                      autoFocus
                    />
                  </div>
                  <div className="max-h-56 overflow-y-auto">
                    {knowledgeBases.length === 0 && loadingKbs ? (
                      <div className="text-muted-foreground p-4 text-center text-sm">
                        <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
                        加载中...
                      </div>
                    ) : filteredKbs.length === 0 ? (
                      <div className="text-muted-foreground p-4 text-center text-sm">
                        {knowledgeBases.length === 0
                          ? "暂无知识库，请先创建知识库并上传文档"
                          : "没有匹配的知识库"}
                      </div>
                    ) : (
                      filteredKbs.map((kb) => (
                        <button
                          key={kb.id}
                          onClick={() => handleAddKb(kb)}
                          className="hover:bg-accent border-border w-full border-b px-4 py-3 text-left transition-colors last:border-0"
                        >
                          <div className="text-foreground flex items-center gap-2 text-sm font-medium">
                            <Database className="h-3.5 w-3.5 text-amber-500" />
                            {kb.name}
                          </div>
                          {kb.description && (
                            <div className="text-muted-foreground mt-0.5 ml-5.5 text-xs">
                              {kb.description}
                            </div>
                          )}
                          {kb.ragflow_dataset_id ? (
                            <div className="mt-0.5 ml-5.5 text-[10px] text-emerald-500">
                              已连接 RAGFlow
                            </div>
                          ) : (
                            <div className="text-muted-foreground mt-0.5 ml-5.5 text-[10px]">
                              未连接 RAGFlow
                            </div>
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
        <p className="text-muted-foreground text-xs">
          提示：关联知识库后，AI
          生成内容时会从这些知识库检索相关参考资料。点击已关联的知识库可调整检索参数。
        </p>
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
  const [selectedVersion, setSelectedVersion] =
    useState<TemplateVersionResponse | null>(null);

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
    void fetchVersions();
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
      <div className="bg-background relative mx-4 flex max-h-[80vh] w-full max-w-3xl flex-col rounded-2xl shadow-2xl">
        <div className="border-border flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-3">
            <History className="text-primary h-5 w-5" />
            <div>
              <h2 className="text-foreground text-lg font-medium">版本历史</h2>
              <p className="text-muted-foreground text-sm">{templateName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg p-2 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="border-border w-64 shrink-0 overflow-y-auto border-r p-4">
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="text-primary h-6 w-6 animate-spin" />
              </div>
            ) : versions.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-sm">
                暂无版本历史
              </div>
            ) : (
              <div className="space-y-2">
                {versions.map((version) => (
                  <button
                    key={version.id}
                    onClick={() => setSelectedVersion(version)}
                    className={cn(
                      "w-full rounded-lg border p-3 text-left transition-all",
                      selectedVersion?.id === version.id
                        ? "bg-primary/5 border-primary/20"
                        : "bg-card border-border hover:border-primary/30",
                    )}
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-foreground font-medium">
                        {version.version}
                      </span>
                      {version.version === currentVersion && (
                        <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 text-xs">
                          当前
                        </span>
                      )}
                    </div>
                    <div className="text-muted-foreground text-xs">
                      {formatDate(version.published_at)}
                    </div>
                    {version.published_by && (
                      <div className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
                        <User className="h-3 w-3" />
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
                  <h3 className="text-foreground text-lg font-bold">
                    版本 {selectedVersion.version}
                  </h3>
                  {selectedVersion.version === currentVersion && (
                    <span className="text-primary text-sm font-medium">
                      当前使用中
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-muted/50 border-border rounded-lg border p-4">
                    <div className="text-muted-foreground mb-1 text-xs">
                      发布时间
                    </div>
                    <div className="text-foreground text-sm font-medium">
                      {formatDate(selectedVersion.published_at)}
                    </div>
                  </div>
                  {selectedVersion.published_by && (
                    <div className="bg-muted/50 border-border rounded-lg border p-4">
                      <div className="text-muted-foreground mb-1 text-xs">
                        发布者
                      </div>
                      <div className="text-foreground flex items-center gap-1 text-sm font-medium">
                        <User className="h-4 w-4" />
                        {selectedVersion.published_by}
                      </div>
                    </div>
                  )}
                </div>

                {selectedVersion.changelog && (
                  <div className="bg-muted/50 border-border rounded-lg border p-4">
                    <div className="text-muted-foreground mb-2 text-xs">
                      更新说明
                    </div>
                    <div className="text-foreground text-sm whitespace-pre-wrap">
                      {selectedVersion.changelog}
                    </div>
                  </div>
                )}

                <button className="text-primary hover:bg-primary/10 flex items-center gap-2 rounded-lg px-4 py-2 text-sm transition-colors">
                  <Eye className="h-4 w-4" />
                  预览此版本
                </button>
              </div>
            ) : (
              <div className="text-muted-foreground flex h-full items-center justify-center">
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
    section?.contentContract?.structureType ?? "narrative_text",
  );
  const [sectionLevel, setSectionLevel] = useState<string>(
    String(section?.level ?? 1),
  );

  useEffect(() => {
    if (section) {
      setStructureType(
        section.contentContract?.structureType ?? "narrative_text",
      );
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
      <div className="text-muted-foreground flex h-64 items-center justify-center">
        <div className="text-center">
          <FileJson className="text-muted mx-auto mb-3 h-12 w-12 opacity-50" />
          <p className="text-sm">请从左侧选择一个章节进行编辑</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Basic Info */}
      <div className="bg-card border-border space-y-6 rounded-xl border p-6 shadow-sm">
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-foreground text-sm font-medium">
              章节ID
            </label>
            <input
              type="text"
              value={section.id}
              readOnly
              className="bg-muted border-border text-muted-foreground w-full rounded-lg border px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-2">
            <label className="text-foreground text-sm font-medium">
              章节标题 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={section.title}
              onChange={(e) => onUpdate({ title: e.target.value })}
              disabled={isReadOnly}
              className="bg-background border-input focus:ring-primary/30 focus:border-primary disabled:bg-muted disabled:text-muted-foreground w-full rounded-lg border px-3 py-2 text-sm transition-all focus:ring-2 focus:outline-none"
            />
          </div>
          <div className="space-y-2">
            <label className="text-foreground text-sm font-medium">层级</label>
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
            <label className="group relative flex cursor-pointer items-center gap-2.5 select-none">
              <div className="relative">
                <input
                  type="checkbox"
                  checked={section.required}
                  onChange={(e) => onUpdate({ required: e.target.checked })}
                  disabled={isReadOnly}
                  className="peer sr-only"
                />
                <div
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-md border-2 transition-all duration-200",
                    "peer-checked:bg-primary peer-checked:border-primary",
                    "peer-focus-visible:ring-primary/30 peer-focus-visible:ring-2 peer-focus-visible:ring-offset-2",
                    "group-hover:border-primary/60",
                    isReadOnly
                      ? "border-muted bg-muted cursor-not-allowed opacity-50"
                      : section.required
                        ? "border-primary bg-primary"
                        : "border-input bg-background",
                  )}
                >
                  <Check
                    className={cn(
                      "text-primary-foreground h-3.5 w-3.5 transition-all duration-200",
                      section.required
                        ? "scale-100 opacity-100"
                        : "scale-0 opacity-0",
                    )}
                  />
                </div>
              </div>
              <span className="text-foreground text-sm font-medium">
                必选章节
              </span>
            </label>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-foreground text-sm font-medium">
            编写目的
          </label>
          <textarea
            value={section.purpose ?? ""}
            onChange={(e) => onUpdate({ purpose: e.target.value })}
            disabled={isReadOnly}
            rows={2}
            placeholder="描述本章的编写目的和主要内容..."
            className="bg-background border-input focus:ring-primary/30 focus:border-primary disabled:bg-muted w-full resize-y rounded-lg border px-3 py-2 text-sm transition-all focus:ring-2 focus:outline-none"
          />
        </div>
      </div>

      {/* Content Contract */}
      <div className="bg-card border-border space-y-4 rounded-xl border p-6 shadow-sm">
        <div className="text-primary border-border flex items-center gap-2 border-b pb-2">
          <Info className="h-4 w-4" />
          <h4 className="text-sm font-bold tracking-wider uppercase">
            内容契约
          </h4>
        </div>

        {/* Key Elements */}
        <div className="space-y-2">
          <label className="text-foreground text-sm font-medium">
            关键要素 (每行一个)
          </label>
          <div className="border-border space-y-2 rounded-lg border p-3">
            {(section.contentContract?.keyElements ?? []).map((item, i) => (
              <div
                key={i}
                className="bg-muted/50 border-border flex items-center justify-between rounded border px-3 py-1.5 text-sm"
              >
                <span className="text-foreground">• {item}</span>
                <button
                  onClick={() => onRemoveKeyElement(i)}
                  disabled={isReadOnly}
                  className="text-muted-foreground transition-colors hover:text-red-500 disabled:opacity-50"
                >
                  <X className="h-3.5 w-3.5" />
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
                className="border-border focus:border-primary flex-1 rounded border border-dashed px-2 py-1.5 text-sm transition-colors focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={handleAddKeyElement}
                disabled={isReadOnly || !newKeyElement.trim()}
                className="bg-primary/10 text-primary border-primary/30 hover:bg-primary/20 rounded border border-dashed px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>

        {/* Structure Type & Min Word Count */}
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-foreground text-sm font-medium">
              结构类型
            </label>
            <AdminSelect
              value={structureType}
              onValueChange={(v) => {
                setStructureType(v);
                onUpdate({
                  contentContract: {
                    ...section.contentContract,
                    structureType: v as
                      | "narrative_text"
                      | "table"
                      | "formula"
                      | "diagram"
                      | "mixed",
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
            <label className="text-foreground text-sm font-medium">
              最小字数
            </label>
            <input
              type="number"
              value={section.contentContract?.minWordCount ?? 0}
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
              className="bg-background border-input focus:ring-primary/30 focus:border-primary disabled:bg-muted w-full rounded-lg border px-3 py-2 text-sm transition-all focus:ring-2 focus:outline-none"
            />
          </div>
        </div>

        {/* Style Rules */}
        <div className="space-y-2">
          <label className="text-foreground text-sm font-medium">
            编写规范
          </label>
          <textarea
            value={section.contentContract?.styleRules ?? ""}
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
            className="bg-background border-input focus:ring-primary/30 focus:border-primary disabled:bg-muted w-full resize-y rounded-lg border px-3 py-2 text-sm transition-all focus:ring-2 focus:outline-none"
          />
        </div>

        {/* Forbidden Phrases */}
        <div className="space-y-2">
          <label className="text-foreground text-sm font-medium">
            禁用短语 (检测到会警告)
          </label>
          <div className="flex flex-wrap gap-2">
            {(section.contentContract?.forbiddenPhrases ?? []).map(
              (phrase, i) => (
                <span
                  key={i}
                  className="flex items-center gap-1 rounded border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs text-red-500"
                >
                  {phrase}
                  <button
                    onClick={() => onRemoveForbiddenPhrase(i)}
                    disabled={isReadOnly}
                    className="transition-colors hover:text-red-500 disabled:opacity-50"
                  >
                    <X className="h-3 w-3 cursor-pointer" />
                  </button>
                </span>
              ),
            )}
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={newForbiddenPhrase}
                onChange={(e) => setNewForbiddenPhrase(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && handleAddForbiddenPhrase()
                }
                disabled={isReadOnly}
                placeholder="添加禁用短语"
                className="border-border w-32 rounded border border-dashed px-2 py-1 text-xs transition-colors focus:border-red-500 focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={handleAddForbiddenPhrase}
                disabled={isReadOnly || !newForbiddenPhrase.trim()}
                className="text-primary hover:text-primary/80 text-xs transition-colors hover:underline disabled:opacity-50"
              >
                + 添加
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Compliance Rules */}
      <div className="bg-card border-border space-y-4 rounded-xl border p-6 shadow-sm">
        <div className="text-primary border-border flex items-center gap-2 border-b pb-2">
          <ShieldCheck className="h-4 w-4" />
          <h4 className="text-sm font-bold tracking-wider uppercase">
            合规规则
          </h4>
        </div>
        <div className="space-y-2">
          {(section.complianceRules ?? []).map((rule, i) => (
            <div
              key={i}
              className="bg-primary/5 border-primary/10 flex items-center justify-between rounded-lg border p-3 text-sm"
            >
              <span className="text-foreground">{rule}</span>
              <button
                onClick={() => {
                  const newRules = [...(section.complianceRules ?? [])];
                  newRules.splice(i, 1);
                  onUpdate({ complianceRules: newRules });
                }}
                disabled={isReadOnly}
                className="text-muted-foreground transition-colors hover:text-red-500 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
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
                      ...(section.complianceRules ?? []),
                      newComplianceRule.trim(),
                    ],
                  });
                  setNewComplianceRule("");
                }
              }}
              disabled={isReadOnly}
              placeholder="添加合规规则，如：必须引用XX法规第X条"
              className="border-border focus:border-primary flex-1 rounded-lg border border-dashed px-3 py-2 text-sm transition-colors focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={() => {
                if (newComplianceRule.trim()) {
                  onUpdate({
                    complianceRules: [
                      ...(section.complianceRules ?? []),
                      newComplianceRule.trim(),
                    ],
                  });
                  setNewComplianceRule("");
                }
              }}
              disabled={isReadOnly || !newComplianceRule.trim()}
              className="bg-primary/10 text-primary border-primary/30 hover:bg-primary/20 rounded-lg border border-dashed px-4 py-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* RAG Sources */}
      <div className="bg-card border-border space-y-4 rounded-xl border p-6 shadow-sm">
        <div className="text-primary border-border flex items-center gap-2 border-b pb-2">
          <Link className="h-4 w-4" />
          <h4 className="text-sm font-bold tracking-wider uppercase">
            RAG 数据源
          </h4>
          <span className="text-muted-foreground ml-auto text-xs font-normal">
            报告生成时的检索知识库
          </span>
        </div>

        {/* 可用的 RAG 数据源 */}
        <RAGSourceSelector
          selected={section.ragSources ?? []}
          onUpdate={(newSources) => onUpdate({ ragSources: newSources })}
          isReadOnly={isReadOnly}
        />
      </div>

      {/* Generation Hint & Example */}
      <div className="bg-card border-border space-y-4 rounded-xl border p-6 shadow-sm">
        <h4 className="text-foreground text-sm font-bold tracking-wider uppercase">
          生成辅助
        </h4>
        <div className="space-y-2">
          <label className="text-foreground text-sm font-medium">
            生成提示
          </label>
          <textarea
            value={section.generationHint ?? ""}
            onChange={(e) => onUpdate({ generationHint: e.target.value })}
            disabled={isReadOnly}
            rows={2}
            placeholder="AI 生成时的参考提示..."
            className="bg-background border-input focus:ring-primary/30 focus:border-primary disabled:bg-muted w-full resize-y rounded-lg border px-3 py-2 text-sm transition-all focus:ring-2 focus:outline-none"
          />
        </div>
        <div className="space-y-2">
          <label className="text-foreground text-sm font-medium">
            示例片段
          </label>
          <textarea
            value={section.exampleSnippet ?? ""}
            onChange={(e) => onUpdate({ exampleSnippet: e.target.value })}
            disabled={isReadOnly}
            rows={3}
            placeholder="本章的参考示例文本..."
            className="bg-background border-input focus:ring-primary/30 focus:border-primary disabled:bg-muted w-full resize-y rounded-lg border px-3 py-2 text-sm transition-all focus:ring-2 focus:outline-none"
          />
        </div>
      </div>

      {/* Rich Metadata: tables, figures, formulas, calc scripts, sub-section profile */}
      <RichMetadataEditor section={section} onChange={onUpdate} />
    </div>
  );
}

// ============== Main TemplateEditor Component ==============

export default function TemplateEditor() {
  const { templates, loading: listLoading, fetchTemplates } = useTemplateList();

  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    null,
  );
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(
    null,
  );
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [confirmAction, setConfirmAction] = useState<{
    action: () => Promise<void>;
    title: string;
    message: string;
  } | null>(null);

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
    kfApi
      .listDomains()
      .then((res) => {
        if (res.domains.length > 0) {
          setDomains(res.domains);
          setNewTemplateDomain(res.domains[0]!.id);
        }
      })
      .catch(() => {
        // intentional no-op: domain list load failure keeps empty options
      });
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
  const [originalSnapshot, setOriginalSnapshot] =
    useState<EditorTemplate | null>(null);

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
  } = useTemplateEditor(selectedTemplateId);

  // 加载模板列表
  useEffect(() => {
    void fetchTemplates({ status: "draft,published", limit: 50 });
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

  // 选中模板后自动选中第一个章节。
  // 依赖用 template?.id 而非 template?.sections：任何章节编辑（updateSection 等）
  // 都会通过 sections.map(...) 产生新的数组引用，若依赖 sections，每次输入都会
  // 重跑本 effect 并把选中项重置回第一个一级章节 → 编辑子章节时焦点"跳到父章节"。
  // 只在切换到不同模板（id 变化）时自动选中，编辑中保持用户当前选中。
  // sectionsRef 持有最新 sections 但不作为依赖：避免每次编辑章节都重跑本 effect。
  const sectionsRef = useRef<EditorSection[] | undefined>(undefined);
  sectionsRef.current = template?.sections;
  useEffect(() => {
    const sections = sectionsRef.current;
    if (sections?.length) {
      const firstSection = findFirstSection(sections);
      if (firstSection) {
        setSelectedSectionId(firstSection.id);
        setExpandedIds((prev) => new Set([...prev, firstSection.id]));
      }
    } else {
      setSelectedSectionId(null);
    }
  }, [template?.id]);

  // 查找第一个章节
  const findFirstSection = (
    sections: EditorSection[],
  ): EditorSection | null => {
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
    [addSection],
  );

  // 删除章节
  const handleDeleteSection = useCallback(
    (id: string) => {
      if (selectedSectionId === id) {
        setSelectedSectionId(null);
      }
      deleteSection(id);
    },
    [deleteSection, selectedSectionId],
  );

  // 保存草稿
  const handleSaveDraft = async () => {
    try {
      await saveDraft();
      toast.success("草稿保存成功");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
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
  // templateRef 持有最新 template 但不作为依赖：快照更新仍只在 id/isDirty 变化时触发。
  const templateRef = useRef<EditorTemplate | null>(null);
  templateRef.current = template;
  useEffect(() => {
    const current = templateRef.current;
    if (current && !current.isDirty) {
      setOriginalSnapshot(JSON.parse(JSON.stringify(current)));
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
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-border bg-background sticky top-0 z-10 flex shrink-0 items-center justify-between border-b p-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Edit3 className="text-primary h-5 w-5" />
            <h2 className="text-foreground text-lg font-medium tracking-tight">
              模板编辑器
            </h2>
          </div>
          <TemplateSelector
            templates={editorTemplates}
            selectedId={selectedTemplateId}
            onSelect={setSelectedTemplateId}
            onRefresh={() =>
              fetchTemplates({ status: "draft,published", limit: 50 })
            }
            loading={listLoading}
          />
          <button
            onClick={() => setShowCreateDialog(true)}
            className="text-primary bg-primary/10 border-primary/30 hover:bg-primary/20 flex items-center gap-1.5 rounded-lg border border-dashed px-3 py-1.5 text-sm font-medium transition-colors"
          >
            <Plus className="h-4 w-4" />
            新建模板
          </button>
          {template?.isDirty && (
            <span className="rounded-full bg-amber-500/10 px-2 py-1 text-xs text-amber-500">
              有未保存的更改
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {/* 版本历史 */}
          <button
            onClick={() => setShowVersionHistory(true)}
            disabled={!template}
            className="text-foreground bg-card border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            <History className="h-4 w-4" />
            版本历史
          </button>

          {/* 导出 */}
          <button
            onClick={handleExport}
            disabled={!template}
            className="text-foreground bg-card border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            导出
          </button>

          {/* 删除 */}
          <button
            onClick={handleDeleteTemplate}
            disabled={!template}
            className="text-destructive bg-card border-border hover:bg-destructive/10 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            删除
          </button>

          <button
            onClick={handleSaveDraft}
            disabled={saving || !template || !template.isDirty || isPublished}
            className="text-foreground bg-card border-border hover:bg-accent flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            保存草稿
          </button>
          <button
            onClick={handlePublish}
            disabled={saving || !template || isPublished}
            className="bg-primary hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            发布
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background flex w-full max-w-sm flex-col rounded-2xl shadow-2xl">
            <div className="px-6 py-5 text-center">
              <div className="bg-destructive/10 mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full">
                <AlertCircle className="text-destructive h-6 w-6" />
              </div>
              <h3 className="text-foreground mb-1 text-base font-medium">
                {confirmAction.title}
              </h3>
              <p className="text-muted-foreground text-sm">
                {confirmAction.message}
              </p>
            </div>
            <div className="border-border flex justify-center gap-3 border-t px-6 py-4">
              <button
                onClick={() => setConfirmAction(null)}
                className="border-border hover:bg-accent rounded-lg border px-4 py-2 text-sm transition-colors"
              >
                取消
              </button>
              <button
                onClick={async () => {
                  const action = confirmAction.action;
                  setConfirmAction(null);
                  await action();
                }}
                className="bg-destructive hover:bg-destructive/90 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors"
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
          <div className="bg-background w-full max-w-md space-y-5 rounded-2xl p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-foreground text-lg font-semibold">
                新建模板
              </h3>
              <button
                onClick={() => setShowCreateDialog(false)}
                className="hover:bg-accent rounded-lg p-1.5 transition-colors"
              >
                <X className="text-muted-foreground h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  模板名称
                </label>
                <input
                  type="text"
                  value={newTemplateName}
                  onChange={(e) => setNewTemplateName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateTemplate()}
                  placeholder="例如：消防设计专篇标准模板"
                  className="border-input focus:ring-primary/30 focus:border-primary w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <label className="text-foreground text-sm font-medium">
                  业务领域
                </label>
                {domains.length > 0 ? (
                  <AdminSelect
                    value={newTemplateDomain}
                    onValueChange={setNewTemplateDomain}
                    options={domains.map((d) => ({
                      value: d.id,
                      label: d.name,
                    }))}
                    placeholder="选择领域"
                  />
                ) : (
                  <input
                    type="text"
                    value={newTemplateDomain}
                    onChange={(e) => setNewTemplateDomain(e.target.value)}
                    placeholder="输入领域标识"
                    className="border-input focus:ring-primary/30 w-full rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
                  />
                )}
              </div>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowCreateDialog(false)}
                className="border-border hover:bg-accent rounded-lg border px-4 py-2 text-sm transition-colors"
              >
                取消
              </button>
              <button
                disabled={creating || !newTemplateName.trim()}
                onClick={handleCreateTemplate}
                className="bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> 创建中...
                  </>
                ) : (
                  "创建"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        {templateLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="text-primary h-8 w-8 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <AlertCircle className="mx-auto mb-3 h-12 w-12 text-red-500" />
              <p className="text-red-500">{error}</p>
            </div>
          </div>
        ) : !template ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="flex flex-col items-center">
              <FileJson className="text-muted-foreground/20 mb-4 h-16 w-16" />
              <p className="text-foreground mb-1 font-medium">
                请从上方选择一个模板进行编辑
              </p>
              <button
                onClick={() =>
                  fetchTemplates({ status: "draft,published", limit: 50 })
                }
                className="text-primary hover:text-primary/80 text-sm hover:underline"
              >
                刷新模板列表
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Sidebar Tree */}
            <div className="border-border bg-muted/50 w-72 shrink-0 overflow-y-auto border-r p-4">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-muted-foreground flex items-center gap-2 text-xs font-bold tracking-wider uppercase">
                  <FileJson className="h-3 w-3" /> 章节树
                </h3>
                {!isPublished && (
                  <button
                    onClick={() => handleAddSection(null, 1)}
                    className="hover:bg-accent text-muted-foreground hover:text-primary rounded-lg p-1.5 transition-colors"
                    title="添加一级章节"
                  >
                    <Plus className="h-4 w-4" />
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
            <div className="bg-muted/30 flex-1 overflow-y-auto p-8">
              <div className="mx-auto max-w-4xl">
                {/* Section Navigation */}
                <div className="bg-card border-border mb-4 flex items-center justify-between rounded-lg border px-4 py-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={goToPrevSection}
                      disabled={currentSectionIndex <= 0}
                      className="hover:bg-accent rounded p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-30"
                      title="上一章节"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                    <span className="text-muted-foreground text-sm">
                      第 {currentSectionIndex + 1} / {allSections.length} 章节
                    </span>
                    <button
                      onClick={goToNextSection}
                      disabled={currentSectionIndex >= allSections.length - 1}
                      className="hover:bg-accent rounded p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-30"
                      title="下一章节"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    {template?.isDirty && (
                      <button
                        onClick={handleRevert}
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs text-amber-500 transition-colors hover:bg-amber-500/10"
                      >
                        <Undo2 className="h-3 w-3" />
                        撤销更改
                      </button>
                    )}
                    {selectedSection && (
                      <span className="text-muted-foreground flex items-center gap-1 text-xs">
                        <Clock className="h-3 w-3" />
                        最后修改:{" "}
                        {template.lastSaved
                          ? new Date(template.lastSaved).toLocaleTimeString()
                          : "未保存"}
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
