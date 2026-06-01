import type {
  MyTasksResponse,
  MyProjectsResponse,
  MyStatsResponse,
  MyCalendarResponse,
} from "./types";

const BASE = "/api/extensions/dashboard";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

async function fetchApi<T>(path: string): Promise<T> {
  const csrf = getCsrfToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  if (csrf) {
    (headers as Record<string, string>)["X-CSRF-Token"] = csrf;
  }

  const baseUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";
  const response = await fetch(`${baseUrl}${path}`, {
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Dashboard API error: ${response.status}`);
  }
  return response.json();
}

export const dashboardApi = {
  getMyTasks: () => fetchApi<MyTasksResponse>(`${BASE}/my-tasks`),
  getMyProjects: () => fetchApi<MyProjectsResponse>(`${BASE}/my-projects`),
  getMyStats: () => fetchApi<MyStatsResponse>(`${BASE}/my-stats`),
  getMyCalendar: (start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const qs = params.toString();
    return fetchApi<MyCalendarResponse>(`${BASE}/my-calendar${qs ? `?${qs}` : ""}`);
  },
};
