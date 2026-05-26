import type { IncomingRequest } from "@hocuspocus/server";
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

export function authenticateConnection(request: IncomingRequest): AuthenticatedUser | null {
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
