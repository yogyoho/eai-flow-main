"use client";

/**
 * bid-write TanStack Query hooks。
 *
 * Query key 前缀 `["bid-write", …]`；解析/抽取中的任务按 2.5s 轮询，终态停止。
 * `useSelectedWriteTask` 与 bid-review 同款：URL `?task_id=` 优先，否则最新任务。
 * 任务详情/矩阵/缺口均按 owner 隔离由后端保证。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import {
  actTaskApproval,
  createMaterial,
  createTask,
  deleteMaterial,
  exportPrecheck,
  exportTaskRevision,
  generateTask,
  getGaps,
  getMaterialProfile,
  getMatrix,
  getPolicy,
  getRegistry,
  getTask,
  getTaskApproval,
  getTaskMetrics,
  listMaterials,
  listTaskExports,
  listTasks,
  patchMaterial,
  patchMatrixRow,
  putMaterialProfile,
  putPolicy,
  submitTaskApproval,
} from "./api";
import type {
  ApprovalActionInput,
  ApprovalSubmitInput,
  ExportDownload,
  ExportHistoryResponse,
  GenerateKnobs,
  MaterialIn,
  MaterialPatch,
  MatrixResponse,
  MatrixRowOut,
  MatrixRowPatch,
  PolicyBody,
  TaskApprovalResponse,
  WriteTaskOut,
} from "./types";

const ACTIVE_STATUSES = new Set(["created", "parsing", "extracting"]);

export const bidWriteKeys = {
  tasks: ["bid-write", "tasks"] as const,
  task: (taskId: string) => ["bid-write", "task", taskId] as const,
  matrix: (taskId: string) => ["bid-write", "matrix", taskId] as const,
  gaps: (taskId: string) => ["bid-write", "gaps", taskId] as const,
  registry: ["bid-write", "registry"] as const,
  // 批廿五 P1-δ:materials/policy/metrics 面
  materials: (entityType?: string) =>
    ["bid-write", "materials", entityType ?? "all"] as const,
  profile: ["bid-write", "material-profile"] as const,
  policy: ["bid-write", "policy"] as const,
  metrics: (taskId: string) => ["bid-write", "metrics", taskId] as const,
  approval: (taskId: string) => ["bid-write", "approval", taskId] as const,
  exports: (taskId: string) => ["bid-write", "exports", taskId] as const,
};

function latestFirst(tasks: WriteTaskOut[]): WriteTaskOut[] {
  return [...tasks].sort((a, b) => {
    const at = a.created_at ? Date.parse(a.created_at) : 0;
    const bt = b.created_at ? Date.parse(b.created_at) : 0;
    return bt - at;
  });
}

export function useBidWriteTasks() {
  return useQuery({
    queryKey: bidWriteKeys.tasks,
    queryFn: listTasks,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((task) => ACTIVE_STATUSES.has(task.status))
        ? 2500
        : false;
    },
  });
}

export function useBidWriteTask(taskId: string | null) {
  return useQuery({
    queryKey: bidWriteKeys.task(taskId ?? ""),
    queryFn: () => getTask(taskId!),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      const task = query.state.data;
      return task && ACTIVE_STATUSES.has(task.status) ? 2500 : false;
    },
  });
}

export function useBidWriteMatrix(taskId: string | null) {
  return useQuery({
    queryKey: bidWriteKeys.matrix(taskId ?? ""),
    queryFn: () => getMatrix(taskId!),
    enabled: Boolean(taskId),
  });
}

export function useBidWriteGaps(taskId: string | null) {
  return useQuery({
    queryKey: bidWriteKeys.gaps(taskId ?? ""),
    queryFn: () => getGaps(taskId!),
    enabled: Boolean(taskId),
  });
}

export function useBidWriteRegistry() {
  return useQuery({
    queryKey: bidWriteKeys.registry,
    queryFn: getRegistry,
    staleTime: 5 * 60_000,
  });
}

export function useCreateBidWriteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createTask,
    onSuccess: (task) => {
      void qc.invalidateQueries({ queryKey: bidWriteKeys.tasks });
      qc.setQueryData(bidWriteKeys.task(task.id), task);
    },
  });
}

export function usePatchBidWriteMatrixRow(taskId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      clauseId,
      patch,
    }: {
      clauseId: string;
      patch: MatrixRowPatch;
    }) => {
      if (!taskId) throw new Error("未选择写作任务");
      return patchMatrixRow(taskId, clauseId, patch);
    },
    onSuccess: (row: MatrixRowOut) => {
      if (!taskId) return;
      qc.setQueryData<MatrixResponse>(
        bidWriteKeys.matrix(taskId),
        (current) => {
          if (!current) return current;
          return {
            ...current,
            items: current.items.map((item) =>
              item.clause_id === row.clause_id ? row : item,
            ),
          };
        },
      );
      void qc.invalidateQueries({ queryKey: bidWriteKeys.gaps(taskId) });
      void qc.invalidateQueries({ queryKey: bidWriteKeys.tasks });
      void qc.invalidateQueries({ queryKey: bidWriteKeys.task(taskId) });
    },
  });
}

// ── 批廿五 P1-δ:生成/导出/素材/policy/metrics hooks ─────────────────────

export function useGenerateTask(taskId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ knobs }: { knobs: GenerateKnobs }) => {
      if (!taskId) throw new Error("未选择写作任务");
      return generateTask(taskId, knobs);
    },
    onSuccess: () => {
      if (!taskId) return;
      void qc.invalidateQueries({ queryKey: bidWriteKeys.task(taskId) });
      void qc.invalidateQueries({ queryKey: bidWriteKeys.gaps(taskId) });
      void qc.invalidateQueries({ queryKey: bidWriteKeys.metrics(taskId) });
      void qc.invalidateQueries({ queryKey: bidWriteKeys.tasks });
    },
  });
}

/** 导出前置只读重算(零落库);结果走 mutation state,不进缓存。 */
export function useExportPrecheck(taskId: string | null) {
  return useMutation({
    mutationFn: () => {
      if (!taskId) throw new Error("未选择写作任务");
      return exportPrecheck(taskId);
    },
  });
}

export function useMaterials(entityType?: string) {
  return useQuery({
    queryKey: bidWriteKeys.materials(entityType),
    queryFn: () => listMaterials(entityType),
  });
}

export function useCreateMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: MaterialIn) => createMaterial(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["bid-write", "materials"] });
    },
  });
}

export function usePatchMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      materialId,
      patch,
    }: {
      materialId: string;
      patch: MaterialPatch;
    }) => patchMaterial(materialId, patch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["bid-write", "materials"] });
    },
  });
}

export function useDeleteMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (materialId: string) => deleteMaterial(materialId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["bid-write", "materials"] });
    },
  });
}

export function useMaterialProfile() {
  return useQuery({
    queryKey: bidWriteKeys.profile,
    queryFn: getMaterialProfile,
  });
}

export function usePutMaterialProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (profile: Record<string, unknown>) =>
      putMaterialProfile(profile),
    onSuccess: (data) => {
      qc.setQueryData(bidWriteKeys.profile, data);
    },
  });
}

export function usePolicy() {
  return useQuery({
    queryKey: bidWriteKeys.policy,
    queryFn: getPolicy,
  });
}

export function usePutPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PolicyBody) => putPolicy(body),
    onSuccess: (data) => {
      qc.setQueryData(bidWriteKeys.policy, data);
    },
  });
}

export function useTaskMetrics(taskId: string | null) {
  return useQuery({
    queryKey: bidWriteKeys.metrics(taskId ?? ""),
    queryFn: () => getTaskMetrics(taskId!),
    enabled: Boolean(taskId),
  });
}

// ── 批三十二:审批面 ───────────────────────────────────────────────────────

export function useTaskApproval(taskId: string | null) {
  return useQuery({
    queryKey: bidWriteKeys.approval(taskId ?? ""),
    queryFn: () => getTaskApproval(taskId!),
    enabled: Boolean(taskId),
  });
}

function invalidateApprovalSurfaces(qc: ReturnType<typeof useQueryClient>, taskId: string) {
  void qc.invalidateQueries({ queryKey: bidWriteKeys.approval(taskId) });
  void qc.invalidateQueries({ queryKey: ["bid-write", "task", taskId] });
  void qc.invalidateQueries({ queryKey: ["bid-write", "tasks"] });
  void qc.invalidateQueries({ queryKey: ["bid-write", "gaps", taskId] });
}

export function useSubmitTaskApproval(taskId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ApprovalSubmitInput) => {
      if (!taskId) throw new Error("未选择写作任务");
      return submitTaskApproval(taskId, input);
    },
    onSuccess: (data) => {
      if (!taskId) return;
      qc.setQueryData<TaskApprovalResponse>(
        bidWriteKeys.approval(taskId),
        data,
      );
      invalidateApprovalSurfaces(qc, taskId);
    },
  });
}

export function useTaskApprovalAction(taskId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ApprovalActionInput) => {
      if (!taskId) throw new Error("未选择写作任务");
      return actTaskApproval(taskId, input);
    },
    onSuccess: (data) => {
      if (!taskId) return;
      qc.setQueryData<TaskApprovalResponse>(
        bidWriteKeys.approval(taskId),
        data,
      );
      invalidateApprovalSurfaces(qc, taskId);
    },
  });
}

export interface SelectedWriteTask {
  taskId: string | null;
  task: WriteTaskOut | null;
  tasks: WriteTaskOut[];
  isLoading: boolean;
  error: Error | null;
}

/** URL task_id → 最新任务 fallback；零任务时 taskId=null（页面显示空态）。 */
export function useSelectedWriteTask(): SelectedWriteTask {
  const params = useSearchParams();
  const query = useBidWriteTasks();
  const tasks = useMemo(
    () => latestFirst(query.data?.items ?? []),
    [query.data?.items],
  );
  const requestedId = params.get("task_id");
  const direct = useBidWriteTask(requestedId);
  const selected =
    direct.data ??
    (requestedId ? tasks.find((task) => task.id === requestedId) : null) ??
    tasks[0] ??
    null;
  return {
    taskId: selected?.id ?? null,
    task: selected,
    tasks,
    isLoading: query.isLoading,
    error: query.error,
  };
}

export function isActiveWriteStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status);
}

// ── 批三十三:批准修订 DOCX 交付包 ─────────────────────────────────────────

export function useTaskExports(taskId: string | null) {
  return useQuery<ExportHistoryResponse>({
    queryKey: bidWriteKeys.exports(taskId ?? ""),
    queryFn: () => listTaskExports(taskId!),
    enabled: Boolean(taskId),
  });
}

export function useExportRevision(taskId: string | null) {
  const qc = useQueryClient();
  return useMutation<ExportDownload, Error, string>({
    mutationFn: (revisionId: string) => {
      if (!taskId) throw new Error("未选择写作任务");
      return exportTaskRevision(taskId, revisionId);
    },
    onSuccess: () => {
      if (!taskId) return;
      void qc.invalidateQueries({ queryKey: bidWriteKeys.exports(taskId) });
    },
  });
}
