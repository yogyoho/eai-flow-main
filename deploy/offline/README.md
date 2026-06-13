# EAI-Flow 生产离线部署

## 快速开始

```bash
# 1. 修改配置（首次部署前必须修改！）
vi .env          # 修改 BETTER_AUTH_SECRET, DEER_FLOW_ROOT
vi config.yaml   # 修改内网 LLM 的 model, base_url

# 2. 部署
chmod +x deploy.sh
./deploy.sh

# 3. 访问
# http://<服务器IP>:4026
# 默认管理员: admin@eai-flow.com / Admin@2026（自动创建）
```

## 与开发环境共存

生产部署使用独立的 Docker 资源，与开发环境 (`eai-docker`) 完全隔离：

| 资源 | 开发环境 | 生产环境 |
|------|----------|----------|
| 项目名 | `eai-docker` | `eai-prod` |
| 网络 | `eai-docker_eai-flow-net` | `eai-prod_eai-flow-net` |
| nginx 端口 | `2026` | `4026`（可通过 `.env` 的 PORT 修改）|
| 容器名前缀 | `deer-flow-*` | `prod-eai-flow-*` |
| 卷名前缀 | 无前缀 | `prod-*` |

**两台环境可以同时运行，互不干扰。**

## 目录结构

```
deploy/offline/
├── .env                          # 环境变量（已预配置）
├── config.yaml                   # 主配置（已预配置内网 LLM 模板）
├── extensions_config.json        # 扩展配置（MCP/技能）
├── docker-compose.yaml           # 核心服务 (nginx + frontend + gateway)
├── docker-compose.extensions.yaml # 扩展服务 (PostgreSQL + Collab)
├── docker-compose.temporal.yaml  # 工作流引擎（可选）
├── docker-compose.ragflow.yaml   # RAGFlow 知识库（可选）
├── nginx/
│   └── nginx.conf                # 生产 nginx 配置
├── deploy.sh                     # 一键部署脚本
├── data/                         # 持久化数据（自动创建）
├── logs/                         # 日志（自动创建）
├── skills/                       # 技能目录
└── mcp-server/                   # MCP 服务器
```

## 关键配置说明

### .env 必填项

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_ROOT` | 部署目录的绝对路径，如 `/opt/eai-flow-offline` |
| `BETTER_AUTH_SECRET` | 会话加密密钥，用 `openssl rand -base64 32` 生成 |
| `PORT` | 对外端口，默认 `4026` |

### config.yaml 必填项

修改 `models` 段中的内网 LLM 配置：

```yaml
models:
  - name: intranet-llm
    display_name: 内网大模型
    model: your-model-name-here        # 必改
    base_url: http://your-llm:port/v1/  # 必改
    api_key: $INTERNAL_LLM_API_KEY
```

### LLM 网络地址说明

| LLM 部署位置 | base_url 写法 |
|-------------|--------------|
| 本机非 Docker | `http://host.docker.internal:端口/v1` |
| 本机 Docker 容器 | `http://容器名:端口/v1` |
| 同网段其他服务器 | `http://内网IP:端口/v1` |

## 常用命令

```bash
./deploy.sh              # 部署全部服务
./deploy.sh status       # 查看服务状态
./deploy.sh logs gateway # 查看 Gateway 日志
./deploy.sh down         # 停止全部服务
./deploy.sh restart      # 重启全部服务
```

## 部署架构

```
浏览器 → Nginx (:4026)
           ├── /api/langgraph/* → Gateway (8001)
           ├── /api/*           → Gateway (8001)
           ├── /api/collab      → Collab (8002, WebSocket)
           └── /*               → Frontend (3000, Next.js)
```

## 与开发环境端口隔离

| 服务 | 开发端口 | 生产端口 | 说明 |
|------|----------|----------|------|
| nginx | `2026` | `4026` | 统一入口 |
| postgres | `5432` | `15432` | 避免与服务器本地 PG 冲突 |
| ES | `9200` | `19200` | 同上 |
| MySQL | `3306` | `13306` | 同上 |
| Redis | `6379` | `16379` | 同上 |
| MinIO | `9000`/`9001` | `19100`/`19101` | 同上 |
| RAGFlow | `9380`/`9381` | `19380`/`19381` | 同上 |
| Temporal | `7233` | `17233` | 同上 |

## 部署注意事项

### 首次部署需手动创建 Temporal 用户

Temporal 需要 PostgreSQL 中存在 `temporal` 用户和数据库。部署后执行：

```bash
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "CREATE USER temporal WITH SUPERUSER PASSWORD 'temporal_password';"
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "CREATE DATABASE temporal OWNER temporal;"
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "CREATE DATABASE temporal_visibility OWNER temporal;"
docker compose -p eai-prod restart temporal
```

### 硬编码端口修复记录

原始代码中存在多处硬编码端口。修复策略：所有服务端 API 调用回退值优先使用 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` 环境变量。

| 文件 | 原值 | 修复 |
|------|------|------|
| `frontend/src/app/api/memory/route.ts` | `127.0.0.1:4001` | 优先 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` → `127.0.0.1:8001` |
| `frontend/src/core/config/index.ts` | `localhost:4026` | 使用 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` |
| `frontend/src/extensions/collab/useCollab.ts` | `ws://localhost:8002` | 生产通过 nginx 代理 `/api/collab` |
| `frontend/src/extensions/collab/aiTransport.ts` | `localhost:8001` | 支持 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` |
| `frontend/src/extensions/knowledge-factory/law-library-api.ts` | `localhost:4026` | 使用 `DEER_FLOW_INTERNAL_GATEWAY_BASE_URL` |

### 依赖声明修复

`python-docx` 已添加到 `backend/pyproject.toml` → `[project] dependencies`，并更新了 `uv.lock`。此前开发环境通过 `markitdown[all]` 间接依赖可用，生产环境 `uv sync` 严格按 lockfile 安装会遗漏。
