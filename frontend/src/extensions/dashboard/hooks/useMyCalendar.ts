"use client";

import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../api";
import type { CalendarEvent } from "../types";

export function useMyCalendar(start?: string, end?: string) {
  return useQuery({
    queryKey: ["my-calendar", start, end],
    queryFn: () => dashboardApi.getMyCalendar(start, end),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
