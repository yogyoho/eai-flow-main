import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../api";

export function useMyStats() {
  return useQuery({
    queryKey: ["dashboard", "my-stats"],
    queryFn: dashboardApi.getMyStats,
    staleTime: 60_000,
  });
}
