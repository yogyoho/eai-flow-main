import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../api";

export function useMyProjects() {
  return useQuery({
    queryKey: ["dashboard", "my-projects"],
    queryFn: dashboardApi.getMyProjects,
    staleTime: 60_000,
  });
}
