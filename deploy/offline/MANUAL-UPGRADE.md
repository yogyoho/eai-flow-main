# EAI-Flow 更新手册（离线生产环境）

> 适用场景：系统已在生产服务器运行，需要把**开发机新改的代码 / 配置**升级上去。
>
> 核心思路：**镜像化增量升级** —— 开发机只导出变化的镜像，服务器 `load` + `up`。数据在镜像之外，更新不丢。

---

## 0. 一句话结论

> **"拷几个镜像 → load → up" 就能完成升级**，前提是：
> 1. License 已持久化到 `./data/license.lic`（见 §4，一次性操作）；
> 2. 不碰数据红线命令（见 §6）；
> 3. 配置改动走"原地编辑"或"delta 带新基线"，不走会覆盖的 install.sh。

---

## 1. 升级分两类

| 升级类型 | 触发条件 | 怎么升 |
|----------|----------|--------|
| **代码升级** | 改了 Python / TS 代码 | §2 镜像 delta 流程 |
| **配置升级** | 改了 `.env` / `config.yaml` / `extensions_config.json` | §3 原地编辑或随包刷新 |

两者相互独立，可单独进行。

---

## 2. 代码升级（镜像 delta 流程）

### 2.1 开发机：重建变化的镜像

代码改动需先在开发机的 dev 环境（`eai-docker`）验证，然后重建对应镜像，让镜像 digest 变化（delta 才能识别）：

```bash
# 后端改动 → 重建 gateway 镜像
docker compose -p eai-docker build gateway

# 前端改动 → 必须重建前端生产镜像（Next.js 生产构建不读 src/，无法热补丁）
# offline-export.sh 内部会用 --target prod 重建 deer-flow-frontend
```

> 改了 `package.json`/`pnpm-lock.yaml`（依赖）：开发机要先 `make rebuild-frontend`，否则镜像里的 node_modules 是旧的。

### 2.2 开发机：导出 delta 包

```bash
# --since 填上次导出的版本 tag（服务器 manifest.json 里有，或开发机 .offline-export-history/ 里）
bash scripts/offline-export.sh --delta --since v20260804-abc1234
```

产出 `eai-flow-delta-<新版本>.tar.gz` —— **只含 digest 变化的镜像**。常只 1 个（如只改了后端 → 只有 `deer-flow-gateway`）。frontend/ragflow/postgres 没变就不在包里，服务器不会动它们。

### 2.3 传到服务器并升级

```bash
# 开发机推送
scp eai-flow-delta-*.tar.gz root@<服务器>:/opt/eai-flow-offline/delta/

# 服务器执行
ssh root@<服务器>
cd /opt/eai-flow-offline                          # 部署目录
mkdir -p delta && tar xzf delta/eai-flow-delta-*.tar.gz -C delta
./upgrade.sh delta
```

### 2.4 `upgrade.sh` 做了什么（自动）

1. **快照旧镜像**（回滚用）→ `docker load` 新镜像；
2. 配置 hash 变化才重生成配置（默认不变，**不碰你的 .env/config.yaml**）；
3. `docker compose up -d`（只重建镜像变化的容器，数据卷/bind-mount 原样保留）；
4. 升级前 `pg_dump` 备份；等待 gateway 健康；跑数据库迁移；
5. **健康检查失败 → 自动 reload 快照镜像回滚**；成功 → 更新服务器 manifest。

升级完成会提示：回滚快照在 `upgrade-backup-<版本>/`，确认稳定后可删。

---

## 3. 配置升级（不丢服务器专属值）

三个配置文件随仓库版本演进，会需要从开发机拿最新；但其中**服务器专属值绝不能被覆盖**。

### 3.1 三个文件的服务器专属值（小集合）

| 文件 | 服务器专属（保护）| 随版本演进（可刷新）|
|------|------|------|
| `.env` | `DEER_FLOW_ROOT`、`BETTER_AUTH_SECRET`、`DEER_FLOW_TRUSTED_ORIGINS`、`INTERNAL_LLM_API_KEY`、云端 key、`RAGFLOW_API_KEY`、DB 密码 | 端口映射、服务名、HOME、ENV 等 |
| `config.yaml` | intranet-llm 块（model/api_key/base_url）| 几乎全部（models/tools/sandbox/memory/subagents…）|
| `extensions_config.json` | ≈ 无（连接串密码默认值）| 全部 MCP/skill 定义 |

**保护机制**：服务器专属值集中在 `deploy.conf`（唯一手写、永不覆盖的文件）。`generate-config.sh` 从「dev 最新基线 + deploy.conf」生成三个文件 —— 所以"从 dev 取最新配置"既自动又安全，因为服务器值在 deploy.conf 里，不在三个文件里。

### 3.2 配置升级的两条路径

**路径 A：随 delta 包刷新（推荐，配置结构有变化时）**

开发机改了 config 基线 → `offline-export.sh --delta` 把新基线打进包 → 服务器 `upgrade.sh` 检测到 `config_hash` 变化 → 从「新基线 + 你的 deploy.conf」重生成。服务器专属值自动保留。

> 前提：你的服务器专属值已写进 `deploy.conf`。若当前是手动改的、还没进 deploy.conf，先做一次性"反推"（把现存值抄进 deploy.conf）。

**路径 B：原地编辑（只改个别值时）**

直接在服务器上改文件，然后按文件类型生效：

| 改什么 | 生效命令（原因）|
|--------|------------------|
| `config.yaml` | `docker compose -p eai-prod restart gateway`（bind-mount `:ro`，启动时读，部分字段热重载）|
| `.env` | `docker compose -p eai-prod up -d --force-recreate gateway`（**`env_file` 在容器创建时烘焙，`restart` 不够**）|
| `extensions_config.json` | 通常 gateway 热重载自动生效；不行则 `restart gateway` |

### 3.3 注意：基础设施字段改完必须重启 gateway

`config.yaml` 中 `database.*` / `checkpointer.*` / `run_events.*` / `sandbox.use` / `log_level` / `channels.*` 这些是**启动期一次性绑定**的字段，热重载不生效，必须 `restart gateway`（见 backend/CLAUDE.md「Config Hot-Reload Boundary」）。

---

## 4. License 持久化

License 是离线 JWT，绑定本机 `machine_id`。gateway 设了 `LICENSE_FILE_PATH=/app/backend/.deer-flow/license.lic`（映射持久 `./data` 卷），且导入逻辑会把 license 写到该持久路径 → **升级重建容器不丢 license，无需重新申请。**

### 新部署 / 已含本修复的系统

UI 导入 license 即自动落 `./data/license.lic`，**无需任何手动拷贝**。验证：

```bash
ls -la data/license.lic      # 应存在
```

### 修复前的老系统（license 还在容器临时层 /app/license.lic）

需一次性把已导入的 license 救到持久卷，之后重建 gateway：

```bash
cd /opt/eai-flow-offline   # 部署目录
docker cp prod-eai-flow-gateway:/app/license.lic ./data/license.lic
ls -la data/license.lic
# 确认 gateway environment 有 LICENSE_FILE_PATH=/app/backend/.deer-flow/license.lic（本仓库 compose 已内置）
docker compose -p eai-prod up -d --force-recreate --no-deps gateway
```

之后所有更新（含 gateway 镜像重建）license 都从 `./data/license.lic` 读，**无需重新申请**。

> `machine_id`（`./data/machine_id`）和宽限期时间戳（`./data/`）本就持久，不受更新影响。

---

## 5. 数据备份与回滚

### 5.1 升级前自动备份

`upgrade.sh` 在 `compose up` 前自动 `pg_dump`：

```bash
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > backup-pre-<版本>.sql
```

文件留在部署目录。**含数据库迁移的升级，升级前建议额外手工备份**：

```bash
BK=/opt/eai-backup-$(date +%Y%m%d); mkdir -p "$BK"; cd "$BK"
# 主库逻辑备份
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > db.sql
# ./data（认证/线程/上传/license）物理备份
tar czf data.tgz -C /opt/eai-flow-offline data
```

### 5.2 自动回滚（镜像问题）

`upgrade.sh` 健康检查失败会**自动 reload 升级前快照的旧镜像**并重新 up。排查：

```bash
docker compose -p eai-prod logs gateway
```

### 5.3 手动回滚（含数据库迁移已跑的情况）

镜像回滚是自动的，但**若迁移已向前执行**，DB 已变更，需手动恢复：

```bash
cd /opt/eai-flow-offline
# reload 升级前快照镜像
for t in upgrade-backup-<版本>/*.tar; do docker load -i "$t"; done
docker compose -p eai-prod up -d
# 恢复数据库（如迁移已跑且不兼容旧代码）
docker exec -i prod-eai-flow-postgres-ext psql -U agentflow agentflow < backup-pre-<版本>.sql
```

> 手动回滚命令 `upgrade.sh` 成功结束时也会打印出来。

---

## 6. 数据安全红线（绝不可执行）

| 命令 | 后果 |
|------|------|
| `docker compose -p eai-prod down -v` | `-v` 删数据卷 → 主库/知识库全丢 |
| `docker volume prune` / `docker system prune --volumes` | 删未挂载卷 |
| `rm -rf` 部署目录（含 `./data`）| 删认证/线程/上传/license |
| `docker system prune -af` | 删已 load 未 up 的镜像（含回滚快照）|
| 生产环境跑 `install.sh` | 触发 generate-config 覆盖配置（本版本已改为非破坏，但生产仍应只用 `upgrade.sh`）|
| 换新部署目录但不拷 `./data` | 丢聊天历史/认证（旧 deerflow.db 没带过来）|

`docker compose down`（不带 `-v`）安全。

---

## 7. 常见场景速查

### 只改了几个后端 Python 文件
开发机 `docker compose -p eai-docker build gateway` → `offline-export.sh --delta --since <版本>` → scp → `upgrade.sh delta`。delta 包只含 gateway 镜像，frontend/ragflow/postgres 不动。

### 改了前端 TS
同上，但 delta 里会是 frontend 镜像。**前端无热补丁捷径** —— 必须重建生产镜像。前端迭代请在开发机 dev 环境做，只把确认的修复推生产。

### 只改了配置（没动代码）
走 §3 路径 B 原地编辑 + 对应生效命令，无需镜像升级。

### 数据库加了新表/新列
无需操心 —— 迁移是加性幂等的（`ADD COLUMN/TABLE IF NOT EXISTS`），`upgrade.sh` 自动跑，不删现有数据，且升级前已 pg_dump。

### 完全搞砸了要回退到上个版本
用 `upgrade.sh` 留的 `upgrade-backup-<版本>/` 快照 reload 旧镜像（§5.3），数据从 `backup-pre-<版本>.sql` 恢复。
