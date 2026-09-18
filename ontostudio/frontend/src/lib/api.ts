/**
 * OntoStudio 独立前端 API Client (S2 Task 1, EAI-CUSTOM).
 *
 * 自 frontend/src/extensions/api/client.ts 移植（错误语义逐行对齐）：
 * - credentials:"include" 带 Gateway 会话 cookie；
 * - POST/PUT/DELETE/PATCH 自动附 X-CSRF-Token（Double Submit Cookie，
 *   merge/unmerge 等 mutation 需要）；
 * - 非 OK 解析 detail（string 或 FastAPI 422 的 [{msg}] 数组）抛带 status 的 Error。
 *
 * 与主系统的差异仅在 BASE：独立后端经 dev proxy / nginx 走 /api/ontostudio
 * 前缀（rewrite → /api/extensions），见 vite.config.ts / deploy nginx S1-T3。
 */

const API_BASE = "/api/ontostudio/api/extensions";

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
        // 保留主系统 `join || message` 语义——全部 msg 为空时回退默认 message（`??` 会得到空串）
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
