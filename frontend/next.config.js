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
  transpilePackages: [],
  serverExternalPackages: ["@blocknote/xl-ai"],
  i18n: {
    locales: ["en", "zh"],
    defaultLocale: "en",
  },
  devIndicators: false,
  async rewrites() {
    const afterFiles = [];
    const fallback = [];
    const gatewayURL = getInternalServiceURL(
      "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL",
      "http://127.0.0.1:8001",
    );

    if (!process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
      afterFiles.push({
        source: "/api/langgraph",
        destination: `${gatewayURL}/api`,
      });
      afterFiles.push({
        source: "/api/langgraph/:path*",
        destination: `${gatewayURL}/api/:path*`,
      });
    }

    if (!process.env.NEXT_PUBLIC_BACKEND_BASE_URL) {
      afterFiles.push({
        source: "/api/agents",
        destination: `${gatewayURL}/api/agents`,
      });
      afterFiles.push({
        source: "/api/agents/:path*",
        destination: `${gatewayURL}/api/agents/:path*`,
      });
      afterFiles.push({
        source: "/api/skills",
        destination: `${gatewayURL}/api/skills`,
      });
      afterFiles.push({
        source: "/api/skills/:path*",
        destination: `${gatewayURL}/api/skills/:path*`,
      });

      // Catch-all for remaining gateway API routes goes into fallback
      // so that local Next.js API routes (e.g. /api/collab/ai-chat)
      // take priority over the proxy.
      fallback.push({
        source: "/api/:path*",
        destination: `${gatewayURL}/api/:path*`,
      });
    }

    // 代理采购服务前端
    afterFiles.push({
      source: "/proxy/procurement/:path*",
      destination: "http://127.0.0.1:5173/:path*",
    });

    return { afterFiles, fallback };
  },
};

export default withNextra(config);
