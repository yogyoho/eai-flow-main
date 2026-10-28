import type {
  DefJson,
  Definition,
  AuthMe,
  DemoUser,
  Enums,
  FormDefinition,
  HandlerOption,
  HisTask,
  InstanceDetail,
  InstanceWire,
  LoadTaskResponse,
  Page,
  Stats,
  Task,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_WORKFLOW_API?.replace(/\/$/, "") ||
  "http://127.0.0.1:8020/api/workflow";

export interface ApiIdentity {
  id: string;
  roles: string;
  dept: string;
  tenant: string;
}

let identity: ApiIdentity = {
  id: "u1001",
  roles: "manager",
  dept: "d01",
  tenant: "000000",
};

export function setApiIdentity(next: ApiIdentity) {
  identity = next;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let redirectingToLogin = false;

// Same-origin deployments serve the API under /workflow/api behind nginx, so a
// 401 means the EAI session is missing/expired: bounce to the EAI login page
// and come back to the exact deep link after signing in. Local development
// points API_BASE at an absolute 127.0.0.1:8020 URL with no /login route, so
// it keeps the normal error states instead of navigating away.
function redirectToEaiLogin(): void {
  if (redirectingToLogin || typeof window === "undefined") return;
  redirectingToLogin = true;
  const target = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  window.location.replace(`/login?redirect=${encodeURIComponent(target)}`);
}

function headers(extra?: HeadersInit): HeadersInit {
  // HTTP header values must stay ASCII: only ids/roles are sent, never display names.
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-User-Id": identity.id,
    "X-User-Roles": identity.roles,
    "X-User-Dept": identity.dept,
    "X-Tenant-Id": identity.tenant,
    ...(extra || {}),
  };
}

function errorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === "object" && item && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : String(item),
      )
      .join("；");
  }
  if (detail && typeof detail === "object" && "msg" in detail) {
    return String((detail as { msg: unknown }).msg);
  }
  return fallback;
}

export async function request<T>(
  path: string,
  init: RequestInit & { query?: Record<string, unknown> } = {},
): Promise<T> {
  const { query, ...rest } = init;
  // In Docker the API is same-origin under /workflow/api; the browser resolves
  // that relative base. Local development keeps an absolute 127.0.0.1:8020 URL.
  const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  const url = new URL(`${API_BASE}${path}`, origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const response = await fetch(url.toString(), {
    ...rest,
    headers: headers(rest.headers),
    cache: "no-store",
    credentials: "include",
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    if (response.status === 401 && API_BASE.startsWith("/")) {
      redirectToEaiLogin();
    }
    throw new ApiError(errorMessage(payload, `请求失败（${response.status}）`), response.status);
  }
  return payload as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<{ status: string }>("/health"),

  meta: {
    me: () => request<AuthMe>("/meta/me"),
    enums: () => request<Enums>("/meta/enums"),
    users: () => request<DemoUser[]>("/meta/users"),
    handlers: () => request<HandlerOption[]>("/meta/handlers"),
    stats: () => request<Stats>("/meta/stats"),
    statusLabels: () => request<Record<string, string>>("/status-labels"),
  },

  definitions: {
    list: (query: {
      page?: number;
      size?: number;
      flowCode?: string;
      flowName?: string;
      category?: string;
      isPublish?: number;
    }) => request<Page<Definition>>("/definitions", { query }),
    get: (id: number) => request<Definition>(`/definitions/${id}`),
    create: (body: {
      flow_code: string;
      flow_name: string;
      category?: string | null;
    }) =>
      request<Definition>("/definitions", { method: "POST", body: JSON.stringify(body) }),
    update: (id: number, body: Record<string, unknown>) =>
      request<Definition>(`/definitions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (id: number) => request<void>(`/definitions/${id}`, { method: "DELETE" }),
    publish: (id: number) => request<Definition>(`/definitions/${id}/publish`, { method: "POST" }),
    unpublish: (id: number) =>
      request<Definition>(`/definitions/${id}/unpublish`, { method: "POST" }),
    copy: (id: number) => request<Definition>(`/definitions/${id}/copy`, { method: "POST" }),
    activate: (id: number) =>
      request<Definition>(`/definitions/${id}/activate`, { method: "POST" }),
    suspend: (id: number) => request<Definition>(`/definitions/${id}/suspend`, { method: "POST" }),
    exportJson: (id: number) => request<DefJson>(`/definitions/${id}/export`),
    importJson: (payload: unknown) =>
      request<Definition>("/definitions/import", {
        method: "POST",
        body: JSON.stringify({ payload }),
      }),
  },

  designer: {
    query: (id: number | "new") =>
      id === "new"
        ? request<DefJson>("/designer/query-def")
        : request<DefJson>(`/designer/query-def/${id}`),
    save: (defJson: DefJson) =>
      request<{ code: number; msg: string; data: DefJson }>("/designer/save-json", {
        method: "POST",
        body: JSON.stringify({ defJson }),
      }),
    chart: (instanceId: number) =>
      request<DefJson>(`/designer/query-flow-chart/${instanceId}`),
    publishedForms: () => request<FormDefinition[]>("/designer/published-form"),
    handlerDict: () =>
      request<{ label: string; value: string }[]>("/designer/handler-dict"),
    handlerResult: (type?: string, keyword?: string) =>
      request<{
        handlerAuths: { rows: HandlerOption[]; total: number; page: number; size: number };
      }>("/designer/handler-result", { query: { type, keyword } }),
    loadTask: (taskId: number) => request<LoadTaskResponse>(`/designer/execute/load/${taskId}`),
    loadHis: (hisId: number) => request<LoadTaskResponse>(`/designer/execute/hisLoad/${hisId}`),
    handle: (
      taskId: number,
      options: { message?: string; skipType?: string; nodeCode?: string },
      variables: Record<string, unknown>,
    ) =>
      request<InstanceWire>("/designer/execute/handle", {
        method: "POST",
        query: {
          taskId,
          skipType: options.skipType || "PASS",
          message: options.message || "",
          nodeCode: options.nodeCode,
        },
        body: JSON.stringify(variables),
      }),
  },

  instances: {
    list: (query: {
      page?: number;
      size?: number;
      definitionId?: number;
      businessId?: string;
      flowStatus?: string;
    }) => request<Page<InstanceWire>>("/instances", { query }),
    get: (id: number) => request<InstanceDetail>(`/instances/${id}`),
    start: (body: {
      flow_code: string;
      business_id: string;
      variables: Record<string, unknown>;
      handler?: string;
    }) => request<InstanceWire>("/instances", { method: "POST", body: JSON.stringify(body) }),
    revoke: (id: number, message: string) =>
      request<InstanceWire>(`/instances/${id}/revoke`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    terminate: (id: number, message: string) =>
      request<InstanceWire>(`/instances/${id}/terminate`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
  },

  tasks: {
    list: (query: { page?: number; size?: number; assignee?: string; instanceId?: number }) =>
      request<Page<Task>>("/tasks", { query }),
    get: (id: number) => request<Task>(`/tasks/${id}`),
    history: (query: { page?: number; size?: number; handler?: string; instanceId?: number }) =>
      request<Page<HisTask>>("/history", { query }),
    approve: (
      id: number,
      body: { message?: string; variables?: Record<string, unknown>; node_code?: string },
    ) =>
      request<InstanceWire>(`/tasks/${id}/approve`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    reject: (
      id: number,
      body: { message?: string; variables?: Record<string, unknown>; node_code?: string | null },
    ) =>
      request<InstanceWire>(`/tasks/${id}/reject`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    rejectLast: (id: number, body: { message?: string; variables?: Record<string, unknown> }) =>
      request<InstanceWire>(`/tasks/${id}/reject-last`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    transfer: (id: number, addHandlers: string[], message: string) =>
      request<Task>(`/tasks/${id}/transfer`, {
        method: "POST",
        body: JSON.stringify({ handler: "", add_handlers: addHandlers, message }),
      }),
    depute: (id: number, addHandlers: string[], message: string) =>
      request<Task>(`/tasks/${id}/depute`, {
        method: "POST",
        body: JSON.stringify({ handler: "", add_handlers: addHandlers, message }),
      }),
    addSignature: (id: number, addHandlers: string[]) =>
      request<Task>(`/tasks/${id}/add-signature`, {
        method: "POST",
        body: JSON.stringify({ handler: "", add_handlers: addHandlers }),
      }),
    reduceSignature: (id: number, reduceHandlers: string[]) =>
      request<Task>(`/tasks/${id}/reduce-signature`, {
        method: "POST",
        body: JSON.stringify({ handler: "", reduce_handlers: reduceHandlers }),
      }),
  },

  forms: {
    list: (query: {
      page?: number;
      size?: number;
      formCode?: string;
      formName?: string;
      isPublish?: number;
    }) => request<Page<FormDefinition>>("/forms", { query }),
    get: (id: number) => request<FormDefinition>(`/forms/${id}`),
    create: (body: Record<string, unknown>) =>
      request<FormDefinition>("/forms", { method: "POST", body: JSON.stringify(body) }),
    update: (id: number, body: Record<string, unknown>) =>
      request<FormDefinition>(`/forms/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (id: number) => request<void>(`/forms/${id}`, { method: "DELETE" }),
    publish: (id: number) => request<FormDefinition>(`/forms/${id}/publish`, { method: "POST" }),
    content: (id: number) => request<string>(`/designer/form-content/${id}`),
    saveContent: (id: number, formContent: string) =>
      request<{ code: number; msg: string }>("/designer/form-content", {
        method: "POST",
        body: JSON.stringify({ id, form_content: formContent }),
      }),
  },
};

export { enc };
