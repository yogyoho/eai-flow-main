"use client";

/**
 * TanStack Query hooks for the geo-sample-bank API.
 */

// EAI-CUSTOM: forked from extensions/contract-price/hooks.ts (geo-sample-bank Phase 1, spec 2026-09-01).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { geoSamplesApi } from "./api";

export function useGsbDocuments(filters: {
  stage?: string;
  mineral?: string;
  status?: string;
  skip?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["gsb-documents", filters],
    queryFn: () => geoSamplesApi.listDocuments(filters),
    placeholderData: (prev) => prev, // 翻页/筛选切换保留上一份数据,不闪「加载中…」(TanStack v5)
    refetchInterval: 5000, // 后台 parse/redact 进行中时表格自刷新
  });
}

export function useGsbRedactions(documentId: string | null) {
  return useQuery({
    queryKey: ["gsb-redactions", documentId],
    queryFn: () => geoSamplesApi.listRedactions(documentId!),
    enabled: documentId != null,
  });
}

export function useGsbRuns() {
  return useQuery({
    queryKey: ["gsb-runs"],
    queryFn: () => geoSamplesApi.listRuns(),
    refetchInterval: 5000,
  });
}

// ore_pack 孵化草稿清单（P5 T6）：抽取为后台任务，5 秒轮询让新草稿自动出现。
export function useGsbDrafts(params?: {
  mineral?: string;
  review_status?: string;
}) {
  return useQuery({
    queryKey: ["gsb-ore-pack-drafts", params],
    queryFn: () => geoSamplesApi.listDrafts(params),
    refetchInterval: 5000,
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["gsb-documents"] });
    void qc.invalidateQueries({ queryKey: ["gsb-runs"] });
    void qc.invalidateQueries({ queryKey: ["gsb-ore-pack-drafts"] });
  };
}

export function useGsbUpload() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (form: FormData) => geoSamplesApi.uploadDocument(form),
    onSuccess: invalidate,
  });
}

export function useGsbAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async ({
      id,
      action,
    }: {
      id: string;
      action: "parse" | "redact";
    }) => {
      if (action === "parse") return geoSamplesApi.parse(id);
      return geoSamplesApi.redact(id);
    },
    onSuccess: invalidate,
  });
}

export function useGsbReview() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: {
      id: string;
      decision: "approve" | "reject";
      note: string | null;
    }) =>
      geoSamplesApi.review(args.id, {
        decision: args.decision,
        note: args.note,
      }),
    onSuccess: invalidate,
  });
}

export function useGsbDelete() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => geoSamplesApi.deleteDocument(id),
    onSuccess: invalidate,
  });
}

// 草稿审阅（approve/reject 二合一，T6 DraftsView 消费）。
export function useGsbDraftReview() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: async ({
      id,
      action,
      note,
    }: {
      id: string;
      action: "approve" | "reject";
      note: string | null;
    }) => {
      if (action === "approve") return geoSamplesApi.approveDraft(id, note);
      return geoSamplesApi.rejectDraft(id, note);
    },
    onSuccess: invalidate,
  });
}
