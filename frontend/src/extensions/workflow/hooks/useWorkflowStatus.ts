"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { workflowApi } from "../api";
import type { WorkflowStatusResponse } from "../types";

export function useWorkflowStatus(projectId: string | null, pollIntervalMs = 5000) {
  const [status, setStatus] = useState<WorkflowStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await workflowApi.getWorkflowStatus(projectId);
      setStatus(data);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();

    if (projectId) {
      intervalRef.current = setInterval(refresh, pollIntervalMs);
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [refresh, pollIntervalMs, projectId]);

  return { status, loading, refresh };
}
