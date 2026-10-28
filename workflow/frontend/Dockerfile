FROM node:20-alpine AS base
RUN corepack enable
# Default to the npmmirror registry for fast installs in China; override with
# NPM_REGISTRY=https://registry.npmjs.org to build against the official registry.
ARG NPM_REGISTRY=https://registry.npmmirror.com
ENV npm_config_registry=$NPM_REGISTRY
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile \
    --fetch-retries=5 \
    --fetch-retry-mintimeout=10000 \
    --fetch-retry-maxtimeout=120000 \
    --fetch-timeout=120000

FROM base AS builder
# Pages live at the app root; basePath supplies the single /workflow prefix for
# routes, RSC payloads and /_next assets behind nginx.
ARG NEXT_PUBLIC_WORKFLOW_API=/workflow/api
ARG NEXT_PUBLIC_BASE_PATH=/workflow
ENV NEXT_PUBLIC_WORKFLOW_API=$NEXT_PUBLIC_WORKFLOW_API \
    NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Run the installed Next binary directly; `pnpm build` can make Corepack
# re-download pnpm in the builder stage and fail on restricted networks.
RUN node ./node_modules/next/dist/bin/next build --webpack

FROM node:20-alpine AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3020
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
RUN chown -R nextjs:nodejs /app
USER nextjs
EXPOSE 3020
CMD ["node", "server.js"]
