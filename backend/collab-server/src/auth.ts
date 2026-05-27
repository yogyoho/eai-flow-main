import type { IncomingMessage } from "http";
import jwt from "jsonwebtoken";

const JWT_SECRET = process.env.JWT_SECRET || process.env.JWT_SECRET_KEY || process.env.AUTH_JWT_SECRET || "";

export interface AuthenticatedUser {
  userId: string;
}

function parseCookies(cookieHeader: string): Record<string, string> {
  const cookies: Record<string, string> = {};
  for (const pair of cookieHeader.split(";")) {
    const [key, ...rest] = pair.split("=");
    if (key) {
      cookies[key.trim()] = rest.join("=").trim();
    }
  }
  return cookies;
}

const DEFAULT_ALLOWED_ORIGINS = "localhost:2026,localhost:3000,localhost:4000";

export function validateOrigin(request: IncomingMessage): boolean {
  const originHeader = request.headers?.origin;
  const refererHeader = request.headers?.referer;

  // Non-browser clients may not send origin headers — allow through
  if (!originHeader && !refererHeader) return true;

  const allowedOrigins = (process.env.ALLOWED_ORIGINS || DEFAULT_ALLOWED_ORIGINS)
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);

  const originToCheck = originHeader || refererHeader;
  try {
    const url = new URL(originToCheck!);
    const host = url.host; // host:port
    return allowedOrigins.includes(host);
  } catch {
    return false;
  }
}

export function authenticateConnection(request: IncomingMessage): AuthenticatedUser | null {
  const cookieHeader = request.headers?.cookie;
  if (!cookieHeader || typeof cookieHeader !== "string") return null;

  const cookies = parseCookies(cookieHeader);
  const accessToken = cookies["access_token"];
  if (!accessToken) return null;

  try {
    const payload = jwt.verify(accessToken, JWT_SECRET) as { sub: string };
    if (!payload.sub) return null;
    return { userId: payload.sub };
  } catch {
    return null;
  }
}
