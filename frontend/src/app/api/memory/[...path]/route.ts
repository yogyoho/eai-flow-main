import type { NextRequest } from "next/server";

// EAI-CUSTOM (2026-08-30, bug-3020): same shadowing issue as ../route.ts — this
// catch-all shadows the rewrite for /api/memory/* but read only
// NEXT_PUBLIC_BACKEND_BASE_URL (unset in our host dev server → dead
// http://127.0.0.1:8001). Resolve the env var the rewrites use instead.
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

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
}
