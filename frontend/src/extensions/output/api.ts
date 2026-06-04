import { authFetch, authFormFetch } from "@/extensions/api/client";

import { transformTemplate } from "./transforms";
import type { GenerateOutputRequest, GenerateOutputResult, HistoryEntry, LayoutTemplate } from "./types";

const API_BASE = "/output";

export const outputApi = {
  listTemplates: async (): Promise<LayoutTemplate[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/templates`);
    return data.items.map(transformTemplate);
  },

  getTemplate: async (id: string): Promise<LayoutTemplate> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/templates/${id}`);
    return transformTemplate(data);
  },

  createTemplate: async (tpl: Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">): Promise<LayoutTemplate> => {
    const payload: Record<string, unknown> = {
      name: tpl.name,
      report_type: tpl.reportType,
      page_settings: tpl.pageSettings,
      body_styles: tpl.bodyStyles,
      heading_styles: tpl.headingStyles ?? [],
      reference_style: tpl.referenceStyle ?? "gb7714",
    };
    if (tpl.coverTemplate) payload.cover_template = tpl.coverTemplate;
    if (tpl.tocSettings) payload.toc_settings = tpl.tocSettings;
    if (tpl.tableStyles) payload.table_styles = tpl.tableStyles;
    if (tpl.figureStyles) payload.figure_styles = tpl.figureStyles;
    if (tpl.headerFooter) payload.header_footer = tpl.headerFooter;
    if (tpl.appendixRules) payload.appendix_rules = tpl.appendixRules;

    const resp = await authFetch<Record<string, unknown>>(`${API_BASE}/templates`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return transformTemplate(resp);
  },

  updateTemplate: async (id: string, tpl: Partial<Omit<LayoutTemplate, "id" | "isBuiltin" | "createdAt" | "updatedAt">>): Promise<LayoutTemplate> => {
    const payload: Record<string, unknown> = {};
    if (tpl.name !== undefined) payload.name = tpl.name;
    if (tpl.reportType !== undefined) payload.report_type = tpl.reportType;
    if (tpl.pageSettings !== undefined) payload.page_settings = tpl.pageSettings;
    if (tpl.bodyStyles !== undefined) payload.body_styles = tpl.bodyStyles;
    if (tpl.headingStyles !== undefined) payload.heading_styles = tpl.headingStyles;
    if (tpl.coverTemplate !== undefined) payload.cover_template = tpl.coverTemplate;
    if (tpl.tocSettings !== undefined) payload.toc_settings = tpl.tocSettings;
    if (tpl.tableStyles !== undefined) payload.table_styles = tpl.tableStyles;
    if (tpl.figureStyles !== undefined) payload.figure_styles = tpl.figureStyles;
    if (tpl.headerFooter !== undefined) payload.header_footer = tpl.headerFooter;
    if (tpl.referenceStyle !== undefined) payload.reference_style = tpl.referenceStyle;
    if (tpl.appendixRules !== undefined) payload.appendix_rules = tpl.appendixRules;

    const resp = await authFetch<Record<string, unknown>>(`${API_BASE}/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    return transformTemplate(resp);
  },

  deleteTemplate: async (id: string): Promise<void> => {
    await authFetch<void>(`${API_BASE}/templates/${id}`, {
      method: "DELETE",
    });
  },

  duplicateTemplate: async (id: string): Promise<LayoutTemplate> => {
    const resp = await authFetch<Record<string, unknown>>(`${API_BASE}/templates/${id}/duplicate`, {
      method: "POST",
    });
    return transformTemplate(resp);
  },

  generate: async (req: GenerateOutputRequest): Promise<GenerateOutputResult> => {
    if (req.source === "markdown" && req.markdownFile) {
      const form = new FormData();
      form.append("source", "markdown");
      form.append("file", req.markdownFile);
      form.append("format", req.format);
      form.append("layout_template_id", req.layoutTemplateId);
      if (req.watermark) form.append("watermark", req.watermark);

      const data = await authFormFetch<Record<string, unknown>>(`${API_BASE}/generate`, form);
      return {
        taskId: data.task_id as string,
        status: data.status as GenerateOutputResult["status"],
        downloadUrl: (data.download_url as string) ?? undefined,
        fileName: (data.file_name as string) ?? undefined,
      };
    }

    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/generate`, {
      method: "POST",
      body: JSON.stringify({
        source: "project",
        project_id: req.projectId,
        format: req.format,
        layout_template_id: req.layoutTemplateId,
        watermark: req.watermark,
        chapter_ids: req.chapterIds,
      }),
    });
    return {
      taskId: data.task_id as string,
      status: data.status as GenerateOutputResult["status"],
      downloadUrl: (data.download_url as string) ?? undefined,
      fileName: (data.file_name as string) ?? undefined,
    };
  },

  getTaskStatus: async (taskId: string): Promise<GenerateOutputResult> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/tasks/${taskId}`);
    return {
      taskId: data.task_id as string,
      status: data.status as GenerateOutputResult["status"],
      downloadUrl: (data.download_url as string) ?? undefined,
      fileName: (data.file_name as string) ?? undefined,
    };
  },

  listHistory: async (): Promise<HistoryEntry[]> => {
    const data = await authFetch<{ items: Record<string, unknown>[] }>(`${API_BASE}/history`);
    return data.items.map((item) => ({
      taskId: item.task_id as string,
      projectId: item.project_id as string,
      format: item.format as string,
      status: item.status as GenerateOutputResult["status"],
      fileName: (item.file_name as string) ?? undefined,
      downloadUrl: (item.download_url as string) ?? undefined,
      createdAt: item.created_at as string,
    }));
  },
};
