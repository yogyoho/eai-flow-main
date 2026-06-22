import { authFetch } from "@/extensions/api/client";

const BASE = "/app-center";

export interface DomainResponse {
  key: string;
  label: string;
  accentColor: string;
  sortOrder: number;
  isUniversal: boolean;
}

export interface AppResponse {
  id: string;
  appId: string;
  name: string;
  description: string | null;
  iconName: string;
  businessDomain: string;
  stageTag: string | null;
  path: string;
  licenseModule: string | null;
  adminOnly: boolean;
  sortOrder: number;
  sortKey: string;
  isBuiltin: boolean;
  isEnabled: boolean;
}

export interface AppCreate {
  appId: string;
  name: string;
  description?: string;
  iconName: string;
  businessDomain: string;
  stageTag?: string;
  path: string;
  licenseModule?: string;
  adminOnly?: boolean;
  sortOrder?: number;
  sortKey: string;
  isEnabled?: boolean;
}

export interface AppUpdate {
  name?: string;
  description?: string;
  iconName?: string;
  businessDomain?: string;
  stageTag?: string;
  path?: string;
  licenseModule?: string;
  adminOnly?: boolean;
  sortOrder?: number;
  sortKey?: string;
  isEnabled?: boolean;
}

// ── Public endpoints ──

export async function fetchDomains(): Promise<DomainResponse[]> {
  const data = await authFetch<{ items: Record<string, unknown>[] }>(`${BASE}/domains`);
  return data.items.map(mapDomain);
}

export async function fetchApps(): Promise<AppResponse[]> {
  const data = await authFetch<{ items: Record<string, unknown>[] }>(`${BASE}/apps`);
  return data.items.map(mapApp);
}

// ── Admin: domains ──

export interface DomainCreate {
  key: string;
  label: string;
  accentColor?: string;
  sortOrder?: number;
  isUniversal?: boolean;
}

export interface DomainUpdate {
  label?: string;
  accentColor?: string;
  sortOrder?: number;
  isUniversal?: boolean;
}

export async function createDomain(req: DomainCreate): Promise<DomainResponse> {
  return mapDomain(
    await authFetch<Record<string, unknown>>(`${BASE}/domains`, {
      method: "POST",
      body: JSON.stringify({
        key: req.key,
        label: req.label,
        accent_color: req.accentColor ?? "blue",
        sort_order: req.sortOrder ?? 0,
        is_universal: req.isUniversal ?? false,
      }),
    }),
  );
}

export async function updateDomain(
  key: string,
  req: DomainUpdate,
): Promise<DomainResponse> {
  const snake: Record<string, unknown> = {};
  if (req.label !== undefined) snake.label = req.label;
  if (req.accentColor !== undefined) snake.accent_color = req.accentColor;
  if (req.sortOrder !== undefined) snake.sort_order = req.sortOrder;
  if (req.isUniversal !== undefined) snake.is_universal = req.isUniversal;
  return mapDomain(
    await authFetch<Record<string, unknown>>(`${BASE}/domains/${key}`, {
      method: "PUT",
      body: JSON.stringify(snake),
    }),
  );
}

export async function deleteDomain(key: string): Promise<void> {
  await authFetch(`${BASE}/domains/${key}`, { method: "DELETE" });
}

// ── Admin endpoints ──

export async function fetchAllApps(): Promise<AppResponse[]> {
  const data = await authFetch<{ items: Record<string, unknown>[] }>(`${BASE}/apps/all`);
  return data.items.map(mapApp);
}

export async function createApp(req: AppCreate): Promise<AppResponse> {
  return mapApp(
    await authFetch<Record<string, unknown>>(`${BASE}/apps`, {
      method: "POST",
      body: JSON.stringify(toSnakeCreate(req)),
    })
  );
}

export async function updateApp(
  appId: string,
  req: AppUpdate
): Promise<AppResponse> {
  return mapApp(
    await authFetch<Record<string, unknown>>(`${BASE}/apps/${appId}`, {
      method: "PUT",
      body: JSON.stringify(toSnakeUpdate(req)),
    })
  );
}

export async function deleteApp(appId: string): Promise<void> {
  await authFetch(`${BASE}/apps/${appId}`, { method: "DELETE" });
}

// ── Helpers ──

function mapApp(raw: Record<string, unknown>): AppResponse {
  return {
    id: raw.id as string,
    appId: raw.app_id as string,
    name: raw.name as string,
    description: raw.description as string | null,
    iconName: raw.icon_name as string,
    businessDomain: raw.business_domain as string,
    stageTag: raw.stage_tag as string | null,
    path: raw.path as string,
    licenseModule: raw.license_module as string | null,
    adminOnly: (raw.admin_only as boolean) ?? false,
    sortOrder: (raw.sort_order as number) ?? 0,
    sortKey: raw.sort_key as string,
    isBuiltin: (raw.is_builtin as boolean) ?? true,
    isEnabled: (raw.is_enabled as boolean) ?? true,
  };
}

function mapDomain(raw: Record<string, unknown>): DomainResponse {
  return {
    key: raw.key as string,
    label: raw.label as string,
    accentColor: raw.accent_color as string,
    sortOrder: (raw.sort_order as number) ?? 0,
    isUniversal: (raw.is_universal as boolean) ?? false,
  };
}

function toSnakeCreate(req: AppCreate): Record<string, unknown> {
  return {
    app_id: req.appId,
    name: req.name,
    description: req.description,
    icon_name: req.iconName,
    business_domain: req.businessDomain,
    stage_tag: req.stageTag,
    path: req.path,
    license_module: req.licenseModule,
    admin_only: req.adminOnly,
    sort_order: req.sortOrder,
    sort_key: req.sortKey,
    is_enabled: req.isEnabled,
  };
}

function toSnakeUpdate(req: AppUpdate): Record<string, unknown> {
  const snake: Record<string, unknown> = {};
  if (req.name !== undefined) snake.name = req.name;
  if (req.description !== undefined) snake.description = req.description;
  if (req.iconName !== undefined) snake.icon_name = req.iconName;
  if (req.businessDomain !== undefined) snake.business_domain = req.businessDomain;
  if (req.stageTag !== undefined) snake.stage_tag = req.stageTag;
  if (req.path !== undefined) snake.path = req.path;
  if (req.licenseModule !== undefined) snake.license_module = req.licenseModule;
  if (req.adminOnly !== undefined) snake.admin_only = req.adminOnly;
  if (req.sortOrder !== undefined) snake.sort_order = req.sortOrder;
  if (req.sortKey !== undefined) snake.sort_key = req.sortKey;
  if (req.isEnabled !== undefined) snake.is_enabled = req.isEnabled;
  return snake;
}
