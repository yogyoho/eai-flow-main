"use client";

import React, { createContext, useEffect, useState, useCallback } from "react";
import type { PermissionState } from "./usePermission";

interface PermissionContextValue extends PermissionState {
  refresh: () => Promise<void>;
}

export const PermissionContext = createContext<PermissionContextValue | null>(null);

export function PermissionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<PermissionState>({
    permissions: [],
    identity: {
      user_id: "",
      username: "",
      role_code: null,
      role_level: 0,
      dept_id: null,
      dept_ids: [],
      member_projects: [],
      project_roles: {},
      tags: [],
      labels: {},
    },
    isLoading: true,
    error: null,
  });

  const fetchPermissions = useCallback(async () => {
    try {
      const res = await fetch("/api/permissions/me", { credentials: "include" });
      if (!res.ok) {
        // Non-admin users may get 403 — degrade gracefully
        setState((s) => ({ ...s, isLoading: false, permissions: [], error: null }));
        return;
      }
      const data = await res.json();
      setState({
        permissions: data.permissions || [],
        identity: data.identity || {
          user_id: "", username: "", role_code: null, role_level: 0,
          dept_id: null, dept_ids: [], member_projects: [],
          project_roles: {}, tags: [], labels: {},
        },
        isLoading: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to load permissions",
      }));
    }
  }, []);

  useEffect(() => {
    fetchPermissions();
  }, [fetchPermissions]);

  return (
    <PermissionContext.Provider value={{ ...state, refresh: fetchPermissions }}>
      {children}
    </PermissionContext.Provider>
  );
}
