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
} from "lucide-react";
import React, { useState, useEffect, useCallback, useMemo } from "react";

import { kfApi } from "@/extensions/api";

import { useTemplateList, useTemplateEditor } from "./hooks";
import type { EditorSection, EditorTemplate, TemplateVersionResponse } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

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
        className="flex items-center gap-2 px-3 py-1.5 bg-zinc-100 hover:bg-zinc-200 rounded-lg transition-colors text-sm"
      >
        <FileText className="w-4 h-4 text-zinc-500" />
        <span className="font-medium text-zinc-700 max-w-[200px] truncate">
          {selected?.name || "选择模板"}
        </span>
        {selected && (
          <span className="text-xs text-zinc-400">v{selected.version}</span>
        )}
        <ChevronDown className="w-4 h-4 text-zinc-400" />
      </button>

      {showDropdown && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setShowDropdown(false)}
          />
          <div className="absolute top-full left-0 mt-2 w-72 bg-white rounded-xl border border-zinc-200 shadow-lg z-20 overflow-hidden">
            <div className="p-3 border-b border-zinc-100 flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                选择模板
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRefresh();
                }}
                className="p-1 hover:bg-zinc-100 rounded transition-colors"
                disabled={loading}
              >
                <RefreshCw
                  className={cn("w-3.5 h-3.5 text-zinc-400", loading && "animate-spin")}
                />
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {templates.length === 0 ? (
                <div className="p-4 text-center text-sm text-zinc-500">
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
                      "w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors border-b border-zinc-50 last:border-0",
                      selectedId === template.id && "bg-indigo-50"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm text-zinc-900">
                        {template.name}
                      </span>
                      {selectedId === template.id && (
                        <Check className="w-4 h-4 text-indigo-600" />
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-zinc-400">
                        v{template.version}
                      </span>
                      <span
                        className={cn(
                          "text-xs px-1.5 py-0.5 rounded-full",
                          template.status === "published"
                            ? "bg-emerald-50 text-emerald-600"
                            : template.status === "draft"
                            ? "bg-amber-50 text-amber-600"
                            : "bg-zinc-100 text-zinc-500"
                        )}
                      >
                        {template.status === "published"
                          ? "已发布"
                          : template.status === "draft"
                          ? "草稿"
                          : "已废弃"}
                      </span>
                      <span className="text-xs text-zinc-400">
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
              ? "bg-indigo-50 text-indigo-700 font-medium"
              : "hover:bg-zinc-100 text-zinc-700"
          )}
          style={{ marginLeft: depth * 16 }}
          onClick={() => onSelect(section.id)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (hasChildren) onToggleExpand(section.id);
            }}
            className="p-0.5 hover:bg-zinc-200 rounded transition-colors"
          >
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown className="w-4 h-4 text-zinc-400" />
              ) : (
                <ChevronRight className="w-4 h-4 text-zinc-400" />
              )
            ) : (
              <div className="w-4" />
            )}
          </button>
          <span className="flex-1 truncate">{section.title}</span>
          {section.required && (
            <span className="text-[10px] text-red-400">必</span>
          )}
          {canDelete && (
            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onAdd(section.id, section.level + 1);
                }}
                className="p-1 hover:bg-indigo-100 rounded transition-colors"
                title="添加子章节"
              >
                <Plus className="w-3 h-3 text-indigo-500" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(section.id);
                }}
                className="p-1 hover:bg-red-50 rounded transition-colors"
                title="删除章节"
              >
                <Trash2 className="w-3 h-3 text-red-400" />
              </button>
            </div>
          )}
        </div>
        {hasChildren && isExpanded && (
          <div className="border-l border-zinc-200 ml-2 mt-1">
            {section.children!.map((child) => renderSection(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-1">
      {sections.length === 0 ? (
        <div className="text-center py-8 text-sm text-zinc-400">
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
  selected: string[];
  onUpdate: (newSources: string[]) => void;
  isReadOnly: boolean;
}

const AVAILABLE_RAG_SOURCES = [
  { id: "laws-national", name: "国家法律法规库", type: "法规", description: "国家法律、行政法规、部门规章等" },
  { id: "laws-local", name: "地方生态环境厅文件库", type: "法规", description: "地方性法规、环保厅规范性文件等" },
  { id: "standards", name: "行业标准规范库", type: "标准", description: "国家标准、行业标准、地方标准等" },
  { id: "cases", name: "历史案例库", type: "案例", description: "同类项目环评报告、历史案例参考" },
  { id: "guides", name: "编制指南库", type: "指南", description: "环评编制技术指南、导则等" },
  { id: "templates", name: "模板参考库", type: "模板", description: "标准模板、章节模板参考" },
];

function RAGSourceSelector({ selected, onUpdate, isReadOnly }: RAGSourceSelectorProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredSources = AVAILABLE_RAG_SOURCES.filter(
    (s) =>
      !selected.includes(s.name) &&
      (s.name.includes(searchQuery) || s.type.includes(searchQuery))
  );

  const handleAdd = (name: string) => {
    onUpdate([...selected, name]);
    setShowDropdown(false);
  };

  const handleRemove = (name: string) => {
    onUpdate(selected.filter((s) => s !== name));
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {selected.map((name) => {
          const source = AVAILABLE_RAG_SOURCES.find((s) => s.name === name);
          return (
            <span
              key={name}
              className="bg-amber-50 text-amber-700 px-3 py-1.5 rounded-full border border-amber-100 text-xs font-medium flex items-center gap-2"
            >
              {source?.type === "法规" && <ShieldCheck className="w-3 h-3" />}
              {source?.type === "标准" && <FileJson className="w-3 h-3" />}
              {source?.type === "案例" && <FileText className="w-3 h-3" />}
              {name}
              <button
                onClick={() => handleRemove(name)}
                disabled={isReadOnly}
                className="hover:text-amber-900 transition-colors disabled:opacity-50"
              >
                <X className="w-3 h-3 cursor-pointer" />
              </button>
            </span>
          );
        })}

        {!isReadOnly && (
          <div className="relative">
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="w-8 h-8 rounded-full border border-dashed border-amber-300 flex items-center justify-center text-amber-400 hover:bg-amber-50 transition-colors"
            >
              <Plus className="w-4 h-4" />
            </button>

            {showDropdown && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowDropdown(false)}
                />
                <div className="absolute top-full left-0 mt-2 w-72 bg-white rounded-xl border border-zinc-200 shadow-lg z-20 overflow-hidden">
                  <div className="p-3 border-b border-zinc-100">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="搜索数据源..."
                      className="w-full px-3 py-2 text-sm bg-zinc-50 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500"
                      autoFocus
                    />
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {filteredSources.length === 0 ? (
                      <div className="p-4 text-center text-sm text-zinc-400">
                        没有更多可添加的数据源
                      </div>
                    ) : (
                      filteredSources.map((source) => (
                        <button
                          key={source.id}
                          onClick={() => handleAdd(source.name)}
                          className="w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors border-b border-zinc-50 last:border-0"
                        >
                          <div className="font-medium text-sm text-zinc-900">
                            {source.name}
                          </div>
                          <div className="text-xs text-zinc-400 mt-0.5">
                            {source.description}
                          </div>
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
        <p className="text-xs text-zinc-400">
          提示：选择 RAG 数据源后，AI 生成内容时会自动参考这些知识库。
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
        className="text-xs text-emerald-600 hover:text-emerald-700 hover:underline transition-colors"
      >
        从模板选择...
      </button>

      {showTemplates && (
        <div className="mt-2 p-3 bg-emerald-50/50 rounded-lg border border-emerald-100 max-h-48 overflow-y-auto">
          {COMPLIANCE_RULE_TEMPLATES.map((template) => (
            <button
              key={template.id}
              onClick={() => {
                onSelect(template.rule);
                setShowTemplates(false);
              }}
              className="w-full text-left p-2 hover:bg-white rounded transition-colors mb-1 last:mb-0"
            >
              <div className="text-xs font-medium text-zinc-700">{template.name}</div>
              <div className="text-xs text-emerald-600 mt-0.5">{template.rule}</div>
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
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200">
          <div className="flex items-center gap-3">
            <History className="w-5 h-5 text-indigo-600" />
            <div>
              <h2 className="text-lg font-bold text-zinc-900">版本历史</h2>
              <p className="text-sm text-zinc-500">{templateName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex">
          <div className="w-64 border-r border-zinc-100 overflow-y-auto p-4 shrink-0">
            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
              </div>
            ) : versions.length === 0 ? (
              <div className="text-center py-8 text-sm text-zinc-400">暂无版本历史</div>
            ) : (
              <div className="space-y-2">
                {versions.map((version) => (
                  <button
                    key={version.id}
                    onClick={() => setSelectedVersion(version)}
                    className={cn(
                      "w-full text-left p-3 rounded-lg border transition-all",
                      selectedVersion?.id === version.id
                        ? "bg-indigo-50 border-indigo-200"
                        : "bg-white border-zinc-200 hover:border-zinc-300"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-zinc-900">v{version.version}</span>
                      {version.version === currentVersion && (
                        <span className="text-xs px-1.5 py-0.5 bg-indigo-100 text-indigo-600 rounded">
                          当前
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-zinc-500">{formatDate(version.published_at)}</div>
                    {version.published_by && (
                      <div className="flex items-center gap-1 mt-1 text-xs text-zinc-400">
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
                  <h3 className="text-lg font-bold text-zinc-900">
                    版本 {selectedVersion.version}
                  </h3>
                  {selectedVersion.version === currentVersion && (
                    <span className="text-sm text-indigo-600 font-medium">当前使用中</span>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-zinc-50 rounded-lg">
                    <div className="text-xs text-zinc-400 mb-1">发布时间</div>
                    <div className="text-sm font-medium text-zinc-900">
                      {formatDate(selectedVersion.published_at)}
                    </div>
                  </div>
                  {selectedVersion.published_by && (
                    <div className="p-4 bg-zinc-50 rounded-lg">
                      <div className="text-xs text-zinc-400 mb-1">发布者</div>
                      <div className="text-sm font-medium text-zinc-900 flex items-center gap-1">
                        <User className="w-4 h-4" />
                        {selectedVersion.published_by}
                      </div>
                    </div>
                  )}
                </div>

                {selectedVersion.changelog && (
                  <div className="p-4 bg-zinc-50 rounded-lg">
                    <div className="text-xs text-zinc-400 mb-2">更新说明</div>
                    <div className="text-sm text-zinc-700 whitespace-pre-wrap">
                      {selectedVersion.changelog}
                    </div>
                  </div>
                )}

                <button className="flex items-center gap-2 px-4 py-2 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors">
                  <Eye className="w-4 h-4" />
                  预览此版本
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-zinc-400">
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
  const [newRagSource, setNewRagSource] = useState("");
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
      <div className="flex items-center justify-center h-64 text-zinc-400">
        <div className="text-center">
          <FileJson className="w-12 h-12 mx-auto mb-3 text-zinc-300" />
          <p className="text-sm">请从左侧选择一个章节进行编辑</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Basic Info */}
      <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm space-y-6">
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">
              章节ID
            </label>
            <input
              type="text"
              value={section.id}
              readOnly
              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 rounded-lg text-zinc-500 text-sm"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">
              章节标题 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={section.title}
              onChange={(e) => onUpdate({ title: e.target.value })}
              disabled={isReadOnly}
              className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm transition-all disabled:bg-zinc-50 disabled:text-zinc-500"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">层级</label>
            <select
              value={sectionLevel}
              onChange={(e) => {
                setSectionLevel(e.target.value);
                onUpdate({ level: parseInt(e.target.value) });
              }}
              disabled={isReadOnly}
              className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm transition-all disabled:bg-zinc-50"
            >
              <option value="1">第1级</option>
              <option value="2">第2级</option>
              <option value="3">第3级</option>
            </select>
          </div>
          <div className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              id="required"
              checked={section.required}
              onChange={(e) => onUpdate({ required: e.target.checked })}
              disabled={isReadOnly}
              className="w-4 h-4 shrink-0 rounded border-zinc-300 focus:ring-2 focus:ring-indigo-500/30 focus:ring-offset-0 disabled:opacity-50"
            />
            <label
              htmlFor="required"
              className="text-sm font-medium text-zinc-700"
            >
              必选章节
            </label>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-700">编写目的</label>
          <textarea
            value={section.purpose || ""}
            onChange={(e) => onUpdate({ purpose: e.target.value })}
            disabled={isReadOnly}
            rows={2}
            placeholder="描述本章的编写目的和主要内容..."
            className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm resize-none transition-all disabled:bg-zinc-50"
          />
        </div>
      </div>

      {/* Content Contract */}
      <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-indigo-600 border-b border-zinc-100 pb-2">
          <Info className="w-4 h-4" />
          <h4 className="font-bold text-sm uppercase tracking-wider">内容契约</h4>
        </div>

        {/* Key Elements */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-700">
            关键要素 (每行一个)
          </label>
          <div className="border border-zinc-200 rounded-lg p-3 space-y-2">
            {(section.contentContract?.keyElements || []).map((item, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-zinc-50 px-3 py-1.5 rounded border border-zinc-200 text-sm"
              >
                <span className="text-zinc-700">• {item}</span>
                <button
                  onClick={() => onRemoveKeyElement(i)}
                  disabled={isReadOnly}
                  className="text-zinc-400 hover:text-red-500 transition-colors disabled:opacity-50"
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
                className="flex-1 px-2 py-1.5 text-sm border border-dashed border-zinc-300 rounded focus:outline-none focus:border-indigo-400 transition-colors disabled:opacity-50"
              />
              <button
                onClick={handleAddKeyElement}
                disabled={isReadOnly || !newKeyElement.trim()}
                className="px-3 py-1.5 bg-indigo-50 text-indigo-600 rounded border border-dashed border-indigo-300 text-xs font-medium hover:bg-indigo-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>

        {/* Structure Type & Min Word Count */}
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">结构类型</label>
            <select
              value={structureType}
              onChange={(e) => {
                setStructureType(e.target.value);
                onUpdate({
                  contentContract: {
                    ...section.contentContract,
                    structureType: e.target.value as "narrative_text" | "table" | "formula" | "diagram" | "mixed",
                  } as EditorSection["contentContract"],
                });
              }}
              disabled={isReadOnly}
              className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm transition-all disabled:bg-zinc-50"
            >
              <option value="narrative_text">叙述文本</option>
              <option value="table">表格数据</option>
              <option value="formula">公式计算</option>
              <option value="diagram">流程图/示意图</option>
              <option value="mixed">混合类型</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-700">最小字数</label>
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
              className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm transition-all disabled:bg-zinc-50"
            />
          </div>
        </div>

        {/* Style Rules */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-700">编写规范</label>
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
            className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm resize-none transition-all disabled:bg-zinc-50"
          />
        </div>

        {/* Forbidden Phrases */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-700">
            禁用短语 (检测到会警告)
          </label>
          <div className="flex flex-wrap gap-2">
            {(section.contentContract?.forbiddenPhrases || []).map((phrase, i) => (
              <span
                key={i}
                className="bg-red-50 text-red-600 px-2 py-1 rounded border border-red-200 text-xs flex items-center gap-1"
              >
                {phrase}
                <button
                  onClick={() => onRemoveForbiddenPhrase(i)}
                  disabled={isReadOnly}
                  className="hover:text-red-700 transition-colors disabled:opacity-50"
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
                className="w-32 px-2 py-1 text-xs border border-dashed border-zinc-300 rounded focus:outline-none focus:border-red-400 transition-colors disabled:opacity-50"
              />
              <button
                onClick={handleAddForbiddenPhrase}
                disabled={isReadOnly || !newForbiddenPhrase.trim()}
                className="text-xs text-indigo-600 hover:text-indigo-700 hover:underline transition-colors disabled:opacity-50"
              >
                + 添加
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Compliance Rules */}
      <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-emerald-600 border-b border-zinc-100 pb-2">
          <ShieldCheck className="w-4 h-4" />
          <h4 className="font-bold text-sm uppercase tracking-wider">合规规则</h4>
        </div>
        <div className="space-y-2">
          {(section.complianceRules || []).map((rule, i) => (
            <div
              key={i}
              className="flex items-center justify-between bg-emerald-50/50 p-3 rounded-lg border border-emerald-100 text-sm"
            >
              <span className="text-emerald-800">{rule}</span>
              <button
                onClick={() => {
                  const newRules = [...(section.complianceRules || [])];
                  newRules.splice(i, 1);
                  onUpdate({ complianceRules: newRules });
                }}
                disabled={isReadOnly}
                className="text-emerald-500 hover:text-red-500 transition-colors disabled:opacity-50"
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
              className="flex-1 px-3 py-2 text-sm border border-dashed border-zinc-300 rounded-lg focus:outline-none focus:border-emerald-400 transition-colors disabled:opacity-50"
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
              className="px-4 py-2 bg-emerald-50 text-emerald-600 rounded-lg border border-dashed border-emerald-300 text-xs font-medium hover:bg-emerald-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* RAG Sources */}
      <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-amber-600 border-b border-zinc-100 pb-2">
          <Link className="w-4 h-4" />
          <h4 className="font-bold text-sm uppercase tracking-wider">RAG 数据源</h4>
          <span className="text-xs text-amber-400 font-normal ml-auto">AI 生成时的参考知识库</span>
        </div>
        
        {/* 可用的 RAG 数据源 */}
        <RAGSourceSelector
          selected={section.ragSources || []}
          onUpdate={(newSources) => onUpdate({ ragSources: newSources })}
          isReadOnly={isReadOnly}
        />
      </div>

      {/* Generation Hint & Example */}
      <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm space-y-4">
        <h4 className="font-bold text-sm text-zinc-700 uppercase tracking-wider">
          生成辅助
        </h4>
        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-700">生成提示</label>
          <textarea
            value={section.generationHint || ""}
            onChange={(e) => onUpdate({ generationHint: e.target.value })}
            disabled={isReadOnly}
            rows={2}
            placeholder="AI 生成时的参考提示..."
            className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm resize-none transition-all disabled:bg-zinc-50"
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-700">示例片段</label>
          <textarea
            value={section.exampleSnippet || ""}
            onChange={(e) => onUpdate({ exampleSnippet: e.target.value })}
            disabled={isReadOnly}
            rows={3}
            placeholder="本章的参考示例文本..."
            className="w-full px-3 py-2 bg-white border border-zinc-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-sm resize-none transition-all disabled:bg-zinc-50"
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
  const [notification, setNotification] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // 版本历史弹窗状态
  const [showVersionHistory, setShowVersionHistory] = useState(false);

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

  // 通知
  const showNotification = useCallback(
    (type: "success" | "error", message: string) => {
      setNotification({ type, message });
      setTimeout(() => setNotification(null), 3000);
    },
    []
  );

  // 保存草稿
  const handleSaveDraft = async () => {
    try {
      await saveDraft();
      showNotification("success", "草稿保存成功");
    } catch (e) {
      showNotification(
        "error",
        e instanceof Error ? e.message : "保存失败"
      );
    }
  };

  // 发布模板
  const handlePublish = async () => {
    if (!template) return;

    if (
      !window.confirm(
        `确定要发布模板「${template.name}」吗？发布后将无法直接修改。`
      )
    ) {
      return;
    }

    try {
      await publishTemplate();
      showNotification("success", "模板发布成功");
    } catch (e) {
      showNotification(
        "error",
        e instanceof Error ? e.message : "发布失败"
      );
    }
  };

  // 导出模板
  const handleExport = useCallback(() => {
    if (!template || !selectedTemplateId) return;

    const exportUrl = kfApi.exportTemplate(selectedTemplateId);
    const link = document.createElement("a");
    link.href = exportUrl;
    link.download = `${template.name}_v${template.version}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showNotification("success", "模板导出成功");
  }, [template, selectedTemplateId, showNotification]);

  // 撤销更改 - 使用快照恢复
  const handleRevert = useCallback(() => {
    if (!originalSnapshot) return;
    
    if (!window.confirm("确定要撤销所有未保存的更改吗？")) {
      return;
    }
    
    // 恢复原始状态
    setTemplate(originalSnapshot);
    showNotification("success", "已撤销所有更改");
  }, [originalSnapshot, setTemplate, showNotification]);

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
      <div className="sticky top-0 z-10 p-4 border-b border-zinc-200 bg-white flex justify-between items-center shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Edit3 className="w-5 h-5 text-indigo-600" />
            <h2 className="text-lg font-semibold text-zinc-900 tracking-tight">
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
          {template?.isDirty && (
            <span className="text-xs text-amber-500 bg-amber-50 px-2 py-1 rounded-full">
              有未保存的更改
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {/* 版本历史 */}
          <button
            onClick={() => setShowVersionHistory(true)}
            disabled={!template}
            className="px-3 py-2 text-zinc-700 bg-white border border-zinc-300 rounded-lg flex items-center gap-2 hover:bg-zinc-50 transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <History className="w-4 h-4" />
            版本历史
          </button>
          
          {/* 导出 */}
          <button
            onClick={handleExport}
            disabled={!template}
            className="px-3 py-2 text-zinc-700 bg-white border border-zinc-300 rounded-lg flex items-center gap-2 hover:bg-zinc-50 transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download className="w-4 h-4" />
            导出
          </button>
          
          <button
            onClick={handleSaveDraft}
            disabled={saving || !template || !template.isDirty || isPublished}
            className="px-4 py-2 text-zinc-700 bg-white border border-zinc-300 rounded-lg flex items-center gap-2 hover:bg-zinc-50 transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
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
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg flex items-center gap-2 hover:bg-indigo-700 transition-colors shadow-sm font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
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

      {/* Notification */}
      {notification && (
        <div
          className={cn(
            "fixed top-20 right-4 z-50 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 animate-in slide-in-from-right",
            notification.type === "success"
              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
              : "bg-red-50 text-red-700 border border-red-200"
          )}
        >
          {notification.type === "success" ? (
            <Check className="w-4 h-4" />
          ) : (
            <AlertCircle className="w-4 h-4" />
          )}
          {notification.message}
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

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {templateLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <AlertCircle className="w-12 h-12 mx-auto mb-3 text-red-400" />
              <p className="text-red-600">{error}</p>
            </div>
          </div>
        ) : !template ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <FileJson className="w-16 h-16 mx-auto mb-4 text-zinc-300" />
              <p className="text-zinc-500 mb-4">请从上方选择一个模板进行编辑</p>
              <button
                onClick={() => fetchTemplates({ status: "draft,published", limit: 50 })}
                className="text-sm text-indigo-600 hover:text-indigo-700 hover:underline"
              >
                刷新模板列表
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Sidebar Tree */}
            <div className="w-72 border-r border-zinc-200 bg-zinc-50/50 overflow-y-auto p-4 shrink-0">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-2">
                  <FileJson className="w-3 h-3" /> 章节树
                </h3>
                {!isPublished && (
                  <button
                    onClick={() => handleAddSection(null, 1)}
                    className="p-1.5 hover:bg-zinc-200 rounded-lg text-zinc-500 hover:text-indigo-600 transition-colors"
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
            <div className="flex-1 overflow-y-auto bg-zinc-50/30 p-8">
              <div className="max-w-4xl mx-auto">
                {/* Section Navigation */}
                <div className="flex items-center justify-between mb-4 bg-white rounded-lg border border-zinc-200 px-4 py-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={goToPrevSection}
                      disabled={currentSectionIndex <= 0}
                      className="p-1.5 hover:bg-zinc-100 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title="上一章节"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <span className="text-sm text-zinc-500">
                      第 {currentSectionIndex + 1} / {allSections.length} 章节
                    </span>
                    <button
                      onClick={goToNextSection}
                      disabled={currentSectionIndex >= allSections.length - 1}
                      className="p-1.5 hover:bg-zinc-100 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      title="下一章节"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    {template?.isDirty && (
                      <button
                        onClick={handleRevert}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-amber-600 hover:bg-amber-50 rounded transition-colors"
                      >
                        <Undo2 className="w-3 h-3" />
                        撤销更改
                      </button>
                    )}
                    {selectedSection && (
                      <span className="text-xs text-zinc-400 flex items-center gap-1">
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
