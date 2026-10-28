FROM node:22-alpine AS build

WORKDIR /workspace
ENV CI=1
RUN corepack enable

# The shared package is supplied as a named build context so the frontend image
# can be built without lifting the whole repository into the Docker context.
WORKDIR /workspace/packages/workflow-embed
# Install dependencies from the lockfile before copying sources so component
# changes do not invalidate the (network-heavy) dependency layer.
COPY --from=workflow_embed package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY --from=workflow_embed . ./
RUN pnpm build

WORKDIR /workspace/business/sales-service/frontend
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/business/sales-service/frontend/dist /usr/share/nginx/html
EXPOSE 80
