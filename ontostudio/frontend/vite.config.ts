/**
 * OntoStudio standalone frontend Vite config (S2 Task 1, EAI-CUSTOM).
 *
 * Dev proxy 对齐 S1-T3 nginx 语义：
 * - /api/ontostudio/* → 独立后端 :8005，剥掉 location 前缀后余路径原样透传
 *   （客户端 BASE 已含 /api/extensions，即 /api/ontostudio/api/extensions/ontology/...
 *   → 后端 /api/extensions/ontology/...；rewrite 再补前缀会产生双重前缀 404）
 *   （独立后端路由挂在 /api/extensions/*，见 ontostudio/backend/app/）。
 * - /api/permissions/* → 主系统 nginx :2026（不 rewrite，cookie 鉴权走主系统）。
 *   localhost 跨端口共享 cookie jar，credentials:"include" 即可带上主系统会话。
 *
 * explorer/ vendored 零改动原则：上游代码含 3 处 `process.env.NODE_ENV`（当初从
 * Vite 移植进 Next 时改写的），Vite 源码默认不注入 process —— 在此按 mode 显式
 * define 还原原语义，避免改 vendored 文件本体。
 */
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // S2 Task 3（EAI-CUSTOM）：子路径部署——主 nginx :2026 把 /ontostudio/* 透传到
  // 前端容器 :3010，产物资产引用须带前缀（默认 base:"/" 产出 /assets/* 会 404）。
  // 构建期定死（方案 a，最简）：base 对 dev server 同样生效 → 本地开发地址变为
  // http://localhost:3010/ontostudio/；下方 server.proxy 的 /api/* 代理不受 base
  // 影响（按原始请求路径匹配）。API_BASE 为常量 "/api/ontostudio/api/extensions"
  // （lib/api.ts），同为相对路径，经 nginx 同源携带 cookie，无需改动。
  base: "/ontostudio/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  define: {
    "process.env.NODE_ENV": JSON.stringify(
      mode === "production" ? "production" : "development",
    ),
  },
  server: {
    port: 3010,
    proxy: {
      "/api/ontostudio": {
        target: "http://localhost:8005",
        changeOrigin: true,
        rewrite: (p: string) => p.replace(/^\/api\/ontostudio/, ""),
      },
      "/api/permissions": {
        target: "http://localhost:2026",
        changeOrigin: true,
      },
    },
  },
}));
