# EAI-Flow 内网离线部署操作手册

> 版本 2.1 | 2026-07-01 | 内网服务器（10.180.41.157）生产部署验证通过
>
> 版本 2.0 | 2026-06-10 | 本机验证通过
>
> 版本 3.0 | 2026-07-29 | `deploy.conf` 零编辑部署 + 增量升级 + 生产前端构建（见下方 v3 速览；其余为 v2 历史流程）

## v3.0 新流程速览（2026-07-29）

**核心变化**：配置从"多处手改"改为**单一 `deploy.conf` 驱动**；升级从"全量重装"改为 **delta 增量 + 快照回滚**；前端从 dev 模式改为**生产构建**（消灭 F.14–F.18 整类问题）。

### 全新部署（零编辑）
1. 解压离线包，`cp deploy.conf.example deploy.conf`，填 4 个品牌值 + 内网 LLM（内网可连外网则 LLM 留空）。
2. `./install.sh` —— 自动生成 `.env`/`config.yaml`/`extensions_config.json`（路径/密钥/origins 自动推导）、load 镜像、起服务、建管理员。
3. **无需手改任何配置文件。** 配置项说明见 `deploy/offline/deploy.conf.example`。

### 增量升级（不再全量重传）
- 开发机：`bash scripts/offline-export.sh --delta --since <上次版本>` → 只导出变化的镜像。
- 服务器：`scp` delta 包 → `./upgrade.sh delta`（load delta → config_hash 变则重生成 → 重建变化服务 → 迁移前 `pg_dump` → 失败自动 reload 快照回滚）。

### 替换已部署的旧系统（不丢数据）
见 **`deploy/offline/cutover.md`**（复用同名 volume 的原地割接 + 完整备份/回滚步骤）。

### 已根治的已知问题（v3 起无需再手动处理）
F.2（`EXTENSIONS_DB`）、F.6（`NETWORK_NAME`）、F.11/F.13（RAGFlow pip PATH / tiktoken 预置）、F.14（nginx webpack-hmr）、F.18 及 HMR/allowedDevOrigins/Google Fonts（由生产前端构建根治）、F.20（`RAGFLOW_API_KEY` 走 `deploy.conf`）。

---

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

### 2.4 磁盘：扩展 root 逻辑卷（强烈建议，部署前先做）

Ubuntu Server 用 LVM 安装时，安装器默认只给 root 逻辑卷分配固定大小（常见 100GB），剩余物理盘空间留在卷组里未分配。**部署前先把它扩满**，避免后续频繁磁盘满（ES 水位、容器创建失败、RAGFlow 503 等都是它的并发症）。

```bash
# 1. 检查:VG 是否有大量未分配空间(VFree 远大于 0)
vgs
# 若 VFree 有几十/几百 GB 甚至 TB,说明 root LV 没用满,继续:

# 2. 把 VG 剩余空间全扩给 root LV(在线,不停机)
lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv

# 3. 在线扩展 ext4 文件系统
resize2fs /dev/ubuntu-vg/ubuntu-lv

# 4. 验证:root 应接近物理盘大小
df -h /
```

> 本机实测：root 从 100GB → 2TB，使用率从 68% → 4%。详见 F.22。

### 2.5 端口检查

```bash
# 确认以下端口未被占用（可在 .env 中修改）
ss -tlnp | grep -E "4026|15432|17233"
```

### 2.6 解压并配置

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

### 2.7 一键部署

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

### 问题 7：前端页面显示不全 / 登录按钮缺失（React 未水合）

**症状**：页面有静态内容（标题、卡片文字），但右上角登录按钮、交互组件缺失；浏览器控制台无 JS 报错，或只有 WebSocket 重连错误。

**根因**：Next.js 16 dev 模式 + nginx 反代环境下，两类问题会阻断 RSC 水合：
1. nginx 对 `/_next/webpack-hmr` 返回非 WebSocket 响应（如 204），导致 dev client HMR 异常循环
2. `next.config.js` 未配置 `allowedDevOrigins`，dev 模式拒绝非 localhost 来源

**排查与修复**：
```bash
# 1. 看 frontend 日志是否有 allowedDevOrigins 提示
docker logs prod-eai-flow-frontend 2>&1 | grep -i allowedDevOrigins

# 2. 确认 nginx 没有 204 hack 拦截 webpack-hmr
docker exec prod-eai-flow-nginx grep -n 'webpack-hmr' /etc/nginx/nginx.conf
# 应无输出（让 HMR 走 location / 的正常 WebSocket 代理）

# 3. 确认 allowedDevOrigins 已注入
docker exec prod-eai-flow-frontend grep allowedDevOrigins /app/frontend/next.config.js
```
如缺失，参考附录 F.14 / F.15 修复。详见 F.14、F.15、F.16（Google Fonts 超时也会阻塞渲染）。

### 问题 8：RAGFlow 反复重启 / 初始化卡住 / 全站 401

```bash
docker logs prod-eai-flow-ragflow --tail 20
```

**v0.27.1（2026-09 起）常见故障对号入座：**
- 容器启动后**什么都不跑**（无 API/无 task executor）→ compose 缺 `API_PROXY_SCHEME=python`（模板已内置；自制 compose 必须加，上游 docker/.env 同款）
- 原本正常、重启/升级后**所有请求 401** → `RAGFLOW_SECRET_KEY` 变了或没设：v0.27.x 把 SECRET_KEY 缓存在 Redis，键不一致即全站 401。必须用固定值（.env 的 `RAGFLOW_SECRET_KEY`），且**永不更改**
- model-provider 相关报错/模型供应商列表为空 → command 缺 `--init-model-provider-tables`（v0.27.x 缺它则建表迁移被静默跳过）
- MySQL 连接认证失败（全新数据卷）→ compose 缺 `--default-authentication-plugin=mysql_native_password` 等 flags（模板已内置）

**v0.25.3 时代的三类旧故障**（`pip: not found` / `No module named 'strenum'` / tiktoken 下载卡死）已由 `v0.27.1-fixed` 离线镜像（pip PATH + tiktoken 预烘焙）+ 取消 `/ragflow` 整卷挂载（改为只挂 `/ragflow/logs`）根治，见附录 F.11–F.13 的历史记录；若仍命中，说明镜像不是 `-fixed` 版或 compose 还是旧挂载方式。

### 问题 9：Temporal 端口被占：`Bind for 0.0.0.0:17233 failed`

```bash
ss -tlnp | grep 17233   # Linux 看占用
```

Linux 上一般空闲；Windows/Hyper-V 可能保留该端口段。改 `.env` 中 `TEMPORAL_PORT=27233` 后 `docker compose -p eai-prod up -d --force-recreate temporal`。详见 F.7。

### 问题 10：Docker 网络 `declared as external, but could not be found`

`deploy.sh` 部署时报错。检查 `.env` 是否有 `NETWORK_NAME=...`：
```bash
grep NETWORK_NAME .env
```
如有且值不是 `eai-prod_eai-flow-net`，注释掉该行（compose 文件已硬编码正确网络名）。详见 F.6。

### 问题 11：nginx 挂载失败：`not a directory`

```bash
ls -la nginx/nginx.conf   # 应是文件,不是目录
```

如显示为目录，是首次挂载时 Docker 自动创建。删除后拷贝真实文件：
```bash
rm -rf nginx && mkdir nginx && cp docker/nginx/nginx.conf nginx/nginx.conf
docker compose -p eai-prod -f docker/docker-compose.yaml up -d --force-recreate nginx
```
详见 F.10。

### 问题 12：磁盘满导致容器创建失败

**第一步先查 LVM 是否只分了 100GB（根治，见 F.22）**：
```bash
vgs                  # 看 VFree(空闲)是否远大于 0
lvs                  # 看 root LV 的 LSize 是否远小于 VSize
```
若 `VFree` 有 ~1.9T 没分配 → 执行 `lvextend -l +100%FREE ... && resize2fs ...`（F.22），root 立刻从 100GB 扩到 2TB，根治。**这是 Ubuntu Server LVM 默认安装的通病，磁盘满多半是没扩 LV，而非真的没空间。**

如果 VG 确实已用满、物理盘就是不够，再做清理：
```bash
df -h /                       # 看根分区
docker system df              # 看 Docker 占用
```

`load-images.sh` 后 `images/*.tar`（约 5GB）不再需要，可删。**切勿用 `docker system prune -af`**——会删掉刚加载、尚未启动的镜像。安全清理：
```bash
rm -rf /opt/eai-flow-offline/images/                          # 镜像 tar 已加载,可删
docker image prune                                            # 只删悬挂镜像(无 tag)
docker container rm $(docker ps -aq --filter status=exited)   # 删已退出容器
```
详见 F.9（清理）和 F.22（扩 LV 根治）。

### 问题 13：知识库创建后不同步到 RAGFlow（RAGFlow 平台看不到）

```bash
# 看 gateway 日志是否有 401 / skipping sync
docker logs prod-eai-flow-gateway 2>&1 | grep -iE 'ragflow|skipping sync|401'
```

若日志显示 `RAGFlow service unavailable, skipping sync` 或调 RAGFlow API 返回 401，是 `RAGFLOW_API_KEY` 没配。在 RAGFlow Web UI（`:19381`）生成 API Key 后填入 `.env`，**force-recreate** gateway（不是 restart）。详见 F.20。

若 gateway 完全连不上 `ragflow:9380`，是 ragflow 容器被手动 `docker run` 起的（没注册服务名），用 compose 重建。详见 F.21。

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

---

以下问题在 **2026-07-01 内网服务器（10.180.41.157）生产部署** 中发现并已修复：

#### F.5 deploy.sh 在非 Linux 环境崩溃：`free: command not found`

- **根因**：`deploy/offline/deploy.sh` 的内存检查直接调用 `free`，该命令仅 Linux 有；在 Windows Git Bash 等环境下 `set -euo pipefail` 直接退出
- **修复**：内存检查用 `if command -v free &>/dev/null` 守护，缺失时跳过（不影响 Linux 目标服务器）

#### F.6 Docker 网络找不到：`network eai-prod_eai-flow-net declared as external, but could not be found`

- **根因**：`deploy/offline/.env` 中有 `NETWORK_NAME=eai-flow-net`，`deploy.sh` 在 `source .env` 后该值覆盖了脚本计算的 `eai-prod_eai-flow-net`，导致创建了错误名字的网络
- **修复**：注释掉 `.env` 中的 `NETWORK_NAME`（compose 文件已硬编码 `name: eai-prod_eai-flow-net`，该变量仅供文档参考）

#### F.7 Temporal 端口被占：`Bind for 0.0.0.0:17233 failed`

- **根因**：Windows Hyper-V / WSL2 会保留一段动态端口（常包含 17xxx 段），Linux 上不会
- **修复**：`.env` 中改 `TEMPORAL_PORT=27233`（或其他未占用端口）。Linux 目标服务器一般无此问题，保留默认 17233 即可

#### F.8 镜像 tag 与 compose 不匹配：`MISSING: postgres:16-alpine`

- **根因**：`offline-export.sh` 早期版本 `docker save` 时用 `image_to_filename` 丢失了 `-alpine` 等后缀；或镜像被其他工具重新 tag。compose 引用 `postgres:16-alpine` 但本地只有 `postgres:16`
- **修复**：手动 `docker tag` 对齐 4 个易错镜像：
  ```bash
  docker tag postgres:16 postgres:16-alpine
  docker tag redis:7 redis:7-alpine
  docker tag elasticsearch:8.11.0 elasticsearch:8.11.3
  docker tag infiniflow/ragflow:v0.27.1 infiniflow/ragflow:v0.27.1-fixed
  ```
- **根治**：`offline-export.sh` 已改为纯本地镜像导出（见 F.19），打包时镜像即 dev 验证过的那批，tag 一致

#### F.9 `docker system prune -af` 误删已加载的部署镜像

- **根因**：磁盘满时执行 `docker system prune -af`，`-a` 会删除**所有未被运行容器使用**的镜像——刚 `load-images.sh` 加载但尚未 `up` 的镜像被一并清掉
- **修复**：从开发机用管道重推（不需要 scp 中间文件）：
  ```bash
  docker save <image1> <image2> | ssh root@<server> "docker load"
  ```
- **预防**：磁盘清理用 `docker image prune`（只删悬挂镜像）而非 `-a`；或清理 `images/*.tar` 文件（load 后不再需要）

#### F.10 nginx 启动失败：`mount src=.../nginx.conf ... not a directory`

- **根因**：compose v5 在 compose 文件所在目录（`docker/`）解析相对路径 `./nginx/nginx.conf`；首次挂载时宿主机不存在该文件，Docker 把它当成目录创建，之后 nginx 想挂载文件却挂到了目录上
- **修复**：在包根目录建 `nginx/nginx.conf` 实体文件（`cp docker/nginx/nginx.conf nginx/nginx.conf`），或部署前确保文件存在

#### F.11 RAGFlow 反复重启：`sh: 1: pip: not found`

> ✅ **现状（2026-09，v0.27.1 起）**：已烘焙进 `ragflow-fixed.Dockerfile`（`infiniflow/ragflow:v0.27.1-fixed`，由 `offline-export.sh` 自动构建导出），全新部署不会遇到。以下为 v0.25.3 时代的手工修复记录。

- **根因**：`infiniflow/ragflow:v0.25.3` 的 entrypoint 调用 `pip`，但 venv 在 `/ragflow/.venv/bin/`，未加入 `PATH`；只有 `pip3` 没有 `pip`
- **修复**：构建修复版镜像并重新 tag：
  ```dockerfile
  FROM infiniflow/ragflow:v0.25.3
  ENV PATH=/ragflow/.venv/bin:${PATH}
  RUN ln -sf pip3 /ragflow/.venv/bin/pip
  ```
  ```bash
  docker build -t infiniflow/ragflow:v0.25.3-fixed -f- . <<'EOF'
  FROM infiniflow/ragflow:v0.25.3
  ENV PATH=/ragflow/.venv/bin:${PATH}
  RUN ln -sf pip3 /ragflow/.venv/bin/pip
  EOF
  docker tag infiniflow/ragflow:v0.25.3-fixed infiniflow/ragflow:v0.25.3
  ```

#### F.12 RAGFlow 报 `ModuleNotFoundError: No module named 'strenum'`

> ✅ **现状（2026-09，v0.27.1 起）**：已根治——离线 compose 不再把 named volume 挂在 `/ragflow` 本体，改为只挂 `prod-ragflow-logs:/ragflow/logs`（非空 named volume 会遮蔽镜像代码，升级镜像后静默跑旧版本，此坑已从结构上消除）。从旧版升级的部署若存在废弃卷 `eai-prod_prod-ragflow-data`，确认无需回滚后可删除。以下为历史记录。

- **根因**：compose 把 named volume `prod-ragflow-data` 挂载到 `/ragflow`，**首次创建的空 volume 覆盖了镜像内 `/ragflow` 的全部内容**（含 `.venv/site-packages`），导致 `strenum` 等 wheel 自带模块也找不到
- **修复**：删除空 volume，重启后 Docker 用（已修复的）镜像内容重新填充：
  ```bash
  docker stop prod-eai-flow-ragflow && docker rm prod-eai-flow-ragflow
  docker volume rm eai-prod_prod-ragflow-data
  docker compose -p eai-prod -f docker/docker-compose.ragflow.yaml up -d
  ```
  **注意**：必须先完成 F.11 的镜像修复，否则新 volume 仍会缺 `pip`/`strenum`

#### F.13 RAGFlow 初始化卡住：`Failed to resolve 'openaipublic.blob.core.windows.net'`

> ✅ **现状（2026-09，v0.27.1 起）**：`cl100k_base.tiktoken` 已由 `ragflow-fixed.Dockerfile` 在**开发机构建期预下载并烘焙进 `v0.27.1-fixed` 镜像**（下载失败会让构建硬失败，不会 ship 假离线镜像），全新离线部署无需代理即可完成初始化。compose 里的 `RAGFLOW_HTTP_PROXY` 代理注入保留，仅兜底其他外部资源。以下为历史记录。

- **根因**：RAGFlow 首次启动需要从 Azure 下载 `cl100k_base.tiktoken` 编码文件；内网容器无公网，DNS 解析失败导致初始化循环
- **修复**：给 RAGFlow 容器注入代理环境变量（代理地址从服务器 `env | grep -i proxy` 获取）：
  ```bash
  docker run ... \
    -e HTTP_PROXY=http://<代理地址>:<端口> \
    -e HTTPS_PROXY=http://<代理地址>:<端口> \
    -e NO_PROXY="localhost,127.0.0.1,.local,ragflow-mysql,ragflow-es,ragflow-redis,ragflow-minio" \
    infiniflow/ragflow:v0.25.3
  ```
  **关键**：`NO_PROXY` 必须包含内部服务名（ragflow-mysql 等），否则内部连接也走代理会失败

#### F.14 前端页面显示不全 / 组件不渲染（React 未水合）

- **根因**：为消除 HMR WebSocket 报错，曾给 nginx 加 `location = /_next/webpack-hmr { return 204; }`。这会让 Next.js dev client 的 HMR 连接收到非 WebSocket 响应，进入异常重连循环，**间接阻断 RSC（React Server Components）水合流程**，导致登录按钮等客户端组件不渲染
- **修复**：**删除** `return 204` 的 hack，让 `/_next/webpack-hmr` 走 `location /` 的正常 WebSocket 代理（该块已有 `proxy_set_header Upgrade $http_upgrade; Connection 'upgrade';`）
- **验证**：浏览器控制台不再有持续的 WebSocket 重连错误，页面右上角登录按钮、卡片等全部渲染

#### F.15 Next.js dev 模式拒绝非 localhost 来源（页面不水合，控制台无报错）

- **根因**：Next.js 16 开发模式默认只允许 `localhost` 来源的 RSC 请求；通过 nginx 反代用服务器 IP 访问时，origin 校验失败，RSC flight 数据虽下发但客户端不消费
- **症状**：HTML 静态内容正常，但所有 `useEffect` 不触发，登录按钮等客户端组件缺失；frontend 容器日志提示 `add it to "allowedDevOrigins" in next.config.js`
- **修复**：`frontend/next.config.js` 增加：
  ```js
  const config = {
    // ...
    devIndicators: false,
    allowedDevOrigins: ['<服务器IP>', '<域名>'],  // 例如 ['10.180.41.157']
    // ...
  };
  ```
  生产环境前端用 `frontend-start.sh` 启动脚本，自动用 `sed` 注入该配置（见 deploy/offline/frontend-start.sh）

#### F.16 Google Fonts 加载超时导致页面阻塞

- **根因**：`frontend/src/styles/globals.css` 和 `frontend/src/extensions/dashboard/dashboard.css` 第一行 `@import url('https://fonts.googleapis.com/...')`，内网无法访问 Google CDN，浏览器等待超时（~30s）才继续渲染
- **修复**：注释掉两个 CSS 文件首行的 `@import url(fonts.googleapis...)`，字体回退到系统字体
- **根治**：如需美观字体，改用 `@fontsource` npm 包自托管（`pnpm add @fontsource/space-grotesk`，在入口 `import "@fontsource/space-grotesk"`），不依赖外部 CDN

#### F.17 frontend 容器启动循环（YAML 解析失败）

- **根因**：compose 的 `command:` 内联 `sh -c "..."` 脚本里含 `: `（冒号+空格，如 `allowedDevOrigins: [...]`），YAML 把它当成 key 分隔符解析失败
- **修复**：把启动逻辑独立成 `deploy/offline/frontend-start.sh`，compose 用数组形式引用：
  ```yaml
  command: ["sh", "/usr/local/bin/frontend-start.sh"]
  volumes:
    - ./docker/frontend-start.sh:/usr/local/bin/frontend-start.sh:ro
  ```

#### F.18 前端 CSS 改动不生效（Turbopack 缓存）

- **根因**：`pnpm dev`（Turbopack）把 CSS 编译产物缓存在 `.next/`，修改源 CSS 后未触发重编译，浏览器拿到的编译产物仍含旧内容（如已注释的 Google Fonts `@import`）
- **修复**：清缓存强制重编译：
  ```bash
  docker exec prod-eai-flow-frontend rm -rf /app/frontend/.next
  docker restart prod-eai-flow-frontend
  ```

#### F.19 SSH 在 `load-images.sh` 加载大镜像时断开

- **根因**：`install.sh` → `load-images.sh` 顺序 `docker load` 17 个镜像（约 5GB），耗时 5-10 分钟，期间无输出，SSH 空闲超时或网络抖动导致连接断开，加载中断
- **修复**：
  - **本机推送镜像**（推荐）：跳过 `load-images.sh`，从开发机管道直推：
    ```bash
    docker save <镜像名> | ssh root@<服务器> "docker load"
    ```
  - **服务器端**：用 `nohup` 后台执行，断开后继续：
    ```bash
    nohup bash load-images.sh > /tmp/load.log 2>&1 &
    tail -f /tmp/load.log
    ```
  - **SSH 配置**：客户端加 `-o ServerAliveInterval=60` 保持连接

#### F.20 RAGFlow 知识库不同步 / Gateway 日志 `RAGFlow service unavailable, skipping sync`

- **症状**：在 EAI-Flow `/knowledge` 创建知识库后，RAGFlow 平台（`http://<IP>:19381/datasets`）没有对应 dataset；gateway 日志：
  ```
  HTTP Request: GET http://ragflow:9380/api/v1/datasets "HTTP/1.1 401"
  WARNING - RAGFlow service unavailable, skipping sync
  ```
- **根因**：`RAGFLOW_API_KEY` 未配置（`RAGFlowConfig.from_env()` 默认空字符串）。知识库同步走 RAGFlow REST API，需 `Authorization: Bearer <key>`，空 key → 401 → `knowledge/service.py` 静默跳过同步，知识库只在 EAI-Flow 本地建。**与 `RAGFLOW_BASE_URL` 是否硬编码无关**（默认值是 `http://localhost:9380`，但 compose env 已覆盖为 `http://ragflow:9380`，gateway 连通正常）
- **获取 API Key**：浏览器打开 `http://<服务器IP>:19381` → 注册/登录 RAGFlow 账号 → 个人设置 → 创建 API Key
- **修复**：在 `.env` 填 `RAGFLOW_API_KEY=ragflow-xxxx`，**force-recreate** gateway 让 `env_file` 重新加载（`docker restart` 不会重读 env）：
  ```bash
  # 1. 写入 key
  echo 'RAGFLOW_API_KEY=ragflow-xxxx' >> /opt/eai-flow-offline/.env
  cp /opt/eai-flow-offline/.env /opt/eai-flow-offline/docker/.env
  # 2. 重建 gateway（不是 restart！）
  cd /opt/eai-flow-offline
  docker compose -p eai-prod --project-directory /opt/eai-flow-offline \
    -f docker/docker-compose.yaml up -d --force-recreate gateway
  # 3. 验证
  docker exec prod-eai-flow-gateway printenv RAGFLOW_API_KEY
  docker exec prod-eai-flow-gateway sh -c \
    'curl -s -H "Authorization: Bearer $RAGFLOW_API_KEY" http://ragflow:9380/api/v1/datasets'
  # 返回 {"code":0,...} 即通
  ```
- **前提**：RAGFlow 需配置一个嵌入模型（如 bge-m3），否则建库时会因无嵌入模型失败。在 RAGFlow Web UI → 模型提供商 → 添加 OpenAI-API-Compatible（指向内网嵌入服务）→ 设置默认嵌入模型

#### F.21 RAGFlow 容器手动 `docker run` 起来导致 gateway 找不到 / Web UI 端口不通

- **症状**：① gateway 日志 `ragflow:9380` 连接失败；② Web UI `http://<IP>:19381` 打不开；但 `docker ps` 显示 ragflow 容器在跑
- **根因**：部署排错时若用 `docker run` 手动起 ragflow 容器（脱离 compose 管理），会：① 容器只注册**容器名** `prod-eai-flow-ragflow`，Docker DNS 无法用**服务名** `ragflow` 解析（gateway 的 `RAGFLOW_BASE_URL` 用的是服务名）；② 手动 run 容易漏掉 `-p 19381:80`（Web 端口）
- **验证**：
  ```bash
  docker inspect prod-eai-flow-ragflow --format '{{index .Config.Labels "com.docker.compose.service"}}'
  # 空 = 手动起的;ragflow = compose 管的
  docker exec prod-eai-flow-gateway getent hosts ragflow   # 能解析 = 正常
  ```
- **修复**：始终用 compose 管理 ragflow：
  ```bash
  cd /opt/eai-flow-offline
  docker compose -p eai-prod --project-directory /opt/eai-flow-offline \
    -f docker/docker-compose.ragflow.yaml up -d
  ```
  compose 起的容器会同时注册服务名 `ragflow`（供 gateway 解析）和发布双端口（API 19380 + Web 19381）

#### F.22 服务器磁盘"不够"但物理盘很大（root LV 只分了 100GB）

- **症状**：`df -h /` 显示根分区只有 ~100GB，频繁磁盘满（ES 水位触发、容器创建失败、镜像加载失败），但服务器实际物理盘有 2TB
- **根因**：Ubuntu Server 用 LVM 安装时，安装器默认只给 root 逻辑卷（LV）分配固定大小（常见 100GB 或 VG 的 50%），**剩余的物理盘空间留在卷组（VG）里完全未分配**。`/dev/sda3` 整个分区作为 LVM 物理卷（PV）给了 VG，但 LV 没用满
- **诊断**：
  ```bash
  lsblk                              # 看物理盘 sda 大小(2T) vs root LV 大小(100G)
  pvs                                # PV: /dev/sda3 → VG ubuntu-vg
  vgs                                # VG: VSize ~2T, VFree 1.9T(空闲!)
  lvs                                # LV: ubuntu-lv 仅 100G
  df -h /                            # root 挂载 98G
  ```
  若 `vgs` 的 `VFree` 有大量空间、`lvs` 的 `LSize` 远小于 `VSize`，即为本问题
- **修复**：把 VG 剩余空间全扩给 root LV，再在线扩展 ext4 文件系统。**不停机、不重启、不丢数据**，服务全程在跑：
  ```bash
  # 1. 扩展 LV 到用满 VG(在线,立即生效)
  lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
  # 2. 在线扩展 ext4(root 挂载着也能扩)
  resize2fs /dev/ubuntu-vg/ubuntu-lv
  # 3. 验证
  df -h /      # 应从 98G 变成 ~2T,使用率从 68% 降到 4%
  ```
  扩展后 root 从 100GB → ~2TB，ES 默认磁盘水位（85%/90%/95%）不会再触发，磁盘压力彻底解决
- **预防**：Ubuntu Server 安装时若选 LVM，安装界面有个「Use entire disk」之外还可手动调整 LV 大小；或在部署前先跑上面的 `lvextend` 把 VG 用满。建议**部署前第一件事**就执行此扩展
- **关联**：本问题常被误判为"磁盘满了要清理容器/镜像"，但根源是空间没分配。清理（F.9/F.12）只是临时缓解，扩 LV 才是根治
