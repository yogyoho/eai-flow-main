import { authFetch } from "@/extensions/api/client";

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

  generate: async (req: GenerateOutputRequest): Promise<GenerateOutputResult> => {
    const data = await authFetch<Record<string, unknown>>(`${API_BASE}/generate`, {
      method: "POST",
      body: JSON.stringify({
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
