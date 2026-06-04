import type {
  MyTasksResponse,
  MyProjectsResponse,
  MyStatsResponse,
  MyCalendarResponse,
  NotificationPreference,
  NotificationPreferenceUpdate,
} from "./types";

const BASE = "/api/extensions/dashboard";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
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
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Dashboard API error: ${response.status}`);
  }
  return response.json();
}

async function putApi<T>(path: string, body: unknown): Promise<T> {
  return fetchApi<T>(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
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
  getNotificationPreferences: () => fetchApi<NotificationPreference>(`${BASE}/notification-preferences`),
  updateNotificationPreferences: (data: NotificationPreferenceUpdate) =>
    putApi<NotificationPreference>(`${BASE}/notification-preferences`, data),
};
