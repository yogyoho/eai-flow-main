"use client";

import { useContext } from "react";
import { PermissionContext } from "./PermissionProvider";

export interface PermissionState {
  permissions: string[];
  nav: string[];
  pages: string[];
  identity: {
    user_id: string;
    username: string;
    role_code: string | null;
    role_level: number;
    dept_id: string | null;
    dept_ids: string[];
    member_projects: string[];
    project_roles: Record<string, string>;
    tags: string[];
    labels: Record<string, string>;
  };
  isLoading: boolean;
  error: string | null;
}

export function usePermission() {
  const ctx = useContext(PermissionContext);
  if (!ctx) {
    throw new Error("usePermission must be used within a PermissionProvider");
  }

  const { permissions, nav, pages, identity, isLoading } = ctx;

  const can = (permission: string): boolean => {
    if (isLoading) return false;
    // Superadmin wildcard
    if (permissions.includes("*")) return true;
    // Exact match
    if (permissions.includes(permission)) return true;
    // Module wildcard: "kb:*" matches "kb:create", "kb:read", etc.
    const prefix = permission.split(":")[0];
    if (permissions.includes(`${prefix}:*`)) return true;
    return false;
  };

  const hasAll = (...perms: string[]): boolean => perms.every(can);

  const hasAny = (...perms: string[]): boolean => perms.some(can);

  const canNav = (navId: string): boolean => {
    if (isLoading) return false;
    if (nav.includes("*")) return true;
    return nav.includes(navId);
  };

  const canPage = (pageId: string): boolean => {
    if (isLoading) return false;
    if (pages.includes("*")) return true;
    return pages.includes(pageId);
  };

  return {
    can,
    hasAll,
    hasAny,
    canNav,
    canPage,
    permissions,
    identity,
    isLoading,
  };
}
