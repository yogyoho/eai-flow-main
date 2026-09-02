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
  limit?: number;
}) {
  return useQuery({
    queryKey: ["gsb-documents", filters],
    queryFn: () => geoSamplesApi.listDocuments(filters),
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

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["gsb-documents"] });
    void qc.invalidateQueries({ queryKey: ["gsb-runs"] });
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
    mutationFn: async ({ id, action }: { id: string; action: "parse" | "redact" }) => {
      if (action === "parse") return geoSamplesApi.parse(id);
      return geoSamplesApi.redact(id);
    },
    onSuccess: invalidate,
  });
}

export function useGsbReview() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: { id: string; decision: "approve" | "reject"; note: string | null }) =>
      geoSamplesApi.review(args.id, { decision: args.decision, note: args.note }),
    onSuccess: invalidate,
  });
}
