// frontend/src/extensions/license/useLicense.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { getLicenseStatus, type LicenseStatus } from "./api";

export function useLicense() {
  const { data, isLoading, error } = useQuery<LicenseStatus>({
    queryKey: ["license", "status"],
    queryFn: getLicenseStatus,
    refetchInterval: 5 * 60 * 1000,
    staleTime: 60 * 1000,
    retry: 2,
  });

  return {
    /** Raw license status data */
    status: data,
    /** Is license data still loading? */
    isLoading,
    /** Did the status fetch fail? */
    isError: !!error,
    /** Developer mode is active */
    isDevMode: data?.is_dev_mode ?? false,
    /** License is valid */
    isValid: data?.valid ?? false,
    /** System is in grace period (no license yet, countdown active) */
    inGracePeriod: data?.in_grace_period ?? false,
    /** System is fully locked (grace period expired, no valid license) */
    isLocked: !data?.valid && !data?.in_grace_period,
    /** Check if a specific module is available */
    hasModule: (name: string): boolean => {
      if (!data) return false;
      if (data.in_grace_period) return true;
      return data.valid && (data.modules[name] ?? false);
    },
    /** Active warnings */
    warnings: data?.warnings ?? [],
    /** Days remaining in grace period */
    gracePeriodDays: data?.grace_period_remaining_days ?? 0,
  };
}
