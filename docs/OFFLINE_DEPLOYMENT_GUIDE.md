# EAI-Flow 内网离线部署操作手册

> 版本 2.0 | 2026-06-10 | 本机验证通过

## 目录

1. [概述](#概述)
2. [第一步：有网开发机 — 导出镜像并打包](#第一步有网开发机--导出镜像并打包)
3. [第二步：目标服务器 — 部署](#第二步目标服务器--部署)
4. [第三步：验证](#第三步验证)
5. [手动部署（不使用 installsh）](#手动部署不使用-installsh)
6. [配置系统](#配置系统)
7. [常用运维命令](#常用运维命令)
8. [故障排查](#故障排查)
9. [附录](#附录)

---

## 概述

EAI-Flow 支持完整的离线部署。离线包内含所有 Docker 镜像、编排文件、预配置文件和一键部署脚本。

### 部署架构

```
浏览器 → Nginx (:4026)
              ├── Frontend (Next.js)              ← 预构建镜像
              ├── Gateway (FastAPI + Agent)        ← 预构建镜像
              ├── PostgreSQL (extensions)          ← 公共镜像
              ├── Collab Server (WebSocket)        ← 预构建镜像
              ├── Temporal Server                  ← 公共镜像
              └── RAGFlow 套件                     ← 公共镜像
```

### 离线包内容

| 类别 | 内容 | 大小 |
|------|------|------|
| 公共镜像 | nginx、postgres、temporal | ~350MB |
| 自建镜像 | gateway、frontend、collab | ~1.1GB |
| RAGFlow 套件 | ragflow、elasticsearch、mysql、redis、minio | ~3.2GB |
| 配置文件 | compose 文件、nginx 配置、.env、config.yaml | < 50KB |
| 脚本 | install.sh、load-images.sh | < 20KB |
| **压缩包总计** | | **约 4.6GB** |

---

## 第一步：有网开发机 — 导出镜像并打包

> 在可联网的开发机器上执行。如已提供打包好的 `.tar.gz`，跳过此步骤。

### 1.1 前置条件

```bash
docker --version       # >= 24.0
docker compose version  # >= 2.20

# 确认在项目根目录
cd /path/to/eai-flow

# 确认开发环境镜像已构建（如未构建先执行 make docker-start）
docker images | grep deer-flow
```

### 1.2 执行打包

```bash
# 导出全部服务（RAGFlow 为必选项）
bash scripts/offline-export.sh
```

打包过程约 10-20 分钟，完成后在项目根目录生成：

```
eai-flow-offline-v<version>-<date>.tar.gz
```

解压后的目录结构：

```
eai-flow-offline-<version>-<date>/
├── images/                                    # Docker 镜像 tar 文件
│   ├── nginx_alpine.tar
│   ├── postgres_16-alpine.tar
│   ├── temporalio_auto-setup_1270.tar
│   ├── deer-flow-gateway_latest.tar           # 自建
│   ├── deer-flow-frontend_latest.tar          # 自建
│   └── eai-flow-collab_latest.tar             # 自建
├── docker/                                    # Compose 文件和配置
│   ├── docker-compose.yaml                   # 核心服务编排
│   ├── docker-compose.extensions.yaml         # 扩展服务编排
│   ├── docker-compose.temporal.yaml           # 工作流引擎编排
│   ├── docker-compose.ragflow.yaml            # RAGFlow 编排
│   └── nginx/nginx.conf                       # Nginx 配置
├── config.yaml                                # 预配置（8 个云端模型 + 内网模板）
├── extensions_config.json                     # MCP/技能配置
├── .env                                       # 预配置 Linux 环境变量
├── install.sh                                 # 一键部署脚本
├── load-images.sh                             # 批量导入镜像脚本
├── skills/                                    # 技能目录
└── mcp-server/                                # MCP 服务器
```

### 1.3 传输到目标服务器

```bash
scp eai-flow-offline-*.tar.gz root@<目标服务器IP>:/opt/
```

---

## 第二步：目标服务器 — 部署

> 在离线目标服务器上执行。

### 2.1 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 磁盘 | 40 GB | 100 GB SSD |
| 架构 | x86_64 | x86_64 |

### 2.2 软件要求

| 软件 | 版本 |
|------|------|
| 操作系统 | openEuler 22.03+ / CentOS 8+ / Ubuntu 22.04+ / Debian 12+ |
| Docker Engine | >= 24.0 + docker compose 插件 |
| curl | 任意版本 |

### 2.3 Docker 离线安装

如目标服务器未安装 Docker：

**在有网机器上下载：**

```bash
# Docker 二进制包
wget https://download.docker.com/linux/static/stable/x86_64/docker-28.0.4.tgz

# docker-compose 插件
wget https://github.com/docker/compose/releases/download/v2.34.0/docker-compose-linux-x86_64

# 传输
scp docker-28.0.4.tgz docker-compose-linux-x86_64 root@<目标IP>:/opt/
```

**在目标服务器上安装：**

```bash
cd /opt
tar xzf docker-28.0.4.tgz
cp docker/* /usr/bin/
rm -rf docker/

# compose 插件
mkdir -p /usr/local/lib/docker/cli-plugins
cp docker-compose-linux-x86_64 /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# systemd 服务
groupadd docker 2>/dev/null || true
cat > /etc/systemd/system/docker.service << 'SYSTEMD'
[Unit]
Description=Docker Application Container Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/dockerd
ExecReload=/bin/kill -s HUP $MAINPID
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TimeoutStartSec=0
Delegate=yes
KillMode=process
Restart=on-failure
StartLimitBurst=3
StartLimitInterval=60s

[Install]
WantedBy=multi-user.target
SYSTEMD

mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'JSON'
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "100m", "max-file": "3" },
  "storage-driver": "overlay2",
  "data-root": "/var/lib/docker"
}
JSON

systemctl daemon-reload
systemctl enable docker
systemctl start docker

docker --version
docker compose version
```

### 2.4 端口检查

```bash
# 确认以下端口未被占用（可在 .env 中修改）
ss -tlnp | grep -E "4026|15432|17233"
```

### 2.5 解压并配置

```bash
cd /opt
tar xzf eai-flow-offline-*.tar.gz
cd eai-flow-offline-*/
```

**首次部署必须修改以下配置：**

```bash
vi .env
```

| 必须修改 | 说明 |
|----------|------|
| `DEER_FLOW_ROOT` | 改为当前目录绝对路径，如 `/opt/eai-flow-offline-v2.0-xxx` |
| `BETTER_AUTH_SECRET` | 用 `openssl rand -base64 32` 生成强随机字符串 |
| `AGNES_API_KEY` 等 | 内网可连外网时填写对应云端 API Key |

```bash
vi config.yaml
```

| 场景 | 操作 |
|------|------|
| 内网可连外网 | 无需修改，8 个云端模型直接可用 |
| 完全离线 | 取消注释末尾内网 LLM 模板，修改 `model` 和 `base_url` |

### 2.6 一键部署

```bash
./install.sh
```

脚本自动执行：

1. 环境检查（Docker 版本、磁盘空间、内存、端口）
2. 导入所有镜像（`load-images.sh`）
3. 创建 Docker 网络 `eai-prod_eai-flow-net`
4. 校验配置文件
5. 启动全部服务
6. 等待 PostgreSQL 和 Gateway 健康检查通过
7. 执行数据库迁移
8. 创建默认管理员 `admin@eai-flow.com` / `Admin@2026`

---

## 第三步：验证

### 3.1 服务状态

```bash
docker compose -p eai-prod ps
```

预期 11 个容器全部 `Up` (healthy)：

| 容器名 | 服务 | 端口 |
|--------|------|------|
| prod-eai-flow-nginx | 反向代理 | 4026 |
| prod-eai-flow-frontend | Next.js 前端 | 3000（内部） |
| prod-eai-flow-gateway | API 网关 + Agent 运行时 | 8001（内部） |
| prod-eai-flow-postgres-ext | 扩展数据库 | 15432 |
| prod-eai-flow-collab | 协同编辑 WebSocket | 8002（内部） |
| prod-eai-flow-temporal | 工作流引擎 | 17233 |
| prod-eai-flow-ragflow | RAGFlow 知识库 | 19380/19381 |
| prod-eai-flow-ragflow-es | Elasticsearch | 19200 |
| prod-eai-flow-ragflow-mysql | MySQL | 13306 |
| prod-eai-flow-ragflow-redis | Redis | 16379 |
| prod-eai-flow-ragflow-minio | MinIO 对象存储 | 19000/19001 |

### 3.2 健康检查

```bash
# Gateway 健康
curl http://localhost:4026/health

# 许可证状态
curl http://localhost:4026/api/license/status

# 模型列表
curl http://localhost:4026/api/models
```

### 3.3 访问系统

浏览器打开 `http://<服务器IP>:4026`

| 字段 | 值 |
|------|-----|
| 邮箱 | `admin@eai-flow.com` |
| 密码 | `Admin@2026` |

> ⚠️ **首次登录后请立即修改密码！**

---

## 手动部署（不使用 install.sh）

```bash
# 1. 解压并导入镜像
cd /opt/eai-flow-offline-*/
./load-images.sh

# 2. 创建 Docker 网络
docker network create eai-prod_eai-flow-net

# 3. 创建运行时目录
mkdir -p data logs skills mcp-server

# 4. 启动核心服务
docker compose -p eai-prod \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.temporal.yaml \
  up -d

# 5. 启动 RAGFlow 知识库
docker compose -p eai-prod -f docker/docker-compose.ragflow.yaml up -d

# 6. 等待 Gateway 就绪
curl -s --retry 20 --retry-delay 5 http://localhost:4026/health

# 7. 初始化管理员
curl -X POST http://localhost:4026/api/v1/auth/initialize \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}'
```

---

## 配置系统

### 编辑 .env

```bash
vi .env
```

关键变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEER_FLOW_ROOT` | 部署目录绝对路径 | 需修改 |
| `BETTER_AUTH_SECRET` | 会话加密密钥 | 需修改 |
| `PORT` | Nginx 对外端口 | `4026` |
| `POSTGRES_EXT_PASSWORD` | 数据库密码 | `agentflow123` |
| `AGNES_API_KEY` | Agnes 模型 API Key | 需填写 |
| `ZHIPU_API_KEY` | 智谱模型 API Key | 需填写 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 需填写 |
| `SILICONFLOW_API_KEY` | SiliconFlow API Key | 需填写 |
| `INTERNAL_LLM_API_KEY` | 内网 LLM Key | `sk-placeholder` |

### 配置 LLM — config.yaml

**内网可连外网**：无需修改，8 个云端模型直接可用。

**完全离线**：取消注释文件末尾的内网 LLM 模板，修改为实际的内网 LLM 配置：

```yaml
models:
  - name: intranet-llm
    display_name: 内网大模型
    use: langchain_openai:ChatOpenAI
    model: qwen-plus                    # 改为实际模型名
    api_key: $INTERNAL_LLM_API_KEY
    base_url: http://192.168.1.100:8080/v1/   # 改为实际地址
    request_timeout: 600.0
    max_retries: 2
    max_tokens: 8192
    temperature: 0.7
    supports_vision: false
    supports_thinking: false
```

**Docker 网络注意事项：**

| LLM 部署位置 | base_url 写法 |
|-------------|--------------|
| 本机（非 Docker） | `http://host.docker.internal:端口/v1` |
| 本机（Docker 容器内） | `http://容器名:端口/v1` |
| 同网段其他服务器 | `http://内网IP:端口/v1` |

---

## 常用运维命令

### 服务管理

```bash
# 查看状态
docker compose -p eai-prod ps

# 查看实时日志
docker compose -p eai-prod logs -f

# 查看指定服务日志
docker compose -p eai-prod logs -f gateway

# 重启 Gateway（修改 config.yaml 后）
docker compose -p eai-prod restart gateway

# 停止所有服务
docker compose -p eai-prod down

# 启动所有服务
docker compose -p eai-prod up -d
```

### 数据管理

```bash
# 备份数据库
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker exec -i prod-eai-flow-postgres-ext psql -U agentflow agentflow < backup.sql

# 备份持久化数据
tar czf data-backup.tar.gz data/ logs/ config.yaml .env
```

---

## 故障排查

### 问题 1：nginx 返回 502 Bad Gateway

```bash
# 检查 Gateway 是否健康
docker logs prod-eai-flow-gateway --tail 20
```

常见原因：
- Gateway 启动中（`uv sync` 需 1-2 分钟）→ 等待后重试
- 缺少 Python 依赖 → 检查日志中是否有 `ModuleNotFoundError`

### 问题 2：Gateway 反复重启

```bash
# 查看完整启动日志
docker logs prod-eai-flow-gateway 2>&1 | grep -i "error\|ModuleNotFoundError"
```

常见原因：
- `config.yaml` 格式错误 → 检查 YAML 缩进
- 端口冲突 → `ss -tlnp | grep 4026`

### 问题 3：数据库连接失败 / Extensions 不可用

```bash
# 检查 postgres-ext 是否健康
docker compose -p eai-prod ps postgres-ext

# 手动测试连接
docker exec prod-eai-flow-postgres-ext pg_isready -U agentflow
```

如果 `.env` 中缺少 `EXTENSIONS_DB_HOST=postgres-ext`，Gateway 会尝试连接 `localhost:5432`（容器自身），导致失败。确认 `.env` 包含：

```
EXTENSIONS_DB_HOST=postgres-ext
EXTENSIONS_DB_PORT=5432
EXTENSIONS_DB_USER=agentflow
EXTENSIONS_DB_PASSWORD=agentflow123
EXTENSIONS_DB_NAME=agentflow
```

### 问题 4：Temporal 反复重启

```bash
docker logs prod-eai-flow-temporal --tail 10
```

如日志显示 `password authentication failed for user "temporal"`，需手动创建用户：

```bash
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "CREATE USER temporal WITH SUPERUSER PASSWORD 'temporal_password';"
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "CREATE DATABASE temporal OWNER temporal;"
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c \
  "CREATE DATABASE temporal_visibility OWNER temporal;"
docker compose -p eai-prod restart temporal
```

### 问题 5：前端页面加载但 Agent 不回复

1. 检查 `config.yaml` 中模型配置的 `base_url` 是否正确
2. 确认 LLM 地址从 Docker 容器内可达：
   ```bash
   docker exec prod-eai-flow-gateway curl -s http://<内网LLM地址>:<端口>/v1/models
   ```
3. 查看 Gateway 日志：`docker logs prod-eai-flow-gateway --tail 100`

### 问题 6：登录失败 / 无管理员账号

全新部署没有预设用户。通过 API 创建管理员：

```bash
curl -X POST http://localhost:4026/api/v1/auth/initialize \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}'
```

如提示 `system_already_initialized`（409），表示管理员已存在。

---

## 附录

### A. 生产环境端口清单

| 服务 | 宿主机端口 | 容器内端口 | 说明 |
|------|-----------|-----------|------|
| nginx | `4026` | `2026` | 浏览器访问入口 |
| postgres-ext | `15432` | `5432` | 扩展数据库 |
| temporal | `17233` | `7233` | 工作流引擎 |
| gateway | — | `8001` | API 网关（仅容器内） |
| frontend | — | `3000` | 前端（仅容器内） |
| collab | — | `8002` | WebSocket（仅容器内） |
| ragflow API | `19380` | `9380` | 知识库 API |
| ragflow Web | `19381` | `80` | 知识库管理 |
| ES | `19200` | `9200` | Elasticsearch |
| MySQL | `13306` | `3306` | RAGFlow 数据库 |
| Redis | `16379` | `6379` | RAGFlow 缓存 |
| MinIO | `19100/19101` | `9000/9001` | 对象存储 |

> 端口采用 1-前缀设计（如 15432 而非 5432），避免与服务器本地已安装的 PostgreSQL 等服务冲突。

### B. 环境变量速查

| 变量 | 用途 | 必填 |
|------|------|:--:|
| `DEER_FLOW_ROOT` | 部署目录绝对路径 | ✅ |
| `BETTER_AUTH_SECRET` | 会话加密密钥 | ✅ |
| `HOME` | 用户主目录 | ✅ |
| `PORT` | Nginx 对外端口 | 否（默认 4026） |
| `EXTENSIONS_DB_HOST` | 扩展数据库主机（Docker 服务名） | ✅ |
| `EXTENSIONS_DB_PORT` | 扩展数据库端口（容器内端口） | 否 |
| `POSTGRES_EXT_USER` | 数据库用户名 | 否（默认 agentflow） |
| `POSTGRES_EXT_PASSWORD` | 数据库密码 | 否（默认 agentflow123） |
| `AGNES_API_KEY` 等 | 云端模型 API Key | 按需 |

### C. 配置项速查

| 配置位置 | 用途 |
|----------|------|
| `config.yaml` → `models` | LLM 模型配置（base_url 指向内网或云端服务） |
| `config.yaml` → `sandbox` | 沙箱模式（默认 LocalSandboxProvider） |
| `config.yaml` → `tools` | 工具开关（内网建议禁用 web_search 等） |
| `.env` | 环境变量（路径、密钥、端口、数据库连接） |
| `extensions_config.json` | MCP 服务器和技能开关 |

### D. 版本与升级

离线包版本号格式：`v<主版本>-<commit>-<日期>`

升级步骤：
1. 获取新版离线包
2. 停止服务：`docker compose -p eai-prod down`
3. 导入新镜像：`./load-images.sh`
4. 备份并对比配置：diff 新旧 `config.yaml`，合并变更
5. 启动服务：`docker compose -p eai-prod up -d`
6. 执行迁移：`docker exec prod-eai-flow-gateway python -m app.extensions.workflow.migration`

### E. 开发环境与生产环境对比

生产环境（`eai-prod`）与开发环境（`eai-docker`）可同时运行在同一台机器上，通过以下机制完全隔离：

| 维度 | 开发环境 | 生产环境 |
|------|----------|----------|
| 项目名 | `eai-docker` | `eai-prod` |
| 网络 | `eai-docker_eai-flow-net` | `eai-prod_eai-flow-net` |
| 容器名前缀 | `deer-flow-*` / `eai-flow-*` | `prod-eai-flow-*` |
| 数据卷前缀 | 无 | `prod-*` |
| nginx 端口 | `2026` | `4026` |
| postgres 端口 | `5432` | `15432` |
| temporal 端口 | `7233` | `17233` |
| 镜像策略 | `build:` 源码构建 | `image:` 预构建镜像 |
| 源码挂载 | ✅ | ❌ |

### F. 已知问题与修复记录

以下问题在 2026-06-10 本机验证部署中发现并已修复：

#### F.1 Gateway 崩溃：ModuleNotFoundError: No module named 'docx'

- **根因**：`python-docx` 未在 `backend/pyproject.toml` 中声明
- **修复**：添加 `"python-docx>=1.2.0"` 到 `[project] dependencies`，更新 `uv.lock`，重建镜像

#### F.2 Extensions 数据库连接失败

- **根因**：`.env` 缺少 `EXTENSIONS_DB_HOST=postgres-ext`，默认 `localhost` 在容器内不可达
- **修复**：在 `.env` 中添加 5 个 `EXTENSIONS_DB_*` 变量

#### F.3 Temporal 用户未创建

- **根因**：新建 postgres 数据库无 `temporal` 用户
- **修复**：部署后手动创建（见故障排查问题 4）

#### F.4 前端容器缺少启动命令

- **根因**：dev target 镜像无默认 CMD
- **修复**：`docker-compose.yaml` 前端服务添加 `command: pnpm dev --port 3000 --hostname 0.0.0.0`
