import { getToken } from "./auth";
import type { ApiResponse } from "./types";

export class ApiClientError extends Error {
  constructor(
    public status: number,
    public detail: string,
    message: string
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

export async function businessFetch<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const token = getToken();
  const { params, ...fetchOptions } = options;

  const url = new URL(path, baseUrl);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) url.searchParams.set(k, String(v));
    });
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url.toString(), {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse error
    }
    throw new ApiClientError(response.status, detail, detail);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  const data: ApiResponse<T> = await response.json();
  return data.data ?? (data as T);
}
