"use client";

import { useState, useCallback, useEffect } from "react";

import { kfApi } from "../../api";
import type {
  TemplateDocument,
  TemplateSection,
  TemplateListItem,
  TemplateListResponse,
  EditorSection,
  EditorTemplate,
  EditorContentContract,
  TemplateUpdatePayload,
} from "@/extensions/knowledge-factory/types";

/** 将后端 TemplateSection（snake_case API 响应）转换为前端 EditorSection（camelCase） */
function apiSectionToEditor(sec: TemplateSection): EditorSection {
  return {
    id: sec.id,
    title: sec.title,
    level: sec.level,
    required: sec.required,
    purpose: sec.purpose,
    children: sec.children?.map(apiSectionToEditor),
    contentContract: sec.content_contract
      ? {
          keyElements: sec.content_contract.key_elements,
          structureType: sec.content_contract.structure_type,
          styleRules: sec.content_contract.style_rules ?? "",
          minWordCount: sec.content_contract.min_word_count ?? 0,
          forbiddenPhrases: sec.content_contract.forbidden_phrases ?? [],
        }
      : undefined,
    complianceRules: sec.compliance_rules,
    ragSources: sec.rag_sources,
    generationHint: sec.generation_hint,
    exampleSnippet: sec.example_snippet,
    completenessScore: sec.completeness_score,
  };
}

/** 将后端 TemplateDocument 转换为前端 EditorTemplate */
function toEditorTemplate(doc: TemplateDocument): EditorTemplate {
  return {
    id: doc.template_id,
    name: doc.name,
    version: doc.version,
    domain: doc.domain,
    status: doc.status,
    completenessScore: doc.completeness_score,
    sections: (doc.root_sections || []).map(apiSectionToEditor),
    isDirty: false,
  };
}

/** 将前端 EditorSection（camelCase）转换为后端 snake_case 格式 */
function sectionToBackend(section: EditorSection): Record<string, unknown> {
  return {
    id: section.id,
    title: section.title,
    level: section.level,
    required: section.required,
    purpose: section.purpose ?? null,
    children: section.children?.length ? section.children.map(sectionToBackend) : [],
    content_contract: section.contentContract
      ? {
          key_elements: section.contentContract.keyElements,
          structure_type: section.contentContract.structureType,
          style_rules: section.contentContract.styleRules || null,
          min_word_count: section.contentContract.minWordCount || null,
          forbidden_phrases: section.contentContract.forbiddenPhrases ?? [],
        }
      : null,
    compliance_rules: section.complianceRules ?? null,
    rag_sources: section.ragSources ?? null,
    generation_hint: section.generationHint ?? null,
    example_snippet: section.exampleSnippet ?? null,
    completeness_score: section.completenessScore ?? null,
  };
}

/** 生成唯一 ID */
function generateId(): string {
  return `sec_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// ============== Hooks ==============

/**
 * 模板列表 Hook
 */
export function useTemplateList() {
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = useCallback(
    async (params?: { domain?: string; status?: string; page?: number; limit?: number }) => {
      setLoading(true);
      setError(null);
      try {
        const response = await kfApi.listTemplates(params);
        setTemplates(response.templates);
      } catch (e) {
        setError(e instanceof Error ? e.message : "获取模板列表失败");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const deleteTemplate = useCallback(async (id: string) => {
    try {
      await kfApi.deleteTemplate(id);
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      throw e;
    }
  }, []);

  return { templates, loading, error, fetchTemplates, deleteTemplate, setTemplates };
}

/**
 * 模板详情与编辑状态 Hook
 */
export function useTemplateEditor(templateId: string | null) {
  const [template, setTemplate] = useState<EditorTemplate | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 加载模板
  const loadTemplate = useCallback(async () => {
    if (!templateId) return;

    setLoading(true);
    setError(null);
    try {
      const doc = await kfApi.getTemplate(templateId);
      setTemplate(toEditorTemplate(doc));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载模板失败");
    } finally {
      setLoading(false);
    }
  }, [templateId]);

  useEffect(() => {
    loadTemplate();
  }, [loadTemplate]);

  // 更新模板基本信息
  const updateTemplateInfo = useCallback(
    (updates: Partial<Pick<EditorTemplate, "name">>) => {
      setTemplate((prev) =>
        prev
          ? {
              ...prev,
              ...updates,
              isDirty: true,
            }
          : null
      );
    },
    []
  );

  // 查找章节（递归）
  const findSection = useCallback(
    (
      sections: EditorSection[],
      id: string
    ): EditorSection | null => {
      for (const section of sections) {
        if (section.id === id) return section;
        if (section.children) {
          const found = findSection(section.children, id);
          if (found) return found;
        }
      }
      return null;
    },
    []
  );

  // 更新章节
  const updateSection = useCallback(
    (sectionId: string, changes: Partial<EditorSection>) => {
      setTemplate((prev) => {
        if (!prev) return null;

        const updateRecursive = (sections: EditorSection[]): EditorSection[] => {
          return sections.map((section) => {
            if (section.id === sectionId) {
              return { ...section, ...changes };
            }
            if (section.children) {
              return {
                ...section,
                children: updateRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: updateRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 添加章节
  const addSection = useCallback(
    (parentId: string | null, level: number, title = "新章节") => {
      setTemplate((prev) => {
        if (!prev) return null;

        const newSection: EditorSection = {
          id: generateId(),
          title,
          level,
          required: false,
          contentContract: {
            keyElements: [],
            structureType: "narrative_text",
            styleRules: "",
            minWordCount: 0,
            forbiddenPhrases: [],
          },
        };

        const addRecursive = (
          sections: EditorSection[]
        ): EditorSection[] => {
          if (parentId === null) {
            return [...sections, newSection];
          }

          return sections.map((section) => {
            if (section.id === parentId) {
              return {
                ...section,
                children: [...(section.children || []), newSection],
              };
            }
            if (section.children) {
              return {
                ...section,
                children: addRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: addRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 删除章节
  const deleteSection = useCallback((sectionId: string) => {
    setTemplate((prev) => {
      if (!prev) return null;

      const deleteRecursive = (sections: EditorSection[]): EditorSection[] => {
        return sections
          .filter((section) => section.id !== sectionId)
          .map((section) => {
            if (section.children) {
              return {
                ...section,
                children: deleteRecursive(section.children),
              };
            }
            return section;
          });
      };

      return {
        ...prev,
        sections: deleteRecursive(prev.sections),
        isDirty: true,
      };
    });
  }, []);

  // 更新内容契约
  const updateContentContract = useCallback(
    (sectionId: string, contract: Partial<EditorContentContract>) => {
      setTemplate((prev) => {
        if (!prev) return null;

        const updateRecursive = (sections: EditorSection[]): EditorSection[] => {
          return sections.map((section) => {
            if (section.id === sectionId) {
              return {
                ...section,
                contentContract: {
                  ...section.contentContract,
                  ...contract,
                } as EditorContentContract,
              };
            }
            if (section.children) {
              return {
                ...section,
                children: updateRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: updateRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 添加关键要素
  const addKeyElement = useCallback(
    (sectionId: string, element: string) => {
      setTemplate((prev) => {
        if (!prev) return null;

        const updateRecursive = (sections: EditorSection[]): EditorSection[] => {
          return sections.map((section) => {
            if (section.id === sectionId) {
              return {
                ...section,
                contentContract: {
                  ...section.contentContract,
                  keyElements: [
                    ...(section.contentContract?.keyElements || []),
                    element,
                  ],
                } as EditorContentContract,
              };
            }
            if (section.children) {
              return {
                ...section,
                children: updateRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: updateRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 删除关键要素
  const removeKeyElement = useCallback(
    (sectionId: string, index: number) => {
      setTemplate((prev) => {
        if (!prev) return null;

        const updateRecursive = (sections: EditorSection[]): EditorSection[] => {
          return sections.map((section) => {
            if (section.id === sectionId) {
              return {
                ...section,
                contentContract: {
                  ...section.contentContract,
                  keyElements: (section.contentContract?.keyElements || []).filter(
                    (_, i) => i !== index
                  ),
                } as EditorContentContract,
              };
            }
            if (section.children) {
              return {
                ...section,
                children: updateRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: updateRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 添加禁用短语
  const addForbiddenPhrase = useCallback(
    (sectionId: string, phrase: string) => {
      setTemplate((prev) => {
        if (!prev) return null;

        const updateRecursive = (sections: EditorSection[]): EditorSection[] => {
          return sections.map((section) => {
            if (section.id === sectionId) {
              return {
                ...section,
                contentContract: {
                  ...section.contentContract,
                  forbiddenPhrases: [
                    ...(section.contentContract?.forbiddenPhrases || []),
                    phrase,
                  ],
                } as EditorContentContract,
              };
            }
            if (section.children) {
              return {
                ...section,
                children: updateRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: updateRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 删除禁用短语
  const removeForbiddenPhrase = useCallback(
    (sectionId: string, index: number) => {
      setTemplate((prev) => {
        if (!prev) return null;

        const updateRecursive = (sections: EditorSection[]): EditorSection[] => {
          return sections.map((section) => {
            if (section.id === sectionId) {
              return {
                ...section,
                contentContract: {
                  ...section.contentContract,
                  forbiddenPhrases: (
                    section.contentContract?.forbiddenPhrases || []
                  ).filter((_, i) => i !== index),
                } as EditorContentContract,
              };
            }
            if (section.children) {
              return {
                ...section,
                children: updateRecursive(section.children),
              };
            }
            return section;
          });
        };

        return {
          ...prev,
          sections: updateRecursive(prev.sections),
          isDirty: true,
        };
      });
    },
    []
  );

  // 保存草稿
  const saveDraft = useCallback(async () => {
    if (!template || !templateId) return;

    setSaving(true);
    try {
      const payload: TemplateUpdatePayload = {
        root_sections_json: {
          sections: template.sections.map(sectionToBackend),
        },
      };

      await kfApi.updateTemplate(templateId, payload);

      setTemplate((prev) =>
        prev
          ? {
              ...prev,
              isDirty: false,
              lastSaved: new Date().toISOString(),
            }
          : null
      );
    } catch (e) {
      throw e;
    } finally {
      setSaving(false);
    }
  }, [template, templateId]);

  // 发布模板
  const publishTemplate = useCallback(async () => {
    if (!template || !templateId) return;

    // 先保存
    await saveDraft();

    try {
      await kfApi.publishTemplate(templateId);

      setTemplate((prev) =>
        prev
          ? {
              ...prev,
              status: "published",
              isDirty: false,
            }
          : null
      );
    } catch (e) {
      throw e;
    }
  }, [template, templateId, saveDraft]);

  // 获取指定章节
  const getSection = useCallback(
    (sectionId: string): EditorSection | null => {
      if (!template) return null;
      return findSection(template.sections, sectionId);
    },
    [template, findSection]
  );

  return {
    template,
    setTemplate,
    loading,
    saving,
    error,
    loadTemplate,
    updateTemplateInfo,
    updateSection,
    addSection,
    deleteSection,
    updateContentContract,
    addKeyElement,
    removeKeyElement,
    addForbiddenPhrase,
    removeForbiddenPhrase,
    saveDraft,
    publishTemplate,
    getSection,
  };
}
