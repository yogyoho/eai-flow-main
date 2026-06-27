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

export function useRuns(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.runs(params),
    queryFn: () => contractPriceApi.listRuns(params),
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
