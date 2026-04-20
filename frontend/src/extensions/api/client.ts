/**
 * API Client with automatic token refresh
 *
 * Features:
 * 1. Automatically adds Authorization header to requests
 * 2. On 401, automatically attempts to refresh using refresh_token
 * 3. After successful refresh, automatically retries the original request
 * 4. On refresh failure, clears tokens and redirects to login page
 */

import type { LoginResponse } from "../types";

const API_BASE = "/api/extensions";

// Token refresh state flag to prevent concurrent refreshes
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

/**
 * Execute token refresh
 */
async function doRefreshToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      return null;
    }

    const data: LoginResponse = await response.json();

    // Update localStorage
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);

    return data.access_token;
  } catch {
    return null;
  }
}

/**
 * Subscribe to token refresh completion event
 */
function subscribeTokenRefresh(callback: (token: string) => void): void {
  refreshSubscribers.push(callback);
}

/**
 * Notify all subscribers that token has been refreshed
 */
function onTokenRefreshed(newToken: string): void {
  refreshSubscribers.forEach((callback) => callback(newToken));
  refreshSubscribers = [];
}

/**
 * Clear tokens and redirect to login page
 */
function clearTokensAndRedirect(): void {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user_id");

  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const redirect = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?redirect=${redirect}`;
  }
}

/**
 * Fetch wrapper with automatic refresh functionality
 */
export async function authFetch<T>(
  url: string,
  options: RequestInit = {},
  baseUrl: string = API_BASE
): Promise<T> {
  const getToken = (): string | null => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("access_token");
    }
    return null;
  };

  const makeRequest = async (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    return fetch(`${baseUrl}${url}`, {
      ...options,
      headers,
    });
  };

  // First request
  let token = getToken();
  let response = await makeRequest(token);

  // If 401, try to refresh token
  if (response.status === 401) {
    if (isRefreshing) {
      // Another request is already refreshing, wait for refresh to complete
      return new Promise((resolve, reject) => {
        subscribeTokenRefresh(async (newToken) => {
          try {
            const retryResponse = await makeRequest(newToken);
            if (!retryResponse.ok) {
              clearTokensAndRedirect();
              reject(new Error("Request failed"));
              return;
            }
            const data = await retryResponse.json();
            resolve(data);
          } catch (error) {
            reject(error);
          }
        });
      });
    }

    isRefreshing = true;

    try {
      const newToken = await doRefreshToken();

      if (newToken) {
        onTokenRefreshed(newToken);
        isRefreshing = false;

        // Retry original request
        const retryResponse = await makeRequest(newToken);

        if (!retryResponse.ok) {
          clearTokensAndRedirect();
          throw new Error("Request failed");
        }

        return await retryResponse.json();
      } else {
        isRefreshing = false;
        clearTokensAndRedirect();
        throw new Error("Token refresh failed");
      }
    } catch (error) {
      isRefreshing = false;
      if ((error as Error).message !== "Token refresh failed") {
        clearTokensAndRedirect();
      }
      throw error;
    }
  }

  if (!response.ok) {
    let message = "Request failed";
    const contentType = response.headers.get("content-type");

    try {
      if (contentType?.includes("application/json")) {
        const error = await response.json();
        message = typeof error.detail === "string"
          ? error.detail
          : Array.isArray(error.detail)
            ? error.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") || message
            : message;
      } else {
        const text = await response.text();
        if (text) message = text.slice(0, 200);
      }
    } catch {
      message = response.statusText || `Error ${response.status}`;
    }

    const err = new Error(message) as Error & { status: number };
    err.status = response.status;
    throw err;
  }

  return await response.json();
}

/**
 * Form data fetch (browser auto-sets Content-Type with boundary)
 */
export async function authFormFetch<T>(
  url: string,
  formData: FormData,
  baseUrl: string = API_BASE
): Promise<T> {
  const token = localStorage.getItem("access_token");

  const makeRequest = async (authToken: string | null): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers["Authorization"] = `Bearer ${authToken}`;
    }

    return fetch(`${baseUrl}${url}`, {
      method: "POST",
      headers,
      body: formData,
    });
  };

  let response = await makeRequest(token);

  // If 401, try to refresh token
  if (response.status === 401) {
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        subscribeTokenRefresh(async (newToken) => {
          try {
            const retryResponse = await makeRequest(newToken);
            if (!retryResponse.ok) {
              clearTokensAndRedirect();
              reject(new Error("Request failed"));
              return;
            }
            const data = await retryResponse.json();
            resolve(data);
          } catch (error) {
            reject(error);
          }
        });
      });
    }

    isRefreshing = true;

    try {
      const newToken = await doRefreshToken();

      if (newToken) {
        onTokenRefreshed(newToken);
        isRefreshing = false;

        const retryResponse = await makeRequest(newToken);

        if (!retryResponse.ok) {
          clearTokensAndRedirect();
          throw new Error("Request failed");
        }

        return await retryResponse.json();
      } else {
        isRefreshing = false;
        clearTokensAndRedirect();
        throw new Error("Token refresh failed");
      }
    } catch (error) {
      isRefreshing = false;
      if ((error as Error).message !== "Token refresh failed") {
        clearTokensAndRedirect();
      }
      throw error;
    }
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = new Error(err.detail || "Request failed") as Error & { status: number };
    error.status = response.status;
    throw error;
  }

  return await response.json();
}

/**
 * Manually trigger token refresh (for external use)
 */
export async function manualRefreshToken(): Promise<boolean> {
  const newToken = await doRefreshToken();
  if (newToken) {
    onTokenRefreshed(newToken);
    return true;
  }
  return false;
}
