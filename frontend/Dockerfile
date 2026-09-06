# Frontend Dockerfile
# Supports two targets:
#   --target dev   — install deps only, run `pnpm dev` at container start
#   --target prod  — full build baked in, run `pnpm start` at container start (default if no --target is specified)

ARG PNPM_STORE_PATH=/root/.local/share/pnpm/store
ARG NPM_REGISTRY

# ── Base: shared setup ────────────────────────────────────────────────────────
FROM node:22-alpine AS base
ARG PNPM_STORE_PATH
ARG NPM_REGISTRY
# Configure corepack registry before installing pnpm so the download itself
# succeeds in restricted networks (COREPACK_NPM_REGISTRY controls where
# corepack fetches package managers from).
RUN if [ -n "${NPM_REGISTRY}" ]; then \
      export COREPACK_NPM_REGISTRY="${NPM_REGISTRY}"; \
    fi && \
    corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
# Optionally override npm registry for restricted networks (e.g. NPM_REGISTRY=https://registry.npmmirror.com)
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi
WORKDIR /app
COPY frontend ./frontend

# ── Dev: install only, CMD is overridden by docker-compose ───────────────────
FROM base AS dev
RUN cd /app/frontend && pnpm install --frozen-lockfile
EXPOSE 3000

# ── Builder: install + compile Next.js ───────────────────────────────────────
FROM base AS builder
RUN cd /app/frontend && pnpm install --frozen-lockfile
# Skip env validation — runtime vars are injected by nginx/container
# App version stamp for the About page. Nightly CI passes
# APP_VERSION=<base>-nightly.<date>-<sha>; release/local builds leave it empty
# and the frontend falls back to package.json's version.
ARG APP_VERSION=""
ENV NEXT_PUBLIC_APP_VERSION=$APP_VERSION
# EAI-CUSTOM: 按客户品牌化（构建期注入 NEXT_PUBLIC_*，next build 内联烘焙进产物）。
# offline-export.sh 通过 --build-arg BRAND_NAME/BRAND_FOOTER 传入（来自 deploy.conf）。
ARG BRAND_NAME=""
ARG BRAND_FOOTER=""
ENV NEXT_PUBLIC_BRAND_NAME=$BRAND_NAME
ENV NEXT_PUBLIC_BRAND_FOOTER=$BRAND_FOOTER
# EAI-CUSTOM (2026-09-06): 设置页服务链接的端口/开关——NEXT_PUBLIC_* 是构建期内联，
# 运行时 env 对客户端组件无效。ARG 默认 = dev 端口；offline-export.sh 构建离线包时
# 经 --build-arg 传入生产端口（19381/19101）并关闭遗留服务链接。
ARG NEXT_PUBLIC_RAGFLOW_WEB_PORT="9381"
ARG NEXT_PUBLIC_MINIO_CONSOLE_PORT="9001"
ARG NEXT_PUBLIC_SHOW_LEGACY_SERVICE_LINKS="true"
ENV NEXT_PUBLIC_RAGFLOW_WEB_PORT=$NEXT_PUBLIC_RAGFLOW_WEB_PORT
ENV NEXT_PUBLIC_MINIO_CONSOLE_PORT=$NEXT_PUBLIC_MINIO_CONSOLE_PORT
ENV NEXT_PUBLIC_SHOW_LEGACY_SERVICE_LINKS=$NEXT_PUBLIC_SHOW_LEGACY_SERVICE_LINKS
RUN cd /app/frontend && SKIP_ENV_VALIDATION=1 pnpm build

# ── Prod: minimal runtime with pre-built output ───────────────────────────────
FROM node:22-alpine AS prod
ARG PNPM_STORE_PATH
ARG NPM_REGISTRY
RUN if [ -n "${NPM_REGISTRY}" ]; then \
      export COREPACK_NPM_REGISTRY="${NPM_REGISTRY}"; \
    fi && \
    corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
RUN if [ -n "${NPM_REGISTRY}" ]; then pnpm config set registry "${NPM_REGISTRY}"; fi
WORKDIR /app
COPY --from=builder /app/frontend ./frontend
EXPOSE 3000
CMD ["sh", "-c", "cd /app/frontend && pnpm start"]
