# EAI-Flow 数据安全割接手册（旧部署 → 新方案）

> 场景：服务器上已运行旧版 EAI-Flow（`eai-prod`，手改 `.env`/`config.yaml`，`:latest` 镜像），
> 现在要切换到新方案（`deploy.conf` 驱动 + 生产前端构建 + 版本化 + 增量升级），**且不丢数据**。

## 核心原理

新方案**复用**旧部署的 **项目名 `eai-prod`、网络 `eai-prod_eai-flow-net`、同名数据卷**
（`eai-prod_prod-postgres-ext-data`、`eai-prod_prod-ragflow-*-data`、`./data`）。
所以"换系统" = 停旧容器（**不删卷**）+ 起新容器，卷自动重连，数据原样保留。

### 绝不可执行（会销毁数据）

| 命令 | 后果 |
|------|------|
| `docker compose -p eai-prod down -v` | `-v` 删除数据卷 |
| `docker volume prune` / `docker system prune --volumes` | 删除 down 后未挂载的卷 |
| `rm -rf` 部署目录（含 `./data`） | 删会话/上传/用户文件 |
| `docker system prune -af` | 删已 `load` 未 `up` 的镜像（F.9） |

`docker compose down`（**不带 `-v`**）是安全的——卷保留。

## 数据在哪里（备份目标）

| 数据 | 位置 |
|------|------|
| 主库（用户/文档/知识库/合同价） | `eai-prod_prod-postgres-ext-data`（named volume） |
| 会话/上传/用户文件 | `./data`（bind mount） |
| RAGFlow ES 索引 | `eai-prod_prod-ragflow-es-data` |
| MinIO 对象（合同价 OCR 桶） | `eai-prod_prod-ragflow-minio-data` |
| RAGFlow MySQL/Redis/app | `eai-prod_prod-ragflow-{mysql,redis,data}` |

---

## 割接步骤

### 0. 准备新离线包（有网开发机）
```bash
bash scripts/offline-export.sh                 # 全量包（含生产前端构建、RAGFlow 硬化、upgrade.sh）
scp eai-flow-offline-*.tar.gz root@<服务器>:/opt/
```

### 1. 备份（非可选，放到部署目录之外）
```bash
OLD=/opt/eai-flow-offline-*                    # 旧部署目录
BK=/opt/eai-backup-$(date +%Y%m%d); mkdir -p "$BK"; cd "$BK"

# 1a. 主库逻辑备份
docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > db.sql

# 1b. 各 named volume 物理备份
for v in eai-prod_prod-postgres-ext-data eai-prod_prod-ragflow-es-data \
         eai-prod_prod-ragflow-minio-data eai-prod_prod-ragflow-mysql-data \
         eai-prod_prod-ragflow-redis-data eai-prod_prod-ragflow-data; do
  docker run --rm -v ${v}:/src -v "$(pwd)":/dst alpine tar czf /dst/${v}.tgz -C /src .
done

# 1c. ./data + 旧配置
tar czf data.tgz -C "$OLD" data
cp "$OLD/.env" "$OLD/config.yaml" .
```

### 2. 配置一次性迁移（旧手改值 → 新 deploy.conf）
```bash
cd /opt && tar xzf eai-flow-offline-*.tar.gz && cd eai-flow-offline-*/
cp deploy.conf.example deploy.conf
vi deploy.conf
```
从旧 `.env`/`config.yaml` 抄入真实值：
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` ← 旧 `config.yaml` 的 `base_url`/`model` + 旧 `.env` 的 key
- `RAGFLOW_API_KEY` ← 旧 `.env`（若已配）
- `DB_PASSWORD` ← 旧 `.env` 的 `POSTGRES_EXT_PASSWORD`（默认 `agentflow123` 可留空）
- 品牌 4 项（显示名/Logo/Favicon/页脚）按客户填

### 3. 停旧服务（**不带 `-v`**）
```bash
cd "$OLD"
docker compose -p eai-prod -f docker/docker-compose.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.ragflow.yaml down        # 无 -v！卷保留
```

### 4. 用新方案部署（install.sh 零编辑）
```bash
cd /opt/eai-flow-offline-<新版>                   # 新解压目录
./install.sh
# 自动：load 镜像 → 读 deploy.conf 生成 .env/config.yaml/extensions_config.json
#       → 创建网络 → up → 健康检查 → 建管理员 admin@eai-flow.com / Admin@2026
```
容器在**同名卷**上重建 → 数据自动重连。

### 5. 验证
```bash
docker compose -p eai-prod ps                     # 全部 Up (healthy)
curl http://localhost:4026/api/license/status
# 浏览器登录，检查知识库 / 合同价分析 / 文档
```

### 6. 回滚（若验证失败）
数据卷未动（步骤 3 未删卷）。恢复旧配置 + 旧镜像后重启即可：
```bash
cp "$BK/.env" "$BK/config.yaml" "$OLD/"          # 还原旧配置到旧部署目录
# 若旧 :latest 镜像已被覆盖，从旧离线包重 load；否则直接起旧服务：
cd "$OLD" && docker compose -p eai-prod -f docker/docker-compose.yaml \
  -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.ragflow.yaml up -d
```

### 7. 稳定后清理（可选，确认几天无问题）
```bash
docker image prune                               # 只删悬空镜像，安全
# rm -rf "$BK"                                   # 删备份（确认不再需要后）
# 绝不：docker volume prune / docker system prune --volumes
```

---

## ⚠️ 已知坑（2026-07-30 服务器实测）

### 坑 1：部署到新目录会丢 `./data`（上传文件/memory/渠道登录态/license）
**症状**：割接后 thread 里的历史附件/图片打不开，或 license 需重新导入。
**根因**：`./data`（bind mount）是相对部署目录的。新版本解压到**新目录**，其 `./data` 是**空的新目录** → 上传文件、memory、渠道登录态、`license.lic`、`machine_id` 没带过来。
**注意（EAI 2026-08-29 核心库切 postgres 后更新）**：Gateway 认证用户 + 聊天 thread/run/checkpoint 已在 named volume `eai-prod_prod-postgres-ext-data`（`deerflow` 库），与部署目录无关、**随割接保留**——聊天历史不再丢。知识库/文档/合同价（agentflow 库）同理。
**对策**：割接后把旧 `./data` 从备份恢复到新部署目录：
```bash
cd /opt/eai-flow-offline-<新版本>
tar xzf /opt/eai-backup-<日期>/data.tgz          # 解出旧 data/（threads 上传文件 + license 等）
ls -la data/                                     # 确认在位
docker compose -p eai-prod -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.ragflow.yaml up -d --force-recreate gateway
```
恢复后用**旧 admin** 登录（密码是旧部署设的，不是 Admin@2026；忘了见坑 2 重置法）。

### 坑 2：install.sh 的 admin 初始化在 gateway 不健康时静默失败
**症状**：install.sh 跑完了，但 `admin@eai-flow.com` 登录报「Incorrect email or password」，postgres `deerflow` 库的 `users` 表为空。
**根因**：install.sh 在 gateway 健康检查后调 `/api/v1/auth/initialize` 建 admin。若 gateway 当时 crash-loop（如坑 3 的 config 缺 sandbox），initialize 调用失败（502）→ admin 没建成。
**对策**：gateway 修复健康后，手动补建 admin（users 表为空时 initialize 会成功，返回 201）：
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST http://localhost:4026/api/v1/auth/initialize \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}'
```
**重置已有 admin 密码**（users 表非空但忘了旧密码时；EAI 2026-08-29 起 users 在 postgres `deerflow` 库，不再用 sqlite）：
```bash
docker exec -e PYTHONPATH=/app/backend prod-eai-flow-gateway /app/backend/.venv/bin/python -c "
import psycopg
from app.gateway.auth.password import hash_password
con = psycopg.connect('postgresql://agentflow:agentflow123@postgres-ext:5432/deerflow')
cur = con.execute('UPDATE users SET password_hash=%s WHERE email=%s', (hash_password('Admin@2026'), 'admin@eai-flow.com'))
con.commit(); print('reset rows:', cur.rowcount)
"
```
> `UPDATE 1` 才是改到了；`UPDATE 0` 说明 users 表为空——走上面的 initialize 补建。
> 限流：连续登录失败 5 次锁 5 分钟（429）。`docker restart prod-eai-flow-gateway` 清内存计数器再登。

### 坑 3：generate-config.sh 曾用最小 config 覆盖（缺 sandbox → gateway crash）
**已在代码修复**（`generate-config.sh` 改为把内网 LLM 注入包内完整 config.yaml，保留 sandbox/tools/...，带回归测试）。**旧包**仍会触发：若 install 后 gateway 日志报 `AppConfig → sandbox → Field required`，说明用了有 bug 的旧 generator。
**临时对策**（旧包）：从包 tar 恢复完整 config.yaml，再重建 gateway：
```bash
mkdir -p /tmp/cfg && tar xzf /opt/eai-flow-offline-*.tar.gz -C /tmp/cfg config.yaml && cp /tmp/cfg/config.yaml config.yaml
docker compose -p eai-prod -f docker/docker-compose.yaml -f docker/docker-compose.extensions.yaml \
  -f docker/docker-compose.ragflow.yaml up -d --force-recreate gateway
```

---

### 坑 4：Temporal 报 `password authentication failed for user "temporal"`
**症状**：temporal 容器 crash-loop，日志 `pq: password authentication failed for user "temporal"`。
**根因**：postgres 的 `/docker-entrypoint-initdb.d/10-temporal.sh`（创建 temporal 角色 + temporal/temporal_visibility 库）只在 postgres **数据卷真正为空** 时执行。若卷有残留（或只清了 `./data` 没清 named volume `eai-prod_prod-postgres-ext-data`），脚本被跳过 → temporal 角色没建 → temporal 连不上。
**对策**：手动补建 temporal 角色 + 库（幂等），再**重启** temporal（不要 force-recreate）：
```bash
docker exec prod-eai-flow-postgres-ext sh /docker-entrypoint-initdb.d/10-temporal.sh   # 幂等：建角色 + 两库
docker restart prod-eai-flow-temporal
docker logs prod-eai-flow-temporal --tail 20   # 期望：Namespace cache refreshed / Search attributes added，无 auth failed
```
> `Search attribute ... already exists` 是幂等告警，不是错误。
> 重启 temporal 即可（重连 postgres）；**别用 `up --force-recreate temporal`**——会级联重建依赖 postgres-ext，触发容器名冲突（`/prod-eai-flow-postgres-ext already in use`）。要单独重建某服务用 `--no-deps`。

---

## 割接后：日常增量升级（不再全量重传）

开发机改代码后：
```bash
bash scripts/offline-export.sh --delta --since <上次版本>     # 只导变化镜像
scp eai-flow-delta-*.tar.gz root@<服务器>:/opt/eai-flow-offline/delta/
ssh root@<服务器> 'cd /opt/eai-flow-offline && mkdir -p delta && \
  tar xzf delta/eai-flow-delta-*.tar.gz -C delta && ./upgrade.sh delta'
```
`upgrade.sh`：load delta → config_hash 变则重生成 → 重建变化服务 → 迁移前 `pg_dump` → 失败自动 reload 快照回滚。
