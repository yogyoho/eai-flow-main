import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../api";

export function useMyTasks() {
  return useQuery({
    queryKey: ["dashboard", "my-tasks"],
    queryFn: dashboardApi.getMyTasks,
    staleTime: 30_000,
  });
}
