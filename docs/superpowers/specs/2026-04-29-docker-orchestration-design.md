# Docker 服务编排重构设计

**日期**: 2026-04-29
**状态**: 已批准

## 背景

项目从 DeerFlow main 分支拉取后，原有 5 个核心服务（nginx, frontend, gateway, langgraph, provisioner）需要与扩展服务（postgres-ext, ragflow 及其依赖）以及业务微服务（procurement, asset, project）统一编排。

当前问题：
- `docker-compose.yaml` 仅含 4 个核心服务（缺少 langgraph）
- `docker-compose-dev.yaml` 混杂了 postgres-ext 和核心服务
- `docker-compose.external.yaml` 将所有服务堆在一起，难以维护
- RAGFlow 及其依赖服务未定义，仅通过环境变量引用外部容器

## 设计目标

1. **关注点分离**：每个 compose 文件只负责一类服务
2. **按需组合**：通过 `docker compose -f` 按需组合启动
3. **单一网络**：所有服务共享一个 bridge 网络，通过服务名互访
4. **配置统一**：环境变量集中在 `.env` 文件中

## 文件结构

```
docker/
├── docker-compose.yaml              # 核心服务
├── docker-compose.extensions.yaml   # 扩展 PostgreSQL
├── docker-compose.ragflow.yaml      # RAGFlow + 依赖
├── docker-compose.business.yaml     # 业务微服务
├── nginx/
│   ├── nginx.conf                   # 核心路由配置
│   └── nginx.full.conf              # 完整路由（含业务服务）
├── .env                             # 主环境变量
└── .env.docker                      # Docker 专用环境变量
```

## 各 Compose 文件职责

### 1. docker-compose.yaml — 核心服务

| 服务 | 端口 | 说明 |
|------|------|------|
| nginx | 2026 | 反向代理，统一路由入口 |
| frontend | 3000 | Next.js 前端 |
| gateway | 8001 | FastAPI 网关 + Agent 运行时 |
| langgraph | 2024 | LangGraph 服务器 |
| provisioner | 8002 | K8s Sandbox 管理（可选） |

网络：`eai-flow-net`（bridge）

### 2. docker-compose.extensions.yaml — 扩展数据库

| 服务 | 端口 | 说明 |
|------|------|------|
| postgres-ext | 5432 | Extensions PostgreSQL（auth, knowledge 等）|

依赖核心网络 `eai-flow-net`。

### 3. docker-compose.ragflow.yaml — RAGFlow 服务栈

| 服务 | 端口 | 说明 |
|------|------|------|
| ragflow | 9380 | RAGFlow RAG 引擎 |
| ragflow-es | 9200 | Elasticsearch（文档索引）|
| ragflow-mysql | 3306 | RAGFlow 元数据存储 |
| ragflow-redis | 6379 | RAGFlow 缓存 |
| ragflow-minio | 9000/9001 | 对象存储（文档文件）|

所有服务名称加 `ragflow-` 前缀以避免命名冲突。依赖核心网络 `eai-flow-net`。

### 4. docker-compose.business.yaml — 业务微服务

| 服务 | 端口 | 说明 |
|------|------|------|
| procurement-backend | 3001 | 采购服务后端 |
| procurement-frontend | 3000 | 采购服务前端 |
| procurement-db | 5432 | 采购数据库 |
| asset-backend | 3002 | 资产服务后端 |
| asset-frontend | 3000 | 资产服务前端 |
| asset-db | 5432 | 资产数据库 |
| project-backend | 3003 | 项目服务后端 |
| project-frontend | 3000 | 项目服务前端 |
| project-db | 5432 | 项目数据库 |

依赖核心网络 `eai-flow-net`。

## 网络设计

```
eai-flow-net (bridge)
├── nginx
├── frontend
├── gateway
├── langgraph
├── provisioner
├── postgres-ext
├── ragflow
├── ragflow-es
├── ragflow-mysql
├── ragflow-redis
├── ragflow-minio
├── procurement-backend
├── procurement-frontend
├── procurement-db
├── asset-backend
├── asset-frontend
├── asset-db
├── project-backend
├── project-frontend
└── project-db
```

## Nginx 路由设计

### 核心路由（nginx.conf）

```
/api/langgraph/*  → langgraph:2024
/api/models       → gateway:8001
/api/memory       → gateway:8001
/api/mcp          → gateway:8001
/api/skills       → gateway:8001
/api/agents       → gateway:8001
/api/extensions/* → gateway:8001
/api/kf/*         → gateway:8001
/api/sandboxes    → provisioner:8002
/api/*            → gateway:8001
/docs, /redoc     → gateway:8001
/health           → gateway:8001
/*                → frontend:3000
```

### 业务路由（nginx.full.conf，追加）

```
/procurement/*      → procurement-frontend:3000
/procurement/api/*  → procurement-backend:3001
/asset/*            → asset-frontend:3000
/asset/api/*        → asset-backend:3002
/project/*          → project-frontend:3000
/project/api/*      → project-backend:3003
```

## 启动命令

```bash
# 仅核心服务
docker compose -f docker/docker-compose.yaml up -d

# 核心 + 扩展数据库
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml up -d

# 核心 + 扩展 + RAGFlow
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml up -d

# 全部服务
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml -f docker/docker-compose.business.yaml up -d

# 停止所有
docker compose -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml -f docker/docker-compose.ragflow.yaml -f docker/docker-compose.business.yaml down
```

## 环境变量

统一使用 `docker/.env` 和 `docker/.env.docker`：

```env
# 网络
NETWORK_NAME=eai-flow-net

# PostgreSQL (extensions)
POSTGRES_EXT_USER=agentflow
POSTGRES_EXT_PASSWORD=agentflow123
POSTGRES_EXT_DB=agentflow

# RAGFlow
RAGFLOW_VERSION=latest
RAGFLOW_MYSQL_PASSWORD=ragflow123
RAGFLOW_MINIO_ACCESS_KEY=minioadmin
RAGFLOW_MINIO_SECRET_KEY=minioadmin

# JWT
JWT_SECRET_KEY=...

# Better Auth
BETTER_AUTH_SECRET=...
```

## 数据卷

```yaml
volumes:
  # 核心
  gateway-venv:
  gateway-uv-cache:
  # 扩展
  postgres-ext-data:
  # RAGFlow
  ragflow-es-data:
  ragflow-mysql-data:
  ragflow-minio-data:
  # 业务
  procurement-db-data:
  asset-db-data:
  project-db-data:
```

## 迁移步骤

1. 创建 `docker-compose.extensions.yaml`（从 dev 文件提取 postgres-ext）
2. 创建 `docker-compose.ragflow.yaml`（新建）
3. 创建 `docker-compose.business.yaml`（从 external 文件提取）
4. 更新 `docker-compose.yaml`（添加 langgraph 服务）
5. 更新 nginx 配置（拆分核心路由和业务路由）
6. 更新 `.env` 文件（统一变量名）
7. 验证各组合启动方式
