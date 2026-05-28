export interface User {
  id: string;
  username: string;
  email?: string;
  full_name?: string;
  dept_id?: string;
  dept_name?: string;
  role_id?: string;
  role_name?: string;
  status: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
}

export interface TokenPayload {
  sub: string;
  username: string;
  role?: string;
  permissions: string[];
  exp?: number;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface PageParams {
  skip?: number;
  limit?: number;
  keyword?: string;
  status?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}
