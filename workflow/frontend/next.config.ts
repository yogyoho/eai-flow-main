import type { NextConfig } from "next";

// Route files live at the app root (inside the `(workflow)` route group), so
// basePath is the single `/workflow` prefix for pages, RSC payloads and
// `/_next` assets. Set NEXT_PUBLIC_BASE_PATH="" only for a root deployment.
const configuredBasePath = process.env.NEXT_PUBLIC_BASE_PATH;
const basePath = configuredBasePath === undefined ? "/workflow" : configuredBasePath || undefined;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  transpilePackages: ["@logicflow/core", "@logicflow/extension"],
  output: "standalone",
  basePath,
};

export default nextConfig;
