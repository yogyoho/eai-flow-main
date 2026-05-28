# Asset Service Frontend Dockerfile
# Supports two modes:
#   dev: development mode with hot reload (default)
#   prod: production build

FROM node:22-alpine AS base

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack install -g pnpm@10.26.2

# Copy package files
COPY package.json ./

# Install dependencies
RUN pnpm install

# Copy source code
COPY . .

# Dev stage - run dev server
FROM base AS dev

EXPOSE 3000

CMD ["pnpm", "dev"]

# Production stage - build and serve
FROM base AS prod

# Build the application
RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "start"]
