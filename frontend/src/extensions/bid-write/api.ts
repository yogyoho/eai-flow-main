/**
 * bid-write API client（Gateway `/api/extensions/bid-write/*`）。
 *
 * 共享 `@/core/api/fetcher` 的 fetch：credentials + CSRF + 401 登录跳转。
 * 非 2xx 抛 ApiError（保留 status，行级 422 由调用方 toast 展示后端 detail）。
 */

import { fetch } from "@/core/api/fetcher";
import type { AssertPayload } from "@/extensions/bid-write/editor/decor";
import type { AstJsonNode } from "@/extensions/bid-write/editor/schema.gen";

import type {
  ExportGateResponse,
  GapsResponse,
  GenerateKnobs,
  GenerateResponse,
  MaterialIn,
  MaterialOut,
  MaterialPatch,
  MatrixResponse,
  MatrixRowOut,
  MatrixRowPatch,
  PolicyBody,
  RegistryResponse,
  TaskDocumentResponse,
  TaskMetricsResponse,
  WriteTaskListResponse,
  WriteTaskOut,
} from "./types";

const API_BASE = "/api/extensions/bid-write";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailOf(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const msg = (entry as { msg?: unknown }).msg;
          if (typeof msg === "string") return msg;
        }
        return "";
      })
      .filter(Boolean)
      .join("；");
  }
  return null;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const data = await res
      .clone()
      .json()
      .catch(() => null);
    throw new ApiError(
      detailOf(data) ?? `请求失败（HTTP ${res.status}）`,
      res.status,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function listTasks(): Promise<WriteTaskListResponse> {
  return requestJson<WriteTaskListResponse>("/tasks");
}

export async function getTask(taskId: string): Promise<WriteTaskOut> {
  return requestJson<WriteTaskOut>(`/tasks/${encodeURIComponent(taskId)}`);
}

export async function createTask(input: {
  files: File[];
  projectName: string;
  lotName: string;
  tenderNo: string;
}): Promise<WriteTaskOut> {
  const body = new FormData();
  for (const file of input.files) body.append("tender_files", file);
  body.append("project_name", input.projectName);
  body.append("lot_name", input.lotName);
  body.append("tender_no", input.tenderNo);
  return requestJson<WriteTaskOut>("/tasks", { method: "POST", body });
}

export async function getMatrix(taskId: string): Promise<MatrixResponse> {
  return requestJson<MatrixResponse>(
    `/tasks/${encodeURIComponent(taskId)}/matrix`,
  );
}

export async function patchMatrixRow(
  taskId: string,
  clauseId: string,
  patch: MatrixRowPatch,
): Promise<MatrixRowOut> {
  return requestJson<MatrixRowOut>(
    `/tasks/${encodeURIComponent(taskId)}/matrix/${encodeURIComponent(clauseId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
}

export async function getGaps(taskId: string): Promise<GapsResponse> {
  return requestJson<GapsResponse>(`/tasks/${encodeURIComponent(taskId)}/gaps`);
}

export async function getRegistry(): Promise<RegistryResponse> {
  return requestJson<RegistryResponse>("/registry");
}

// ── 批廿五 P1-δ:生成/导出/素材/policy/metrics 七组端点 ──────────────────

/** 生成+门禁+L4 审查(body 旋钮合并 meta.knobs,None 键不覆盖);409=矩阵未就绪。 */
export async function generateTask(
  taskId: string,
  knobs: GenerateKnobs,
): Promise<GenerateResponse> {
  return requestJson<GenerateResponse>(
    `/tasks/${encodeURIComponent(taskId)}/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(knobs),
    },
  );
}

/** 导出前置校验只读重算(D0 断言+L1 fatal+L4 advisory);零落库无副作用。 */
export async function exportPrecheck(
  taskId: string,
): Promise<ExportGateResponse> {
  return requestJson<ExportGateResponse>(
    `/tasks/${encodeURIComponent(taskId)}/export-precheck`,
    { method: "POST" },
  );
}

export async function listMaterials(
  entityType?: string,
): Promise<{ items: MaterialOut[] }> {
  const query = entityType
    ? `?entity_type=${encodeURIComponent(entityType)}`
    : "";
  return requestJson<{ items: MaterialOut[] }>(`/materials${query}`);
}

export async function createMaterial(input: MaterialIn): Promise<MaterialOut> {
  return requestJson<MaterialOut>("/materials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function patchMaterial(
  materialId: string,
  patch: MaterialPatch,
): Promise<MaterialOut> {
  return requestJson<MaterialOut>(
    `/materials/${encodeURIComponent(materialId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
}

export async function deleteMaterial(
  materialId: string,
): Promise<{ deleted: boolean }> {
  return requestJson<{ deleted: boolean }>(
    `/materials/${encodeURIComponent(materialId)}`,
    { method: "DELETE" },
  );
}

export async function getMaterialProfile(): Promise<{
  profile: Record<string, unknown>;
}> {
  return requestJson<{ profile: Record<string, unknown> }>(
    "/materials/profile",
  );
}

export async function putMaterialProfile(
  profile: Record<string, unknown>,
): Promise<{ profile: Record<string, unknown> }> {
  return requestJson<{ profile: Record<string, unknown> }>(
    "/materials/profile",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile }),
    },
  );
}

export async function getPolicy(): Promise<{
  policy: Record<string, unknown>;
}> {
  return requestJson<{ policy: Record<string, unknown> }>("/policy");
}

/** policy 合并语义(只改传入键);ghost 键/税率越界 422 由后端拒。 */
export async function putPolicy(
  body: PolicyBody,
): Promise<{ policy: Record<string, unknown> }> {
  return requestJson<{ policy: Record<string, unknown> }>("/policy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getTaskMetrics(
  taskId: string,
): Promise<TaskMetricsResponse> {
  return requestJson<TaskMetricsResponse>(
    `/tasks/${encodeURIComponent(taskId)}/metrics`,
  );
}

/** 正文 AST 读取(批廿八 M2;未保存 ast=null)。 */
export async function getTaskDocument(
  taskId: string,
): Promise<TaskDocumentResponse> {
  return requestJson<TaskDocumentResponse>(
    `/tasks/${encodeURIComponent(taskId)}/document`,
  );
}

/** 正文 AST 保存(PUT 全量幂等;根非 doc / semver 非法 422 由后端拒)。 */
export async function putTaskDocument(
  taskId: string,
  input: { ast: AstJsonNode; schema_version: string },
): Promise<TaskDocumentResponse> {
  return requestJson<TaskDocumentResponse>(
    `/tasks/${encodeURIComponent(taskId)}/document`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

/** 编辑器真执行器(批三十):任务 ctx + AST → 43 条断言结果 → states 侧信道。
 *  只读,不落 skill_run。非 2xx 抛 ApiError(调用方据此显示「校验未完成」)。 */
export async function assertTaskDocument(
  taskId: string,
  input: { ast: AstJsonNode; skills?: string[] },
): Promise<AssertPayload> {
  return requestJson<AssertPayload>(
    `/tasks/${encodeURIComponent(taskId)}/assert`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}
