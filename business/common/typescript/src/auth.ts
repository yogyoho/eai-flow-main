import type { TokenPayload } from "./types";

const TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function setRefreshToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function base64UrlDecode(str: string): string {
  let base64 = str.replace(/-/g, "+").replace(/_/g, "/");
  while (base64.length % 4) base64 += "=";
  return atob(base64);
}

export function decodeJWT(token: string): TokenPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(base64UrlDecode(parts[1]));
    return payload as TokenPayload;
  } catch {
    return null;
  }
}

export function getCurrentUsername(): string | null {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJWT(token);
  return payload?.username ?? null;
}

export function getCurrentUserId(): string | null {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJWT(token);
  return payload?.sub ?? null;
}
