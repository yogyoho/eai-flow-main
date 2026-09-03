/**
 * API client for the geo-sample-bank management API.
 *
 * Endpoints live under `/api/extensions/geo-samples/*` (mounted in the
 * Gateway). `authFetch`'s default base is `/api/extensions`, so we pass the
 * `/geo-samples/...` suffix.
 */

// EAI-CUSTOM: forked from extensions/contract-price/api.ts (geo-sample-bank Phase 1, spec 2026-09-01).
import { authFetch, authFormFetch } from "@/extensions/api/client";

import type { GsbDocument, GsbRedaction, GsbRun } from "./types";

const API_BASE = "/geo-samples";

/** Build a query string, skipping empty/null/undefined values. */
export function qs(
  params?: Record<string, string | number | boolean | null | undefined>,
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const geoSamplesApi = {
  // Functional area 1: documents
  listDocuments: (params?: {
    stage?: string;
    mineral?: string;
    status?: string;
    skip?: number;
    limit?: number;
  }) =>
    authFetch<{
      items: GsbDocument[];
      skip: number;
      limit: number;
      total: number;
    }>(`${API_BASE}/documents${qs(params)}`),

  getDocument: (id: string) =>
    authFetch<GsbDocument>(`${API_BASE}/documents/${id}`),

  uploadDocument: (form: FormData) =>
    authFormFetch<{ document: GsbDocument; run_id: string }>(
      `${API_BASE}/documents/upload`,
      form,
    ),

  deleteDocument: (id: string) =>
    authFetch<{ deleted: boolean; report_id: string }>(
      `${API_BASE}/documents/${id}`,
      { method: "DELETE" },
    ),

  // Functional area 2: parse / redact pipeline
  parse: (id: string) =>
    authFetch<{ run_id: string }>(`${API_BASE}/documents/${id}/parse`, {
      method: "POST",
    }),

  redact: (id: string) =>
    authFetch<{ run_id: string }>(`${API_BASE}/documents/${id}/redact`, {
      method: "POST",
    }),

  // Functional area 3: review
  review: (
    id: string,
    body: { decision: "approve" | "reject"; note: string | null },
  ) =>
    authFetch<GsbDocument>(`${API_BASE}/documents/${id}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listRedactions: (id: string) =>
    authFetch<{ items: GsbRedaction[] }>(
      `${API_BASE}/documents/${id}/redactions`,
    ),

  // Functional area 4: tasks
  listRuns: () => authFetch<{ items: GsbRun[] }>(`${API_BASE}/runs`),
};
