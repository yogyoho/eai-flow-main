# EAI-Flow 全新部署手册（离线生产环境）

> 适用场景：在一台**无法访问外网**的内网 Linux 服务器上，从零部署 EAI-Flow 生产环境。
>
> 全新部署的运维动作很少 —— **主要就是替换客户品牌信息（公司名 / Logo）**，其余环境值（部署目录、密钥、受信来源）由脚本自动推导。

---

## 0. 角色与分工

| 角色 | 机器 | 网络 | 职责 |
|------|------|------|------|
| **开发机** | 你日常开发的机器（Windows/Linux）| 需能联网拉镜像/装依赖 | 构建带客户品牌的离线包 |
| **生产服务器** | 内网 Linux 服务器 | **无外网**，能与内网 LLM 通信 | 接收包、部署、运行 |

两台机器在同一内网时，用 `scp`/`ssh` 传包；完全隔离则用 U 盘。

---

## 第一阶段：开发机构建离线包（每个客户一次）

品牌信息（公司名、Logo、favicon）在 `docker build` 时**烘焙进前端镜像**，所以换客户品牌必须在开发机重建前端镜像，不能在服务器上改文件。

### 1.1 放入客户品牌资产

把客户的以下文件放进 `deploy/offline/brand-assets/`（覆盖默认）：

```
deploy/offline/brand-assets/
├── logo.svg          # 必须，登录页/页眉 Logo
├── favicon.ico       # 浏览器标签图标
└── favicon.svg       # 高清 favicon（可选）
```

> 缺失的文件会保留默认 EAIFlow 资产，不会报错。

### 1.2 填写 `deploy.conf`（唯一需要手写的配置源）

在**仓库根目录**创建 `deploy.conf`（从模板拷贝）：

```bash
cp deploy/offline/deploy.conf.example deploy.conf
vi deploy.conf
```

只需关心两类字段：

```ini
# ── 品牌（按客户改）──
BRAND_NAME=客户公司简称
BRAND_FOOTER=© 2026 客户公司全称
BRAND_ASSETS_DIR=./deploy/offline/brand-assets

# ── 内网 LLM（完全离线必填；内网可连外网则三项全留空走云端）──
LLM_BASE_URL=http://内网LLM地址:端口/v1
LLM_API_KEY=内网LLM的key
LLM_MODEL=模型名
```

其余字段（`RAGFLOW_API_KEY` 可后补、`DB_PASSWORD` 留空走默认）按需。

### 1.3 导出离线包

```bash
# 在仓库根目录，需已用 make docker-start 预热过开发镜像
bash scripts/offline-export.sh
```

产出：`eai-flow-offline-<版本>-<日期>.tar.gz`（含全部镜像 tar + compose + 配置 + install.sh）。

> 首次导出较慢（构建所有镜像）；后续更新用 `--delta` 只导变化镜像（见《更新手册》）。

### 1.4 传到生产服务器

```bash
# 同内网（推荐）
scp eai-flow-offline-*.tar.gz root@<服务器IP>:/opt/

# 或 U 盘：拷到服务器 /opt/
```

---

## 第二阶段：生产服务器首次部署

以下命令在**生产服务器**上执行，以 `root`（或具备 docker 权限的用户）登录。

### 2.1 解压

```bash
cd /opt
tar xzf eai-flow-offline-*.tar.gz
cd eai-flow-offline-*/      # 进入解压出的部署目录（此后即为 $DEER_FLOW_ROOT）
```

### 2.2 确认/修改环境值

包内已带**完整的** `.env` / `config.yaml` / `extensions_config.json`（随仓库版本演进，无需从头写）。首次部署只需核对少量必改项：

**`.env` 必改项：**

| 变量 | 改成 | 说明 |
|------|------|------|
| `DEER_FLOW_TRUSTED_ORIGINS` | `http://<服务器IP>:4026` | **通过服务器 IP 访问必填**，否则登录被拒（CSRF）。多个地址逗号分隔 |
| `INTERNAL_LLM_API_KEY` | 内网 LLM 的真实 key | 与 config.yaml 的 intranet-llm 配合 |

**`.env` 自动推导项（一般不用手动改，install.sh 会处理）：**

| 变量 | 说明 |
|------|------|
| `DEER_FLOW_ROOT` | 当前部署目录绝对路径，install.sh 自动写入 |
| `BETTER_AUTH_SECRET` | 会话密钥，install.sh 自动 `openssl rand` 生成 |
| `BETTER_AUTH_SECRET` 若你手填 | 用 `openssl rand -base64 32` 生成强随机值 |

**`config.yaml`（仅当 1.2 未填 LLM_*，需手动配内网模型时）：**

找到注释掉的 `intranet-llm` 模板（约 80 行附近），取消注释并填 `model` / `api_key` / `base_url`。

**`extensions_config.json`：** 一般无需改动（MCP 服务地址已配好）。

### 2.3 部署

```bash
chmod +x install.sh
./install.sh
```

`install.sh` 会依次：环境预检 → 从 deploy.conf 生成配置（**保留完整 .env，只注入必要键，不覆盖**）→ load 全部镜像 → 创建 Docker 网络 → `docker compose up -d` → 等待 gateway 健康 → 跑数据库迁移 → 创建管理员。

### 2.4 创建管理员账号

`install.sh` 末尾会自动尝试创建管理员。若提示失败，手动补建：

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST \
  http://localhost:4026/api/v1/auth/initialize \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}'
# 期望 HTTP 201（建成）；409 表示已存在
```

> 默认管理员：`admin@eai-flow.com` / `Admin@2026`，**首次登录后立即改密码**。
> 连续登录失败 5 次会锁 5 分钟（429），`docker restart prod-eai-flow-gateway` 可清计数器。

### 2.5 导入 License（关键）

License 是离线 JWT，绑定到本机 `machine_id`。**首次部署必须导入**，否则 7 天宽限期后系统锁定。

浏览器登录 → 管理后台 → License 页，粘贴 EAI 签发的 license 文本，导入。

> 导入会**自动落到持久路径 `./data/license.lic`**（gateway 设了 `LICENSE_FILE_PATH=/app/backend/.deer-flow/license.lic`，映射持久 `./data` 卷；导入逻辑写该路径）。**之后所有升级重建容器都不会丢 license，无需重新申请，也无需手动拷贝。**

验证已落持久卷：

```bash
ls -la data/license.lic      # 应存在
```

> 重置管理员密码 / license 绑定异常等，见本文档「常见坑」。

### 2.6 Temporal 用户（仅启用了 Temporal 时）

若部署含 Temporal（`docker-compose.temporal.yaml`），且 postgres 数据卷不是全新空卷，需手动补建 temporal 角色：

```bash
docker exec prod-eai-flow-postgres-ext sh /docker-entrypoint-initdb.d/10-temporal.sh
docker restart prod-eai-flow-temporal
docker logs prod-eai-flow-temporal --tail 20   # 期望无 password authentication failed
```

---

## 第三阶段：验证

```bash
# 1. 全部容器 Up (healthy)
docker compose -p eai-prod ps

# 2. Gateway 健康
curl http://localhost:4026/api/license/status

# 3. 浏览器访问
#    http://<服务器IP>:4026
#    用 admin@eai-flow.com 登录，检查：知识库 / 合同价分析 / 文档管理 / 对话
```

---

## 常见坑（服务器实测记录）

### 坑 1：配置文件被生成脚本覆盖成残缺版
**症状**：部署后 gateway crash，日志报 `AppConfig → sandbox → Field required`，或 `.env` 缺失大量变量。
**根因**：旧版 `generate-config.sh` 用最小模板覆盖了包内完整的 `.env`/`config.yaml`。
**对策**：本手册对应版本已修复（生成只做定向注入、不覆盖完整文件）。若拿到的是旧包，从包内 tar 恢复完整 config 再重建：
```bash
mkdir -p /tmp/cfg && tar xzf /opt/eai-flow-offline-*.tar.gz -C /tmp/cfg config.yaml && cp /tmp/cfg/config.yaml config.yaml
docker compose -p eai-prod up -d --force-recreate --no-deps gateway
```

### 坑 2：install.sh 的 admin 初始化在 gateway 不健康时静默失败
**症状**：install.sh 跑完，但 `admin@eai-flow.com` 登录报「Incorrect」，`deerflow.db` 的 users 表为空。
**根因**：gateway 当时 crash-loop，`/api/v1/auth/initialize` 返回 502 → admin 没建成。
**对策**：gateway 修复健康后手动补建（见 2.4）。

**重置已有 admin 密码**（users 表非空但忘了密码）：
```bash
docker exec -e PYTHONPATH=/app/backend prod-eai-flow-gateway /app/backend/.venv/bin/python -c "
import sqlite3
from app.gateway.auth.password import hash_password
con = sqlite3.connect('/app/backend/.deer-flow/data/deerflow.db')
cur = con.execute('UPDATE users SET password_hash=? WHERE email=?', (hash_password('Admin@2026'), 'admin@eai-flow.com'))
con.commit(); print('reset rows:', cur.rowcount)
"
```

### 坑 3：License 升级后失效，需重新申请
**症状**：更新（重建 gateway 容器）后系统进入宽限期或锁定。
**根因**：license 默认写到容器临时层 `/app/license.lic`，容器重建即丢。
**对策**：本版本已修复 —— gateway 设了 `LICENSE_FILE_PATH` 指向持久 `./data`，且导入逻辑写该路径，UI 导入即自动持久化。**修复前的老系统**需一次性把已导入的 license 救到 `./data/`（见《更新手册》§4）。

### 坑 4：Temporal 报 `password authentication failed for user "temporal"`
**根因**：postgres 初始化脚本只在数据卷**真正为空**时跑；卷有残留则 temporal 角色没建。
**对策**：见 2.6（幂等补建 + 重启 temporal，**不要** `--force-recreate temporal`，会级联重建 postgres 触发容器名冲突）。

---

## 数据安全红线（绝不可执行）

| 命令 | 后果 |
|------|------|
| `docker compose -p eai-prod down -v` | `-v` 删除数据卷 → 主库/知识库全丢 |
| `docker volume prune` / `docker system prune --volumes` | 删未挂载卷 |
| `rm -rf` 部署目录（含 `./data`）| 删认证/线程/上传/用户文件 |
| `docker system prune -af` | 删已 load 未 up 的镜像 |

`docker compose down`（**不带 `-v`**）安全 —— 卷保留。

---

## 常用运维命令

```bash
docker compose -p eai-prod ps            # 服务状态
docker compose -p eai-prod logs -f gateway   # 看日志
docker compose -p eai-prod restart gateway   # 重启 gateway（改 config.yaml 后）
docker compose -p eai-prod up -d --force-recreate gateway  # 重建 gateway（改 .env 后）
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c "SELECT ..."  # 查库
```

> 系统跑起来后，**日常更新请用《更新手册》的 `upgrade.sh`，不要再跑 `install.sh`**。

---

## 附：部署架构

```
浏览器 → Nginx (:4026)
           ├── /api/langgraph/* → Gateway (8001)
           ├── /api/*           → Gateway (8001)
           ├── /api/collab      → Collab (8002, WebSocket)
           └── /*               → Frontend (Next.js 生产构建)
```

数据持久化位置：

| 数据 | 位置 | 类型 |
|------|------|------|
| 主库（用户/文档/知识库/合同价/license镜像） | `eai-prod_prod-postgres-ext-data` | named volume |
| RAGFlow 索引/MinIO对象/MySQL | `eai-prod_prod-ragflow-*-data` | named volume |
| 认证+线程+反馈+上传+checkpoints+machine_id+license | `./data`（→ `/app/backend/.deer-flow`）| bind mount |
