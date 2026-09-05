# EAI-Flow 全新部署手册（离线生产环境 · 完整操作步骤）

> 适用场景：在一台**无法访问外网**的内网 Linux 服务器上，从零部署 EAI-Flow 生产环境。
>
> 全新部署的运维动作很少 —— **主要就是替换客户品牌信息（公司名 / Logo）+ 填内网 LLM**，其余环境值（部署目录、密钥、受信来源）由脚本自动推导。
>
> 访问地址：`http://<服务器IP>:4026`　默认管理员：`admin@eai-flow.com` / `Admin@2026`（首登即改）

---

## 0. 角色与约定

| 角色 | 机器 | 网络 | 典型目录 |
|------|------|------|----------|
| **开发机** | 你的开发机（Windows/Linux）| 需联网拉镜像/装依赖 | 仓库根（含 `scripts/`、`docker/`、`deploy/offline/`）|
| **生产服务器** | 内网 Linux 服务器 | **无外网**，能与内网 LLM 通信 | `/opt/eai-flow-offline`（部署目录 = `$DEER_FLOW_ROOT`）|

两台机器同内网用 `scp`/`ssh`；完全隔离用 U 盘。

**服务器侧统一约定**（下文命令用到）：先 `cd` 到部署目录并设好 compose 前缀变量：

```bash
cd /opt/eai-flow-offline
export COMPOSE="docker compose -p eai-prod \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.ragflow.yaml"
```

> 之后服务器侧命令都写成 `$COMPOSE ps` 这样的短形式。
>
> **关于 compose 文件**：生产部署只有 3 个 —— 核心 `docker-compose.yaml`（nginx/frontend/gateway）、`docker-compose.extensions.yaml`（postgres-ext/collab/temporal/cad/text-to-cad/ocr/cad-viewer 等次级服务合集）、`docker-compose.ragflow.yaml`（知识库栈，独立）。**browserless**（无头 Chrome，供 web_fetch/web_capture 渲染 JS 页）在 extensions.yaml 里默认注释 —— 离线部署通常用不到（web 工具需外网），需要时按文件内注释启用（开发机 `docker pull browserless/chrome:1` + 取消注释 + 加入导出镜像清单）。

---

## 1. 前置条件检查（开工前确认）

### 1.1 开发机要有

| 项 | 确认命令 | 要求 |
|----|----------|------|
| Docker | `docker --version` | >= 24.0 |
| compose v2 | `docker compose version` | 已装 |
| 仓库代码 | — | 已 clone，在 `main-dev-fork` 分支 |
| **开发镜像已预热** | `docker images \| grep eai-docker` | **必须先跑过一次 `make docker-start`**，否则导出报 "Image not found locally" |
| 客户品牌资产 | — | logo.svg / favicon（见步骤 2）|

> ⚠️ **开发镜像预热是硬前提**：`offline-export.sh` 只导出本机已存在的、dev 验证过的镜像，不联网拉。首次部署前必须 `make docker-start` 把所有服务镜像构建/拉到本机。

### 1.2 生产服务器要有

| 项 | 确认命令 | 要求 |
|----|----------|------|
| Docker | `docker --version` | >= 24.0 |
| compose v2 | `docker compose version` | 已装 |
| 磁盘 | `df -h /opt` | >= 40GB 可用（RAGFlow 全量约 30GB+）|
| 内存 | `free -g` | >= 8GB（建议 16GB）|
| 端口 4026 | `ss -tlnp \| grep 4026` | 空闲（否则改 `.env` 的 `PORT`）|
| 无同名项目 | `docker compose -p eai-prod ps` | 无残留（或先 `down` 清掉）|
| 内网 LLM 可达 | — | 服务器容器能访问到内网 LLM 的 `base_url` |

---

## 第一阶段：开发机构建离线包（每个客户一次）

> 品牌信息（公司名、Logo、favicon）在 `docker build` 时**烘焙进前端镜像**，所以换客户品牌必须在开发机重建前端镜像，**不能在服务器上改文件**。

### 步骤 1：准备客户品牌资产

把客户的资产放进 `deploy/offline/brand-assets/`（覆盖默认）：

```
deploy/offline/brand-assets/
├── logo.svg          # 登录页/页眉 Logo（建议 SVG）
├── favicon.ico       # 浏览器标签图标
└── favicon.svg       # 高清 favicon（可选）
```

确认文件就位：

```bash
ls -la deploy/offline/brand-assets/
```

> 缺失的文件保留默认 EAIFlow 资产，不报错；但要让品牌生效，至少放 `logo.svg`。

### 步骤 2：填写 `deploy.conf`（唯一需要手写的配置源）

在**仓库根目录**从模板创建并编辑：

```bash
cp deploy/offline/deploy.conf.example deploy.conf
vi deploy.conf
```

按客户填这几项（其余留空走默认）：

```ini
# ── 品牌（按客户改）──
BRAND_NAME=客户公司简称
BRAND_FOOTER=© 2026 客户公司全称
BRAND_ASSETS_DIR=./deploy/offline/brand-assets    # ⚠️ 必须指向步骤1放资产的目录（别用模板默认的 ./brand-assets）

# ── 内网 LLM（完全离线必填；内网可连外网则三项全留空走云端模型）──
LLM_BASE_URL=http://内网LLM地址:端口/v1
LLM_API_KEY=内网LLM的key
LLM_MODEL=模型名
```

> `RAGFLOW_API_KEY` 可部署后在 RAGFlow Web UI (:19381) 生成再补；`DB_PASSWORD` 留空走默认 `agentflow123`。

### 步骤 3：预热开发镜像（首次必做）

```bash
# 在仓库根目录。首次会构建/拉取所有服务镜像到本机
make docker-start
# 验证关键镜像在位
docker images | grep -E 'eai-docker-(gateway|frontend)|deer-flow-frontend'
```

> 已预热过可跳过。这一步保证步骤 4 导出时有镜像可导。

### 步骤 4：导出离线包

```bash
# 在仓库根目录
bash scripts/offline-export.sh
```

脚本依次：构建项目镜像（gateway/collab/cad/ocr 等，缺失才建）→ **重建前端生产镜像**（`--target prod` + 注入品牌）→ 导出全部镜像为 tar → 拷 compose/配置/install.sh → 打包。

预期末尾输出：

```
  Offline Package Created!
  File:     eai-flow-offline-<版本>-<日期>.tar.gz
  Size:     约 3–5GB（含 RAGFlow）
  Images:   12（或更多）
```

### 步骤 5：核对包内容（强烈建议）

```bash
# 包内应有：images/、docker/、install.sh、load-images.sh、config.yaml、.env、manifest.json 等
tar tzf eai-flow-offline-*.tar.gz | head -30
# 镜像数量
tar tzf eai-flow-offline-*.tar.gz | grep -c 'images/.*\.tar'
```

> 首次导出较慢（构建全量镜像）；后续更新用 `--delta` 只导变化镜像（见《更新手册》）。

### 步骤 6：把包传到生产服务器

**方式 A：同内网 scp（推荐）**

```bash
scp eai-flow-offline-*.tar.gz root@<服务器IP>:/opt/
```

**方式 B：U 盘**（开发机与服务器物理隔离）

把 `eai-flow-offline-*.tar.gz` 拷进 U 盘，到服务器挂载后复制到 `/opt/`。

---

## 第二阶段：生产服务器首次部署

> 以下在**生产服务器**上以 `root`（或具备 docker 权限的用户）执行。

### 步骤 7：服务器环境预检

```bash
docker --version && docker compose version    # Docker >= 24 + compose v2
df -h /opt | awk 'NR==2{print "可用磁盘: "$4}'  # 建议 >= 40GB
free -g | awk '/^Mem:/{print "内存: "$2"GB"}'    # 建议 >= 8GB
ss -tlnp | grep -q ':4026 ' && echo "⚠️ 4026 被占用" || echo "4026 空闲"
docker compose -p eai-prod ps 2>/dev/null | grep -q prod-eai-flow && echo "⚠️ 有残留 eai-prod 项目" || echo "无残留"
```

任一项不达标先解决（端口占用改 `.env` 的 `PORT`；有残留先 `docker compose -p eai-prod down`，**不带 `-v`**）。

### 步骤 8：解压

```bash
cd /opt
tar xzf eai-flow-offline-*.tar.gz
cd eai-flow-offline-*/      # 进入解压出的部署目录（此后即 $DEER_FLOW_ROOT）
pwd && ls                    # 确认有 install.sh、docker/、images/、config.yaml、.env
```

### 步骤 9：核对/修改环境值

包内已带**完整的** `.env` / `config.yaml` / `extensions_config.json`（随仓库版本演进，无需从头写）。`install.sh` 会自动推导部署目录/密钥/受信来源，**通常你只需核对两项**：

**`.env` —— 检查这两个（最易错）：**

```bash
# 受信来源：通过服务器 IP 访问必填，否则登录被拒（CSRF）
grep DEER_FLOW_TRUSTED_ORIGINS .env
#   应为 http://<服务器IP>:4026（多个地址逗号分隔）。不对就 vi 改

# 内网 LLM key（与 config.yaml 的 intranet-llm 配合）
grep INTERNAL_LLM_API_KEY .env

# RAGFLOW_SECRET_KEY（RAGFlow v0.27.x 必需，包内 .env 已带固定值）
grep RAGFLOW_SECRET_KEY .env
#   ⚠️ 只核对非空即可，绝不可修改或清空：RAGFlow v0.27.x 把它缓存在 Redis，
#   变更后所有请求 401。系统整个生命周期（跨重启/升级）必须保持同一个值。

# RAGFlow API Key（部署后回填——法规库种子 + geo 样例库 RAGFlow 推送都靠它）
grep RAGFLOW_API_KEY .env
#   部署完成后：浏览器打开 http://<服务器IP>:19381 登录 → 个人设置 → 创建 API Key，
#   回填 .env 后 docker compose -p eai-prod up -d --force-recreate --no-deps gateway

# geo 样例库 RAGFlow 推送 dataset id（可选；留空=跳过推送，不影响入库主流程）
grep GSB_RAGFLOW_DATASET_ID .env
#   需要时在 RAGFlow Web UI 创建 geo-samples-slices 知识库，取其 dataset id 回填（同上重启 gateway）
```

**`.env` 自动推导项（一般不用手动改）：**

| 变量 | 由谁处理 |
|------|----------|
| `DEER_FLOW_ROOT` | `install.sh` 自动写入当前部署目录绝对路径 |
| `BETTER_AUTH_SECRET` | `install.sh` 自动 `openssl rand -base64 32` 生成（若你手填，用 `openssl rand -base64 32`）|

**`config.yaml`（仅当步骤 2 的 deploy.conf 没填 LLM_*、需手动配内网模型时）：**

```bash
grep -n 'intranet-llm' config.yaml          # 找到注释模板（约 80 行）
# vi 取消注释 intranet-llm 块，填 model / api_key / base_url
```

**`extensions_config.json`：** 一般无需改动（MCP 服务地址已配好）。

### 步骤 10：执行部署

```bash
chmod +x install.sh
./install.sh
```

**`install.sh` 会依次自动执行（看输出即可）：**
1. 环境预检（Docker/磁盘/内存/端口）；
2. 交互确认 `[y/N]` → 输入 `y`；
3. 从 `deploy.conf` 生成配置（**保留完整 .env，只定向注入必要键，不覆盖**）；
4. `load-images.sh` 导入全部镜像；
5. 创建 Docker 网络 `eai-prod_eai-flow-net`；
6. `docker compose up -d` 启动全部服务；
7. 等待 postgres-ext / gateway 健康（2–5 分钟）；
8. 跑数据库迁移；
9. 创建管理员 `admin@eai-flow.com`。

预期末尾：

```
  DeerFlow Installation Complete!
  Access URL:   http://<服务器IP>:4026
  Admin:        admin@eai-flow.com / Admin@2026
```

### 步骤 11：确认服务健康

```bash
$COMPOSE ps                          # 全部 Up，gateway/postgres-ext 应 healthy
curl -s http://localhost:4026/api/license/status | head -c 200
#   有 JSON 返回即 gateway 起来了（license 未导入会显示 in_grace_period）
```

> 若 gateway 没起来，先看日志：`$COMPOSE logs --tail=80 gateway`。常见原因见「常见坑」。

### 步骤 12：创建管理员账号（通常 install.sh 已自动建好）

验证管理员是否建成；没建成再手动补：

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST \
  http://localhost:4026/api/v1/auth/initialize \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}'
#   201=建成；409=已存在；其它=见坑2
```

> 默认管理员 `admin@eai-flow.com` / `Admin@2026`，**首次登录后立即改密码**。连续登录失败 5 次锁 5 分钟（429），`docker restart prod-eai-flow-gateway` 清计数器。

### 步骤 13：导入 License（关键，必须做）

License 是离线 JWT，绑定本机 `machine_id`。**不导入则 7 天宽限期后系统锁定。**

1. 浏览器打开 `http://<服务器IP>:4026` → 用 admin 登录 → 管理后台 → License 页；
2. 把 EAI 签发的 license 文本粘贴进去，导入；
3. 验证已落持久卷（导入逻辑写 `LICENSE_FILE_PATH`，自动持久化）：

```bash
ls -la data/license.lic            # 应存在
curl -s http://localhost:4026/api/license/status | head -c 300
#   期望 "valid": true
```

> 之后所有升级重建容器都不会丢 license（见《更新手册》§5）。

### 步骤 14：Temporal 用户（仅当部署含 Temporal 且 gateway 日志报 temporal 认证失败时）

```bash
# 检查 temporal 是否健康
$COMPOSE ps temporal
docker logs prod-eai-flow-temporal --tail 20 | grep -i 'password\|auth' && echo "⚠️ 需补建 temporal 用户"

# 幂等补建 temporal 角色 + 库
docker exec prod-eai-flow-postgres-ext sh /docker-entrypoint-initdb.d/10-temporal.sh
docker restart prod-eai-flow-temporal
docker logs prod-eai-flow-temporal --tail 20    # 期望无 password authentication failed
```

> 不要用 `--force-recreate temporal`，会级联重建 postgres 触发容器名冲突。

---

## 第三阶段：验证（部署完必做）

```bash
# 1. 全部容器 Up (healthy)
$COMPOSE ps

# 2. Gateway + license 健康
curl -s http://localhost:4026/api/license/status | head -c 300

# 3. 内网 LLM 连通性（从 gateway 容器内试连）
docker exec prod-eai-flow-gateway curl -sS -m 5 <你的LLM_BASE_URL>/models | head -c 200
#   有响应即通；超时/拒绝则检查 LLM 地址与 Docker 网络

# 4. 浏览器功能冒烟
#    http://<服务器IP>:4026 → 登录 → 检查：
#    · 对话（能调通 LLM）
#    · 知识库（RAGFlow，:19381 后台）
#    · 合同价分析
#    · 文档管理
```

任一项异常 → 看「常见坑」或对应服务日志。

---

## 常见坑（服务器实测记录）

### 坑 1：配置文件被生成脚本覆盖成残缺版
**症状**：部署后 gateway crash，日志报 `AppConfig → sandbox → Field required`，或 `.env` 缺失大量变量。
**根因**：旧版 `generate-config.sh` 用最小模板覆盖了包内完整的 `.env`/`config.yaml`。
**对策**：本手册对应版本已修复（生成只做定向注入、不覆盖完整文件）。若拿到旧包，从包内 tar 恢复完整 config 再重建：
```bash
mkdir -p /tmp/cfg && tar xzf /opt/eai-flow-offline-*.tar.gz -C /tmp/cfg config.yaml && cp /tmp/cfg/config.yaml config.yaml
$COMPOSE up -d --force-recreate --no-deps gateway
```

### 坑 2：install.sh 的 admin 初始化在 gateway 不健康时静默失败
**症状**：install.sh 跑完，但 `admin@eai-flow.com` 登录报「Incorrect」，postgres `agentflow` 库的 users 表为空（EAI 2026-08-29 核心库切 postgres，不再有 deerflow.db）。
**根因**：gateway 当时 crash-loop，`/api/v1/auth/initialize` 返回 502 → admin 没建成。
**对策**：gateway 修复健康后手动补建（见步骤 12）。

**重置已有 admin 密码**（users 表非空但忘了密码）：
```bash
# 密码真源在 extensions agentflow 库 users 表；gateway 侧镜像行在下一次成功登录时自动重建
HASH=$(docker exec -e PYTHONPATH=/app/backend prod-eai-flow-gateway /app/backend/.venv/bin/python -c "
from app.gateway.auth.password import hash_password; print(hash_password('Admin@2026'))")
# 校验 HASH 非空再落库——空 HASH 会把密码清成空串，锁死账号
[ -n "$HASH" ] || { echo "HASH 为空（gateway 内 hash_password 执行失败），中止"; exit 1; }
docker exec prod-eai-flow-postgres-ext psql -U agentflow -d agentflow -c "UPDATE users SET password_hash='$HASH' WHERE email='admin@eai-flow.com'"
# 必须输出 UPDATE 1；UPDATE 0 = 没这个用户（表空 → 走步骤 12 initialize 补建）
```

### 坑 3：License 升级后失效，需重新申请
**症状**：更新（重建 gateway 容器）后系统进入宽限期或锁定。
**根因**：license 默认写到容器临时层 `/app/license.lic`，容器重建即丢。
**对策**：本版本已修复 —— gateway 设了 `LICENSE_FILE_PATH` 指向持久 `./data`，且导入逻辑写该路径，UI 导入即自动持久化。**修复前的老系统**需一次性 rescue（见《更新手册》§5）。

### 坑 4：Temporal 报 `password authentication failed for user "temporal"`
**根因**：postgres 初始化脚本只在数据卷**真正为空**时跑；卷有残留则 temporal 角色没建。
**对策**：见步骤 14（幂等补建 + 重启 temporal，**不要** `--force-recreate temporal`）。

### 坑 5：登录被拒 / CSRF 报错（通过 IP 访问时）
**根因**：`.env` 的 `DEER_FLOW_TRUSTED_ORIGINS` 没填服务器 IP。
**对策**：
```bash
vi .env     # DEER_FLOW_TRUSTED_ORIGINS=http://<服务器IP>:4026（多个逗号分隔）
$COMPOSE up -d --force-recreate --no-deps gateway
```

---

## 数据安全红线（绝不可执行）

| 命令 | 后果 |
|------|------|
| `docker compose -p eai-prod down -v`（带 `-v`）| 删数据卷 → 主库/知识库全丢 |
| `docker volume prune` / `docker system prune --volumes` | 删未挂载卷 |
| `rm -rf` 部署目录（含 `./data`）| 删认证/线程/上传/license |
| `docker system prune -af` | 删已 load 未 up 的镜像 |

`docker compose down`（**不带 `-v`**）安全 —— 卷保留。

---

## 常用运维命令

```bash
$COMPOSE ps                                  # 服务状态
$COMPOSE logs -f gateway                     # 看 gateway 日志
$COMPOSE restart gateway                     # 重启 gateway（改 config.yaml 后）
$COMPOSE up -d --force-recreate --no-deps gateway   # 重建 gateway（改 .env 后）
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

**数据持久化位置（更新时全保留）：**

| 数据 | 位置 | 类型 |
|------|------|------|
| 主库（用户/文档/知识库/合同价/license镜像）| `eai-prod_prod-postgres-ext-data` | named volume |
| RAGFlow 索引/MinIO对象/MySQL | `eai-prod_prod-ragflow-*-data` | named volume |
| 核心库（线程/运行/checkpoints；EAI 2026-08-29 切 postgres）| `eai-prod_prod-postgres-ext-data`（`deerflow` 库）| named volume |
| 上传+memory/渠道登录态+machine_id+license | `./data`（→ `/app/backend/.deer-flow`）| bind mount |

---

## 部署流程速览图

```
开发机（有网）                         生产服务器（无外网）
─────────────                         ─────────────────
[1] 放品牌资产
[2] 填 deploy.conf
[3] make docker-start 预热
[4] offline-export.sh
       │  eai-flow-offline-*.tar.gz
[5] 核对包
[6] scp ──────────────────────────────▶  [7] 环境预检
                                          [8] 解压
                                          [9] 核对环境值(TRUSTED_ORIGINS/LLM key)
                                          [10] install.sh
                                                  │ 自动: 生成配置→load镜像
                                                  │       →建网络→up→等健康
                                                  │       →迁移→建admin
                                          [11] 确认健康
                                          [12] 建管理员(若未自动)
                                          [13] 导入 license(自动持久化)
                                          [14] temporal 用户(按需)
                                          [验证] ps/license/LLM连通/浏览器冒烟
```
