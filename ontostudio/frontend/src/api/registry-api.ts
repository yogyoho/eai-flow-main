/**
 * registry 内容管理适配层（建模器页数据源, EAI-CUSTOM）.
 * 路径均为扩展内相对路径（authFetch base = /api/ontostudio/api/extensions）。
 */
import { authFetch } from "@/lib/api";

const BASE = "/ontology/registry-content";

export interface RegistryClass {
  name: string;
  label: string;
  definition: string;
  parents: string[];
  hasKey: string[];
  etypes: string[];
}

export interface DomainSummary {
  namespace: string;
  classes: RegistryClass[];
  predicates: string[];
}

export interface RegistryAxioms {
  property_chains: Array<{ derived: string; chain: string[] }>;
  transitive: string[];
  inverse: Array<{ pair: string[] }>;
  disjoint: string[];
}

export interface RegistrySummary {
  domains: Record<string, DomainSummary>;
  axioms: Record<string, RegistryAxioms>;
}

export interface RegistryContent {
  file: string;
  raw: string;
  summary: RegistrySummary;
  fingerprint: string;
  registry_version: number;
}

export interface ValidateResult {
  ok: boolean;
  errors: string[];
  summary: RegistrySummary | null;
}

export interface SaveResult {
  ok: boolean;
  fingerprint: string;
  registry_version: number;
}

export function fetchRegistryFiles(): Promise<{ files: string[] }> {
  return authFetch<{ files: string[] }>(`${BASE}/files`);
}

export function fetchRegistryContent(file: string): Promise<RegistryContent> {
  return authFetch<RegistryContent>(`${BASE}/content?file=${encodeURIComponent(file)}`);
}

export function validateRegistryDraft(file: string, content: string): Promise<ValidateResult> {
  return authFetch<ValidateResult>(`${BASE}/validate`, {
    method: "POST",
    body: JSON.stringify({ file, content }),
  });
}

export function saveRegistryContent(file: string, content: string): Promise<SaveResult> {
  return authFetch<SaveResult>(`${BASE}/content`, {
    method: "PUT",
    body: JSON.stringify({ file, content }),
  });
}
