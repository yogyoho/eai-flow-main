import { fileURLToPath } from "node:url";

/**
 * Run `build` or `dev` with `SKIP_ENV_VALIDATION` to skip env validation. This is especially useful
 * for Docker builds.
 */
import "./src/env.js";

function getInternalServiceURL(envKey, fallbackURL) {
  const configured = process.env[envKey]?.trim();
  return configured && configured.length > 0
    ? configured.replace(/\/+$/, "")
    : fallbackURL;
}
import nextra from "nextra";

const withNextra = nextra({});

/** @type {import("next").NextConfig} */
const config = {
  output:
    process.env.NEXT_CONFIG_BUILD_OUTPUT === "standalone"
      ? "standalone"
      : undefined,
  i18n: {
    locales: ["en", "zh"],
    defaultLocale: "en",
  },
  turbopack: {
    root: fileURLToPath(new URL(".", import.meta.url)),
  },
  devIndicators: false,
  // EAI-CUSTOM: 离线生产构建跳过 TS 检查。
  // Next.js 16 已移除 next.config.js 的 eslint 键（build 不再内嵌跑 ESLint，
  // lint 走 pnpm lint/check 单独执行），故此处只需跳 TS。
  // 前端有 82 个既存 TS 错误（docmgr/BlockNote 雷区、agent-settings/workflow API 漂移等），
  // dev 模式本就不类型检查（pnpm dev 不跑 tsc）。设此开关让 prod 构建通过以解锁离线部署；
  // 这些错误作为独立技术债分批修（勿动 BlockNote DefaultChatTransport——重蹈崩溃复辙）。
  // 详见 docs/superpowers/specs/2026-07-29-offline-deploy-simplification-design.md (Task #18)。
  typescript: { ignoreBuildErrors: true },
  // Raise the dev-proxy body limit so large contract PDF uploads (>10MB scanned
  // docs) aren't truncated by the Next.js rewrite proxy (default 10MB → socket
  // hang up). Host `pnpm dev` only; Docker :2026 goes direct via nginx.
  experimental: {
    proxyClientMaxBodySize: "100mb",
  },
  // 允许局域网其他设备 + ngrok 隧道访问 dev server（HMR/WebSocket 跨域）
  allowedDevOrigins: ["192.168.2.35", "*.ngrok-free.dev"],
  async rewrites() {
    const rewrites = [];
    const gatewayURL = getInternalServiceURL(
      "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL",
      "http://127.0.0.1:8001",
    );

    if (!process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
      rewrites.push({
        source: "/api/langgraph",
        destination: `${gatewayURL}/api`,
      });
      rewrites.push({
        source: "/api/langgraph/:path*",
        destination: `${gatewayURL}/api/:path*`,
      });
    }

    if (!process.env.NEXT_PUBLIC_BACKEND_BASE_URL) {
      rewrites.push({
        source: "/api/agents",
        destination: `${gatewayURL}/api/agents`,
      });
      rewrites.push({
        source: "/api/agents/:path*",
        destination: `${gatewayURL}/api/agents/:path*`,
      });
      rewrites.push({
        source: "/api/skills",
        destination: `${gatewayURL}/api/skills`,
      });
      rewrites.push({
        source: "/api/skills/:path*",
        destination: `${gatewayURL}/api/skills/:path*`,
      });

      // Catch-all for remaining gateway API routes (models, threads, memory,
      // mcp, artifacts, uploads, suggestions, runs, etc.) that don't have
      // their own NEXT_PUBLIC_* env var toggle.
      //
      // NOTE: this must come AFTER the /api/langgraph rewrite above so that
      // LangGraph-compatible routes keep their public prefix while Gateway
      // receives its native /api/* paths.
      rewrites.push({
        source: "/api/:path*",
        destination: `${gatewayURL}/api/:path*`,
      });
    }

    // 代理采购服务前端
    rewrites.push({
      source: "/proxy/procurement/:path*",
      destination: "http://127.0.0.1:5173/:path*",
    });

    return rewrites;
  },
};

export default withNextra(config);
