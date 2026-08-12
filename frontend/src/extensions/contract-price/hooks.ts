"use client";

/**
 * TanStack Query hooks for the contract-price-analysis API.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { contractPriceApi } from "./api";

const KEYS = {
  dashboard: ["cpa", "dashboard"] as const,
  documents: (p: Record<string, unknown>) => ["cpa", "documents", p] as const,
  clusters: (p: Record<string, unknown>) => ["cpa", "clusters", p] as const,
  cluster: (id: string) => ["cpa", "cluster", id] as const,
  items: (p: Record<string, unknown>) => ["cpa", "items", p] as const,
  runs: (p: Record<string, unknown>) => ["cpa", "runs", p] as const,
  config: ["cpa", "config"] as const,
};

export function useDashboard() {
  return useQuery({ queryKey: KEYS.dashboard, queryFn: contractPriceApi.dashboard });
}

export function useGoodsAnalysis(params: { name?: string; cluster_id?: string; skip?: number; limit?: number }) {
  return useQuery({
    queryKey: ["cpa", "goods-analysis", params],
    queryFn: () => contractPriceApi.goodsAnalysis(params),
    enabled: !!(params.name || params.cluster_id),
  });
}

export function useDocuments(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.documents(params),
    queryFn: () => contractPriceApi.listDocuments(params),
  });
}

export function useClusters(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.clusters(params),
    queryFn: () => contractPriceApi.listClusters(params),
  });
}

export function useCluster(id: string | null) {
  return useQuery({
    queryKey: KEYS.cluster(id ?? ""),
    queryFn: () => contractPriceApi.getCluster(id!),
    enabled: !!id,
  });
}

export function useItems(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.items(params),
    queryFn: () => contractPriceApi.listItems(params),
  });
}

export function useItemContracts() {
  return useQuery({
    queryKey: ["cpa", "item-contracts"] as const,
    queryFn: () => contractPriceApi.listItemContracts(),
  });
}

export function useRuns(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.runs(params),
    queryFn: () => contractPriceApi.listRuns(params),
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => contractPriceApi.deleteRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa", "runs"] });
    },
  });
}

export function useConfig() {
  return useQuery({ queryKey: KEYS.config, queryFn: contractPriceApi.getConfig });
}

export function useRunPipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ mode, trigger }: { mode?: string; trigger?: string }) =>
      contractPriceApi.runPipeline(mode, trigger),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useMoveItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ item_id, target_cluster_id }: { item_id: string; target_cluster_id: string }) =>
      contractPriceApi.moveItem(item_id, target_cluster_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useConfirmCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, expected_version }: { id: string; expected_version?: number }) =>
      contractPriceApi.confirmCluster(id, { expected_version }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useRejectCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, expected_version }: { id: string; expected_version?: number }) =>
      contractPriceApi.rejectCluster(id, { expected_version }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
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
        clusters.map((c) => contractPriceApi.confirmCluster(c.id, { expected_version: c.version })),
      );
      const fail = results.filter((r) => r.status === "rejected").length;
      return { ok: results.length - fail, fail, total: results.length };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useUpdateCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { category?: string; representative_name?: string } }) =>
      contractPriceApi.updateCluster(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
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
    }) => contractPriceApi.mergeClusters(cluster_ids, representative_name, category),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useUpdateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      contractPriceApi.updateItem(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: contractPriceApi.updateConfig,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEYS.config });
    },
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => contractPriceApi.uploadDocument(file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useReparseDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => contractPriceApi.reparseDocument(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useUpdateDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      contractPriceApi.updateDocument(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useConfirmDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, confirm_status }: { id: string; confirm_status: "confirmed" | "skipped" }) =>
      contractPriceApi.confirmDocument(id, confirm_status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useConfirmAllDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (confirm_status: "confirmed" | "skipped") =>
      contractPriceApi.confirmAllDocuments(confirm_status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => contractPriceApi.deleteItem(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useBatchDeleteItems() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) => contractPriceApi.batchDeleteItems(itemIds),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useBatchValidateItems() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) => contractPriceApi.batchValidateItems(itemIds),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useDeleteItemsByRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => contractPriceApi.deleteItemsByRun(runId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useRunCluster() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ mode, trigger }: { mode?: string; trigger?: string }) =>
      contractPriceApi.runCluster(mode, trigger),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}
