# Docker 服务编排重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Docker 服务编排拆分为 4 个独立的 compose 文件（核心、扩展、RAGFlow、业务），通过 `docker compose -f` 按需组合启动。

**Architecture:** 4 个 compose 文件共享同一个 `eai-flow-net` bridge 网络。核心文件定义网络和 5 个核心服务，其余文件引用同一网络。Nginx 配置拆分为核心版和完整版。

**Tech Stack:** Docker Compose v2, nginx:alpine, PostgreSQL 16, Elasticsearch 8, RAGFlow, Redis, MinIO

---

## 文件结构

```
docker/
├── docker-compose.yaml              ← 修改：添加 langgraph，定义共享网络
├── docker-compose.extensions.yaml   ← 新建：postgres-ext
├── docker-compose.ragflow.yaml      ← 新建：ragflow + 依赖
├── docker-compose.business.yaml     ← 新建：业务微服务 + 统一 DB
├── docker-compose-dev.yaml          ← 保留：本地开发用
├── docker-compose.external.yaml     ← 保留：兼容旧配置
├── nginx/
│   ├── nginx.conf                   ← 修改：添加 langgraph upstream
│   └── nginx.full.conf              ← 新建：完整路由（含业务+ragflow-web）
├── .env                             ← 修改：统一变量
└── .env.docker                      ← 修改：统一变量
```

---

### Task 1: 创建共享网络定义和更新核心 compose 文件

**Files:**
- Modify: `docker/docker-compose.yaml`
- Modify: `docker/nginx/nginx.conf`

- [ ] **Step 1: 更新 docker-compose.yaml — 添加 langgraph 服务和共享网络**

在 `docker/docker-compose.yaml` 末尾的 networks 部分，将 `deer-flow` 改为 `eai-flow-net`：

```yaml
networks:
  eai-flow-net:
    driver: bridge
```

在 `provisioner` 服务之后、`networks` 之前，添加 langgraph 服务：

```yaml
  # ── LangGraph Server ─────────────────────────────────────────────────
  langgraph:
    build:
      context: ../
      dockerfile: backend/Dockerfile
      args:
        APT_MIRROR: ${APT_MIRROR:-}
        UV_IMAGE: ${UV_IMAGE:-ghcr.io/astral-sh/uv:0.7.20}
        UV_INDEX_URL: ${UV_INDEX_URL:-https://pypi.org/simple}
    container_name: eai-flow-langgraph
    command: sh -c 'cd /app/backend && args="--no-browser --no-reload --host 0.0.0.0 --port 2024 --n-jobs-per-worker $${LANGGRAPH_JOBS_PER_WORKER:-10}" && if [ "$${LANGGRAPH_ALLOW_BLOCKING:-0}" = "1" ]; then args="$$args --allow-blocking"; fi && uv run langgraph dev $$args'
    volumes:
      - ${DEER_FLOW_CONFIG_PATH}:/app/backend/config.yaml:ro
      - ${DEER_FLOW_EXTENSIONS_CONFIG_PATH}:/app/backend/extensions_config.json:ro
      - ${DEER_FLOW_HOME}:/app/backend/.deer-flow
      - ../skills:/app/skills:ro
      - ../backend/.langgraph_api:/app/backend/.langgraph_api
      - ${DEER_FLOW_DOCKER_SOCKET}:/var/run/docker.sock
      - type: bind
        source: ${HOME:?HOME must be set}/.claude
        target: /root/.claude
        read_only: true
        bind:
          create_host_path: true
      - type: bind
        source: ${HOME:?HOME must be set}/.codex
        target: /root/.codex
        read_only: true
        bind:
          create_host_path: true
    environment:
      - CI=true
      - DEER_FLOW_HOME=/app/backend/.deer-flow
      - DEER_FLOW_CONFIG_PATH=/app/backend/config.yaml
      - DEER_FLOW_EXTENSIONS_CONFIG_PATH=/app/backend/extensions_config.json
      - DEER_FLOW_HOST_BASE_DIR=${DEER_FLOW_HOME}
      - DEER_FLOW_HOST_SKILLS_PATH=${DEER_FLOW_REPO_ROOT}/skills
      - DEER_FLOW_SANDBOX_HOST=host.docker.internal
    env_file:
      - ../.env
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - eai-flow-net
    restart: unless-stopped
```

将所有服务的 `networks: - deer-flow` 改为 `networks: - eai-flow-net`（nginx, frontend, gateway, provisioner 共 4 处）。

将 nginx 的 depends_on 添加 langgraph：

```yaml
    depends_on:
      - frontend
      - gateway
      - langgraph
```

- [ ] **Step 2: 更新 nginx.conf — 添加 langgraph upstream 和路由**

在 `docker/nginx/nginx.conf` 的 upstream gateway 之后添加：

```nginx
    upstream langgraph {
        server langgraph:2024;
    }
```

将 `/api/langgraph/` location 的 rewrite 和 proxy_pass 改为：

```nginx
        location /api/langgraph/ {
            rewrite ^/api/langgraph/(.*) /$1 break;
            proxy_pass http://langgraph;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection '';
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
            chunked_transfer_encoding on;
        }
```

- [ ] **Step 3: 验证核心 compose 文件语法**

```bash
cd docker && docker compose -f docker-compose.yaml config --quiet
```

Expected: 无输出（语法正确）

- [ ] **Step 4: 提交**

```bash
git add docker/docker-compose.yaml docker/nginx/nginx.conf
git commit -m "feat(docker): add langgraph to core compose and update nginx routing"
```

---

### Task 2: 创建扩展服务 compose 文件

**Files:**
- Create: `docker/docker-compose.extensions.yaml`

- [ ] **Step 1: 创建 docker-compose.extensions.yaml**

```yaml
# DeerFlow Extensions Services
# Usage: docker compose -f docker-compose.yaml -f docker-compose.extensions.yaml up -d
#
# Services:
#   - postgres-ext: Extensions PostgreSQL (auth, knowledge, etc.)

services:
  # ── Extensions PostgreSQL ──────────────────────────────────────────────
  postgres-ext:
    image: postgres:16-alpine
    container_name: eai-flow-postgres-ext
    environment:
      - POSTGRES_USER=${POSTGRES_EXT_USER:-agentflow}
      - POSTGRES_PASSWORD=${POSTGRES_EXT_PASSWORD:-agentflow123}
      - POSTGRES_DB=${POSTGRES_EXT_DB:-agentflow}
      - POSTGRES_HOST_AUTH_METHOD=md5
    volumes:
      - postgres-ext-data:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_EXT_PORT:-5432}:5432"
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_EXT_USER:-agentflow} -d ${POSTGRES_EXT_DB:-agentflow}"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 10s

volumes:
  postgres-ext-data:

networks:
  eai-flow-net:
    external: true
    name: docker_eai-flow-net
```

- [ ] **Step 2: 验证语法**

```bash
cd docker && docker compose -f docker-compose.yaml -f docker-compose.extensions.yaml config --quiet
```

Expected: 无输出

- [ ] **Step 3: 提交**

```bash
git add docker/docker-compose.extensions.yaml
git commit -m "feat(docker): add extensions compose file with postgres-ext"
```

---

### Task 3: 创建 RAGFlow 服务栈 compose 文件

**Files:**
- Create: `docker/docker-compose.ragflow.yaml`
- Create: `docker/ragflow/.env` (RAGFlow 专用环境变量)

- [ ] **Step 1: 创建 RAGFlow 环境变量文件**

```bash
mkdir -p docker/ragflow
```

创建 `docker/ragflow/.env`：

```env
# RAGFlow Configuration
RAGFLOW_IMAGE=infiniflow/ragflow:latest

# MySQL
MYSQL_ROOT_PASSWORD=ragflow123
MYSQL_DATABASE=ragflow

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Elasticsearch
ES_PORT=9200
ELASTIC_PASSWORD=ragflow123

# Redis
REDIS_PASSWORD=ragflow123
```

- [ ] **Step 2: 创建 docker-compose.ragflow.yaml**

```yaml
# RAGFlow Service Stack
# Usage: docker compose -f docker-compose.yaml -f docker-compose.ragflow.yaml up -d
#
# Services:
#   - ragflow:       RAGFlow API server (port 9380)
#   - ragflow-web:   RAGFlow Web UI (port 9381)
#   - ragflow-es:    Elasticsearch (port 9200)
#   - ragflow-mysql: MySQL (port 3306)
#   - ragflow-redis: Redis (port 6379)
#   - ragflow-minio: MinIO (ports 9000/9001)

services:
  # ── RAGFlow API ────────────────────────────────────────────────────────
  ragflow:
    image: ${RAGFLOW_IMAGE:-infiniflow/ragflow:latest}
    container_name: eai-flow-ragflow
    command: >
      bash -c "python3 -m ragflow.svr.api --host 0.0.0.0 --port 9380"
    environment:
      - ES_HOSTS=http://ragflow-es:9200
      - ES_USERNAME=elastic
      - ES_PASSWORD=${ELASTIC_PASSWORD:-ragflow123}
      - MYSQL_HOST=ragflow-mysql
      - MYSQL_PORT=3306
      - MYSQL_USER=root
      - MYSQL_PASSWORD=${MYSQL_ROOT_PASSWORD:-ragflow123}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-ragflow}
      - REDIS_HOST=ragflow-redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD:-ragflow123}
      - MINIO_ENDPOINT=ragflow-minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
    volumes:
      - ragflow-data:/ragflow
    depends_on:
      ragflow-mysql:
        condition: service_healthy
      ragflow-es:
        condition: service_healthy
      ragflow-redis:
        condition: service_healthy
      ragflow-minio:
        condition: service_healthy
    networks:
      - eai-flow-net
    restart: unless-stopped

  # ── RAGFlow Web UI ─────────────────────────────────────────────────────
  ragflow-web:
    image: ${RAGFLOW_IMAGE:-infiniflow/ragflow:latest}
    container_name: eai-flow-ragflow-web
    command: >
      bash -c "python3 -m ragflow.svr.web --host 0.0.0.0 --port 9381"
    environment:
      - RAGFLOW_API_URL=http://ragflow:9380
    ports:
      - "${RAGFLOW_WEB_PORT:-9381}:9381"
    depends_on:
      - ragflow
    networks:
      - eai-flow-net
    restart: unless-stopped

  # ── Elasticsearch ──────────────────────────────────────────────────────
  ragflow-es:
    image: elasticsearch:8.11.3
    container_name: eai-flow-ragflow-es
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=true
      - ELASTIC_PASSWORD=${ELASTIC_PASSWORD:-ragflow123}
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    volumes:
      - ragflow-es-data:/usr/share/elasticsearch/data
    ports:
      - "${ES_PORT:-9200}:9200"
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -sf -u elastic:${ELASTIC_PASSWORD:-ragflow123} http://localhost:9200/_cluster/health || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 10
      start_period: 30s

  # ── MySQL ──────────────────────────────────────────────────────────────
  ragflow-mysql:
    image: mysql:8.0
    container_name: eai-flow-ragflow-mysql
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD:-ragflow123}
      - MYSQL_DATABASE=${MYSQL_DATABASE:-ragflow}
    volumes:
      - ragflow-mysql-data:/var/lib/mysql
    ports:
      - "${MYSQL_PORT:-3306}:3306"
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD:-ragflow123}"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 15s

  # ── Redis ──────────────────────────────────────────────────────────────
  ragflow-redis:
    image: redis:7-alpine
    container_name: eai-flow-ragflow-redis
    command: redis-server --requirepass ${REDIS_PASSWORD:-ragflow123}
    volumes:
      - ragflow-redis-data:/data
    ports:
      - "${REDIS_PORT:-6379}:6379"
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-ragflow123}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── MinIO ──────────────────────────────────────────────────────────────
  ragflow-minio:
    image: minio/minio:latest
    container_name: eai-flow-ragflow-minio
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
    volumes:
      - ragflow-minio-data:/data
    ports:
      - "${MINIO_API_PORT:-9000}:9000"
      - "${MINIO_CONSOLE_PORT:-9001}:9001"
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  ragflow-data:
  ragflow-es-data:
  ragflow-mysql-data:
  ragflow-redis-data:
  ragflow-minio-data:

networks:
  eai-flow-net:
    external: true
    name: docker_eai-flow-net
```

- [ ] **Step 3: 验证语法**

```bash
cd docker && docker compose -f docker-compose.yaml -f docker-compose.ragflow.yaml config --quiet
```

Expected: 无输出

- [ ] **Step 4: 提交**

```bash
git add docker/docker-compose.ragflow.yaml docker/ragflow/.env
git commit -m "feat(docker): add RAGFlow service stack with ES, MySQL, Redis, MinIO"
```

---

### Task 4: 创建业务微服务 compose 文件

**Files:**
- Create: `docker/docker-compose.business.yaml`
- Create: `docker/postgres-init/` (数据库初始化脚本)

- [ ] **Step 1: 创建数据库初始化脚本目录和脚本**

```bash
mkdir -p docker/postgres-init
```

创建 `docker/postgres-init/init-business-dbs.sh`：

```bash
#!/bin/bash
set -e

# Create databases for business services
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE procurement;
    CREATE DATABASE asset;
    CREATE DATABASE project;
    GRANT ALL PRIVILEGES ON DATABASE procurement TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE asset TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE project TO $POSTGRES_USER;
EOSQL
```

- [ ] **Step 2: 创建 docker-compose.business.yaml**

```yaml
# Business Microservices
# Usage: docker compose -f docker-compose.yaml -f docker-compose.business.yaml up -d
#
# Services:
#   - business-db:            Unified PostgreSQL (procurement, asset, project databases)
#   - procurement-backend:    Procurement API (port 3001)
#   - procurement-frontend:   Procurement UI (port 3000 internal)
#   - asset-backend:          Asset API (port 3002)
#   - asset-frontend:         Asset UI (port 3000 internal)
#   - project-backend:        Project API (port 3003)
#   - project-frontend:       Project UI (port 3000 internal)

services:
  # ── Unified Business PostgreSQL ────────────────────────────────────────
  business-db:
    image: postgres:16-alpine
    container_name: eai-flow-business-db
    environment:
      - POSTGRES_USER=${BUSINESS_DB_USER:-business}
      - POSTGRES_PASSWORD=${BUSINESS_DB_PASSWORD:-business123}
      - POSTGRES_DB=postgres
    volumes:
      - business-db-data:/var/lib/postgresql/data
      - ./postgres-init:/docker-entrypoint-initdb.d:ro
    ports:
      - "${BUSINESS_DB_PORT:-5433}:5432"
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${BUSINESS_DB_USER:-business}"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 10s

  # ── Procurement Backend ────────────────────────────────────────────────
  procurement-backend:
    build:
      context: ../business/procurement-service/backend
      dockerfile: Dockerfile
    container_name: eai-flow-procurement-backend
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 3001 --workers 2
    environment:
      - DATABASE_URL=${PROCUREMENT_DATABASE_URL:-postgresql+asyncpg://${BUSINESS_DB_USER:-business}:${BUSINESS_DB_PASSWORD:-business123}@business-db:5432/procurement}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=1440
      - API_PREFIX=/api/v1
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    env_file:
      - ../.env
    depends_on:
      business-db:
        condition: service_healthy
    networks:
      - eai-flow-net
    restart: unless-stopped

  # ── Procurement Frontend ───────────────────────────────────────────────
  procurement-frontend:
    build:
      context: ../business/procurement-service/frontend-shadcn
      dockerfile: Dockerfile
    container_name: eai-flow-procurement-frontend
    environment:
      - NODE_ENV=production
      - VITE_API_BASE_URL=http://localhost:${PORT:-2026}/procurement
    networks:
      - eai-flow-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3

  # ── Asset Backend ──────────────────────────────────────────────────────
  asset-backend:
    build:
      context: ../business/asset-service/backend
      dockerfile: Dockerfile
    container_name: eai-flow-asset-backend
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 3002 --workers 2
    environment:
      - DATABASE_URL=${ASSET_DATABASE_URL:-postgresql+asyncpg://${BUSINESS_DB_USER:-business}:${BUSINESS_DB_PASSWORD:-business123}@business-db:5432/asset}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=1440
      - API_PREFIX=/api/v1
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    env_file:
      - ../.env
    depends_on:
      business-db:
        condition: service_healthy
    networks:
      - eai-flow-net
    restart: unless-stopped

  # ── Asset Frontend ─────────────────────────────────────────────────────
  asset-frontend:
    build:
      context: ../business/asset-service/frontend
      dockerfile: Dockerfile
    container_name: eai-flow-asset-frontend
    environment:
      - NEXT_PUBLIC_API_BASE_URL=
      - NEXT_PUBLIC_APP_BASE_URL=
    networks:
      - eai-flow-net
    restart: unless-stopped

  # ── Project Backend ────────────────────────────────────────────────────
  project-backend:
    build:
      context: ../business/project-service/backend
      dockerfile: Dockerfile
    container_name: eai-flow-project-backend
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 3003 --workers 2
    environment:
      - DATABASE_URL=${PROJECT_DATABASE_URL:-postgresql+asyncpg://${BUSINESS_DB_USER:-business}:${BUSINESS_DB_PASSWORD:-business123}@business-db:5432/project}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ALGORITHM=HS256
      - ACCESS_TOKEN_EXPIRE_MINUTES=1440
      - API_PREFIX=/api/v1
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    env_file:
      - ../.env
    depends_on:
      business-db:
        condition: service_healthy
    networks:
      - eai-flow-net
    restart: unless-stopped

  # ── Project Frontend ───────────────────────────────────────────────────
  project-frontend:
    build:
      context: ../business/project-service/frontend
      dockerfile: Dockerfile
    container_name: eai-flow-project-frontend
    environment:
      - NEXT_PUBLIC_API_BASE_URL=
      - NEXT_PUBLIC_APP_BASE_URL=
    networks:
      - eai-flow-net
    restart: unless-stopped

volumes:
  business-db-data:

networks:
  eai-flow-net:
    external: true
    name: docker_eai-flow-net
```

- [ ] **Step 3: 验证语法**

```bash
cd docker && docker compose -f docker-compose.yaml -f docker-compose.business.yaml config --quiet
```

Expected: 无输出

- [ ] **Step 4: 提交**

```bash
git add docker/docker-compose.business.yaml docker/postgres-init/
git commit -m "feat(docker): add business services compose with unified PostgreSQL"
```

---

### Task 5: 创建完整版 nginx 配置

**Files:**
- Create: `docker/nginx/nginx.full.conf`

- [ ] **Step 1: 创建 nginx.full.conf**

基于现有 `nginx.external.conf`，创建完整版配置。包含核心路由 + RAGFlow Web + 业务服务路由：

```nginx
# Nginx Full Configuration (core + RAGFlow Web + business services)
# Use with: docker compose -f docker-compose.yaml -f docker-compose.ragflow.yaml -f docker-compose.business.yaml

events {
    worker_connections 1024;
}
pid /tmp/nginx.pid;
http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    access_log /dev/stdout;
    error_log /dev/stderr;

    resolver 127.0.0.11 valid=10s ipv6=off;

    upstream gateway {
        server gateway:8001;
    }

    upstream langgraph {
        server langgraph:2024;
    }

    upstream frontend {
        server frontend:3000;
    }

    upstream ragflow-web {
        server ragflow-web:9381;
    }

    upstream procurement-frontend {
        server procurement-frontend:3000;
    }

    upstream procurement-backend {
        server procurement-backend:3001;
    }

    upstream asset-frontend {
        server asset-frontend:3000;
    }

    upstream asset-backend {
        server asset-backend:3002;
    }

    upstream project-frontend {
        server project-frontend:3000;
    }

    upstream project-backend {
        server project-backend:3003;
    }

    server {
        listen 2026 default_server;
        listen [::]:2026 default_server;
        server_name _;

        proxy_hide_header 'Access-Control-Allow-Origin';
        proxy_hide_header 'Access-Control-Allow-Methods';
        proxy_hide_header 'Access-Control-Allow-Headers';
        proxy_hide_header 'Access-Control-Allow-Credentials';

        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, PATCH, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' '*' always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }

        # ── LangGraph API ───────────────────────────────────────────────
        location /api/langgraph/ {
            rewrite ^/api/langgraph/(.*) /$1 break;
            proxy_pass http://langgraph;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection '';
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
            chunked_transfer_encoding on;
        }

        # ── Gateway API routes ──────────────────────────────────────────
        location /api/models {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/memory {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/mcp {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/skills {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/agents {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location ~ ^/api/threads/[^/]+/uploads {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            client_max_body_size 100M;
            proxy_request_buffering off;
        }

        location ~ ^/api/threads {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /docs {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /redoc {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /openapi.json {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /health {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/sandboxes {
            set $provisioner_upstream provisioner:8002;
            proxy_pass http://$provisioner_upstream;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /api/ {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_pass_header Set-Cookie;
        }

        # ── RAGFlow Web UI ──────────────────────────────────────────────
        location /ragflow/ {
            rewrite ^/ragflow/(.*) /$1 break;
            proxy_pass http://ragflow-web;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        # ── Procurement Microservice ─────────────────────────────────────
        location /procurement/ {
            rewrite ^/procurement/(.*) /$1 break;
            proxy_pass http://procurement-frontend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        location /procurement/api/ {
            rewrite ^/procurement/api/(.*) /api/v1/$1 break;
            proxy_pass http://procurement-backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        # ── Asset Microservice ───────────────────────────────────────────
        location /asset/ {
            rewrite ^/asset/(.*) /$1 break;
            proxy_pass http://asset-frontend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        location /asset/api/ {
            rewrite ^/asset/api/(.*) /api/v1/$1 break;
            proxy_pass http://asset-backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        # ── Project Microservice ─────────────────────────────────────────
        location /project/ {
            rewrite ^/project/(.*) /$1 break;
            proxy_pass http://project-frontend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        location /project/api/ {
            rewrite ^/project/api/(.*) /api/v1/$1 break;
            proxy_pass http://project-backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }

        # ── Frontend catch-all ───────────────────────────────────────────
        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_cache_bypass $http_upgrade;
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
        }
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add docker/nginx/nginx.full.conf
git commit -m "feat(docker): add full nginx config with RAGFlow web and business routes"
```

---

### Task 6: 更新环境变量文件

**Files:**
- Modify: `docker/.env`
- Modify: `docker/.env.docker`

- [ ] **Step 1: 更新 docker/.env**

在现有内容末尾追加：

```env
# ─────────────────────────────────────────────────────────────────────────
# 网络名称 (所有 compose 文件共享)
# ─────────────────────────────────────────────────────────────────────────
NETWORK_NAME=eai-flow-net

# ─────────────────────────────────────────────────────────────────────────
# Extensions PostgreSQL
# ─────────────────────────────────────────────────────────────────────────
POSTGRES_EXT_USER=agentflow
POSTGRES_EXT_PASSWORD=agentflow123
POSTGRES_EXT_DB=agentflow
POSTGRES_EXT_PORT=5432

# ─────────────────────────────────────────────────────────────────────────
# Business PostgreSQL (统一)
# ─────────────────────────────────────────────────────────────────────────
BUSINESS_DB_USER=business
BUSINESS_DB_PASSWORD=business123
BUSINESS_DB_PORT=5433

# ─────────────────────────────────────────────────────────────────────────
# RAGFlow
# ─────────────────────────────────────────────────────────────────────────
RAGFLOW_IMAGE=infiniflow/ragflow:latest
RAGFLOW_WEB_PORT=9381
ELASTIC_PASSWORD=ragflow123
MYSQL_ROOT_PASSWORD=ragflow123
MYSQL_DATABASE=ragflow
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
ES_PORT=9200
MYSQL_PORT=3306
REDIS_PORT=6379
REDIS_PASSWORD=ragflow123
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
```

- [ ] **Step 2: 更新 docker/.env.docker**

在现有内容末尾追加与上述相同的变量段。

- [ ] **Step 3: 提交**

```bash
git add docker/.env docker/.env.docker
git commit -m "feat(docker): add environment variables for all service groups"
```

---

### Task 7: 更新 .gitignore 和验证完整启动

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 添加 RAGFlow 数据目录到 .gitignore**

在 `.gitignore` 末尾追加：

```
# RAGFlow runtime data
docker/ragflow/
```

- [ ] **Step 2: 验证核心服务启动**

```bash
cd docker && docker compose -f docker-compose.yaml config --quiet && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: 验证核心+扩展启动**

```bash
cd docker && docker compose -f docker-compose.yaml -f docker-compose.extensions.yaml config --quiet && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: 验证核心+扩展+RAGFlow 启动**

```bash
cd docker && docker compose -f docker-compose.yaml -f docker-compose.extensions.yaml -f docker-compose.ragflow.yaml config --quiet && echo "OK"
```

Expected: `OK`

- [ ] **Step 5: 验证全部服务启动**

```bash
cd docker && docker compose -f docker-compose.yaml -f docker-compose.extensions.yaml -f docker-compose.ragflow.yaml -f docker-compose.business.yaml config --quiet && echo "OK"
```

Expected: `OK`

- [ ] **Step 6: 提交**

```bash
git add .gitignore
git commit -m "chore: add ragflow runtime data to gitignore"
```

---

## 启动命令速查

```bash
# 仅核心服务 (nginx, frontend, gateway, langgraph, provisioner)
docker compose -f docker/docker-compose.yaml up -d

# 核心 + Extensions PostgreSQL
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml up -d

# 核心 + Extensions + RAGFlow
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml up -d

# 全部服务
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml -f docker/docker-compose.business.yaml up -d

# 停止全部
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml -f docker/docker-compose.business.yaml down
```

## 端口分配

| 端口 | 服务 | 说明 |
|------|------|------|
| 2026 | nginx | 统一入口 |
| 3000 | frontend | Next.js |
| 8001 | gateway | FastAPI |
| 2024 | langgraph | LangGraph |
| 8002 | provisioner | K8s Sandbox |
| 5432 | postgres-ext | Extensions DB |
| 5433 | business-db | 业务统一 DB |
| 9380 | ragflow | RAGFlow API |
| 9381 | ragflow-web | RAGFlow Web UI |
| 9200 | ragflow-es | Elasticsearch |
| 3306 | ragflow-mysql | MySQL |
| 6379 | ragflow-redis | Redis |
| 9000 | ragflow-minio | MinIO API |
| 9001 | ragflow-minio | MinIO Console |
