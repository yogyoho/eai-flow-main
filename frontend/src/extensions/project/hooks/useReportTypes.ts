"use client";

import { useEffect, useState } from "react";

import { kfApi } from "@/extensions/api";

export interface ReportTypeOption {
  value: string;
  label: string;
}

const COLOR_PALETTE = [
  "border-success/20 bg-success/10 text-success",
  "border-warning/20 bg-warning/10 text-warning",
  "border-primary/20 bg-primary/10 text-primary",
  "border-destructive/20 bg-destructive/10 text-destructive",
  "border-primary/20 bg-primary/10 text-primary",
  "border-info/20 bg-info/10 text-info",
  "border-destructive/20 bg-destructive/10 text-destructive",
  "border-primary/20 bg-primary/10 text-primary",
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
