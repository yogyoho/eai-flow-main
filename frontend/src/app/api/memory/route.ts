import type { NextRequest } from "next/server";

// EAI-CUSTOM (2026-08-30, bug-3020): this route handler shadows the
// next.config.js rewrite for /api/memory (route handlers win over afterFiles
// rewrites), but read only NEXT_PUBLIC_BACKEND_BASE_URL — unset in our host dev
// server (:3000, .env.local), so it fell back to http://127.0.0.1:8001, which is
// dead outside Docker → settings memory tab showed
// "Failed to fetch memory: Internal Server Error". Resolve the same env var the
// rewrites use (DEER_FLOW_INTERNAL_GATEWAY_BASE_URL) so both paths agree.
// Upstream fallback chain preserved below it.
function resolveBackendBaseURL() {
  const internal = process.env.DEER_FLOW_INTERNAL_GATEWAY_BASE_URL?.trim();
  if (internal) {
    return internal.replace(/\/+$/, "");
  }
  return (
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL?.trim().replace(/\/+$/, "") ||
    "http://127.0.0.1:8001"
  );
}

function buildBackendUrl(pathname: string) {
  return new URL(pathname, resolveBackendBaseURL());
}

async function proxyRequest(request: NextRequest, pathname: string) {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(buildBackendUrl(pathname), {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
  });

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    headers: response.headers,
  });
}

export async function GET(request: NextRequest) {
  return proxyRequest(request, "/api/memory");
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request, "/api/memory");
}
