# EAI-Flow 更新手册（离线生产环境 · 完整操作步骤）

> 适用场景：系统已在生产服务器运行，需要把**开发机新改的代码 / 配置**升级上去。
>
> 核心思路：**镜像化增量升级** —— 开发机只导出变化的镜像，服务器 `load` + `up`。数据在镜像之外，更新不丢。
>
> **底线结论："拷几个镜像 → load → up" 就能完成升级**，前提：① license 已持久化（§5，一次性）；② 不碰数据红线（§7）；③ 升级只用 `upgrade.sh`，不跑 `install.sh`。

---

## 0. 角色与约定

| 角色 | 机器 | 网络 | 典型目录 |
|------|------|------|----------|
| **开发机** | 你的开发机 | 需联网 | 仓库根（含 `scripts/`、`docker/`、`deploy/offline/`）|
| **生产服务器** | 内网 Linux | 无外网 | `/opt/eai-flow-offline`（部署目录，即 `$DEER_FLOW_ROOT`）|

**服务器侧统一约定**（下文命令用到）：先 `cd` 到部署目录，并设好 compose 前缀变量：

```bash
cd /opt/eai-flow-offline                                          # 你的部署目录
# 一次性设好（本终端会话有效）：项目名 + 全部 compose 文件
export COMPOSE="docker compose -p eai-prod \
  -f docker/docker-compose.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.ragflow.yaml"
```

> 之后本手册服务器侧命令都写成 `$COMPOSE restart gateway` 这样的短形式。

**关键容器/镜像名：**
- 容器：`prod-eai-flow-gateway` / `prod-eai-flow-frontend` / `prod-eai-flow-nginx` / `prod-eai-flow-postgres-ext` / `prod-eai-flow-collab` / `prod-eai-flow-temporal`
- 镜像：`deer-flow-gateway:latest` / `deer-flow-frontend:latest` / `eai-flow-collab:latest` / `eai-flow-ocr:latest` / `eai-flow-cad:latest` / `eai-flow-text-to-cad:latest` / `eai-flow-cad-viewer:latest`

---

## 1. 升级前必读：分清两类升级

| 升级类型 | 触发条件 | 走哪节 |
|----------|----------|--------|
| **代码升级** | 改了 Python / TS 代码（修 bug、加功能）| **§2**（镜像 delta 流程）|
| **配置升级** | 改了 `.env` / `config.yaml` / `extensions_config.json` | **§3**（原地编辑或随包刷新）|
| **首次升级前一次性准备** | license 持久化、deploy.conf 反推 | **§5**、**§4** |

两者相互独立，可单独进行；也可合并（代码 + 配置一起 delta 升级）。

---

## 2. 代码升级（镜像 delta 流程）—— 完整步骤

> 全程约 5–10 分钟（后端单服务）。改了什么服务，就只重建/导出/升级那个服务的镜像，其余服务不动。

### 步骤 0：开发机——确认改动已在 dev 环境验证通过

升级生产前，先在开发机 dev 环境（`eai-docker`）跑通你的改动：

```bash
# 后端改动：重启 gateway 使新代码生效，在 http://localhost:2026 验证
docker compose -p eai-docker restart gateway

# 前端改动：HMR 不靠谱时重启 frontend 验证
docker compose -p eai-docker restart frontend
```

**确认无误后再进下一步。** 不要把没验证过的代码推生产。

---

### 步骤 1：开发机——重建"变化的"镜像

delta 靠镜像 digest 变化来识别"哪些要导"。所以必须先让新代码进镜像。

#### 1a. 后端（gateway）改动

```bash
# 在仓库根目录，用 dev compose 重建 gateway 镜像（产出 eai-docker-gateway:latest）
docker compose -p eai-docker \
  -f docker/docker-compose-dev.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.temporal.yaml \
  build gateway
```

验证镜像 digest 已变（记下，待会儿和 delta 导出对照）：

```bash
docker image inspect eai-docker-gateway:latest --format '{{.Id}}'
```

#### 1b. 前端（frontend）改动

前端**不用手动重建**——`offline-export.sh` 步骤 2 会自动用 `--target prod` 重建 `deer-flow-frontend:latest`。直接进步骤 2。

> ⚠️ 若改了 `package.json` / `pnpm-lock.yaml`（依赖变更）：必须先 `make rebuild-frontend`（重建含新 node_modules 的 dev 前端镜像），否则 prod 构建仍用旧依赖。

#### 1c. 其他服务（collab / ocr / cad / text-to-cad / cad-viewer）改动

很少改。若改了，按 1a 同理用 dev compose 重建对应服务：

```bash
docker compose -p eai-docker \
  -f docker/docker-compose-dev.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.temporal.yaml \
  build <服务名>      # 如 collab / cad / ocr ...
```

---

### 步骤 2：开发机——查到"--since"基线版本

`--delta` 需要一个基线版本（= 服务器当前跑的版本）来比对 digest。**查服务器当前的版本：**

```bash
ssh root@<服务器> 'cat /opt/eai-flow-offline/manifest.json'
# 输出形如：{ "version": "v20260804-abc1234", ... }  ← 取这个 version 值
```

记下 `version` 值（如 `v20260804-abc1234`）。开发机必须有对应的基线 manifest：

```bash
ls .offline-export-history/                       # 应能看到上面那个版本目录
ls .offline-export-history/v20260804-abc1234/manifest.json   # 确认存在
```

> **若开发机 `.offline-export-history/` 丢了**（重装/清理过）：`--delta` 没基线可用 → 本次只能跑**全量** `bash scripts/offline-export.sh`（不带 `--delta`），它会重建基线；之后恢复 delta 流程。

---

### 步骤 3：开发机——导出 delta 包

```bash
# 在仓库根目录
bash scripts/offline-export.sh --delta --since v20260804-abc1234   # 换成步骤2查到的版本
```

脚本会：拉取/构建镜像 → 与基线比对 digest → 只 `docker save` 变化的镜像 → 产出 delta 包。

预期输出末尾：

```
Delta 包已生成（version=v20260805-def4567）
  文件:     eai-flow-delta-v20260805-def4567.tar.gz (例如 280M)
  变化镜像: 1，未变 11
```

### 步骤 4：开发机——核对 delta 包内容（强烈建议）

确认包里只有该变的镜像、没漏没多：

```bash
# 看包内文件清单
tar tzf eai-flow-delta-*.tar.gz
# 期望：images/<变化镜像>.tar + manifest.json，不该出现没变的服务

# 看新 manifest 记录了哪些镜像 + digest
tar xOzf eai-flow-delta-*.tar.gz manifest.json
```

> 例如只改了 gateway → 包里应只有 `images/deer-flow-gateway_latest.tar`。若包里冒出没改过的 frontend/ragflow，说明步骤 1 没对齐或基线选错，停下来排查。

---

### 步骤 5：把 delta 包传到服务器

**方式 A：同内网 scp（推荐）**

```bash
scp eai-flow-delta-*.tar.gz root@<服务器>:/opt/eai-flow-offline/delta/
```

**方式 B：U 盘**（开发机与服务器物理隔离时）

把 `eai-flow-delta-*.tar.gz` 拷进 U 盘，到服务器挂载后复制到 `/opt/eai-flow-offline/delta/`。

---

### 步骤 6：服务器——升级前手动备份（重要变更前必做）

`upgrade.sh` 会自动 `pg_dump`，但**涉及数据库迁移或重要升级时**，额外手工备一份放到部署目录外：

```bash
cd /opt/eai-flow-offline
BK=/opt/eai-backup-$(date +%Y%m%d-%H%M); mkdir -p "$BK"

# 6a. 主库逻辑备份（用户/文档/知识库/合同价/license镜像）
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > "$BK/db.sql"

# 6a-2. 核心库逻辑备份（线程/运行/checkpoints；EAI 2026-08-29 核心库已切 postgres）
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow deerflow > "$BK/core-db.sql"

# 6b. ./data 物理备份（上传 / memory / 渠道登录态 / license.lic / machine_id）
tar czf "$BK/data.tgz" -C /opt/eai-flow-offline data

ls -lh "$BK"                    # 确认两个文件都有内容
```

---

### 步骤 7：服务器——解压 delta 包

```bash
cd /opt/eai-flow-offline
mkdir -p delta
tar xzf delta/eai-flow-delta-*.tar.gz -C delta
ls delta/                       # 应看到 images/ 和 manifest.json
```

---

### 步骤 8：服务器——执行升级

```bash
cd /opt/eai-flow-offline
./upgrade.sh delta
```

**`upgrade.sh` 会自动依次执行（你看着输出即可）：**

1. 读 `delta/manifest.json` 拿新版本号；
2. **快照当前镜像**（回滚用）→ 存到 `upgrade-backup-<新版本>/`；
3. `docker load` delta 里的新镜像（覆盖同名 `:latest`）；
4. 若 `config_hash` 变化才重生成配置（**默认不变，不碰你的 .env/config.yaml**）；
5. `docker compose up -d`（**只重建镜像变化的容器**，数据卷/bind-mount 原样保留）；
6. `pg_dump` 备份到 `backup-pre-<新版本>.sql`；
7. 等 gateway 健康（轮询 `/api/license/status`）→ 跑数据库迁移；
8. **健康检查失败 → 自动 reload 步骤 2 的快照镜像回滚**；成功 → 把新 manifest 拷成服务器 `manifest.json`。

**预期成功末尾：**

```
[UP] 升级完成: v20260805-def4567
[UP]   回滚快照在 upgrade-backup-v20260805-def4567/；确认稳定后可删
[UP]   手动回滚: for t in upgrade-backup-v20260805-def4567/*.tar; do docker load -i "$t"; done && docker compose ...
```

---

### 步骤 9：服务器——升级后验证（必做）

```bash
# 9a. 全部容器 Up (healthy)，尤其 gateway
$COMPOSE ps

# 9b. Gateway 健康 + license 有效
curl -s http://localhost:4026/api/license/status | head -c 300
# 期望 JSON 里 "valid": true（或宽限期内），不报 502/连接拒绝

# 9c. 镜像版本已更新
cat manifest.json | grep version

# 9d. 功能冒烟（浏览器）
#    http://<服务器IP>:4026 → 登录 → 开个对话 / 查知识库 / 查合同价分析
```

任一项异常 → 走 **§6 回滚**。

---

### 步骤 10：稳定后清理（可选，确认几天无问题再做）

```bash
cd /opt/eai-flow-offline
rm -rf upgrade-backup-v20260805-def4567/      # 回滚快照（确认不再回退才删）
docker image prune                             # 只删悬空镜像，安全
# 绝不：docker volume prune / docker system prune --volumes（见 §7 红线）
```

---

## 3. 配置升级（不丢服务器专属值）

三个配置文件随仓库版本演进，会需要从开发机拿最新；但其中**服务器专属值绝不能被覆盖**。

### 3.1 三个文件的服务器专属值（小集合）

| 文件 | 服务器专属（保护）| 随版本演进（可刷新）|
|------|------|------|
| `.env` | `DEER_FLOW_ROOT`、`BETTER_AUTH_SECRET`、`DEER_FLOW_TRUSTED_ORIGINS`、`INTERNAL_LLM_API_KEY`、云端 key、`RAGFLOW_API_KEY`、DB 密码 | 端口映射、服务名、HOME、ENV 等 |
| `config.yaml` | intranet-llm 块（model/api_key/base_url）| 几乎全部（models/tools/sandbox/memory/subagents…）|
| `extensions_config.json` | ≈ 无（连接串密码默认值）| 全部 MCP/skill 定义 |

**保护机制**：服务器专属值集中在 `deploy.conf`（唯一手写、永不覆盖的文件）。`generate-config.sh` 从「dev 最新基线 + deploy.conf」生成三个文件 —— 已改为**非破坏式**（存在则定向 patch、不存在才创建）。

### 3.2 配置升级的两条路径

#### 路径 A：随 delta 包刷新（推荐，配置结构有变化时）

开发机改了 config 基线 → 走 §2 的 delta 流程 → `offline-export.sh --delta` 把新基线打进包 → 服务器 `upgrade.sh` 检测到 `config_hash` 变化 → 从「新基线 + 你的 deploy.conf」重生成。服务器专属值自动保留。

> **前提**：服务器专属值已写进 `deploy.conf`。若当前是手动改的、还没进 deploy.conf，先做 §4 的"反推"。

#### 路径 B：原地编辑（只改个别值时，最快）

直接在服务器上改文件，然后按文件类型生效：

| 改什么 | 生效命令 | 原因 |
|--------|----------|------|
| `config.yaml`（多数字段）| `$COMPOSE restart gateway` | bind-mount `:ro`，启动时读，部分字段热重载 |
| `.env` | `$COMPOSE up -d --force-recreate --no-deps gateway` | **`env_file` 在容器创建时烘焙，`restart` 读不到新值** |
| `extensions_config.json` | 通常 gateway 热重载自动生效；不行则 `$COMPOSE restart gateway` | mtime 触发重载 |

**原地编辑完整步骤（以改 `config.yaml` 的 LLM 超时为例）：**

```bash
cd /opt/eai-flow-offline
# 1. 改前备份
cp config.yaml config.yaml.bak.$(date +%Y%m%d)
# 2. 编辑
vi config.yaml
# 3. 生效
$COMPOSE restart gateway
# 4. 验证 gateway 起来了
$COMPOSE ps gateway
curl -s http://localhost:4026/api/license/status | head -c 200
# 5. 不对就还原
cp config.yaml.bak.<日期> config.yaml && $COMPOSE restart gateway
```

### 3.3 注意：基础设施字段改完必须 restart（不能靠热重载）

`config.yaml` 中 `database.*` / `checkpointer.*` / `run_events.*` / `sandbox.use` / `log_level` / `channels.*` 是**启动期一次性绑定**的字段，热重载不生效，改完必须 `$COMPOSE restart gateway`（见 backend/CLAUDE.md「Config Hot-Reload Boundary」）。

---

## 4. 一次性准备：把服务器专属值反推进 deploy.conf

> 仅需做一次。做完后"配置从 dev 刷新"才安全自动（§3 路径 A）。

若服务器上的 `.env`/`config.yaml` 是当初手动从开发机拷过来改的（很可能），服务器专属值还散落在三个文件里、没进 `deploy.conf`。一次性把它们抄进去：

```bash
cd /opt/eai-flow-offline
cp -n deploy.conf.example deploy.conf       # 没有则从模板建
vi deploy.conf
```

对照服务器现状填这几项（其余留空走默认）：

```ini
# 从 .env 抄：
LLM_API_KEY=<.env 里的 INTERNAL_LLM_API_KEY 值>
RAGFLOW_API_KEY=<.env 里的 RAGFLOW_API_KEY 值>
DB_PASSWORD=<.env 里的 POSTGRES_EXT_PASSWORD；默认 agentflow123 可留空>

# 从 config.yaml 的 intranet-llm 块抄：
LLM_BASE_URL=<base_url>
LLM_MODEL=<model>

# 品牌（一般首次部署已定，不用再改）：
BRAND_NAME=...
BRAND_FOOTER=...
```

> `DEER_FLOW_ROOT` / `BETTER_AUTH_SECRET` / `DEER_FLOW_TRUSTED_ORIGINS` 不用写进 deploy.conf —— `upgrade.sh`/`install.sh` 会自动从部署目录、现有 `.env`、本机 IP 推导。

验证 deploy.conf 能正确生成（dry run，不会覆盖现有配置——generate-config 已非破坏）：

```bash
# 用现有 .env 的 secret 和本机 origin 试生成（定向 patch，不动其它键）
bash scripts/generate-config.sh --conf deploy.conf --out . \
  --root "$(pwd)" \
  --secret "$(grep '^BETTER_AUTH_SECRET=' .env | cut -d= -f2)" \
  --origin "http://$(hostname -I | awk '{print $1}'):4026"
diff .env .env.bak.$(date +%Y%m%d)   # 应只有你预期的键变化
```

---

## 5. 一次性准备：License 持久化

License 是离线 JWT，绑定本机 `machine_id`。gateway 设了 `LICENSE_FILE_PATH=/app/backend/.deer-flow/license.lic`（映射持久 `./data` 卷），且导入逻辑写该路径 → **升级重建容器不丢 license，无需重新申请。**

### 5.1 判断你的系统属于哪种

```bash
cd /opt/eai-flow-offline
ls -la data/license.lic 2>/dev/null && echo "持久卷已有 license（新系统/已修复）" \
  || docker exec prod-eai-flow-gateway test -f /app/license.lic && echo "license 在容器临时层（老系统，需 §5.3 rescue）" \
  || echo "未找到 license，需重新导入"
```

### 5.2 新部署 / 已含本修复的系统

UI 导入 license 即自动落 `./data/license.lic`，**无需任何手动拷贝**。验证：

```bash
ls -la data/license.lic      # 应存在
```

### 5.3 修复前的老系统（license 在容器临时层 /app/license.lic）

一次性把已导入的 license 救到持久卷，再重建 gateway：

```bash
cd /opt/eai-flow-offline

# 1. 确认 gateway environment 有 LICENSE_FILE_PATH（本仓库 compose 已内置）
grep LICENSE_FILE_PATH docker/docker-compose.yaml
#   期望输出含 LICENSE_FILE_PATH=/app/backend/.deer-flow/license.lic
#   若没有（很老的部署）：手动加进 docker/docker-compose.yaml 的 gateway.environment 再继续

# 2. 把 license 救到持久目录（./data 挂载到 /app/backend/.deer-flow）
docker cp prod-eai-flow-gateway:/app/license.lic ./data/license.lic
ls -la data/license.lic       # 确认在位、有内容

# 3. 重建 gateway 使其从持久路径读 license（顺便应用 LICENSE_FILE_PATH）
$COMPOSE up -d --force-recreate --no-deps gateway

# 4. 验证 license 仍有效
curl -s http://localhost:4026/api/license/status | head -c 300
#   期望 "valid": true
```

之后所有更新（含 gateway 镜像重建）license 都从 `./data/license.lic` 读，**无需重新申请**。

> `machine_id`（`./data/machine_id`）和宽限期时间戳（`./data/license_start.log`）本就持久，不受更新影响。

---

## 6. 回滚（升级出问题时）

### 6.1 自动回滚（镜像问题，upgrade.sh 已自动处理）

`upgrade.sh` 健康检查失败会**自动 reload 升级前快照的旧镜像**并重新 up。若它报了回滚，排查：

```bash
$COMPOSE logs --tail=100 gateway
```

### 6.2 手动回滚——仅镜像变了（最常见）

数据库没动，只是新代码起不来：

```bash
cd /opt/eai-flow-offline
# 1. reload 升级前快照的旧镜像（目录名见升级完成时的提示）
for t in upgrade-backup-<新版本>/*.tar; do docker load -i "$t"; done
# 2. 用旧镜像重新 up（只重建，不碰数据卷）
$COMPOSE up -d
# 3. 验证
$COMPOSE ps
curl -s http://localhost:4026/api/license/status | head -c 200
```

### 6.3 手动回滚——数据库迁移已跑（需连数据一起回退）

镜像回滚 + 数据库从升级前的备份恢复：

```bash
cd /opt/eai-flow-offline

# 1. reload 旧镜像
for t in upgrade-backup-<新版本>/*.tar; do docker load -i "$t"; done
$COMPOSE up -d

# 2. 等 gateway 起来
$COMPOSE ps

# 3. 恢复数据库（用 upgrade.sh 自动留的，或 §6 手工备的）
#    dump 用 --clean --if-exists 生成（先 DROP 后 CREATE，可直接灌回已建表的库）；
#    ON_ERROR_STOP=1 让首错即停——静默吞错会得到"看似成功"的半恢复库。
docker exec -i prod-eai-flow-postgres-ext psql -v ON_ERROR_STOP=1 -U agentflow agentflow < backup-pre-<新版本>.sql
docker exec -i prod-eai-flow-postgres-ext psql -v ON_ERROR_STOP=1 -U agentflow deerflow < backup-pre-<新版本>-core.sql
#   若用手工备份：psql ... < /opt/eai-backup-<日期>/db.sql + core-db.sql

# 4. 验证功能
```

> ⚠️ 恢复数据库会覆盖当前数据。仅在"新迁移破坏了旧代码运行"时才做，且确认备份是升级前的。

---

## 7. 数据安全红线（绝不可执行）

| 命令 | 后果 |
|------|------|
| `docker compose -p eai-prod down -v`（带 `-v`）| 删数据卷 → 主库/知识库全丢 |
| `docker volume prune` / `docker system prune --volumes` | 删未挂载卷 |
| `rm -rf` 部署目录（含 `./data`）| 删认证/线程/上传/license |
| `docker system prune -af` | 删已 load 未 up 的镜像（含回滚快照）|
| 生产环境跑 `install.sh` | 触发 generate-config（本版本已非破坏，但生产仍只用 `upgrade.sh`）|
| 换新部署目录但不拷 `./data` | 丢上传文件/memory/渠道登录态/license（聊天历史+认证已入 postgres named volume，不受部署目录影响）|

`docker compose down`（**不带 `-v`**）安全 —— 卷保留。

**数据持久化位置（更新时全保留）：**

| 数据 | 位置 | 类型 |
|------|------|------|
| 主库（用户/文档/知识库/合同价/license镜像）| `eai-prod_prod-postgres-ext-data` | named volume |
| RAGFlow 索引/MinIO/MySQL | `eai-prod_prod-ragflow-*-data` | named volume |
| 核心库（线程/运行/checkpoints；EAI 2026-08-29 切 postgres）| `eai-prod_prod-postgres-ext-data`（`deerflow` 库）| named volume |
| 上传+memory/渠道登录态+machine_id+license | `./data`（→ `/app/backend/.deer-flow`）| bind mount |

---

## 8. 常见场景速查

| 场景 | 怎么做 |
|------|--------|
| **只改几个后端 Python 文件** | §2：dev `build gateway` → `offline-export.sh --delta --since <现版本>` → scp → `upgrade.sh delta`。delta 只含 gateway 镜像，其余不动。 |
| **改了前端 TS** | §2：前端不用手动重建，`offline-export.sh --delta` 会自动 `--target prod` 重建。前端无热补丁捷径。 |
| **改了前端依赖** | 先 `make rebuild-frontend`，再 `offline-export.sh --delta`。 |
| **只改了配置（没动代码）** | §3 路径 B 原地编辑 + 对应生效命令，无需镜像升级。 |
| **配置结构变了（dev 改了 config 基线）** | §3 路径 A：随 delta 刷新（前提：§4 deploy.conf 已反推）。 |
| **数据库加了新表/新列** | 无需操心——迁移加性幂等（`ADD COLUMN/TABLE IF NOT EXISTS`），`upgrade.sh` 自动跑，不删数据，且升级前已 pg_dump。 |
| **升级后起不来** | §6.2 手动 reload 旧镜像快照回滚。 |
| **完全搞砸** | §6.3 镜像 + 数据库备份一起回退。 |
| **首次升级前** | 先做 §5（license 持久化）+ §4（deploy.conf 反推）。 |

---

## 9. 升级流程速览图

```
开发机（有网）                         生产服务器（无外网）
─────────────                         ─────────────────
[1] dev 验证改动
[2] build 变化的镜像
       │
[3] 查服务器现版本(--since)
[4] offline-export.sh --delta
       │  eai-flow-delta-*.tar.gz
[5] scp ──────────────────────────────▶  [6] 手工备份(pg_dump + ./data)
                                          [7] 解压 delta
                                          [8] upgrade.sh delta
                                                 │ 自动: 快照→load→up
                                                 │       →pg_dump→迁移
                                                 │       →健康检查/回滚
                                          [9] 验证 (ps/license/冒烟)
                                          [10] 稳定后清快照
```

---

## 10. 地质样例库编译产物（references）备份/恢复

地质样例库（geo-samples）的编译产物**不在数据库里**，落盘在 `skills/public/geological-report/references/` 下三个子目录（容器内为 `/app/skills/public/geological-report/references/`；宿主 bind-mount 时即仓库同路径）：

| 子目录 | 内容 |
|--------|------|
| `samples_bank/` | 切片库（`<stage>/slices/chN/<rid>__N.md`）+ `bank_index.json` 索引 |
| `depth_targets/<stage>/` | per 矿种深度基线 `<mineral>.json` |
| `samples/<stage>/` | SL3 指纹池增量 `chN__<rid>.md` |

离线生产镜像是非 bind-mount 打包的——这些产物写在**容器可写层**，每次升级换镜像即丢弃可写层。**升级前备份、升级后恢复，两步都不能省：**

### 10.1 升级前备份（服务器执行）

```bash
cd /opt/eai-flow-offline
BK=/opt/eai-backup-$(date +%Y%m%d-%H%M); mkdir -p "$BK"

# 从现容器可写层打包三个 references 子目录
docker exec prod-eai-flow-gateway tar czf - -C /app/skills/public/geological-report/references \
  samples_bank depth_targets samples > "$BK/geo-references.tgz"
ls -lh "$BK/geo-references.tgz"    # 确认有内容

# dev 环境 references 是 bind-mount（即仓库路径），宿主在仓库根直接打包即可：
# tar czf geo-references.tgz skills/public/geological-report/references/samples_bank \
#   skills/public/geological-report/references/depth_targets \
#   skills/public/geological-report/references/samples
```

### 10.2 升级后恢复

解包回**新容器**同路径即可；产物是确定性再生（`bank_index`/基线均 `sort_keys` 幂等写），不恢复、直接在管理页重跑 compile 也能全部再生，只是耗时更长：

```bash
docker exec -i prod-eai-flow-gateway tar xzf - -C /app/skills/public/geological-report/references \
  < "$BK/geo-references.tgz"
```

### 10.3 状态回退（产物丢失但状态未跟着降级时）

编译完成后 `gsb_documents.status='compiled'`，而 compile 只消费 `reviewed` 状态的样例（compiled 的会被跳过）。若产物已丢、状态还停在 `compiled`，先降回 `reviewed` 再重跑：

```bash
docker exec prod-eai-flow-postgres-ext psql -U agentflow agentflow -c \
  "UPDATE gsb_documents SET status='reviewed' WHERE status='compiled';"
# 随后在管理页重跑 compile，再生全部产物
```
