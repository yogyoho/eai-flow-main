// frontend/src/extensions/license/api.ts

export interface LicenseSystemInfo {
  hostname: string;
  platform: string;
}

export interface LicenseStatus {
  valid: boolean;
  machine_id: string | null;
  type: "permanent" | "trial" | "subscription" | "grace" | null;
  customer: string | null;
  max_users: number | null;
  current_users: number;
  modules: Record<string, boolean>;
  features: Record<string, unknown>;
  expires_at: string | null;
  days_remaining: number | null;
  in_grace_period: boolean;
  grace_period_remaining_days: number | null;
  warnings: string[];
  is_dev_mode: boolean;
  system_info: LicenseSystemInfo;
}

export interface LicenseImportResult {
  success: boolean;
  machine_id: string | null;
  type: string | null;
  customer: string | null;
  message: string;
}

export interface LicenseHistoryItem {
  id: string;
  jwt_jti: string;
  machine_id: string;
  type: string;
  customer: string | null;
  max_users: number | null;
  modules: Record<string, boolean>;
  issued_at: string;
  expires_at: string | null;
  imported_at: string;
  is_active: boolean;
}

const BASE = "/api/license";

export async function getLicenseStatus(): Promise<LicenseStatus> {
  const res = await fetch(`${BASE}/status`);
  if (!res.ok) throw new Error(`License status failed: ${res.status}`);
  return res.json();
}

export async function importLicense(file: File): Promise<LicenseImportResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/import`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Import failed" }));
    throw new Error(err.detail ?? "Import failed");
  }
  return res.json();
}

export async function getLicenseHistory(
  skip = 0,
  limit = 20
): Promise<{ items: LicenseHistoryItem[]; total: number }> {
  const res = await fetch(`${BASE}/history?skip=${skip}&limit=${limit}`);
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  return res.json();
}

export async function exportLicense(): Promise<Blob> {
  const res = await fetch(`${BASE}/export`);
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  return res.blob();
}
