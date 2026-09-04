/**
 * API Client — uses Gateway Auth HttpOnly cookie (credentials: "include").
 *
 * Auth is handled by the Gateway's cookie-based JWT.  The extensions module
 * no longer manages its own access_token / refresh_token in localStorage.
 */

const API_BASE = "/api/extensions";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = /(?:^|;\s*)csrf_token=([^;]*)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

const CSRF_HEADER = "X-CSRF-Token";
const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "DELETE", "PATCH"]);

function withCsrf(
  headers: Record<string, string>,
  method?: string,
): Record<string, string> {
  if (method && STATE_CHANGING_METHODS.has(method)) {
    const token = getCsrfToken();
    if (token) {
      return { ...headers, [CSRF_HEADER]: token };
    }
  }
  return headers;
}

/**
 * Fetch wrapper that sends the Gateway Auth session cookie and CSRF token.
 */
export async function authFetch<T>(
  url: string,
  options: RequestInit = {},
  baseUrl: string = API_BASE,
): Promise<T> {
  const headers: Record<string, string> = withCsrf(
    {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    },
    options.method,
  );

  const response = await fetch(`${baseUrl}${url}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let message = "Request failed";
    const contentType = response.headers.get("content-type");

    try {
      if (contentType?.includes("application/json")) {
        const error = await response.json();
        // EAI note: 保留原 `join || message` 语义——全部 msg 为空时回退默认 message（`??` 会得到空串）
        const detailMessages: string[] = Array.isArray(error.detail)
          ? error.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean)
          : [];
        message =
          typeof error.detail === "string"
            ? error.detail
            : detailMessages.length > 0
              ? detailMessages.join("; ")
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

  if (
    response.status === 204 ||
    response.headers.get("content-length") === "0"
  ) {
    return undefined as T;
  }

  return await response.json();
}

/**
 * Form-data fetch wrapper — browser auto-sets Content-Type with boundary.
 */
export async function authFormFetch<T>(
  url: string,
  formData: FormData,
  baseUrl: string = API_BASE,
): Promise<T> {
  const response = await fetch(`${baseUrl}${url}`, {
    method: "POST",
    credentials: "include",
    headers: withCsrf({}, "POST"),
    body: formData,
  });

  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    // EAI note: 对齐 authFetch 的数组分支——FastAPI 422 的 detail 是 [{loc,msg,...}] 数组形态，
    // 只按字符串解析会得到 "[object Object]"。仍保留 `||` 语义：detail 为 ""（空 detail 错误体）时回退默认消息。
    const detailMessages: string[] = Array.isArray(errJson.detail)
      ? errJson.detail.map((x: { msg?: string }) => x?.msg).filter(Boolean)
      : [];
    const message =
      typeof errJson.detail === "string" && errJson.detail
        ? errJson.detail
        : detailMessages.length > 0
          ? detailMessages.join("; ")
          : "Request failed";
    const error = new Error(message) as Error & { status: number };
    error.status = response.status;
    throw error;
  }

  return await response.json();
}
