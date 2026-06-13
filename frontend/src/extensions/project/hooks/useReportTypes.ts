"use client";

import { useEffect, useState } from "react";
import { kfApi } from "@/extensions/api";

export interface ReportTypeOption {
  value: string;
  label: string;
}

const COLOR_PALETTE = [
  "border-green-500/20 bg-green-500/10 text-green-600",
  "border-amber-500/20 bg-amber-500/10 text-amber-600",
  "border-blue-500/20 bg-blue-500/10 text-blue-600",
  "border-red-500/20 bg-red-500/10 text-red-600",
  "border-purple-500/20 bg-purple-500/10 text-purple-600",
  "border-teal-500/20 bg-teal-500/10 text-teal-600",
  "border-pink-500/20 bg-pink-500/10 text-pink-600",
  "border-indigo-500/20 bg-indigo-500/10 text-indigo-600",
] as const;

// ── Module-level cache ──

let _cachedOptions: ReportTypeOption[] | null = null;
let _pendingPromise: Promise<ReportTypeOption[]> | null = null;

function fetchReportTypes(): Promise<ReportTypeOption[]> {
  if (_cachedOptions) return Promise.resolve(_cachedOptions);
  if (_pendingPromise) return _pendingPromise;

  _pendingPromise = kfApi
    .listDictItems("report_type", { limit: 200 })
    .then((res) => {
      _cachedOptions = res.items
        .filter((i) => i.enabled)
        .map((i) => ({ value: i.id, label: i.label }));
      return _cachedOptions;
    })
    .catch(() => {
      _cachedOptions = [];
      return _cachedOptions;
    })
    .finally(() => {
      _pendingPromise = null;
    });

  return _pendingPromise;
}

// ── Hook ──

export function useReportTypes(): {
  options: ReportTypeOption[];
  labelMap: Record<string, string>;
  loading: boolean;
} {
  const [options, setOptions] = useState<ReportTypeOption[]>(_cachedOptions ?? []);
  const [loading, setLoading] = useState(!_cachedOptions);

  useEffect(() => {
    if (_cachedOptions) {
      setOptions(_cachedOptions);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchReportTypes().then((data) => {
      if (!cancelled) {
        setOptions(data);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const labelMap: Record<string, string> = {};
  for (const opt of options) {
    labelMap[opt.value] = opt.label;
  }

  return { options, labelMap, loading };
}

// ── Synchronous helpers (require hook to have loaded first) ──

export function getReportTypeLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const opt = _cachedOptions?.find((o) => o.value === value);
  return opt?.label ?? value;
}

export function getReportTypeColor(value: string | null | undefined): string {
  if (!value) return COLOR_PALETTE[0];
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = ((hash << 5) - hash) + value.charCodeAt(i);
    hash |= 0;
  }
  return COLOR_PALETTE[Math.abs(hash) % COLOR_PALETTE.length];
}

export function getReportTypeIcon(label: string | null | undefined): string {
  if (!label) return "?";
  return label.charAt(0);
}
