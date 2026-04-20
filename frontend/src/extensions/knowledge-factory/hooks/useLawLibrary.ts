import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { authFetch, authFormFetch } from "@/extensions/api/client";

import { buildLawLibraryUrl } from "../law-library-api";
import type {
  LawItem,
  LawListResponse,
  LawStatistics,
  RAGFlowStatusResponse,
  LawType,
} from "@/extensions/knowledge-factory/types";

// ========== Query Hooks ==========

export function useLawList(params: {
  law_type?: LawType | "all";
  status?: string;
  keyword?: string;
  page?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["laws", "list", params],
    queryFn: async () => {
      const searchParams: Record<string, string> = {};
      if (params.law_type && params.law_type !== "all") {
        searchParams.law_type = params.law_type;
      }
      if (params.status) {
        searchParams.status = params.status;
      }
      if (params.keyword) {
        searchParams.keyword = params.keyword;
      }
      if (params.page) {
        searchParams.page = String(params.page);
      }
      if (params.limit) {
        searchParams.limit = String(params.limit);
      }
      const url = buildLawLibraryUrl("/kf/laws", searchParams);
      return authFetch<LawListResponse>(url, undefined, "");
    },
    staleTime: 30000,
  });
}

export function useLawItem(lawId: string | null) {
  return useQuery({
    queryKey: ["laws", "item", lawId],
    queryFn: async () => {
      if (!lawId) return null;
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}`);
      return authFetch<LawItem>(url, undefined, "");
    },
    enabled: !!lawId,
  });
}

export function useLawStatistics() {
  return useQuery({
    queryKey: ["laws", "statistics"],
    queryFn: async () => {
      const url = buildLawLibraryUrl("/kf/laws/statistics");
      return authFetch<LawStatistics>(url, undefined, "");
    },
    staleTime: 60000,
  });
}

export function useRAGFlowStatus() {
  return useQuery({
    queryKey: ["laws", "ragflow-status"],
    queryFn: async () => {
      const url = buildLawLibraryUrl("/kf/laws/ragflow-status");
      return authFetch<RAGFlowStatusResponse>(url, undefined, "");
    },
    staleTime: 30000,
  });
}

// ========== Mutation Hooks ==========

export function useImportLawWithFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (formData: FormData) => {
      const url = buildLawLibraryUrl("/kf/laws/import-with-file");
      return authFormFetch<LawItem>(url, formData, "");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws"] });
    },
  });
}

export function useCreateLaw() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      title: string;
      law_number?: string;
      law_type: LawType;
      status?: string;
      department?: string;
      effective_date?: string;
      update_date?: string;
      content?: string;
      raw_content?: string;
      summary?: string;
      keywords?: string[];
      referred_laws?: string[];
      sector?: string;
      version?: string;
    }) => {
      const url = buildLawLibraryUrl("/kf/laws");
      return authFetch<LawItem>(
        url,
        {
          method: "POST",
          body: JSON.stringify(data),
        },
        ""
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws"] });
    },
  });
}

export function useUpdateLaw() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      lawId,
      data,
    }: {
      lawId: string;
      data: Partial<{
        title: string;
        law_number: string;
        status: string;
        department: string;
        effective_date: string;
        update_date: string;
        content: string;
        summary: string;
        keywords: string[];
        referred_laws: string[];
        sector: string;
      }>;
    }) => {
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}`);
      return authFetch<LawItem>(
        url,
        {
          method: "PUT",
          body: JSON.stringify(data),
        },
        ""
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws"] });
    },
  });
}

export function useDeleteLaw() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (lawId: string) => {
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}`);
      return authFetch<{ message: string }>(url, { method: "DELETE" }, "");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws"] });
    },
  });
}

export function useSyncLaw() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (lawId: string) => {
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}/sync`);
      return authFetch<{ message: string }>(url, { method: "POST" }, "");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws"] });
      void queryClient.invalidateQueries({ queryKey: ["laws", "ragflow-status"] });
    },
  });
}

export function useSyncAllLaws() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (lawType?: LawType) => {
      const url = buildLawLibraryUrl("/kf/laws/sync-all", { law_type: lawType });
      return authFetch<{ message: string }>(url, { method: "POST" }, "");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws"] });
      void queryClient.invalidateQueries({ queryKey: ["laws", "ragflow-status"] });
    },
  });
}

export interface InitRAGFlowResponse {
  created: string[];
  already_exists: string[];
  failed: Array<{ name: string; error: string }>;
}

export function useInitRAGFlow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (lawType?: LawType) => {
      const url = buildLawLibraryUrl("/kf/laws/init-ragflow", { law_type: lawType });
      return authFetch<InitRAGFlowResponse>(url, { method: "POST" }, "");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["laws", "ragflow-status"] });
    },
  });
}

export function useLinkTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      lawId,
      templateId,
      sectionTitle,
    }: {
      lawId: string;
      templateId: string;
      sectionTitle?: string;
    }) => {
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}/templates`);
      return authFetch<{ message: string }>(
        url,
        {
          method: "POST",
          body: JSON.stringify({ template_id: templateId, section_title: sectionTitle }),
        },
        ""
      );
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["laws", "item", variables.lawId],
      });
    },
  });
}

export function useUnlinkTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      lawId,
      templateId,
    }: {
      lawId: string;
      templateId: string;
    }) => {
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}/templates/${templateId}`);
      return authFetch<{ message: string }>(url, { method: "DELETE" }, "");
    },
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["laws", "item", variables.lawId],
      });
    },
  });
}

export function useLawTemplates(lawId: string | null) {
  return useQuery({
    queryKey: ["laws", "templates", lawId],
    queryFn: async () => {
      if (!lawId) return { templates: [], total: 0 };
      const url = buildLawLibraryUrl(`/kf/laws/${lawId}/templates`);
      return authFetch<{ templates: unknown[]; total: number }>(url, undefined, "");
    },
    enabled: !!lawId,
  });
}
