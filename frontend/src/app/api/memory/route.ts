import type { NextRequest } from "next/server";

// EAI-CUSTOM (2026-08-30, bug-3020/3021): this route handler shadows the
// next.config.js rewrite for /api/memory (route handlers win over afterFiles
// rewrites), but read only NEXT_PUBLIC_BACKEND_BASE_URL — unset in our host dev
// server (:3000, .env.local), so it fell back to http://127.0.0.1:8001, which is
// dead outside Docker → settings memory tab showed
// "Failed to fetch memory: Internal Server Error". Resolve the same env var the
// rewrites use (DEER_FLOW_INTERNAL_GATEWAY_BASE_URL) so both paths agree.
// Precedence note (code-review bug-3020 follow-up): server-side legs intentionally
// prefer the INTERNAL gateway URL — upstream semantics (NEXT_PUBLIC authoritative
// everywhere) assume a single-URL deployment; ours has internal (rewrites/proxy)
// vs public (browser) split, and a server-side fetch must never target the public
// URL. Falls through to the next candidate on a scheme-less value (natural typo
// for this var) instead of new URL() throwing.
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
  // Forward the query string too — the shadowed rewrite ("/api/:path*") does,
  // so both same-origin paths to the same endpoint must behave identically.
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

  // EAI-CUSTOM (bug-3021): undici transparently decompresses gzip/deflate/br,
  // but response.headers still carry the upstream framing — and our upstream is
  // nginx (:2026, gzip on, application/json, min_length 1024), so any response
  // over 1KB arrives decompressed while the rebuilt Response re-declares
  // content-encoding: gzip + stale content-length. Browsers then fail with
  // ERR_CONTENT_DECODING_FAILED. Strip body-framing headers before rebuilding;
  // the null-body statuses additionally reject any body at all.
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

export async function GET(request: NextRequest) {
  return proxyRequest(request, "/api/memory");
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request, "/api/memory");
}
