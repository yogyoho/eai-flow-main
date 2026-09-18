# OntoStudio Frontend Dockerfile — 独立 Vite SPA，nginx 托管静态产物（S2 Task 3）
# EAI-CUSTOM: 两阶段构建（node build → nginx:alpine 托管 dist）。构建上下文 =
# ontostudio/frontend/（compose build.context 指向本目录）。风格照 frontend/Dockerfile：
# corepack 装 pnpm（版本对齐 package.json packageManager 字段）、NPM_REGISTRY 可覆盖
# （受限网络）。产物 base=/ontostudio/（vite.config.ts），由主 nginx :2026 的
# /ontostudio/ 反代到本容器 :3010（前缀透传）。

# ── Build stage: pnpm install + vite build ──────────────────────────────────
FROM node:22-alpine AS build

# corepack registry 先行配置（受限网络下 pnpm 本体下载走同一 mirror，照 frontend/Dockerfile）
ARG NPM_REGISTRY
RUN if [ -n "${NPM_REGISTRY}" ]; then export COREPACK_NPM_REGISTRY="${NPM_REGISTRY}"; fi && \
    corepack enable && corepack install -g pnpm@10.26.2
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi

WORKDIR /app

# 依赖清单先行拷贝：lockfile 不变时本层缓存命中
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# 源码 + 构建配置（.dockerignore 已排除 node_modules/dist）
COPY index.html tsconfig.json tsconfig.node.json vite.config.ts ./
COPY src ./src

# build script = tsc --noEmit + vite build（类型门禁与产物一次成型；base=/ontostudio/）
RUN pnpm build

# ── Runtime stage: nginx 托管静态产物 ────────────────────────────────────────
FROM nginx:alpine

COPY nginx-frontend.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3010
