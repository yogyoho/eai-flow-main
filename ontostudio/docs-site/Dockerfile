# ── Build stage: pnpm install + vitepress build ──────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# ── Serve stage: nginx 静态托管 ──────────────────────────────────────────────
# dist 放到 /ontostudio/docs/ 同名子路径——主 nginx 前缀透传（不改写 URI），
# 与 VitePress base=/ontostudio/docs/ 的资源路径天然对齐。
FROM nginx:alpine
# 覆写 server 配置：监听 3011（compose healthcheck 与主 nginx upstream 端口）
RUN printf 'server {\n  listen 3011;\n  root /usr/share/nginx/html;\n  index index.html;\n  location / {\n    try_files $uri $uri.html $uri/ =404;\n  }\n}\n' > /etc/nginx/conf.d/default.conf
COPY --from=build /app/.vitepress/dist /usr/share/nginx/html/ontostudio/docs/
EXPOSE 3011
