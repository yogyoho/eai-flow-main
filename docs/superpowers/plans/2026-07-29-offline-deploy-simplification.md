# 离线部署简化与增量升级 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 EAI-Flow 内网离线部署从"多文件手改 + 全量重装"改造为"`deploy.conf` 驱动的零编辑部署 + ssh/scp 推送式增量升级 + 数据安全原地替换"，并附带按客户的值驱动品牌化。

**Architecture:** 在现有 `scripts/offline-export.sh` + `deploy/offline/*` 体系上增量改造。新增 `deploy.conf`（唯一手写配置源）+ `generate-config.sh`（conf→各配置）+ `upgrade.sh`（delta 升级）。前端从 `pnpm dev` 切到 `prod` 构建镜像；镜像打 `:v<ver>` tag + `${IMAGE_TAG:-latest}` 实现回滚；品牌走构建期 `NEXT_PUBLIC_BRAND_*` + `public/` 资源。

**Tech Stack:** Bash（部署脚本）、Docker/compose、Next.js 16（前端 prod 构建 + `NEXT_PUBLIC_*` 注入）、Python（无新增，仅镜像内迁移）、Rstest（前端单测）。

**Branch:** `main-dev-fork`（项目约定，所有提交到此；可用 worktree 隔离）。所有 deer-flow 上游文件改动加 `// EAI-CUSTOM` 注释。

**Spec:** `docs/superpowers/specs/2026-07-29-offline-deploy-simplification-design.md`

---

## ⚠️ 关键假设（执行前确认）

- **品牌化采用 Option A**：生产前端构建 + 少量带 `// EAI-CUSTOM` 注释的上游前端改动（`brand.ts` 读 `NEXT_PUBLIC_BRAND_*`）。若改选 Option B（保留 dev 模式 + 运行时整文件覆盖），则 Phase 1 的前端 prod 构建 + Phase 4 整体作废——二者绑定。
- 部署目标为单台内网 Linux 服务器，开发机↔服务器 ssh/scp 内网直连。
- 已部署旧系统（`eai-prod`）原地替换，复用同名 volume。

---

## File Structure

**新增**
| 文件 | 职责 |
|------|------|
| `deploy/offline/deploy.conf.example` | 唯一手写配置源模板（品牌值 + LLM + 可选项） |
| `scripts/generate-config.sh` | 读 `deploy.conf` → 生成 `config.yaml`/`.env`/`extensions_config.json` |
| `scripts/tests/test_generate_config.sh` | generate-config.sh 的 bash 自检 |
| `deploy/offline/brand-assets/README.md` | 每客户 logo/favicon 资源目录说明 + 示例 |
| `frontend/src/brand.ts` | 集中导出 `BRAND_NAME`/`BRAND_FOOTER`（镜像 `version.ts` 模式） |
| `frontend/tests/unit/brand.test.ts` | brand.ts 的 Rstest 单测 |

**修改**
| 文件 | 改动 |
|------|------|
| `scripts/offline-export.sh` | 加 `--delta --since`、版本 tag、`--target prod`、品牌 build arg、RAGFlow fixed 镜像、生成 `manifest.json` + `upgrade.sh` |
| `deploy/offline/docker-compose.yaml` | 前端用 prod 镜像 + `${IMAGE_TAG:-latest}`；删 `frontend-start.sh`/`frontend-overrides` 挂载；各 image 版本化 |
| `deploy/offline/docker-compose.ragflow.yaml` | 默认 `RAGFLOW_IMAGE=infiniflow/ragflow:v0.25.3-fixed` |
| `deploy/offline/docker-compose.extensions.yaml` | collab image 版本化 `${IMAGE_TAG:-latest}` |
| `deploy/offline/deploy.sh` | 零编辑自动推导、合并 compose 调用、`down -v`/`volume prune` 守卫 |
| `deploy/offline/.env` | 由 generate-config.sh 产出（保留为模板，脚本填充/覆盖） |
| `deploy/offline/nginx/nginx.conf` | 仅**校验**无 webpack-hmr 204 hack（已干净，line 33 的 `return 204` 是合法 CORS 预检，**勿删**） |
| `frontend/src/app/layout.tsx` | `title` 改读 `BRAND_NAME`（EAI-CUSTOM） |
| `frontend/src/app/(auth)/setup/page.tsx` | 两处 `<h1>EAIFlow</h1>` 改读 `BRAND_NAME`（EAI-CUSTOM） |
| `frontend/src/components/landing/footer.tsx` | © 行改读 `BRAND_FOOTER`（EAI-CUSTOM） |
| `docs/OFFLINE_DEPLOYMENT_GUIDE.md` | 更新为新流程 + 增量升级 + 割接章节 |

**删除**
| 文件 | 原因 |
|------|------|
| `deploy/offline/frontend-start.sh` | 被 prod 构建取代（prod 镜像默认 `pnpm start`） |

---

# Phase 1: 镜像层（生产前端构建 + RAGFlow 硬化 + 修复入默认值）

## Task 1.1: 前端切换为生产构建

**Files:**
- Modify: `deploy/offline/docker-compose.yaml`（frontend 服务，约 41-80 行）
- Modify: `scripts/offline-export.sh`（BUILD/导出逻辑）

- [ ] **Step 1: 改 offline compose 前端服务为 prod 镜像、移除 dev 启动与覆盖挂载**

把 `deploy/offline/docker-compose.yaml` 的 `frontend:` 服务改为（删除 `command:` 与 `frontend-start.sh`/`frontend-overrides`/favicon 运行时挂载；favicon 改由品牌资源构建期注入，见 Phase 4；image 加版本变量）：

```yaml
  frontend:
    image: deer-flow-frontend:${IMAGE_TAG:-latest}
    container_name: prod-eai-flow-frontend
    environment:
      - DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://gateway:8001
      - DEER_FLOW_TRUSTED_ORIGINS=${DEER_FLOW_TRUSTED_ORIGINS:-http://localhost:${PORT:-4026}}
      - NEXT_PUBLIC_BACKEND_BASE_URL=
      - NEXT_PUBLIC_LANGGRAPH_BASE_URL=
      - NEXT_PUBLIC_COLLAB_WS_URL=
      - NEXT_PUBLIC_KF_API_BASE_URL=
      - BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}
      - NODE_ENV=production
      - SKIP_ENV_VALIDATION=1
      - NEXT_PUBLIC_RAGFLOW_WEB_PORT=${RAGFLOW_WEB_PORT:-19381}
    networks:
      - prod-eai-flow-net
    restart: unless-stopped
```

要点：去掉 `command: ["sh","/usr/local/bin/frontend-start.sh"]`（prod 镜像 `Dockerfile:55` 默认 `CMD ["sh","-c","cd /app/frontend && pnpm start"]`）；去掉 `INTRANET_HOSTS`（prod 构建不水合校验来源）；保留 `SKIP_ENV_VALIDATION=1`。

- [ ] **Step 2: offline-export.sh 前端构建改用 prod target**

在 `scripts/offline-export.sh` 的"Step 2: Build project images"段，前端构建调用加 `--target prod`。定位现有构建 gateway/frontend 的逻辑（约 152-170 行的 `$COMPOSE_CMD build "$svc"` 循环），在循环前增加显式 prod 前端构建：

```bash
# Build frontend with prod target (pnpm build + pnpm start), NOT dev.
# Kills F.14–F.18 (HMR / allowedDevOrigins / Turbopack) — prod serves compiled .next.
info "  Building: frontend (prod target)"
if ! $COMPOSE_CMD build --progress=plain --build-arg APP_VERSION="${VERSION}" frontend; then
    err "  Build failed for: frontend (prod)"
    err "  Populate it via 'make docker-start' on this dev machine, then re-run."
    exit 1
fi
ok "  Built:    frontend (prod)"
```

（其余服务沿用现有 `build "$svc"` 循环，gateway/collab 等不变。）

- [ ] **Step 3: 删除 frontend-start.sh**

```bash
git rm deploy/offline/frontend-start.sh
```

- [ ] **Step 4: 本机验证 prod 前端镜像可起**

在有网开发机执行：
```bash
# 构建 prod 前端镜像
docker compose -p eai-docker -f docker/docker-compose-dev.yaml build --progress=plain frontend
# 注意：dev compose 的 frontend target 是 dev；为验证 prod target，直接用 Dockerfile：
docker build --target prod -t deer-flow-frontend:prod-test -f frontend/Dockerfile .
# 起一个临时容器确认 pnpm start 监听 3000
docker run --rm -d --name fe-prod-smoke -p 3099:3000 deer-flow-frontend:prod-test
sleep 8
curl -s -o /dev/null -w "%{http_code}" http://localhost:3099/   # 期望 200
docker stop fe-prod-smoke
```
Expected: HTTP 200（prod server 正常响应）。若报缺环境变量，确认 `SKIP_ENV_VALIDATION=1` 已在 Dockerfile/runtime（`Dockerfile:40` 已有 build 期 `SKIP_ENV_VALIDATION=1 pnpm build`）。

- [ ] **Step 5: Commit**
```bash
git add deploy/offline/docker-compose.yaml scripts/offline-export.sh
git commit -m "feat(deploy): switch offline frontend to prod build (kill F.14-F.18)"
git rm deploy/offline/frontend-start.sh  # 若上一步未提交删除
git commit -m "chore(deploy): remove frontend-start.sh (superseded by prod build)"
```

---

## Task 1.2: RAGFlow 硬化（v0.25.3-fixed + tiktoken 预置）

**Files:**
- Modify: `deploy/offline/docker-compose.ragflow.yaml:8`
- Modify: `scripts/offline-export.sh`（RAGFlow 镜像清单 + fixed 构建）
- Create: `deploy/offline/ragflow-fixed.Dockerfile`

- [ ] **Step 1: 新建 RAGFlow 修复镜像 Dockerfile**（固化 F.11 修复）

`deploy/offline/ragflow-fixed.Dockerfile`：
```dockerfile
# EAI-CUSTOM: RAGFlow v0.25.3 离线修复（F.11: pip/venv PATH；F.13: tiktoken 预置）
FROM infiniflow/ragflow:v0.25.3
# F.11: entrypoint 调 pip 但 venv 未入 PATH
ENV PATH=/ragflow/.venv/bin:${PATH}
RUN ln -sf pip3 /ragflow/.venv/bin/pip || true
# F.13: 预置 tiktoken 编码文件，避免内网首次初始化拉取 Azure
# （构建机有网时下载；离线服务器直接用）
RUN mkdir -p /ragflow/.venv/lib/python3.11/site-packages/tiktoken_ext && \
    /ragflow/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" 2>/dev/null || true
```

- [ ] **Step 2: compose 默认指向 fixed 镜像**

`deploy/offline/docker-compose.ragflow.yaml:8`：
```yaml
    image: ${RAGFLOW_IMAGE:-infiniflow/ragflow:v0.25.3-fixed}
```

- [ ] **Step 3: offline-export.sh 构建 fixed 镜像并加入导出清单**

在 `scripts/offline-export.sh` 的"Step 1/2"之间，加 fixed 镜像构建（仅 WITH_RAGFLOW=true 时）：
```bash
if [ "$WITH_RAGFLOW" = true ]; then
    info "  Building: ragflow v0.25.3-fixed (F.11/F.13 hardening)"
    docker build -t infiniflow/ragflow:v0.25.3-fixed \
        -f "${REPO_ROOT}/deploy/offline/ragflow-fixed.Dockerfile" "${REPO_ROOT}/deploy/offline" \
        || { err "ragflow-fixed build failed"; exit 1; }
    ok "  Built:    infiniflow/ragflow:v0.25.3-fixed"
fi
```
并把 `PUBLIC_IMAGES` 中的 `infiniflow/ragflow:v0.25.3` 改为 `infiniflow/ragflow:v0.25.3-fixed`（约 108 行）。

- [ ] **Step 4: 验证 fixed 镜像 pip 可用**
```bash
docker build -t infiniflow/ragflow:v0.25.3-fixed \
    -f deploy/offline/ragflow-fixed.Dockerfile deploy/offline
docker run --rm infiniflow/ragflow:v0.25.3-fixed sh -lc 'which pip && python -c "import tiktoken"'
```
Expected: pip 路径输出 + tiktoken 导入无报错。

- [ ] **Step 5: Commit**
```bash
git add deploy/offline/ragflow-fixed.Dockerfile deploy/offline/docker-compose.ragflow.yaml scripts/offline-export.sh
git commit -m "feat(deploy): harden RAGFlow offline (v0.25.3-fixed: pip PATH + tiktoken)"
```

---

## Task 1.3: 已知修复烘焙进默认值

**Files:**
- Modify: `deploy/offline/.env`（模板）
- Verify: `deploy/offline/nginx/nginx.conf`、`deploy/offline/postgres-init/10-temporal.sh`

- [ ] **Step 1: 校验 nginx 无 webpack-hmr 204 hack（F.14，应已干净）**
```bash
grep -n "webpack-hmr" deploy/offline/nginx/nginx.conf || echo "OK: no webpack-hmr hack"
grep -n "return 204" deploy/offline/nginx/nginx.conf   # 应仅命中 line 33 的 CORS OPTIONS 预检，勿删
```
Expected: `OK: no webpack-hmr hack` + line 33 `return 204`（CORS 预检，保留）。无需改动。

- [ ] **Step 2: 校验 Temporal 自动建用户脚本存在（F.3）**
```bash
cat deploy/offline/postgres-init/10-temporal.sh | head -n 20
```
确认脚本创建 `temporal` 用户/库（已存在则跳过创建）。若内容缺失，补全 one-shot SQL（`CREATE USER temporal ... ; CREATE DATABASE temporal ...`，加 `DO $$ ... IF NOT EXISTS` 守护）。已存在则本步为校验，不改动。

- [ ] **Step 3: .env 模板预填 EXTENSIONS_DB_* 与注释 NETWORK_NAME（F.2/F.6）**

在 `deploy/offline/.env` 中确保存在（若缺则追加；generate-config.sh 在 Phase 2 会基于此填充）：
```bash
# F.2: gateway 必须用 Docker 服务名连库，否则容器内 localhost 不通
EXTENSIONS_DB_HOST=postgres-ext
EXTENSIONS_DB_PORT=5432
EXTENSIONS_DB_USER=agentflow
EXTENSIONS_DB_PASSWORD=agentflow123
EXTENSIONS_DB_NAME=agentflow
# F.6: compose 已硬编码网络名，此变量仅供文档参考；切勿取消注释覆盖
# NETWORK_NAME=eai-flow-net
```

- [ ] **Step 4: Commit**
```bash
git add deploy/offline/.env
git commit -m "fix(deploy): bake F.2/F.6 fixes into .env defaults"
```

---

# Phase 2: 配置生成器 + 零编辑安装器

## Task 2.1: generate-config.sh（conf → 配置）

**Files:**
- Create: `scripts/generate-config.sh`
- Create: `scripts/tests/test_generate_config.sh`
- Test: `scripts/tests/test_generate_config.sh`

- [ ] **Step 1: 写失败测试**

`scripts/tests/test_generate_config.sh`：
```bash
#!/usr/bin/env bash
# Self-check for generate-config.sh (Ponytail: one small runnable check, no framework)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GEN="$HERE/../generate-config.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Minimal deploy.conf
cat > "$WORK/deploy.conf" <<'EOF'
BRAND_NAME=客户A
BRAND_FOOTER=© 2026 客户A
LLM_BASE_URL=http://10.0.0.5:8080/v1
LLM_API_KEY=sk-test
LLM_MODEL=qwen-plus
EOF

bash "$GEN" --conf "$WORK/deploy.conf" --out "$WORK" --root "/opt/eai" --secret "SECRETXYZ" --origin "http://10.0.0.5:4026"

# Assertions
grep -q "EXTENSIONS_DB_HOST=postgres-ext" "$WORK/.env"           || { echo "FAIL: EXTENSIONS_DB_HOST"; exit 1; }
grep -q "BETTER_AUTH_SECRET=SECRETXYZ" "$WORK/.env"              || { echo "FAIL: secret"; exit 1; }
grep -q "DEER_FLOW_TRUSTED_ORIGINS=http://10.0.0.5:4026" "$WORK/.env" || { echo "FAIL: origin"; exit 1; }
grep -q "base_url: http://10.0.0.5:8080/v1" "$WORK/config.yaml"  || { echo "FAIL: llm base_url"; exit 1; }
grep -q "model: qwen-plus" "$WORK/config.yaml"                   || { echo "FAIL: llm model"; exit 1; }
grep -q "mcpServers" "$WORK/extensions_config.json"              || { echo "FAIL: extensions_config"; exit 1; }
echo "PASS: generate-config.sh"
```

- [ ] **Step 2: 运行测试，确认失败**
```bash
chmod +x scripts/tests/test_generate_config.sh
bash scripts/tests/test_generate_config.sh
```
Expected: FAIL（`generate-config.sh: No such file or directory`）。

- [ ] **Step 3: 实现 generate-config.sh**

`scripts/generate-config.sh`：
```bash
#!/usr/bin/env bash
# generate-config.sh — read deploy.conf, emit config.yaml / .env / extensions_config.json
# Usage: generate-config.sh --conf <deploy.conf> --out <dir> --root <abs path> --secret <str> --origin <url>
set -euo pipefail

CONF=""; OUT="."; ROOT=""; SECRET=""; ORIGIN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --conf) CONF="$2"; shift 2;;
    --out)  OUT="$2";  shift 2;;
    --root) ROOT="$2"; shift 2;;
    --secret) SECRET="$2"; shift 2;;
    --origin) ORIGIN="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done
[ -n "$CONF" ] && [ -f "$CONF" ] || { echo "ERR: --conf <file> required" >&2; exit 1; }
mkdir -p "$OUT"

# Source conf as simple KEY=VALUE (trusted, operator-authored)
# shellcheck disable=SC1090
set -a; . "$CONF"; set +a

BRAND_NAME="${BRAND_NAME:-EAIFlow}"
BRAND_FOOTER="${BRAND_FOOTER:-}"
LLM_BASE_URL="${LLM_BASE_URL:-}"
LLM_API_KEY="${LLM_API_KEY:-}"
LLM_MODEL="${LLM_MODEL:-}"
RAGFLOW_API_KEY="${RAGFLOW_API_KEY:-}"
RAGFLOW_HTTP_PROXY="${RAGFLOW_HTTP_PROXY:-}"
DB_PASSWORD="${DB_PASSWORD:-agentflow123}"

# ── .env ──
cat > "$OUT/.env" <<EOF
# Generated by generate-config.sh — do not hand-edit; edit deploy.conf + regenerate
DEER_FLOW_ROOT=${ROOT}
BETTER_AUTH_SECRET=${SECRET}
HOME=/root
PORT=4026
EXTENSIONS_DB_HOST=postgres-ext
EXTENSIONS_DB_PORT=5432
EXTENSIONS_DB_USER=agentflow
EXTENSIONS_DB_PASSWORD=${DB_PASSWORD}
EXTENSIONS_DB_NAME=agentflow
POSTGRES_EXT_PASSWORD=${DB_PASSWORD}
DEER_FLOW_TRUSTED_ORIGINS=${ORIGIN}
RAGFLOW_API_KEY=${RAGFLOW_API_KEY}
RAGFLOW_HTTP_PROXY=${RAGFLOW_HTTP_PROXY}
EOF
# Merge cloud API keys if present in conf (AGNES_API_KEY etc.) — append verbatim
for k in AGNES_API_KEY ZHIPU_API_KEY DEEPSEEK_API_KEY SILICONFLOW_API_KEY INTERNAL_LLM_API_KEY; do
  v=$(eval "echo \${${k}:-}"); [ -n "$v" ] && echo "${k}=${v}" >> "$OUT/.env"
done

# ── config.yaml ──
if [ -n "$LLM_BASE_URL" ]; then
cat > "$OUT/config.yaml" <<EOF
models:
  - name: intranet-llm
    display_name: 内网大模型
    use: langchain_openai:ChatOpenAI
    model: ${LLM_MODEL}
    api_key: ${LLM_API_KEY}
    base_url: ${LLM_BASE_URL}
    request_timeout: 600.0
    max_retries: 2
    max_tokens: 8192
    temperature: 0.7
    supports_vision: false
    supports_thinking: false
EOF
else
  # No intranet LLM configured — keep cloud defaults (intranet-with-egress case)
  cp "${OUT}/config.yaml.cloud-default" "$OUT/config.yaml" 2>/dev/null || \
    echo "# LLM_BASE_URL not set; configure models manually or allow cloud egress" > "$OUT/config.yaml"
fi

# ── extensions_config.json ──
cat > "$OUT/extensions_config.json" <<'EOF'
{"mcpServers": {}, "skills": {}}
EOF

echo "Generated: $OUT/{.env,config.yaml,extensions_config.json} (brand=${BRAND_NAME})"
```

- [ ] **Step 4: 运行测试，确认通过**
```bash
bash scripts/tests/test_generate_config.sh
```
Expected: `PASS: generate-config.sh`

- [ ] **Step 5: Commit**
```bash
chmod +x scripts/generate-config.sh
git add scripts/generate-config.sh scripts/tests/test_generate_config.sh
git commit -m "feat(deploy): add generate-config.sh (deploy.conf -> configs) + self-test"
```

---

## Task 2.2: deploy.conf 模板 + 安装期自动推导

**Files:**
- Create: `deploy/offline/deploy.conf.example`
- Modify: `deploy/offline/deploy.sh`

- [ ] **Step 1: 写 deploy.conf 模板**

`deploy/offline/deploy.conf.example`（内容见 spec §4.1，此处为可执行模板）：
```ini
# ===== EAI-Flow 部署配置（唯一手写文件）=====
# 拷贝为 deploy.conf 后填值；其余配置由 generate-config.sh 自动推导

# ── 品牌（按客户变）──
BRAND_NAME=EAIFlow
BRAND_FOOTER=
BRAND_ASSETS_DIR=./brand-assets

# ── LLM（内网可连外网则留空，走云端默认）──
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

# ── 可选 ──
RAGFLOW_API_KEY=
RAGFLOW_HTTP_PROXY=
DB_PASSWORD=
```

- [ ] **Step 2: deploy.sh 零编辑改造（自动推导 + 守卫）**

在 `deploy/offline/deploy.sh` 的 `preflight()` 后、`start_all()` 前新增 `setup_config()`，并在 `deploy` 分支调用。关键改动：

```bash
setup_config() {
  log_info "=== 生成配置（零编辑）==="
  # 首次部署：若无 deploy.conf，从 example 拷贝并提示填 LLM
  if [[ ! -f deploy.conf ]]; then
    cp deploy.conf.example deploy.conf
    log_warn "已从模板创建 deploy.conf；完全离线时请填 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 后重跑"
    exit 0
  fi

  # 自动推导不可猜的值
  local root; root="$(pwd)"
  local secret; secret="$(grep '^BETTER_AUTH_SECRET=' .env 2>/dev/null | cut -d= -f2 || true)"
  if [[ -z "$secret" || "$secret" == "change-me-to-a-random-string" ]]; then
    secret="$(openssl rand -base64 32)"
  fi
  local ip; ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -z "$ip" ]] && ip="localhost"
  local origin="http://${ip}:${PORT:-4026}"

  bash "${SCRIPT_DIR}/../scripts/generate-config.sh" \
      --conf deploy.conf --out . --root "$root" --secret "$secret" --origin "$origin" \
      || { log_error "generate-config.sh 失败"; exit 1; }

  # nginx.conf 文件预置（防 F.10 目录陷阱）
  [[ -f nginx/nginx.conf ]] || { mkdir -p nginx && cp docker/nginx/nginx.conf nginx/nginx.conf 2>/dev/null || true; }

  mkdir -p data logs skills mcp-server
  log_info "配置就绪"
}

# down -v / volume prune 守卫（加到文件末尾用法提示前）
guard_destructive() {
  # 拒绝任何 down -v / volume prune 调用——会删数据
  for a in "$@"; do
    case "$a" in
      *-v|--volumes) log_error "禁止 down -v（会销毁数据卷）；如需重置请手动备份后操作"; exit 1;;
    esac
  done
}
```
并在 `case` 的 `deploy|start|up)` 分支改为：`preflight; setup_config; ensure_network; start_all`。
`down|stop)` 分支调用前加 `guard_destructive "$@"`。

- [ ] **Step 3: 验证 deploy.conf 缺失时引导**
```bash
cd deploy/offline
# 模拟首次（临时移走 deploy.conf）
[[ -f deploy.conf ]] && mv deploy.conf deploy.conf.bak
bash deploy.sh deploy 2>&1 | grep -q "已从模板创建 deploy.conf" && echo "OK: guided first-run" || echo "FAIL"
[[ -f deploy.conf.bak ]] && mv deploy.conf.bak deploy.conf || rm -f deploy.conf
```
Expected: `OK: guided first-run`

- [ ] **Step 4: Commit**
```bash
git add deploy/offline/deploy.conf.example deploy/offline/deploy.sh
git commit -m "feat(deploy): zero-edit deploy.conf-driven installer + destructive guards"
```

---

# Phase 3: 版本化 + 增量升级

## Task 3.1: 版本 tag + ${IMAGE_TAG:-latest} + manifest.json

**Files:**
- Modify: `deploy/offline/docker-compose.yaml`、`docker-compose.extensions.yaml`（image 版本化）
- Modify: `scripts/offline-export.sh`（写 manifest.json）

- [ ] **Step 1: compose image 引用版本化**

`deploy/offline/docker-compose.yaml`：
- nginx: `image: nginx:alpine`（公共镜像，不变）
- frontend: `image: deer-flow-frontend:${IMAGE_TAG:-latest}`（Task 1.1 已改）
- gateway: `image: deer-flow-gateway:${IMAGE_TAG:-latest}`

`deploy/offline/docker-compose.extensions.yaml`：
- collab: `image: eai-flow-collab:${IMAGE_TAG:-latest}`
- postgres-ext: `image: postgres:16-alpine`（公共，不变）

- [ ] **Step 2: offline-export.sh 导出后写 manifest.json**

在 `scripts/offline-export.sh` 的"Step 5 生成脚本"之后、打包之前，加 manifest 生成：
```bash
# manifest.json: 版本 + 各镜像 digest（供 --delta 比对与回滚记录）
MANIFEST="${OUTPUT_DIR}/manifest.json"
VERSION_TAG="v${DATE}-$(git rev-parse --short HEAD)"
{
  echo "{"
  echo "  \"version\": \"${VERSION_TAG}\","
  echo "  \"exported_at\": \"${DATE}\","
  echo "  \"images\": {"
  first=1
  for img in "${BUILT_IMAGE_NAMES[@]}" "${PUBLIC_IMAGES[@]}"; do
    dgst=$(docker image inspect "$img" --format '{{.Id}}' 2>/dev/null || echo "unknown")
    [[ $first -eq 1 ]] || echo ","
    printf '    "%s": {"digest": "%s"}' "$img" "$dgst"
    first=0
  done
  echo ""
  echo "  },"
  echo "  \"config_hash\": \"$(sha256sum deploy/offline/deploy.conf.example 2>/dev/null | cut -d' ' -f1 || echo unknown)\""
  echo "}"
} > "$MANIFEST"
ok "  Generated: manifest.json (version=${VERSION_TAG})"
```
并在最终包说明里输出 `VERSION_TAG`（供 `--since` 引用）。

- [ ] **Step 3: 验证 manifest 生成**
```bash
bash scripts/offline-export.sh --no-ragflow 2>&1 | tail -n 5
ls eai-flow-offline-*/manifest.json && head eai-flow-offline-*/manifest.json
```
Expected: manifest.json 存在，含 version + images digest。

- [ ] **Step 4: Commit**
```bash
git add deploy/offline/docker-compose.yaml deploy/offline/docker-compose.extensions.yaml scripts/offline-export.sh
git commit -m "feat(deploy): version-tagged images + manifest.json (rollback via IMAGE_TAG)"
```

---

## Task 3.2: offline-export.sh --delta 增量导出

**Files:**
- Modify: `scripts/offline-export.sh`（加 `--delta --since` 分支）
- Create: `scripts/tests/test_delta_export.sh`

- [ ] **Step 1: 写 delta 逻辑**

在 `scripts/offline-export.sh` 参数解析段加：
```bash
DELTA=false; SINCE=""
for arg in "$@"; do
  case "$arg" in
    --delta) DELTA=true ;;
    --since) shift; SINCE="$2" ;;
    ...（既有 --with-ragflow 等）...
  esac
done
```
在 Step 3（导出镜像）段，按 `$DELTA` 分支：
```bash
if [ "$DELTA" = true ]; then
  # 读上次 manifest，仅导 digest 变化的镜像
  PREV_MANIFEST="${REPO_ROOT}/.offline-export-history/${SINCE}/manifest.json"
  [ -f "$PREV_MANIFEST" ] || { err "找不到上次 manifest: $PREV_MANIFEST"; err "  先跑一次全量导出建立基线"; exit 1; }
  info "Delta 模式：对比 ${SINCE} 基线，仅导变化镜像"
  ALL_IMAGES=("${BUILT_IMAGE_NAMES[@]}" "${PUBLIC_IMAGES[@]}")
  CHANGED=()
  for img in "${ALL_IMAGES[@]}"; do
    cur=$(docker image inspect "$img" --format '{{.Id}}' 2>/dev/null || echo "")
    prev=$(python3 -c "import json,sys;d=json.load(open('$PREV_MANIFEST'));print(d['images'].get('$img',{}).get('digest',''))" 2>/dev/null || echo "")
    if [[ "$cur" != "$prev" ]]; then
      CHANGED+=("$img")
      info "  变化: $img"
    fi
  done
  [ ${#CHANGED[@]} -gt 0 ] || { warn "无镜像变化，仅可能 config 变更"; }
  DELTA_IMAGES=("${CHANGED[@]}")
fi
```
导出循环改为：`for img in ${DELTA_IMAGES:-${BUILT_IMAGE_NAMES[@]}} ...`（delta 时仅 CHANGED，全量时全部）。

导出后把当前 manifest 存入历史：`mkdir -p .offline-export-history/${VERSION_TAG} && cp $MANIFEST .offline-export-history/${VERSION_TAG}/`。

- [ ] **Step 2: 写 delta 自检**

`scripts/tests/test_delta_export.sh`：构造两个不同 digest 的假 manifest，断言 `--delta` 仅列出变化项（用 `--dry-run` 或直接调 python 比对逻辑）。最小可执行：
```bash
#!/usr/bin/env bash
set -euo pipefail
# 用 python 直接复现比对逻辑，验证 "digest 不同才入选"
python3 - <<'PY'
import json
prev={"images":{"a":{"digest":"x"},"b":{"digest":"y"}}}
cur={"a":"x","b":"Z"}  # b 变了
changed=[k for k in cur if cur[k]!=prev["images"].get(k,{}).get("digest","")]
assert changed==["b"], changed
print("PASS: delta diff logic")
PY
```

- [ ] **Step 3: 运行测试**
```bash
bash scripts/tests/test_delta_export.sh
```
Expected: `PASS: delta diff logic`

- [ ] **Step 4: Commit**
```bash
git add scripts/offline-export.sh scripts/tests/test_delta_export.sh
git commit -m "feat(deploy): offline-export --delta (ship only changed images)"
```

---

## Task 3.3: upgrade.sh（服务器端 delta 升级 + 回滚）

**Files:**
- Create: `deploy/offline/upgrade.sh`（由 offline-export.sh 拷入包）

- [ ] **Step 1: 写 upgrade.sh**

`deploy/offline/upgrade.sh`：
```bash
#!/usr/bin/env bash
# upgrade.sh — 服务器端增量升级：load delta → 按需重生成配置 → 仅重建变化服务 → 迁移 → 回滚
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$SCRIPT_DIR"
P=eai-prod
COMPOSE=(-f docker-compose.yaml -f docker-compose.extensions.yaml -f docker-compose.temporal.yaml -f docker-compose.ragflow.yaml -f docker-compose.mcp-cad.yaml)
DELTA_DIR="${1:-delta}"
CUR_TAG="$(grep -o '"version": *"[^"]*"' manifest.json 2>/dev/null | head -1 | sed 's/.*"\([^"]*\)"$/\1/' || echo latest)"
PREV_TAG="${IMAGE_TAG:-latest}"

log(){ echo -e "\033[0;32m[UP]\033[0m $*"; }
err(){ echo -e "\033[0;31m[UP-ERR]\033[0m $*" >&2; }

# 1. load delta 镜像
if [ -d "$DELTA_DIR/images" ]; then
  for t in "$DELTA_DIR/images"/*.tar; do [ -f "$t" ] && { log "load $(basename "$t")"; docker load -i "$t"; }; done
fi

# 2. 配置变化才重生成（config_hash 不同）
if [ -f "$DELTA_DIR/manifest.json" ] && ! diff -q <(python3 -c "import json;print(json.load(open('$DELTA_DIR/manifest.json'))['config_hash'])") \
     <(python3 -c "import json;print(json.load(open('manifest.json'))['config_hash'])") >/dev/null 2>&1; then
  log "config 变化，重新生成"
  bash ../scripts/generate-config.sh --conf deploy.conf --out . --root "$SCRIPT_DIR" \
       --secret "$(grep '^BETTER_AUTH_SECRET=' .env|cut -d= -f2)" \
       --origin "http://$(hostname -I|awk '{print $1}'):${PORT:-4026}"
fi

# 3. 仅重建（变化镜像已 load；compose up 自动重建引用新镜像的容器，未变服务不动）
log "应用新版本 ${CUR_TAG}"
export IMAGE_TAG="$CUR_TAG"
docker compose -p "$P" "${COMPOSE[@]}" up -d

# 4. gateway 变化则迁移（先 pg_dump）
if docker compose -p "$P" "${COMPOSE[@]}" ps gateway | grep -q gateway; then
  log "备份数据库"
  docker exec prod-eai-flow-postgres-ext pg_dump -U agentflow agentflow > "backup-pre-${CUR_TAG}.sql" || true
  log "等待 gateway 健康"
  for i in $(seq 1 40); do curl -sf "http://localhost:${PORT:-4026}/api/license/status" >/dev/null && break; sleep 3; done
  log "执行迁移"
  docker exec prod-eai-flow-gateway python -m app.extensions.workflow.migration 2>/dev/null || log "迁移跳过（可能不需要）"
fi

# 5. 健康检查 + 失败回滚
if ! curl -sf "http://localhost:${PORT:-4026}/api/license/status" >/dev/null; then
  err "健康检查失败，回滚到 ${PREV_TAG}"
  export IMAGE_TAG="$PREV_TAG"
  docker compose -p "$P" "${COMPOSE[@]}" up -d
  exit 1
fi
# 成功：固化新 tag
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${CUR_TAG}/" .env 2>/dev/null || true
log "升级完成：${PREV_TAG} -> ${CUR_TAG}（旧镜像保留可回滚：IMAGE_TAG=${PREV_TAG}）"
```

- [ ] **Step 2: 让 offline-export.sh 把 upgrade.sh 拷进包**

在 `scripts/offline-export.sh` Step 4（拷配置）加：
```bash
cp "deploy/offline/upgrade.sh" "${OUTPUT_DIR}/upgrade.sh"
chmod +x "${OUTPUT_DIR}/upgrade.sh"
```

- [ ] **Step 3: 语法检查**
```bash
bash -n deploy/offline/upgrade.sh && echo "OK: syntax"
```
Expected: `OK: syntax`

- [ ] **Step 4: Commit**
```bash
git add deploy/offline/upgrade.sh scripts/offline-export.sh
git commit -m "feat(deploy): upgrade.sh (delta load + selective recreate + pg_dump + rollback)"
```

---

# Phase 4: 按客户品牌化（Option A）

## Task 4.1: brand.ts + 单测

**Files:**
- Create: `frontend/src/brand.ts`
- Create: `frontend/tests/unit/brand.test.ts`

- [ ] **Step 1: 写失败测试**

`frontend/tests/unit/brand.test.ts`（镜像 `version.ts` 的 `NEXT_PUBLIC_*` 模式）：
```typescript
import { describe, it, expect } from "rstest";
import { BRAND_NAME, BRAND_FOOTER } from "@/brand";

describe("brand", () => {
  it("BRAND_NAME defaults to EAIFlow when env unset", () => {
    // NEXT_PUBLIC_BRAND_NAME 未注入时回落默认（测试环境无注入）
    expect(typeof BRAND_NAME).toBe("string");
    expect(BRAND_NAME.length).toBeGreaterThan(0);
  });
  it("BRAND_FOOTER is a string (empty allowed)", () => {
    expect(typeof BRAND_FOOTER).toBe("string");
  });
});
```

- [ ] **Step 2: 运行测试确认失败**
```bash
cd frontend && pnpm test -- brand.test.ts
```
Expected: FAIL（`@/brand` 无法解析）。

- [ ] **Step 3: 实现 brand.ts**

`frontend/src/brand.ts`（EAI-CUSTOM）：
```typescript
// EAI-CUSTOM: 按客户品牌化（构建期注入）。镜像 version.ts 的 NEXT_PUBLIC_* 模式。
// 导出常量供 layout/setup/footer 等处统一引用，避免散落硬编码。
export const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME || "EAIFlow";
export const BRAND_FOOTER = process.env.NEXT_PUBLIC_BRAND_FOOTER || "";
```

- [ ] **Step 4: 运行测试确认通过**
```bash
cd frontend && pnpm test -- brand.test.ts
```
Expected: PASS。

- [ ] **Step 5: Commit**
```bash
git add frontend/src/brand.ts frontend/tests/unit/brand.test.ts
git commit -m "feat(brand): add brand.ts (NEXT_PUBLIC_BRAND_* with defaults) + test"
```

---

## Task 4.2: 接线 brand.ts 到 layout / setup / footer

**Files:**
- Modify: `frontend/src/app/layout.tsx:16-19`
- Modify: `frontend/src/app/(auth)/setup/page.tsx:176,247`
- Modify: `frontend/src/components/landing/footer.tsx:24-27`

- [ ] **Step 1: layout.tsx 标题改读 BRAND_NAME**

`frontend/src/app/layout.tsx`：
```typescript
// EAI-CUSTOM: 标题按客户品牌
import { BRAND_NAME } from "@/brand";
export const metadata: Metadata = {
  title: BRAND_NAME,
  description: "A LangChain-based framework for building super agents.",
};
```
（保留原 description，或后续按需参数化。）

- [ ] **Step 2: setup/page.tsx 两处 h1 改读 BRAND_NAME**

`frontend/src/app/(auth)/setup/page.tsx` 顶部加 import，两处 `<h1 className="font-serif text-3xl">EAIFlow</h1>` 改为：
```tsx
<h1 className="font-serif text-3xl">{BRAND_NAME}</h1>
```
（加 `// EAI-CUSTOM` 注释 + `import { BRAND_NAME } from "@/brand";`）

- [ ] **Step 3: footer.tsx © 行改读 BRAND_FOOTER**

`frontend/src/components/landing/footer.tsx`：
```tsx
// EAI-CUSTOM: 页脚按客户品牌
import { BRAND_FOOTER } from "@/brand";
// ... 在底部 <div>（line 24-27）改为：
<div className="text-muted-foreground container mb-8 flex flex-col items-center justify-center text-xs">
  {BRAND_FOOTER ? (
    <p>{BRAND_FOOTER}</p>
  ) : (
    <>
      <p>Licensed under MIT License</p>
      <p>&copy; {year} </p>
    </>
  )}
</div>
```

- [ ] **Step 4: typecheck + 单测**
```bash
cd frontend && pnpm typecheck && pnpm test -- brand
```
Expected: 无类型错误 + brand 测试 PASS。

- [ ] **Step 5: Commit**
```bash
git add frontend/src/app/layout.tsx frontend/src/app/\(auth\)/setup/page.tsx frontend/src/components/landing/footer.tsx
git commit -m "feat(brand): wire BRAND_NAME/BRAND_FOOTER into layout/setup/footer (EAI-CUSTOM)"
```

---

## Task 4.3: Logo/Favicon 资源机制 + build arg 注入

**Files:**
- Create: `deploy/offline/brand-assets/README.md`
- Modify: `scripts/offline-export.sh`

- [ ] **Step 1: 资源目录说明**

`deploy/offline/brand-assets/README.md`：
```markdown
# 每客户品牌资源

把该客户的 `favicon.ico`、`favicon.svg`、`logo.svg` 放到此目录。
`deploy.conf` 的 `BRAND_ASSETS_DIR` 指向它（默认 ./brand-assets）。
导出时这些文件 COPY 进前端镜像 public/（构建期烘焙，prod 构建必需）。
未提供则用源码默认 favicon/logo。
```

- [ ] **Step 2: offline-export.sh 注入品牌 build arg + 资源**

在前端 prod 构建调用（Task 1.1 Step 2）前，读 deploy.conf 的 BRAND_* 并传 build-arg；若有 brand-assets，临时拷进 frontend/public/ 再构建：
```bash
# EAI-CUSTOM: 按客户品牌（deploy.conf -> build-arg + public assets）
BRAND_NAME_DEF="EAIFlow"; BRAND_FOOTER_DEF=""
[ -f "${REPO_ROOT}/deploy.conf" ] && { . "${REPO_ROOT}/deploy.conf"; BRAND_NAME_DEF="${BRAND_NAME:-EAIFlow}"; BRAND_FOOTER_DEF="${BRAND_FOOTER:-}"; }
ASSETS="${REPO_ROOT}/${BRAND_ASSETS_DIR:-./brand-assets}"
if [ -d "$ASSETS" ]; then
  for f in favicon.ico favicon.svg logo.svg; do
    [ -f "$ASSETS/$f" ] && cp "$ASSETS/$f" "${REPO_ROOT}/frontend/public/$f"
  done
fi
# 构建时注入（注意：构建后恢复默认 public，避免污染源码——见 Step 3）
docker build --target prod \
  --build-arg APP_VERSION="${VERSION}" \
  -t deer-flow-frontend:latest \
  -f frontend/Dockerfile .
# NEXT_PUBLIC_* 需在构建环境注入；compose 无法影响 build 期，故用 -e 或 .env.build
```
> 注：`NEXT_PUBLIC_*` 是**构建期**变量。offline-export.sh 在前端构建时需把它们作为 build 环境变量传入。由于 `frontend/Dockerfile` 用 `ARG`/`ENV` 模式未声明 BRAND arg，需在 Dockerfile builder stage 加 `ARG NEXT_PUBLIC_BRAND_NAME` + `ENV NEXT_PUBLIC_BRAND_NAME=$NEXT_PUBLIC_BRAND_NAME`（构建前 `export NEXT_PUBLIC_BRAND_NAME=...`），或直接 `docker build --build-arg`（Next.js 对 `NEXT_PUBLIC_*` build-arg 的支持需 `ENV` 中转）。**实现时确认 Next.js 16 的 build-arg→ENV 路径**，必要时在 Dockerfile builder 段补两行 `ARG/ENV`。

- [ ] **Step 3: 构建后恢复默认 public（防源码污染）**
```bash
git checkout -- frontend/public/favicon.ico frontend/public/favicon.svg frontend/public/logo.svg 2>/dev/null || true
```

- [ ] **Step 4: 验证品牌注入**
```bash
export NEXT_PUBLIC_BRAND_NAME="测试客户"
export NEXT_PUBLIC_BRAND_FOOTER="© 测试"
docker build --target prod -t fe-brand-test -f frontend/Dockerfile .
docker run --rm fe-brand-test sh -c "grep -o '测试客户' /app/frontend/.next/server/app/*.html 2>/dev/null | head -1 || echo '(brand baked into JS bundle, verify via runtime)'"
git checkout -- frontend/public/ 2>/dev/null || true
```
Expected: 能在构建产物中找到品牌字符串，或运行时确认标题为"测试客户"。

- [ ] **Step 5: Commit**
```bash
git add deploy/offline/brand-assets/README.md scripts/offline-export.sh
git commit -m "feat(brand): per-customer logo/favicon + NEXT_PUBLIC_BRAND_* build injection"
```

---

# Phase 5: 数据安全割接 + 文档

## Task 5.1: 割接流程脚本/文档

**Files:**
- Create: `deploy/offline/cutover.md`（操作手册）

- [ ] **Step 1: 写割接手册**

`deploy/offline/cutover.md`：把 spec §4.6 的 6 步（备份 → 配置迁移 → 导入新镜像 → down 不带 -v → up → 验证回滚 → 清理）写成可照抄命令清单，强调：
- 备份命令（pg_dump + volume tar + data tar）；
- `docker compose -p eai-prod down`（**不带 -v**）；
- 回滚：`IMAGE_TAG=<旧> docker compose -p eai-prod ... up -d`；
- 禁用 `docker system prune -af` / `docker volume prune` / `system prune --volumes`。

- [ ] **Step 2: Commit**
```bash
git add deploy/offline/cutover.md
git commit -m "docs(deploy): data-safe cutover procedure (replace existing eai-prod in place)"
```

---

## Task 5.2: 更新部署指南

**Files:**
- Modify: `docs/OFFLINE_DEPLOYMENT_GUIDE.md`

- [ ] **Step 1: 更新指南为新流程**

在 `docs/OFFLINE_DEPLOYMENT_GUIDE.md` 中：
- "第二步：部署"改为 `deploy.conf` 驱动（填 4 品牌 + LLM → `./deploy.sh`）；
- "D. 版本与升级"改为 delta 流程（`offline-export.sh --delta --since` → scp → `./upgrade.sh`）；
- 新增"替换已部署系统"章节指向 `cutover.md`；
- 附录 F 标注哪些已通过本期改造根治（F.2/F.6/F.8/F.10/F.11–F.14/F.18/F.20）。

- [ ] **Step 2: Commit**
```bash
git add docs/OFFLINE_DEPLOYMENT_GUIDE.md
git commit -m "docs(deploy): rewrite guide for deploy.conf + delta upgrade + cutover"
```

---

# 自审 (Self-Review)

**Spec 覆盖：**
- G1 零编辑 → Task 2.1/2.2 ✓
- G2 生产前端构建 → Task 1.1 ✓
- G3 增量升级 → Task 3.1/3.2/3.3 ✓
- G4 数据安全替换 → Task 5.1 ✓
- G5 按客户品牌 → Task 4.1/4.2/4.3 ✓
- G6 修复入默认值 → Task 1.2/1.3 ✓

**已知实现风险点（执行时注意）：**
1. **Next.js `NEXT_PUBLIC_*` build-arg 注入路径**（Task 4.3 Step 2）：Next 16 对 `--build-arg NEXT_PUBLIC_*` 需 Dockerfile `ARG`+`ENV` 中转才在构建期生效，执行时务必验证产物含品牌串。
2. **`generate-config.sh` 的 conf source**（Task 2.1）：`set -a; . "$CONF"` 要求 deploy.conf 为合法 `KEY=VALUE`；已限定为运维手写可信文件。
3. **manifest digest**（Task 3.1/3.2）：用 `docker image inspect --format '{{.Id}}'`；本地构建镜像无 RepoDigest，`.Id` 可靠。
4. **Phase 4 假设 Option A**：若改 Option B，Phase 1 前端 prod 构建 + Phase 4 全部作废。

**类型一致性：** `BRAND_NAME`/`BRAND_FOOTER` 在 brand.ts 定义，layout/setup/footer 引用一致；`IMAGE_TAG`/`manifest.json` 字段在 compose/export/upgrade 三处一致。

---

# 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-07-29-offline-deploy-simplification.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派一个 fresh subagent，任务间 review，迭代快。
**2. Inline Execution** — 本会话内用 executing-plans 批量执行，带检查点。

选哪种？
