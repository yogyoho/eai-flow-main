"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

const ROLE_LABELS: Record<string, string> = {
  manager: "部门负责人",
  director: "分管领导",
  finance: "财务审核",
  employee: "普通员工",
};

export function useUserDirectory() {
  const query = useQuery({
    queryKey: ["meta", "users"],
    queryFn: api.meta.users,
    staleTime: 5 * 60 * 1000,
  });

  const map = useMemo(() => {
    const result: Record<string, { name: string; group: string; roles: string[] }> = {};
    for (const user of query.data || []) {
      result[user.handler] = {
        name: user.name,
        group: user.group,
        roles: user.roles || [],
      };
    }
    return result;
  }, [query.data]);

  return {
    users: query.data || [],
    name: (handler?: string | null) =>
      handler
        ? map[handler]?.name ||
          (handler.startsWith("role:")
            ? ROLE_LABELS[handler.slice(5)] || `角色 · ${handler.slice(5)}`
            : handler)
        : "—",
    group: (handler?: string | null) => (handler ? map[handler]?.group || "" : ""),
    map,
  };
}
