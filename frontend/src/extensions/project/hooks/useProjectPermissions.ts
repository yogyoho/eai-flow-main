import { useQuery } from "@tanstack/react-query";

import { projectApi } from "../api";
import { getDefaultTab, getVisibleTabs } from "../tabRegistry";
import type { TabConfig } from "../tabRegistry";

export function useProjectPermissions(projectId: string, stage: number) {
  const { data, isLoading } = useQuery({
    queryKey: ["project-permissions", projectId],
    queryFn: () => projectApi.getMyPermissions(projectId),
    staleTime: 5 * 60 * 1000,
    enabled: !!projectId,
  });

  const permissions = data?.permissions ?? [];
  const role = data?.role ?? null;
  const can = (action: string) => permissions.includes(action);

  const visibleTabs: TabConfig[] = getVisibleTabs(stage, permissions, role);
  const defaultTab = getDefaultTab(stage, permissions, role);

  return {
    role,
    permissions,
    can,
    defaultTab,
    visibleTabs,
    isLoading,
  };
}
