/**
 * API Client — uses Gateway Auth HttpOnly cookie (credentials: "include").
 *
 * Auth is handled by the Gateway's cookie-based JWT. No longer manages its
 * own access_token / refresh_token in localStorage.
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '') + "/procurement/api"

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

const CSRF_HEADER = "X-CSRF-Token";
const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "DELETE", "PATCH"]);

function withCsrf(headers: Record<string, string>, method?: string): Record<string, string> {
  if (method && STATE_CHANGING_METHODS.has(method)) {
    const token = getCsrfToken();
    if (token) {
      return { ...headers, [CSRF_HEADER]: token };
    }
  }
  return headers;
}

function redirectToLogin() {
  if (typeof window === "undefined") return;
  const loginUrl = '/login';
  const topWindow = window.top || window;
  try {
    topWindow.location.href = loginUrl;
  } catch {
    window.location.href = loginUrl;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = withCsrf({
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  }, options.method);

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    if (response.status === 401) {
      redirectToLogin();
      throw new Error("登录已过期，请重新登录");
    }
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `Error ${response.status}`);
  }

  return response.json();
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Expert {
  id: string;
  name: string;
  id_card?: string;
  phone?: string;
  email?: string;
  expertise: string;
  title?: string;
  organization?: string;
  region?: string;
  is_active: boolean;
  evaluation_count: number;
  avg_score?: number;
  bank_account?: string;
  bank_name?: string;
  remark?: string;
  created_at: string;
  updated_at: string;
}

export interface Bidder {
  id: string;
  name: string;
  unified_credit_code?: string;
  legal_person?: string;
  contact_person?: string;
  phone?: string;
  email?: string;
  address?: string;
  region?: string;
  business_scope?: string;
  credit_rating?: string;
  status: string;
  registration_date?: string;
  remark?: string;
  created_at: string;
  updated_at: string;
}

export interface TenderPlan {
  id: string;
  plan_no: string;
  title: string;
  procurement_type: string;
  procurement_method?: string;
  dept_id?: string;
  dept_name?: string;
  budget?: number;
  estimated_price?: number;
  funding_source?: string;
  plan_year?: number;
  estimated_start?: string;
  estimated_end?: string;
  description?: string;
  status: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface TenderProject {
  id: string;
  project_no: string;
  title: string;
  procurement_type: string;
  procurement_method: string;
  dept_id?: string;
  dept_name?: string;
  budget?: number;
  control_price?: number;
  funding_source?: string;
  bid_amount?: number;
  plan_id?: string;
  announcement_url?: string;
  description?: string;
  qualification_requirements?: string;
  status: string;
  bidding_start?: string;
  bidding_end?: string;
  evaluation_date?: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

export interface Bid {
  id: string;
  project_id: string;
  bidder_id: string;
  bid_no: string;
  bid_price?: number;
  technical_score?: number;
  commercial_score?: number;
  total_score?: number;
  ranking?: number;
  technical_proposal_url?: string;
  compliance_check_passed?: boolean;
  compliance_issues?: string[];
  status: string;
  submitted_at?: string;
  created_at: string;
  updated_at: string;
}

export interface Evaluation {
  id: string;
  project_id: string;
  bid_id: string;
  evaluation_type: string;
  technical_score?: number;
  commercial_score?: number;
  total_score?: number;
  ranking?: number;
  status: string;
  verified: boolean;
  verification_comment?: string;
  evaluation_report_url?: string;
  evaluation_details?: string;
  evaluator_ids?: string[];
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface Contract {
  id: string;
  contract_no: string;
  project_id: string;
  winning_bid_id?: string;
  bidder_id: string;
  title: string;
  total_price?: number;
  sign_date?: string;
  start_date?: string;
  end_date?: string;
  payment_terms?: string;
  contract_file_url?: string;
  status: string;
  risk_level?: string;
  risk_issues?: string[];
  operator_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Complaint {
  id: string;
  project_id?: string;
  complaint_no: string;
  title: string;
  complaint_type: string;
  description: string;
  evidence_urls?: string[];
  complainer_name?: string;
  complainer_phone?: string;
  status: string;
  priority: string;
  response_content?: string;
  decision_content?: string;
  responded_by?: string;
  responded_at?: string;
  decided_by?: string;
  decided_at?: string;
  created_at: string;
  updated_at: string;
}

export interface WitnessRecord {
  id: string;
  project_id: string;
  stage: string;
  event_type: string;
  description?: string;
  audio_transcript?: string;
  risk_warnings?: string;
  sensitive_words_detected?: string[];
  video_url?: string;
  operator_id?: string;
  created_at: string;
}

export interface VenueSpace {
  id: string;
  venue_name: string;
  space_no: string;
  floor?: string;
  capacity?: number;
  equipment?: string;
  hourly_rate?: number;
  description?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  active_projects: number;
  ongoing_bids: number;
  pending_evaluations: number;
  active_contracts: number;
  pending_complaints: number;
  total_budget: string;
  total_contracts_value: string;
}

// ─── API Functions ────────────────────────────────────────────────────────────

export const expertApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ experts: Expert[]; total: number }>(`/experts${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<Expert>) =>
    request<Expert>("/experts", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<Expert>(`/experts/${id}`),
  update: (id: string, data: Partial<Expert>) =>
    request<Expert>(`/experts/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ message: string }>(`/experts/${id}`, { method: "DELETE" }),
  batchImport: (experts: Partial<Expert>[]) =>
    request<{ experts: Expert[]; total: number }>("/experts/batch", {
      method: "POST",
      body: JSON.stringify(experts),
    }),
  draw: (data: { project_id: string; required_count: number; draw_method?: string }) =>
    request<unknown>("/experts/draws", { method: "POST", body: JSON.stringify(data) }),
};

export const bidderApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ bidders: Bidder[]; total: number }>(`/bidders${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<Bidder>) =>
    request<Bidder>("/bidders", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<Bidder>(`/bidders/${id}`),
  update: (id: string, data: Partial<Bidder>) =>
    request<Bidder>(`/bidders/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ message: string }>(`/bidders/${id}`, { method: "DELETE" }),
};

export const planApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ plans: TenderPlan[]; total: number }>(`/plans${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<TenderPlan>) =>
    request<TenderPlan>("/plans", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<TenderPlan>(`/plans/${id}`),
  update: (id: string, data: Partial<TenderPlan>) =>
    request<TenderPlan>(`/plans/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ message: string }>(`/plans/${id}`, { method: "DELETE" }),
};

export const projectApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ projects: TenderProject[]; total: number }>(`/projects${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<TenderProject>) =>
    request<TenderProject>("/projects", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<TenderProject>(`/projects/${id}`),
  update: (id: string, data: Partial<TenderProject>) =>
    request<TenderProject>(`/projects/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: string) =>
    request<{ message: string }>(`/projects/${id}`, { method: "DELETE" }),
  publish: (id: string) =>
    request<TenderProject>(`/projects/${id}/publish`, { method: "POST" }),
};

export const bidApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ bids: Bid[]; total: number }>(`/bids${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<Bid>) =>
    request<Bid>("/bids", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<Bid>(`/bids/${id}`),
  update: (id: string, data: Partial<Bid>) =>
    request<Bid>(`/bids/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  complianceCheck: (id: string) =>
    request<{ passed: boolean; score: number; issues: unknown[] }>(
      `/bids/${id}/compliance-check`,
      { method: "POST" }
    ),
};

export const evaluationApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ evaluations: Evaluation[]; total: number }>(`/evaluations${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<Evaluation>) =>
    request<Evaluation>("/evaluations", { method: "POST", body: JSON.stringify(data) }),
  verify: (id: string) =>
    request<{ passed: boolean; issues: unknown[] }>(`/evaluations/${id}/verify`, { method: "POST" }),
  complete: (id: string) =>
    request<Evaluation>(`/evaluations/${id}/complete`, { method: "POST" }),
};

export const winningBidApi = {
  create: (data: { project_id: string; bid_id: string; decision_summary?: string }) =>
    request<unknown>("/winning-bids", { method: "POST", body: JSON.stringify(data) }),
  confirm: (id: string) =>
    request<unknown>(`/winning-bids/${id}/confirm`, { method: "POST" }),
  generateContract: (id: string) =>
    request<Contract>(`/winning-bids/${id}/contract`, { method: "POST" }),
};

export const contractApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ contracts: Contract[]; total: number }>(`/contracts${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<Contract>) =>
    request<Contract>("/contracts", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<Contract>(`/contracts/${id}`),
  update: (id: string, data: Partial<Contract>) =>
    request<Contract>(`/contracts/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  riskCheck: (id: string) =>
    request<{ passed: boolean; issues: unknown[]; warnings: unknown[]; risk_level: string }>(
      `/contracts/${id}/risk-check`,
      { method: "POST" }
    ),
};

export const complaintApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ complaints: Complaint[]; total: number }>(`/complaints${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<Complaint>) =>
    request<Complaint>("/complaints", { method: "POST", body: JSON.stringify(data) }),
  get: (id: string) => request<Complaint>(`/complaints/${id}`),
  update: (id: string, data: Partial<Complaint>) =>
    request<Complaint>(`/complaints/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  reply: (id: string, response_content: string) =>
    request<Complaint>(
      `/complaints/${id}/reply?response_content=${encodeURIComponent(response_content)}`,
      { method: "POST" }
    ),
  decide: (id: string, decision_content: string) =>
    request<Complaint>(
      `/complaints/${id}/decide?decision_content=${encodeURIComponent(decision_content)}`,
      { method: "POST" }
    ),
};

export const witnessApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ records: WitnessRecord[]; total: number }>(`/witness-records${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<WitnessRecord>) =>
    request<WitnessRecord>("/witness-records", { method: "POST", body: JSON.stringify(data) }),
};

export const venueApi = {
  list: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request<{ spaces: VenueSpace[]; total: number }>(`/venue-spaces${q ? `?${q}` : ""}`);
  },
  create: (data: Partial<VenueSpace>) =>
    request<VenueSpace>("/venue-spaces", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Partial<VenueSpace>) =>
    request<VenueSpace>(`/venue-spaces/${id}`, { method: "PUT", body: JSON.stringify(data) }),
};

export const dashboardApi = {
  getStats: () => request<DashboardStats>("/dashboard/stats"),
};
