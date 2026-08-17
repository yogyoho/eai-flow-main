"use client";

/**
 * TanStack Query hooks for the spare-parts-analysis API.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sparePartsApi } from "./api";

const KEYS = {
  dashboard: ["csp", "dashboard"] as const,
  documents: (p: Record<string, unknown>) => ["csp", "documents", p] as const,
  clusters: (p: Record<string, unknown>) => ["csp", "clusters", p] as const,
  cluster: (id: string) => ["csp", "cluster", id] as const,
  items: (p: Record<string, unknown>) => ["csp", "items", p] as const,
  runs: (p: Record<string, unknown>) => ["csp", "runs", p] as const,
  config: ["csp", "config"] as const,
};

export function useDashboard() {
  return useQuery({
    queryKey: KEYS.dashboard,
    queryFn: sparePartsApi.dashboard,
  });
}

export function usePartAnalysis(params: {
  name?: string;
  cluster_id?: string;
  skip?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["csp", "goods-analysis", params],
    queryFn: () => sparePartsApi.partsAnalysis(params),
    enabled: !!(params.name ?? params.cluster_id),
  });
}

export function useDocuments(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.documents(params),
    queryFn: () => sparePartsApi.listDocuments(params),
  });
}

export function useClusters(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.clusters(params),
    queryFn: () => sparePartsApi.listClusters(params),
  });
}

export function useCluster(id: string | null) {
  return useQuery({
    queryKey: KEYS.cluster(id ?? ""),
    queryFn: () => sparePartsApi.getCluster(id!),
    enabled: !!id,
  });
}

export function useItems(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.items(params),
    queryFn: () => sparePartsApi.listItems(params),
  });
}

export function useItemContracts() {
  return useQuery({
    queryKey: ["csp", "item-contracts"] as const,
    queryFn: () => sparePartsApi.listItemContracts(),
  });
}

export function useRuns(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.runs(params),
    queryFn: () => sparePartsApi.listRuns(params),
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => sparePartsApi.deleteRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp", "runs"] });
    },
  });
}

export function useConfig() {
  return useQuery({ queryKey: KEYS.config, queryFn: sparePartsApi.getConfig });
}

export function useRunPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ mode, trigger }: { mode?: string; trigger?: string }) =>
      sparePartsApi.runPipeline(mode, trigger),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useMoveItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      item_id,
      target_cluster_id,
    }: {
      item_id: string;
      target_cluster_id: string;
    }) => sparePartsApi.moveItem(item_id, target_cluster_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useConfirmCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      expected_version,
    }: {
      id: string;
      expected_version?: number;
    }) => sparePartsApi.confirmCluster(id, { expected_version }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useRejectCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      expected_version,
    }: {
      id: string;
      expected_version?: number;
    }) => sparePartsApi.rejectCluster(id, { expected_version }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useBatchConfirmClusters() {
  const qc = useQueryClient();
  return useMutation({
    // ponytail: loop the existing single-confirm (version-locked) instead of a
    // new backend batch endpoint. allSettled so one version clash fails that row
    // alone and the rest still confirm.
    mutationFn: async (clusters: { id: string; version: number }[]) => {
      const results = await Promise.allSettled(
        clusters.map((c) =>
          sparePartsApi.confirmCluster(c.id, { expected_version: c.version }),
        ),
      );
      const fail = results.filter((r) => r.status === "rejected").length;
      return { ok: results.length - fail, fail, total: results.length };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useUpdateCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { category?: string; representative_name?: string };
    }) => sparePartsApi.updateCluster(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useMergeClusters() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      cluster_ids,
      representative_name,
      category,
    }: {
      cluster_ids: string[];
      representative_name: string;
      category?: string;
    }) =>
      sparePartsApi.mergeClusters(cluster_ids, representative_name, category),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useUpdateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      sparePartsApi.updateItem(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: sparePartsApi.updateConfig,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEYS.config });
    },
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => sparePartsApi.uploadDocument(file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useReparseDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sparePartsApi.reparseDocument(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useUpdateDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      sparePartsApi.updateDocument(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useConfirmDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      confirm_status,
    }: {
      id: string;
      confirm_status: "confirmed" | "skipped";
    }) => sparePartsApi.confirmDocument(id, confirm_status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useConfirmAllDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (confirm_status: "confirmed" | "skipped") =>
      sparePartsApi.confirmAllDocuments(confirm_status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sparePartsApi.deleteItem(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useBatchDeleteItems() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) => sparePartsApi.batchDeleteItems(itemIds),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useBatchValidateItems() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) =>
      sparePartsApi.batchValidateItems(itemIds),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useDeleteItemsByRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => sparePartsApi.deleteItemsByRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

export function useRunCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ mode, trigger }: { mode?: string; trigger?: string }) =>
      sparePartsApi.runCluster(mode, trigger),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp"] });
    },
  });
}

// --- 客户维度 (D3: master/alias 归并) ---

export function useCustomers(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: ["csp", "customers", params] as const,
    queryFn: () => sparePartsApi.listCustomers(params),
  });
}

export function useItemCustomers() {
  return useQuery({
    queryKey: ["csp", "item-customers"] as const,
    queryFn: () => sparePartsApi.listItemCustomers(),
  });
}

export function useCreateCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: sparePartsApi.createCustomer,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp", "customers"] });
    },
  });
}

export function useUpdateCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { canonical_name?: string; aliases?: string[] };
    }) => sparePartsApi.updateCustomer(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp", "customers"] });
    },
  });
}

export function useClaimCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, raw_name }: { id: string; raw_name: string }) =>
      sparePartsApi.claimCustomer(id, raw_name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp", "customers"] });
    },
  });
}

export function useMergeCustomers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      source_ids,
      target_id,
    }: {
      source_ids: string[];
      target_id: string;
    }) => sparePartsApi.mergeCustomers(source_ids, target_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp", "customers"] });
    },
  });
}

export function useResolveCustomers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (raw_names: string[]) =>
      sparePartsApi.resolveCustomers(raw_names),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["csp", "customers"] });
    },
  });
}
