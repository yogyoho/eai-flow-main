# 离线部署简化与增量升级 — 设计文档

> 日期：2026-07-29
> 状态：草案，待 review
> 关联：`docs/OFFLINE_DEPLOYMENT_GUIDE.md`、`scripts/offline-export.sh`、`deploy/offline/*`、附录 F.1–F.22 故障记录

## 1. 背景与问题

EAI-Flow 已有一套成熟的内网离线部署体系（`scripts/offline-export.sh` 导出镜像 + `deploy/offline/` 编排 + `install.sh`/`deploy.sh` 一键部署），并在内网服务器（10.180.41.157）验证通过。但**部署与升级体验痛苦**，用户反馈集中在：

- **配置复杂度太高**：`.env`、`config.yaml`、`extensions_config.json` 多处手填，漏一个就报奇怪的错（F.2 缺 `EXTENSIONS_DB_HOST`、F.6 `NETWORK_NAME` 覆盖、F.20 缺 `RAGFLOW_API_KEY`）。
- **步骤繁琐**：5 个 `-f` compose 文件按序拼接、镜像 tag 手工对齐（F.8）、首次挂载把文件变目录（F.10）。
- **升级=全量重装**：附录 D 的升级流程是"获取整包 → 全停 → 全量重导镜像 → 手工 diff config → 重启"，与首次部署同款痛苦复发，且无回滚。

### 关键认知（推翻"直接部署开发环境"的设想）

用户曾设想"直接把本机开发环境搬到服务器"。经核查代码，**这会更难而非更易**：

1. **离线包本就是开发镜像**：`offline-export.sh:120-170` 明确 *拒绝 pull / 拒绝 rebuild*，只导出开发机已验证的本地镜像并 retag。离线包 = dev 镜像 + 一层生产 compose 包装，二者同源。
2. **生产前端跑的是 dev 模式**：`deploy/offline/frontend-start.sh:33` 执行 `pnpm dev`。附录 22 个故障中 **F.14–F.18（HMR、allowedDevOrigins、Google Fonts、Turbopack 缓存）全是 dev 模式独有问题**。
3. **开发环境被焊在本机**：`docker/docker-compose-dev.yaml` 用 `build:` 从源码构建，bind-mount `../frontend/src`、`${HOME}/.claude`、`${HOME}/.codex`、kubeconfig。原样搬服务器需传**完整源码树 + 构建上下文**，是离线包的超集。
4. 真正难的（镜像离线传输、装 Docker、LVM 磁盘满 F.22、RAGFlow 抽风 F.11–F.13）与 dev/prod 选择无关，两种方案一样难。

**结论**：不切换环境，而是正交地做三件事——配置自动化、生产前端构建、把已知修复烘焙进默认值。

## 2. 目标 / 非目标

### 目标
- **G1 零编辑部署**：全新部署只需一个 `deploy.conf`（几行）+ 一条命令；路径/密钥/origins 全自动推导。
- **G2 生产前端构建**：离线镜像用 `pnpm build` 产出，消灭 F.14–F.18 整类 dev 模式问题。
- **G3 增量升级**：开发机只导变化镜像，ssh/scp 推送，服务器只重建变化服务，内置回滚。
- **G4 数据安全替换**：把已部署的旧系统原地替换为新方案，数据（postgres / `./data` / RAGFlow 卷 / MinIO）零丢失，可回滚。
- **G5 按客户品牌化**：显示名 / Logo / Favicon / 页脚信息按客户变，值驱动，无源码漂移。
- **G6 已知修复入默认值**：F.2/F.6/F.8/F.10/F.11–F.13/F.20 等在导出时预置，不再靠人记得改。

### 非目标
- 不改变服务范围（全量：核心 + RAGFlow + Temporal + 合同价 OCR + CAD）。
- 不做多服务器批量编排（单台内网服务器场景；批量部署留待后续）。
- 不改 deer-flow 上游核心/harness 代码；改动限定在 `scripts/`、`deploy/offline/`、前端品牌重构（遵循 EAI-CUSTOM 注释规范）。
- 不引入镜像仓库/registry（保持文件级 `docker save/load` 离线交付）。

## 3. 现状分析

### 数据持久化布局（G4 的安全基础）
全部持久化数据在 **named volume + `./data`**，与镜像（只读模板）无关：

| 数据 | 位置 | 来源 |
|------|------|------|
| 主库（用户/文档/知识库元数据/合同价） | `eai-prod_prod-postgres-ext-data` | `docker-compose.extensions.yaml:17` |
| 会话/上传/用户文件 | `./data`（bind mount → `/app/backend/.deer-flow`） | `docker-compose.yaml:93` |
| RAGFlow ES 索引 | `eai-prod_prod-ragflow-es-data` | `docker-compose.ragflow.yaml:61` |
| MinIO 对象（合同价 OCR 桶） | `eai-prod_prod-ragflow-minio-data` | `docker-compose.ragflow.yaml:122` |
| RAGFlow MySQL/Redis/app | `eai-prod_prod-ragflow-{mysql,redis,data}` | `docker-compose.ragflow.yaml:82,101,34` |

**关键性质**：named volume 在 `docker compose down` 后仍存在；仅 `down -v` / `docker volume rm` / `docker volume prune` / `rm -rf 部署目录` 会销毁。这是原地替换的数据安全前提。

### 已具备的基础
- `frontend/Dockerfile:42-55` 已有完整 `prod` target（`pnpm build` + `pnpm start`）。
- `frontend/src/version.ts` 已有 `NEXT_PUBLIC_APP_VERSION` 构建期注入先例 → 值驱动品牌机制可复用同模式。
- `docker-compose.ragflow.yaml:8` 已支持 `${RAGFLOW_IMAGE:-...}` 覆盖 → 切换 `v0.25.3-fixed` 仅改默认值。
- `frontend/src/styles/globals.css:1-2`、`dashboard.css:1` 已用 `@fontsource`（离线兼容）→ F.16 已根治，**不需再处理 Google Fonts**。
- `frontend/src/app/settings/basic-settings.tsx:459` RAGFlow 链接为 `http://${hostname}:${port}`（`:87` 注释：当前访问主机名 + 固定端口）→ **动态拼、不需按客户改**。

## 4. 设计

### 4.1 配置层：单一配置源 + 生成器

**唯一手写文件 `deploy.conf`**（部署目录根，~10 行）：

```ini
# ── 必填（完全离线时）──
BRAND_NAME=客户公司名            # 显示名（NEXT_PUBLIC_BRAND_NAME）
BRAND_FOOTER=© 2026 客户公司 ...  # 页脚（NEXT_PUBLIC_BRAND_FOOTER）
BRAND_ASSETS_DIR=./brand-assets  # 该客户的 logo/favicon 文件目录

# ── LLM（内网可连外网则留空走云端默认）──
LLM_BASE_URL=http://192.168.x.x:8080/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen-plus

# ── 可选 ──
RAGFLOW_API_KEY=                 # 首次可留空，Web UI 生成后补
RAGFLOW_HTTP_PROXY=              # RAGFlow 拉取 tiktoken 用代理
DB_PASSWORD=                     # 留空走默认 agentflow123
```

**`scripts/generate-config.sh`**（新）：读 `deploy.conf`，展开生成：
- `config.yaml`（models 段按 LLM_* 注入内网模板，或保留云端默认）；
- `.env`（`DEER_FLOW_ROOT` 自动取部署目录、`BETTER_AUTH_SECRET` 默认值时 `openssl rand -base64 32` 生成、`EXTENSIONS_DB_*` 预填、`RAGFLOW_*` 注入）；
- `extensions_config.json`（默认空 mcpServers/skills）。

**`deploy.sh`（改）/ `install.sh`（生成）零编辑流**：
- 自动推导：`DEER_FLOW_ROOT=$(pwd)`；`BETTER_AUTH_SECRET` 若仍为默认占位则生成；`DEER_FLOW_TRUSTED_ORIGINS` / `INTRANET_HOSTS` 从 `hostname -I` 取当前 IP + `http://<ip>:${PORT}`。
- 唯一交互：`deploy.conf` 未填 LLM 且检测到无外网时，提示填 LLM 地址。
- 把 5 个 `-f` 合并为生成器产出的一条 compose 调用，消除"按序拼接"心智负担。

### 4.2 镜像层：生产前端构建 + RAGFlow 硬化 + 修复入默认值

- **前端生产构建**：`offline-export.sh` 构建前端时用 `--target prod`（而非 dev 镜像 + `pnpm dev`）。删除 `deploy/offline/frontend-start.sh` 及 compose 中 `frontend-overrides/` 运行时 bind mount（品牌改走构建期注入，见 4.5）。→ 消灭 F.14（HMR）、F.15（allowedDevOrigins）、F.17（YAML command）、F.18（Turbopack 缓存）。
- **RAGFlow 硬化**：导出时使用 `infiniflow/ragflow:v0.25.3-fixed`（F.11：补 `pip` + venv PATH）；预置 `cl100k_base.tiktoken` 文件（F.13：消除首次拉取对外网依赖），`RAGFLOW_HTTP_PROXY` 作为可选后备；修掉 named-volume 覆盖镜像内容（F.12：导出文档/脚本提示首次起 ragflow 前的 volume 处理）。
- **修复入默认值**：`.env` 预填 `EXTENSIONS_DB_HOST=postgres-ext` 等 5 项（F.2）；Temporal 首次启动自动建用户/库（F.3，由 `postgres-init/` one-shot 脚本完成）；`nginx.conf` 去掉 `/_next/webpack-hmr` 的 `return 204` hack（F.14）；包内预置 `nginx/nginx.conf` 实体文件防 F.10 目录陷阱；注释掉 `.env` 中误导性的 `NETWORK_NAME`（F.6）。

### 4.3 版本化与回滚

- 镜像打 **`:v<ver>` tag**（如 `deer-flow-gateway:v2.1`），不再只用 `:latest`。
- compose 镜像引用统一为 `${GATEWAY_IMAGE:-deer-flow-gateway}:${IMAGE_TAG:-latest}` 形式 → 不设 `IMAGE_TAG` 自动回退老 `:latest` 行为，**与现有部署二进制兼容**。
- 回滚 = 改 `IMAGE_TAG` 回旧值 + `up -d --no-deps <svc>`，秒级，老镜像仍留存服务器。
- 导出时记录 `manifest.json`：版本号、各镜像名+tag+digest、配置 hash。

### 4.4 增量升级（ssh/scp 推送，G3）

**开发机侧**：`offline-export.sh --delta --since vN`
- 对比上次导出的 `manifest.json` 与当前本地镜像 digest；
- 仅 `docker save` 变化过的镜像（典型迭代只动 gateway+frontend 两三个）；
- 产出 delta 包：`images/<changed>.tar` + 新 `manifest.json` + 配置 hash。

**推送**（内网 ssh/scp 直连）：
- 小 delta：`scp -r delta-pkg/ root@srv:/opt/eai-flow-offline/delta/`；
- 单镜像管道直推（避开大包 SSH 断连 F.19）：`docker save <img> | ssh root@srv "docker load"`。

**服务器侧 `upgrade.sh`（新，打进包内）**：
1. `docker load` 仅 delta 镜像；
2. 仅当 `deploy.conf` 变化（配置 hash 不同）才 `generate-config.sh` 重新生成配置，并 `diff` 展示；
3. 仅重建变化的服务：`docker compose ... up -d --no-deps <changed-svcs>`；
4. gateway 变化时，迁移前先 `pg_dump` 备份主库，再跑 `python -m app.extensions.workflow.migration`；
5. 健康检查（`/api/license/status`）；失败则 `IMAGE_TAG=<旧> up -d --no-deps` 自动回滚；
6. **数据卷绝不重建**（不 `down -v`、不 `volume prune`）。

### 4.5 按客户品牌化（G5，值驱动）

经核查，品牌文本在 app UI 硬编码面极小（落地页品牌主要为 Logo 图非文字；`EAIFlow` 文本仅 `setup/page.tsx` 等零星处；其余在 `content/` 文档里，不按客户改）。机制：

- **显示名 / 页脚** → 构建期 `NEXT_PUBLIC_BRAND_NAME` / `NEXT_PUBLIC_BRAND_FOOTER` 环境变量。前端小重构：把硬编码品牌文本处改为读 `process.env.NEXT_PUBLIC_BRAND_* || <默认>`（复用 `version.ts` 的 `NEXT_PUBLIC_*` 模式）。涉及点：`src/app/(auth)/setup/page.tsx`、登录页、`layout.tsx` 的 `<title>`/metadata、导航/页脚组件（实现时枚举全部）。
- **Logo 图 / Favicon** → 每客户静态资源，构建时 COPY 进镜像 `public/`（`deploy.conf` 的 `BRAND_ASSETS_DIR` 指向的目录）。
- 导出时 `offline-export.sh` 把 `BRAND_*` 作为 build arg 注入前端构建。
- **彻底删除 `frontend-overrides/` 运行时 bind mount**（含 `App.tsx`/`DashboardPage.tsx`/CSS 整文件覆盖）——品牌不再靠整文件覆盖，源码漂移风险消除。
- 所有前端改动加 `// EAI-CUSTOM` 注释（遵循项目定制化规范）。

### 4.6 数据安全替换旧系统（G4，迁移/割接）

复用 `eai-prod` 项目名、网络 `eai-prod_eai-flow-net`、**完全相同的 volume 名** → 新容器重建后卷自动重连，数据无感。首次替换本质是一次"大升级"：

1. **备份（非可选）**：`pg_dump` 主库；逐 volume 打包（`docker run --rm -v <vol>:/d -v $PWD:/b alpine tar czf /b/<vol>.tgz /d`）；`tar data/ logs/ deploy.conf`。备份放部署目录之外。
2. **配置一次性迁移**：从旧 `.env`/`config.yaml` 抽取真实手填值（LLM 地址、`RAGFLOW_API_KEY`、DB 密码、服务器 IP）写入新 `deploy.conf`，`generate-config.sh` 生成新配置，`diff` 对比确认无丢失。
3. **导入新镜像（不删旧的）**：`docker load` 新 `:v1` 镜像，与老 `:latest` 并存（老的留作回滚）。
4. **切换（短暂停机）**：`docker compose -p eai-prod down`（**不带 `-v`**）→ `IMAGE_TAG=v1 up -d` → 卷重连、数据无感 → 跑迁移。
5. **验证 + 回滚通道**：冒烟测登录/知识库/合同价；挂了 `IMAGE_TAG` 回退老 `:latest`（仍在）`up -d` 秒回。
6. **稳定后清理（可选）**：`docker image prune`（只删悬空）或定向 `rmi`；**永不** `docker system prune -af`（F.9）、`docker volume prune` / `system prune --volumes`（删数据）。

**安全守卫**：`install.sh` / `upgrade.sh` / `deploy.sh` 全部**永不**包含 `down -v` 或 `volume prune`；脚本中加显式注释与（如可行）参数校验防手滑。

## 5. 涉及文件

**新增**
- `deploy.conf`（模板，部署目录根，唯一手写配置源）
- `scripts/generate-config.sh`（deploy.conf → config.yaml/.env/extensions_config.json）
- `upgrade.sh`（delta 增量升级 + 回滚，由 offline-export.sh 生成进包）
- `deploy/offline/brand-assets/`（每客户 logo/favicon 资源目录示例）

**修改**
- `scripts/offline-export.sh`：加 `--delta --since`、版本 tag、`--target prod` 前端构建、品牌 build arg 注入、RAGFlow `v0.25.3-fixed` + tiktoken 预置、生成 `manifest.json`、生成 `upgrade.sh`。
- `deploy/offline/docker-compose.yaml`：前端用 prod 镜像 + `${IMAGE_TAG:-latest}`；删 `frontend-overrides/` 挂载与 `frontend-start.sh` 挂载；各 image 引用版本化。
- `deploy/offline/docker-compose.ragflow.yaml`：默认 `RAGFLOW_IMAGE=infiniflow/ragflow:v0.25.3-fixed`。
- `deploy/offline/deploy.sh`：零编辑自动推导、合并 compose 调用、down -v/volume prune 守卫。
- `deploy/offline/.env` 模板 / `config.yaml`：由 generate-config.sh 产出（含 `EXTENSIONS_DB_*` 预填等修复默认值）。
- `deploy/offline/nginx/nginx.conf`：去掉 `/_next/webpack-hmr` return 204 hack。
- 前端（加 EAI-CUSTOM 注释）：品牌文本处改读 `NEXT_PUBLIC_BRAND_NAME`/`NEXT_PUBLIC_BRAND_FOOTER`。

**删除/弃用**
- `deploy/offline/frontend-start.sh`（被 prod 构建取代）。

## 6. 风险与对策

| 风险 | 对策 |
|------|------|
| 生产前端构建暴露隐藏的 dev-only 依赖（如运行时才报缺环境变量） | 构建用 `SKIP_ENV_VALIDATION=1`（已存在）；导出后在开发机用 prod 镜像冒烟测试一轮再交付 |
| RAGFlow `v0.25.3-fixed` 镜像需在有网机构建并验证 | 作为导出前置步骤；F.11 已有 Dockerfile 片段，固化进构建脚本 |
| 品牌 build arg 漏注入导致显示默认名 | `generate-config.sh` 校验 `BRAND_NAME` 非空；构建后 grep 镜像内产物确认 |
| 增量 delta 漏算镜像（manifest 漂移） | manifest 记录 digest；`--delta` 时与本地 `docker images` 双向校验，缺失则告警降级为全量 |
| 割接误用 `down -v` 删数据 | 脚本守卫 + 文档强调；割接步骤 1 强制备份 |
| postgres 迁移破坏数据 | 迁移前自动 `pg_dump`；迁移失败回滚 gateway 镜像（迁移幂等或加回滚 SQL 视迁移性质） |
| 品牌值驱动需改 deer-flow **上游前端**文件（setup/login/layout/页脚），与"不改 core 代码"偏好冲突 | 改动极小且隔离（仅把硬编码品牌文本改为读 `NEXT_PUBLIC_BRAND_*` 带默认值），全部加 `// EAI-CUSTOM` 注释——属定制化规范明确允许的带注释例外；Logo/Favicon 走 `public/` 资源可运行时挂载（prod 也支持），免改源码 |

## 7. 验收标准

- 全新离线部署：填 `deploy.conf`（4 个品牌值 + LLM）→ `./deploy.sh` 一条命令 → 11 容器全 healthy，登录/知识库/合同价可用，**无需手改任何配置文件**。
- 增量升级：开发机改代码 → `--delta` 导出 2 个镜像 → scp → `upgrade.sh` → 仅对应服务重建、数据无丢失、回滚验证通过。
- 品牌：换 `BRAND_NAME`/Logo/Favicon 重导后，落地页/登录/setup/页脚显示新品牌。
- 割接：旧系统数据（postgres + `./data` + RAGFlow 卷）替换后完整保留，可回滚至旧版。
- F.14–F.18、F.2、F.6、F.10、F.11–F.13、F.20 在新流程中不再出现。

## 8. 后续（非本期）
- 多服务器批量部署 / 一致性校验。
- 灾备：定时 `pg_dump` + volume 快照策略。
- 镜像仓库（Harbor 内网 registry）替代文件级 save/load（当服务器增多时）。
