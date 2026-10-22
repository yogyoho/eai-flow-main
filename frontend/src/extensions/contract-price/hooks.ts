"use client";

/**
 * TanStack Query hooks for the contract-price-analysis API.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  contractPriceApi,
  libraryApi,
  nameSplitApi,
  ragflowApi,
  termsApi,
} from "./api";

const KEYS = {
  dashboard: ["cpa", "dashboard"] as const,
  documents: (p: Record<string, unknown>) => ["cpa", "documents", p] as const,
  clusters: (p: Record<string, unknown>) => ["cpa", "clusters", p] as const,
  cluster: (id: string) => ["cpa", "cluster", id] as const,
  items: (p: Record<string, unknown>) => ["cpa", "items", p] as const,
  runs: (p: Record<string, unknown>) => ["cpa", "runs", p] as const,
  config: ["cpa", "config"] as const,
  // EAI-CUSTOM: cpa v3 合同文件库
  libraryFolders: ["cpa", "library-folders"] as const,
  libraryFiles: (folderId: string | null) =>
    ["cpa", "library-files", folderId] as const,
  // EAI-CUSTOM: cpa v3 货物分类术语
  terms: ["cpa", "terms"] as const,
  // EAI-CUSTOM: RAGFlow SSO 知识库连通状态
  ragflowStatus: ["cpa", "ragflow-status"] as const,
};

export function useDashboard() {
  return useQuery({
    queryKey: KEYS.dashboard,
    queryFn: contractPriceApi.dashboard,
  });
}

export function useGoodsAnalysis(params: {
  name?: string;
  cluster_id?: string;
  skip?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["cpa", "goods-analysis", params],
    queryFn: () => contractPriceApi.goodsAnalysis(params),
    enabled: [params.name, params.cluster_id].some(Boolean),
  });
}

export function useDocuments(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: KEYS.documents(params),
    queryFn: () => contractPriceApi.listDocuments(params),
  });
}

export function useClusters(
  params: Record<string, unknown> = {},
  options: { enabled?: boolean; staleTime?: number } = {},
) {
  return useQuery({
    queryKey: KEYS.clusters(params),
    queryFn: () => contractPriceApi.listClusters(params),
    // 翻页过渡期保留上一页数据: 否则 key 变化瞬间 data=undefined → total=0 →
    // totalPages=1 → 钳位 effect 误判"尾部清空"把页面弹回第 1 页(bug: 翻到
    // 11 页后回第 1 页)。
    placeholderData: (prev) => prev,
    ...options,
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
  return useQuery({
    queryKey: KEYS.config,
    queryFn: contractPriceApi.getConfig,
  });
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
    mutationFn: ({
      item_id,
      target_cluster_id,
    }: {
      item_id: string;
      target_cluster_id: string;
    }) => contractPriceApi.moveItem(item_id, target_cluster_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
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
    }) => contractPriceApi.confirmCluster(id, { expected_version }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
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
    }) => contractPriceApi.rejectCluster(id, { expected_version }),
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
        clusters.map((c) =>
          contractPriceApi.confirmCluster(c.id, {
            expected_version: c.version,
          }),
        ),
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
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { category?: string; representative_name?: string };
    }) => contractPriceApi.updateCluster(id, body),
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
    }) =>
      contractPriceApi.mergeClusters(
        cluster_ids,
        representative_name,
        category,
      ),
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
    // re_ocr=false 显式声明走 OCR 缓存路径(秒级)。省略参数等效,但绝不能
    // 传空值——`?re_ocr=` 会被 FastAPI 拒以 422。
    mutationFn: (id: string) => contractPriceApi.reparseDocument(id, false),
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
    mutationFn: ({
      id,
      confirm_status,
    }: {
      id: string;
      confirm_status: "confirmed" | "skipped";
    }) => contractPriceApi.confirmDocument(id, confirm_status),
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
    mutationFn: (itemIds: string[]) =>
      contractPriceApi.batchDeleteItems(itemIds),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa"] });
    },
  });
}

export function useBatchValidateItems() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) =>
      contractPriceApi.batchValidateItems(itemIds),
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

// EAI-CUSTOM: cpa v3 合同文件库 hooks
export function useLibraryFolders() {
  return useQuery({
    queryKey: KEYS.libraryFolders,
    queryFn: libraryApi.listFolders,
  });
}

export function useLibraryFiles(folderId: string | null) {
  return useQuery({
    queryKey: KEYS.libraryFiles(folderId),
    queryFn: () => libraryApi.listFiles(folderId),
  });
}

export function useLibraryMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["cpa", "library-folders"] });
    void qc.invalidateQueries({ queryKey: ["cpa", "library-files"] });
    void qc.invalidateQueries({ queryKey: ["cpa", "documents"] }); // 加入解析影响解析列表
  };
  const createFolder = useMutation({
    mutationFn: (p: { name: string; parentId: string | null }) =>
      libraryApi.createFolder(p.name, p.parentId),
    onSuccess: invalidate,
  });
  const updateFolder = useMutation({
    mutationFn: (p: {
      id: string;
      patch: { name?: string; parent_id?: string | null };
    }) => libraryApi.updateFolder(p.id, p.patch),
    onSuccess: invalidate,
  });
  const deleteFolder = useMutation({
    mutationFn: (id: string) => libraryApi.deleteFolder(id),
    onSuccess: invalidate,
  });
  const uploadFiles = useMutation({
    mutationFn: (p: {
      folderId: string | null;
      files: File[];
      ragflowSync?: boolean; // EAI-CUSTOM
    }) => libraryApi.uploadFiles(p.folderId, p.files, p.ragflowSync ?? false),
    onSuccess: invalidate,
  });
  const analyzeFile = useMutation({
    mutationFn: (id: string) => libraryApi.analyzeFile(id),
    onSuccess: invalidate,
  });
  const moveFile = useMutation({
    mutationFn: (p: { id: string; folderId: string | null }) =>
      libraryApi.moveFile(p.id, p.folderId),
    onSuccess: invalidate,
  });
  const deleteFile = useMutation({
    mutationFn: (id: string) => libraryApi.deleteFile(id),
    onSuccess: invalidate,
  });
  return {
    createFolder,
    updateFolder,
    deleteFolder,
    uploadFiles,
    analyzeFile,
    moveFile,
    deleteFile,
  };
}

// EAI-CUSTOM: cpa v3 货物分类术语 hooks
export function useTerms() {
  return useQuery({ queryKey: KEYS.terms, queryFn: termsApi.list });
}

export function useTermsMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["cpa", "terms"] });
  };
  const createTerm = useMutation({
    mutationFn: (p: { canonical: string; aliases: string[] }) =>
      termsApi.create(p.canonical, p.aliases),
    onSuccess: invalidate,
  });
  const updateTerm = useMutation({
    mutationFn: (p: {
      id: string;
      patch: { canonical?: string; aliases?: string[]; enabled?: boolean };
    }) => termsApi.update(p.id, p.patch),
    onSuccess: invalidate,
  });
  const deleteTerm = useMutation({
    mutationFn: (id: string) => termsApi.remove(id),
    onSuccess: invalidate,
  });
  return { createTerm, updateTerm, deleteTerm };
}

// EAI-CUSTOM: RAGFlow SSO 知识库连通状态 + 幂等初始化
export function useContractRagflowStatus() {
  return useQuery({
    queryKey: KEYS.ragflowStatus,
    queryFn: ragflowApi.status,
    // 状态徽标只在进入设置页/主动初始化后刷新,不在窗口聚焦时打扰
    refetchOnWindowFocus: false,
  });
}

export function useInitContractRagflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => ragflowApi.init(),
    onSuccess: (data) => {
      // 先用响应里的 connectivity 即时落缓存（避免 init 完成到 refetch 落地间
      // 徽标闪回未初始化）,再 invalidate 做一次权威重查
      qc.setQueryData(KEYS.ragflowStatus, data.connectivity);
      void qc.invalidateQueries({ queryKey: KEYS.ragflowStatus });
    },
  });
}

// EAI-CUSTOM (决策 B): 分项表手动同步——替换式上传「合同货物分项表格」后
// 重查文档列表（同步不改变行数据,重查仅为幂等兜底）与 RAGFlow 状态徽标
// （分项库 document_count 变化）。
export function useSyncItemsRagflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (docId: string) => ragflowApi.syncItems(docId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cpa", "documents"] });
      void qc.invalidateQueries({ queryKey: KEYS.ragflowStatus });
    },
  });
}

// EAI-CUSTOM: 易混名称区分表 hooks（2026-10-22）
export function useNameSplits() {
  return useQuery({
    queryKey: ["cpa", "name-splits"],
    queryFn: nameSplitApi.list,
  });
}

export function useNameSplitMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["cpa", "name-splits"] });
  };
  const createSplit = useMutation({
    mutationFn: (p: { name_a: string; name_b: string; reason?: string }) =>
      nameSplitApi.create(p.name_a, p.name_b, p.reason),
    onSuccess: invalidate,
  });
  const updateSplit = useMutation({
    mutationFn: (p: {
      id: string;
      patch: { reason?: string; enabled?: boolean };
    }) => nameSplitApi.update(p.id, p.patch),
    onSuccess: invalidate,
  });
  const deleteSplit = useMutation({
    mutationFn: (id: string) => nameSplitApi.remove(id),
    onSuccess: invalidate,
  });
  return { createSplit, updateSplit, deleteSplit };
}
