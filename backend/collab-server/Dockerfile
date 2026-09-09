FROM node:22-alpine

WORKDIR /app

# EAI-CUSTOM (bug-3210): 裸 npm install 在 node:22-alpine 自带 npm 上触发
# arborist "edgesOut" 崩溃,镜像一度停在 2026-06-10。改用 lockfile + npm ci
# (确定性安装,lockfile 由 host npm 11 生成,lockfileVersion 3 兼容 npm 9+)。
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

EXPOSE 8002

CMD ["npm", "start"]
