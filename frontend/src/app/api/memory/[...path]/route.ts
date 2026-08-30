import type { NextRequest } from "next/server";

// EAI-CUSTOM (2026-08-30, bug-3020/3021): same shadowing issue as ../route.ts —
// this catch-all shadows the rewrite for /api/memory/* but read only
// NEXT_PUBLIC_BACKEND_BASE_URL (unset in our host dev server → dead
// http://127.0.0.1:8001). Resolve the env var the rewrites use instead.
// Server-side legs intentionally prefer the INTERNAL gateway URL (see
// ../route.ts for the precedence rationale); scheme-less values fall through.
function resolveBackendBaseURL() {
  const candidates = [
    process.env.DEER_FLOW_INTERNAL_GATEWAY_BASE_URL,
    process.env.NEXT_PUBLIC_BACKEND_BASE_URL,
  ];
  for (const raw of candidates) {
    const value = raw?.trim().replace(/\/+$/, "");
    if (value && /^[a-z][a-z0-9+.-]*:\/\//i.test(value)) {
      return value;
    }
  }
  return "http://127.0.0.1:8001";
}

function buildBackendUrl(request: NextRequest, pathname: string) {
  // Forward the query string too — the shadowed rewrite ("/api/:path*") does.
  return new URL(pathname + request.nextUrl.search, resolveBackendBaseURL());
}

async function proxyRequest(request: NextRequest, pathname: string) {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(buildBackendUrl(request, pathname), {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
  });

  // EAI-CUSTOM (bug-3021): strip body-framing headers — undici decompresses the
  // body but the upstream headers still say gzip/chunked (nginx :2026 gzips
  // JSON >1KB) → browsers hit ERR_CONTENT_DECODING_FAILED. Null-body statuses
  // reject any body at all.
  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");

  if ([204, 205, 304].includes(response.status)) {
    return new Response(null, {
      status: response.status,
      headers: responseHeaders,
    });
  }

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    headers: responseHeaders,
  });
}

async function resolveTarget(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const segments = (await params).path;
  // Catch-all params arrive decoded; re-encode so an id containing "/" or "%2F"
  // stays one segment, and reject traversal before URL normalization can escape
  // the /api/memory namespace (e.g. ..%2fauth → /api/auth).
  if (segments.some((segment) => segment === "." || segment === "..")) {
    return null;
  }
  return `/api/memory/${segments.map(encodeURIComponent).join("/")}`;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const target = await resolveTarget(request, context);
  if (target === null) {
    return new Response("Bad Request", { status: 400 });
  }
  return proxyRequest(request, target);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const target = await resolveTarget(request, context);
  if (target === null) {
    return new Response("Bad Request", { status: 400 });
  }
  return proxyRequest(request, target);
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const target = await resolveTarget(request, context);
  if (target === null) {
    return new Response("Bad Request", { status: 400 });
  }
  return proxyRequest(request, target);
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const target = await resolveTarget(request, context);
  if (target === null) {
    return new Response("Bad Request", { status: 400 });
  }
  return proxyRequest(request, target);
}
