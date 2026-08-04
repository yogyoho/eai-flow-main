#!/usr/bin/env bash
#
# offline-export.sh - Export DeerFlow as a self-contained offline deployment package
#
# Usage: ./scripts/offline-export.sh [--with-ragflow] [--with-business]
#
# Run this script on a machine WITH internet access. It will:
#   1. Build all project Docker images
#   2. Pull all public (third-party) images
#   3. Export everything as .tar files
#   4. Generate install.sh and load-images.sh for the target machine
#   5. Package into a single .tar.gz archive
#
# Must be run from the repo root directory.

set -e

# ── Parse args ─────────────────────────────────────────────────────────────────

WITH_RAGFLOW=true
WITH_BUSINESS=false
DELTA=false
SINCE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --with-ragflow)   WITH_RAGFLOW=true;  shift;;
        --no-ragflow)     WITH_RAGFLOW=false; shift;;
        --with-business)  WITH_BUSINESS=true; shift;;
        --delta)          DELTA=true;         shift;;
        --since)          SINCE="${2:-}";     shift 2;;
        --help|-h)
            echo "Usage: $0 [--with-ragflow] [--no-ragflow] [--with-business] [--delta --since <version>]"
            echo ""
            echo "Options:"
            echo "  --with-ragflow    Include RAGFlow knowledge base images (default)"
            echo "  --no-ragflow      Exclude RAGFlow images"
            echo "  --with-business   Include business microservice images"
            echo "  --delta           增量模式：只导出变化的镜像（需配合 --since）"
            echo "  --since <version> 增量基线版本（.offline-export-history/<version>/manifest.json）"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--with-ragflow] [--no-ragflow] [--with-business] [--delta --since <version>]" >&2
            exit 1
            ;;
    esac
done

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DATE=$(date +%Y%m%d)
VERSION=$(git describe --tags --always 2>/dev/null || echo "dev")
PACKAGE_NAME="eai-flow-offline-${VERSION}-${DATE}"
OUTPUT_DIR="${REPO_ROOT}/${PACKAGE_NAME}"
IMAGES_DIR="${OUTPUT_DIR}/images"

# ── Colors ─────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Preflight ──────────────────────────────────────────────────────────────────

info "DeerFlow Offline Export Tool"
info "Version: ${VERSION}  Date: ${DATE}"
echo ""

if ! command -v docker &>/dev/null; then
    err "Docker is not installed. Aborting."
    exit 1
fi

if ! docker compose version &>/dev/null; then
    err "docker compose v2 is not available. Aborting."
    exit 1
fi

# EAI-CUSTOM: 检测可用的 Python 3（manifest.json 生成用）。
# Windows 上 `python3` 常是 Microsoft Store 占位符（不可用），故检测失败时回退 `python`。
PYTHON=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; assert sys.version_info >= (3,)' 2>/dev/null; then
        PYTHON="$c"; break
    fi
done
if [ -z "$PYTHON" ]; then
    err "Python 3 未找到（生成 manifest.json 需要）。请安装 python3。"
    exit 1
fi
ok "Python: ${PYTHON} ($("${PYTHON}" --version 2>&1))"

# ── Image inventories ──────────────────────────────────────────────────────────

# Public images (pulled from registries)
PUBLIC_IMAGES=(
    "nginx:alpine"
    "postgres:16-alpine"
    "temporalio/auto-setup:1.27.0"
)

# Services to build via dev compose (compose service names).
# EAI-CUSTOM: `frontend` is intentionally excluded here — the dev compose pins
# build target=dev, which would produce a dev image. The frontend prod image is
# built directly with `--target prod` in Step 2 below.
BUILD_SERVICES="gateway collab cad text-to-cad ocr cad-viewer"

# Compose files for building (in order)
COMPOSE_FILES=(
    "docker/docker-compose-dev.yaml"
    "docker/docker-compose.extensions.yaml"
    "docker/docker-compose.temporal.yaml"
)

if [ "$WITH_RAGFLOW" = true ]; then
    COMPOSE_FILES+=("docker/docker-compose.ragflow.yaml")
    PUBLIC_IMAGES+=(
        "infiniflow/ragflow:v0.25.3-fixed"
        "elasticsearch:8.11.3"
        "mysql:8.0"
        "redis:7-alpine"
        "minio/minio:latest"
    )
fi

if [ "$WITH_BUSINESS" = true ]; then
    COMPOSE_FILES+=("docker/docker-compose.business.yaml")
    BUILD_SERVICES="${BUILD_SERVICES} procurement-backend procurement-frontend"
fi

# ── RAGFlow offline hardening: build v0.25.3-fixed (F.11 pip PATH + F.13 tiktoken) ─
# EAI-CUSTOM: 在 Step 1 的 local-only 检查之前构建 fixed 镜像（基于本地 base 叠加修复），
# 这样 Step 1 校验 infiniflow/ragflow:v0.25.3-fixed 时它已在本地。
if [ "$WITH_RAGFLOW" = true ]; then
    if ! docker image inspect infiniflow/ragflow:v0.25.3-fixed &>/dev/null; then
        info "  Building: infiniflow/ragflow:v0.25.3-fixed (F.11/F.13 hardening)"
        if ! docker build -t infiniflow/ragflow:v0.25.3-fixed \
             -f "${REPO_ROOT}/deploy/offline/ragflow-fixed.Dockerfile" "${REPO_ROOT}/deploy/offline"; then
            err "  ragflow-fixed build failed"
            err "  Is the base infiniflow/ragflow:v0.25.3 present locally? Run 'make docker-start' first."
            exit 1
        fi
        ok "  Built:    infiniflow/ragflow:v0.25.3-fixed"
    else
        ok "  Local:    infiniflow/ragflow:v0.25.3-fixed (already built)"
    fi
fi

# ── Step 1: Pull public images ─────────────────────────────────────────────────

info "Step 1/5: Resolving ${#PUBLIC_IMAGES[@]} public images (local-only, no pull)..."
echo ""

for img in "${PUBLIC_IMAGES[@]}"; do
    # Offline export = ship the locally-present (dev-verified) image only.
    # NEVER pull: the package must match exactly what the dev environment
    # validated. Floating tags (nginx:alpine, minio/minio:latest) would drift
    # to a different digest if pulled, and pulling contradicts the offline
    # premise. A missing image means the dev env isn't populated yet.
    if docker image inspect "$img" &>/dev/null; then
        ok "  Local:   ${img}  (dev-verified, will export)"
    else
        err "  Image not found locally: ${img}"
        err "  Populate it first on this online dev machine (make docker-start), then re-run."
        exit 1
    fi
done

echo ""

# ── Step 2: Build project images ───────────────────────────────────────────────

info "Step 2/5: Resolving project images (local-only, rebuild only if missing)..."
echo ""

COMPOSE_CMD="docker compose -p eai-docker"
for f in "${COMPOSE_FILES[@]}"; do
    COMPOSE_CMD="${COMPOSE_CMD} -f ${REPO_ROOT}/${f}"
done

for svc in $BUILD_SERVICES; do
    COMPOSE_IMG="eai-docker-${svc}:latest"
    # Ship the locally-present (dev-verified) image. Rebuilding here is both
    # wasteful and risky: the Dockerfiles run online `uv sync` / `pnpm install`
    # that can flake on a restricted network, and a fresh build could diverge
    # from what dev validated. Only build when the image is truly absent.
    if docker image inspect "$COMPOSE_IMG" &>/dev/null; then
        ok "  Local:   ${svc}  (${COMPOSE_IMG}, dev-verified)"
    else
        info "  Building: ${svc} (not found locally)"
        if $COMPOSE_CMD build "$svc"; then
            ok "  Built:    ${svc}"
        else
            err "  Build failed for: ${svc}"
            err "  Populate it via 'make docker-start' on this dev machine, then re-run."
            exit 1
        fi
    fi
done

# ── Frontend: build PROD image directly (dev compose pins target=dev) ────────
# EAI-CUSTOM: prod build kills F.14-F.18 (HMR / allowedDevOrigins / Turbopack).
# The dev compose (`docker/docker-compose-dev.yaml`) pins the frontend build to
# `target: dev`, and `docker compose build` has no CLI flag to override the
# target — so building through the compose yields a dev image. To ship a real
# production image, build the Dockerfile directly with `--target prod`. Base /
# builder layers (pnpm install) are reused from the cached dev build, so this
# only re-runs `pnpm build` and assembles the minimal runtime stage.
FRONTEND_PROD_IMAGE="deer-flow-frontend:latest"

# EAI-CUSTOM: 按客户品牌注入。读 repo 根 deploy.conf 的 BRAND_*（运维导出前按客户填）；
# 无 deploy.conf 则用默认（brand.ts 回落 "EAIFlow"）。
BRAND_NAME_VAL=""; BRAND_FOOTER_VAL=""; BRAND_ASSETS_DIR_VAL=""
if [ -f "${REPO_ROOT}/deploy.conf" ]; then
    BRAND_NAME_VAL=$(grep -E "^BRAND_NAME=" "${REPO_ROOT}/deploy.conf" | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^"//;s/"$//')
    BRAND_FOOTER_VAL=$(grep -E "^BRAND_FOOTER=" "${REPO_ROOT}/deploy.conf" | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^"//;s/"$//')
    BRAND_ASSETS_DIR_VAL=$(grep -E "^BRAND_ASSETS_DIR=" "${REPO_ROOT}/deploy.conf" | head -1 | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^"//;s/"$//')
fi
# 拷客户 logo/favicon 进 frontend/public/（构建期 COPY 烘焙进镜像）
ASSETS_DIR="${REPO_ROOT}/${BRAND_ASSETS_DIR_VAL:-deploy/offline/brand-assets}"
if [ -d "$ASSETS_DIR" ]; then
    for f in favicon.ico favicon.svg logo.svg; do
        [ -f "$ASSETS_DIR/$f" ] && cp "$ASSETS_DIR/$f" "${REPO_ROOT}/frontend/public/$f"
    done
fi

info "  Building: frontend (prod target, brand=\"${BRAND_NAME_VAL:-EAIFlow}\")"
if ! docker build --target prod --progress=plain \
     --build-arg APP_VERSION="${VERSION}" \
     --build-arg BRAND_NAME="${BRAND_NAME_VAL}" \
     --build-arg BRAND_FOOTER="${BRAND_FOOTER_VAL}" \
     -t "${FRONTEND_PROD_IMAGE}" \
     -f frontend/Dockerfile .; then
    err "  Build failed for: frontend (prod)"
    err "  Run 'make docker-start' on this dev machine first to populate base layers, then re-run."
    exit 1
fi
ok "  Built:    frontend (prod) → ${FRONTEND_PROD_IMAGE}"

# 恢复 frontend/public（防客户资源污染源码树）
git -C "${REPO_ROOT}" checkout -- frontend/public/favicon.ico frontend/public/favicon.svg frontend/public/logo.svg 2>/dev/null || true

# Collect actual image names from built services.
# docker compose -p eai-docker build produces images named eai-docker-<service>:latest
# We tag them with the canonical names expected by docker-compose-offline.yaml.
# EAI-CUSTOM: frontend is NOT in this map — it is built directly as
# deer-flow-frontend:latest above and added to BUILT_IMAGE_NAMES below.
BUILT_IMAGE_NAMES=()

# Known compose project prefix → canonical tag mapping
declare -A SERVICE_TAG_MAP=(
    ["eai-docker-gateway:latest"]="deer-flow-gateway:latest"
    ["eai-docker-collab:latest"]="eai-flow-collab:latest"
    ["eai-docker-procurement-backend:latest"]="eai-flow-procurement-backend:latest"
    ["eai-docker-procurement-frontend:latest"]="eai-flow-procurement-frontend:latest"
    ["eai-docker-cad:latest"]="eai-flow-cad:latest"
    ["eai-docker-text-to-cad:latest"]="eai-flow-text-to-cad:latest"
    ["eai-docker-ocr:latest"]="eai-flow-ocr:latest"
    ["eai-docker-cad-viewer:latest"]="eai-flow-cad-viewer:latest"
)

for COMPOSE_IMG in "${!SERVICE_TAG_MAP[@]}"; do
    CANONICAL="${SERVICE_TAG_MAP[$COMPOSE_IMG]}"
    # Check if the compose-built image exists
    if docker image inspect "$COMPOSE_IMG" &>/dev/null; then
        docker tag "$COMPOSE_IMG" "$CANONICAL"
        ok "  Tagged:   ${COMPOSE_IMG} → ${CANONICAL}"
        BUILT_IMAGE_NAMES+=("$CANONICAL")
    else
        warn "  Image not found: ${COMPOSE_IMG} — skipping"
    fi
done

# EAI-CUSTOM: frontend prod image was built directly with the canonical tag, so
# no retag is needed — just register it for the export (docker save) below.
if docker image inspect "${FRONTEND_PROD_IMAGE}" &>/dev/null; then
    BUILT_IMAGE_NAMES+=("${FRONTEND_PROD_IMAGE}")
else
    err "  Frontend prod image missing after build: ${FRONTEND_PROD_IMAGE}"
    exit 1
fi

if [ ${#BUILT_IMAGE_NAMES[@]} -eq 0 ]; then
    err "No built images found. Build may have failed. Check docker images for eai-docker-*"
    exit 1
fi

# ── Delta 模式：仅导出相对上次 manifest 变化的镜像，打小增量包后退出 ──────────
# EAI-CUSTOM: 增量升级（G3）。本地镜像 digest 与 .offline-export-history/<ver>/manifest.json
# 比对，只 docker save 变化项；服务器端 upgrade.sh 只 load 这些。
if [ "$DELTA" = true ]; then
    PREV_MANIFEST="${REPO_ROOT}/.offline-export-history/${SINCE}/manifest.json"
    if [ ! -f "$PREV_MANIFEST" ]; then
        err "Delta 基线 manifest 未找到: $PREV_MANIFEST"
        err "  先跑一次全量导出建立基线：bash scripts/offline-export.sh"
        exit 1
    fi
    # 一次性载入上次各镜像 digest 到关联数组
    declare -A PREV_DGST
    while IFS=$'\t' read -r k v; do
        [ -n "$k" ] && PREV_DGST["$k"]="$v"
    done < <("${PYTHON}" - "$PREV_MANIFEST" <<'PY'
import json, sys
for k, v in json.load(open(sys.argv[1])).get("images", {}).items():
    print(f"{k}\t{v.get('digest','')}")
PY
)
    ALL_DELTA=("${BUILT_IMAGE_NAMES[@]}" "${PUBLIC_IMAGES[@]}")
    mkdir -p "${IMAGES_DIR}"
    CHANGED=0; UNCHANGED=0
    info "Delta 导出（基线 ${SINCE}），仅导变化镜像："
    for img in "${ALL_DELTA[@]}"; do
        cur=$(docker image inspect "$img" --format '{{.Id}}' 2>/dev/null || echo "")
        [ -z "$cur" ] && { warn "  本地缺失，跳过: ${img}"; continue; }
        if [ "$cur" = "${PREV_DGST[$img]:-}" ]; then
            UNCHANGED=$((UNCHANGED+1)); continue
        fi
        fname=$(echo "$img" | sed 's|[/:]|_|g; s|\.||g' | tr '[:upper:]' '[:lower:]')
        info "  变化: ${img} → images/${fname}.tar"
        if docker save "$img" -o "${IMAGES_DIR}/${fname}.tar"; then
            ok "  已导: ${fname}.tar ($(du -sh "${IMAGES_DIR}/${fname}.tar" | cut -f1))"; CHANGED=$((CHANGED+1))
        else
            warn "  导出失败: ${img}"
        fi
    done
    info "  变化 ${CHANGED}，未变 ${UNCHANGED}"

    # 生成新 manifest + 存入历史
    VERSION_TAG="v${DATE}-$(git rev-parse --short HEAD)"
    # EAI-CUSTOM: hash 实际 deploy.conf（用户的真实配置输入），缺失才回落到模板。
    # 旧实现 hash 静态 deploy.conf.example → 永远不变 → upgrade.sh 永不触发配置重生成。
    CFG_HASH=$(sha256sum deploy.conf 2>/dev/null | cut -d' ' -f1 || sha256sum deploy/offline/deploy.conf.example 2>/dev/null | cut -d' ' -f1 || echo unknown)
    MANIFEST="${OUTPUT_DIR}/manifest.json"
    "${PYTHON}" - "$VERSION_TAG" "$DATE" "$CFG_HASH" "$MANIFEST" "${ALL_DELTA[@]}" <<'PY'
import json, subprocess, sys
ver, date, cfg, out, *imgs = sys.argv[1:]
digests = {}
for img in imgs:
    try:
        dgst = subprocess.check_output(["docker","image","inspect",img,"--format","{{.Id}}"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        dgst = "unknown"
    digests[img] = {"digest": dgst}
with open(out,"w") as f:
    json.dump({"version":ver,"exported_at":date,"images":digests,"config_hash":cfg}, f, indent=2, ensure_ascii=False)
PY
    mkdir -p "${REPO_ROOT}/.offline-export-history/${VERSION_TAG}"
    cp "$MANIFEST" "${REPO_ROOT}/.offline-export-history/${VERSION_TAG}/manifest.json"

    # 增量包只含 images/ + manifest（compose/config 已在全量包里）
    tar czf "${REPO_ROOT}/eai-flow-delta-${VERSION_TAG}.tar.gz" -C "${OUTPUT_DIR}" images manifest.json
    DELTA_SIZE=$(du -sh "${REPO_ROOT}/eai-flow-delta-${VERSION_TAG}.tar.gz" | cut -f1)
    echo ""
    echo "============================================="
    echo "  Delta 包已生成（version=${VERSION_TAG}）"
    echo "============================================="
    echo "  文件:     eai-flow-delta-${VERSION_TAG}.tar.gz (${DELTA_SIZE})"
    echo "  变化镜像: ${CHANGED}，未变 ${UNCHANGED}"
    echo ""
    echo "  推送升级（内网 ssh/scp）："
    echo "    scp eai-flow-delta-${VERSION_TAG}.tar.gz root@<服务器>:/opt/eai-flow-offline/delta/"
    echo "    ssh root@<服务器> 'cd /opt/eai-flow-offline && mkdir -p delta && tar xzf delta/eai-flow-delta-${VERSION_TAG}.tar.gz -C delta && ./upgrade.sh delta'"
    echo ""
    exit 0
fi

TOTAL_IMAGES=$(( ${#PUBLIC_IMAGES[@]} + ${#BUILT_IMAGE_NAMES[@]} ))

echo ""

# ── Step 3: Export images ──────────────────────────────────────────────────────

info "Step 3/5: Exporting ${TOTAL_IMAGES} images to ${IMAGES_DIR}/..."
echo ""

mkdir -p "${IMAGES_DIR}"

# Helper: convert image name to safe filename
image_to_filename() {
    echo "$1" | sed 's|[/:]|_|g; s|\.||g' | tr '[:upper:]' '[:lower:]'
}

for img in "${PUBLIC_IMAGES[@]}"; do
    fname=$(image_to_filename "$img")
    info "  Exporting: ${img} → images/${fname}.tar"
    docker save "$img" -o "${IMAGES_DIR}/${fname}.tar"
    ok "  Done:      ${fname}.tar ($(du -sh "${IMAGES_DIR}/${fname}.tar" | cut -f1))"
done

for img in "${BUILT_IMAGE_NAMES[@]}"; do
    fname=$(image_to_filename "$img")
    info "  Exporting: ${img} → images/${fname}.tar"
    if docker save "$img" -o "${IMAGES_DIR}/${fname}.tar"; then
        ok "  Done:      ${fname}.tar ($(du -sh "${IMAGES_DIR}/${fname}.tar" | cut -f1))"
    else
        warn "  Could not export: ${img}"
    fi
done

echo ""

# ── Step 4: Copy configuration files ───────────────────────────────────────────

info "Step 4/5: Copying configuration files..."
echo ""

# Docker compose files — use PRODUCTION offline compose from deploy/offline/
# These are pre-configured for production with:
#   - Project name: eai-prod (isolated from dev eai-docker)
#   - Container prefix: prod-* (no collision with dev containers)
#   - Network: eai-prod_eai-flow-net (separate from dev)
#   - No source code mounts, no build: directives
mkdir -p "${OUTPUT_DIR}/docker/nginx"
cp "deploy/offline/docker-compose.yaml"            "${OUTPUT_DIR}/docker/"
cp "deploy/offline/docker-compose.extensions.yaml" "${OUTPUT_DIR}/docker/"
if [ "$WITH_RAGFLOW" = true ]; then
    cp "deploy/offline/docker-compose.ragflow.yaml" "${OUTPUT_DIR}/docker/"
fi
if [ "$WITH_BUSINESS" = true ]; then
    warn "  Business offline compose not yet created — business services will need manual image tagging"
fi

# Docker support files — production nginx config (no IPv6, no procurement, no HMR)
cp "deploy/offline/nginx/nginx.conf"     "${OUTPUT_DIR}/docker/nginx/nginx.conf"

# Postgres one-shot init scripts (Temporal user/db automation)
mkdir -p "${OUTPUT_DIR}/postgres-init"
cp "deploy/offline/postgres-init/"*.sh   "${OUTPUT_DIR}/postgres-init/" 2>/dev/null || true

# Pre-configured configuration files (NOT templates — ready to use out of the box)
# User only needs to edit: config.yaml models section (LLM endpoint) + .env BETTER_AUTH_SECRET
cp "deploy/offline/config.yaml"          "${OUTPUT_DIR}/config.yaml"
if [ -f "deploy/offline/extensions_config.json" ]; then
    cp "deploy/offline/extensions_config.json" "${OUTPUT_DIR}/extensions_config.json"
fi
cp "deploy/offline/.env"                 "${OUTPUT_DIR}/.env"

# EAI-CUSTOM: 零编辑部署所需 —— 配置生成器 + 唯一配置源模板拷进包。
# install.sh 的 setup_config 调用 scripts/generate-config.sh，从 deploy.conf 生成全部配置。
mkdir -p "${OUTPUT_DIR}/scripts"
cp "scripts/generate-config.sh"          "${OUTPUT_DIR}/scripts/generate-config.sh"
chmod +x "${OUTPUT_DIR}/scripts/generate-config.sh"
cp "deploy/offline/deploy.conf.example"  "${OUTPUT_DIR}/deploy.conf.example"
# EAI-CUSTOM: 服务器端增量升级脚本
cp "deploy/offline/upgrade.sh"           "${OUTPUT_DIR}/upgrade.sh"
chmod +x "${OUTPUT_DIR}/upgrade.sh"

# Skills directory (just the public structure)
if [ -d "skills/public" ]; then
    mkdir -p "${OUTPUT_DIR}/skills"
    cp -r "skills/public"                 "${OUTPUT_DIR}/skills/"
fi

# MCP server (if present) — exclude .git to avoid submodule permission issues
if [ -d "mcp-server" ]; then
    rsync -a --exclude='.git' "mcp-server/" "${OUTPUT_DIR}/mcp-server/" 2>/dev/null || \
        cp -r "mcp-server"                "${OUTPUT_DIR}/mcp-server/"
    # Clean any .git dirs that may have been copied (Windows safety)
    find "${OUTPUT_DIR}/mcp-server" -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true
fi

ok "  Configuration files copied"
echo ""

# ── Step 5: Generate helper scripts ────────────────────────────────────────────

info "Step 5/5: Generating deployment scripts..."
echo ""

# ── load-images.sh ─────────────────────────────────────────────────────────────

cat > "${OUTPUT_DIR}/load-images.sh" << 'LOADSCRIPT'
#!/usr/bin/env bash
#
# load-images.sh - Load all Docker images from .tar files
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_DIR="${SCRIPT_DIR}/images"

if [ ! -d "$IMAGES_DIR" ]; then
    echo "ERROR: images/ directory not found in ${SCRIPT_DIR}"
    exit 1
fi

COUNT=0
TOTAL=$(ls -1 "${IMAGES_DIR}"/*.tar 2>/dev/null | wc -l)

echo "Loading ${TOTAL} Docker images..."
echo ""

for tar in "${IMAGES_DIR}"/*.tar; do
    [ -f "$tar" ] || continue
    COUNT=$((COUNT + 1))
    FNAME=$(basename "$tar")
    echo "  [${COUNT}/${TOTAL}] Loading ${FNAME}..."
    docker load -i "$tar"
done

echo ""
echo "Done. ${COUNT} images loaded successfully."
echo ""
echo "Verifying loaded images:"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | head -30
LOADSCRIPT
chmod +x "${OUTPUT_DIR}/load-images.sh"

# ── install.sh ─────────────────────────────────────────────────────────────────

cat > "${OUTPUT_DIR}/install.sh" << 'INSTALLSCRIPT'
#!/usr/bin/env bash
#
# install.sh - DeerFlow Offline Installation Script
#
# This script deploys DeerFlow on an air-gapped Linux server.
# It checks prerequisites, loads images, and starts all services.
#
set -e

# ── Colors ─────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Environment Check ──────────────────────────────────────────────────────────

check_environment() {
    echo "============================================="
    echo "  DeerFlow Offline Deployment"
    echo "  Environment Check"
    echo "============================================="
    echo ""

    local ERRORS=0

    # OS check
    if [ "$(uname -s)" != "Linux" ]; then
        warn "Not running on Linux (detected: $(uname -s)). Script is designed for Linux."
    else
        ok "OS: $(uname -s) $(uname -r)"
    fi

    # Docker
    if command -v docker &>/dev/null; then
        DOCKER_VER=$(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)
        ok "Docker: ${DOCKER_VER}"
    else
        err "Docker is NOT installed. Please install Docker Engine >= 24.0 first."
        err "  Offline install: see docker-install/ directory for .rpm/.deb packages"
        ERRORS=$((ERRORS + 1))
    fi

    # docker compose
    if docker compose version &>/dev/null; then
        COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "unknown")
        ok "docker compose: ${COMPOSE_VER}"
    else
        err "docker compose v2 is NOT available (docker compose plugin required)."
        ERRORS=$((ERRORS + 1))
    fi

    # Disk space
    if command -v df &>/dev/null; then
        AVAILABLE_GB=$(df -BG "$SCRIPT_DIR" | tail -1 | awk '{print $4}' | tr -d 'G')
        if [ "$AVAILABLE_GB" -lt 20 ]; then
            warn "Disk space: ${AVAILABLE_GB}GB available (recommended: >= 40GB)"
        else
            ok "Disk space: ${AVAILABLE_GB}GB available"
        fi
    fi

    # Memory
    if command -v free &>/dev/null; then
        TOTAL_MEM_GB=$(free -g | awk '/^Mem:/{print $2}')
        if [ "$TOTAL_MEM_GB" -lt 7 ]; then
            warn "Memory: ${TOTAL_MEM_GB}GB (recommended: >= 8GB)"
        else
            ok "Memory: ${TOTAL_MEM_GB}GB"
        fi
    fi

    # Port check (read actual port from .env if it exists)
    CHECK_PORT=$(grep '^PORT=' "${SCRIPT_DIR}/.env" 2>/dev/null | cut -d= -f2 || echo 4026)
    if ss -tlnp 2>/dev/null | grep -q ":${CHECK_PORT} "; then
        warn "Port ${CHECK_PORT} is already in use. DeerFlow needs this port."
    else
        ok "Port ${CHECK_PORT}: available"
    fi

    echo ""
    if [ "$ERRORS" -gt 0 ]; then
        err "Found ${ERRORS} error(s). Please fix before continuing."
        exit 1
    fi

    ok "Environment check passed!"
    echo ""
}

# ── Confirm ────────────────────────────────────────────────────────────────────

confirm_install() {
    echo "============================================="
    echo "  Ready to install DeerFlow"
    echo "============================================="
    echo ""
    echo "This will:"
    echo "  1. Load all Docker images from images/"
    echo "  2. Create Docker network (eai-prod_eai-flow-net)"
    echo "  3. Start all services via docker compose"
    echo ""
    read -r -p "Continue? [y/N] " REPLY
    echo ""
    if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
        info "Aborted."
        exit 0
    fi
}

# ── Load images ────────────────────────────────────────────────────────────────

load_images() {
    info "Loading Docker images..."
    bash "${SCRIPT_DIR}/load-images.sh"
    ok "All images loaded."
    echo ""
}

# ── Create network ─────────────────────────────────────────────────────────────

create_network() {
    if docker network inspect eai-prod_eai-flow-net &>/dev/null; then
        ok "Docker network 'eai-prod_eai-flow-net' already exists."
    else
        info "Creating Docker network 'eai-prod_eai-flow-net'..."
        docker network create eai-prod_eai-flow-net
        ok "Network created."
    fi
    echo ""
}

# ── Setup config ───────────────────────────────────────────────────────────────

setup_config() {
    info "Generating configuration (zero-edit)..."
    echo ""

    # 首次部署：无 deploy.conf 则从模板创建，提示填 LLM 后重跑
    if [ ! -f "${SCRIPT_DIR}/deploy.conf" ]; then
        cp "${SCRIPT_DIR}/deploy.conf.example" "${SCRIPT_DIR}/deploy.conf"
        warn "Created deploy.conf from template."
        warn "  Fully offline? Edit deploy.conf (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL), then re-run ./install.sh"
        warn "  Intranet with cloud egress? Leave LLM_* empty and re-run."
        exit 0
    fi

    # 自动推导不可猜的值：root=部署目录；secret=已存在或随机生成；origin=本机IP:4026
    local root="${SCRIPT_DIR}"
    local secret
    secret=$(grep '^BETTER_AUTH_SECRET=' "${SCRIPT_DIR}/.env" 2>/dev/null | cut -d= -f2 || true)
    if [ -z "${secret}" ] || [ "${secret}" = "change-me-to-a-random-string" ]; then
        secret=$(openssl rand -base64 32)
        ok "Generated a fresh BETTER_AUTH_SECRET."
    fi
    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${ip}" ] && ip="localhost"
    local origin="http://${ip}:4026"
    ok "Auto-derived: root=${root}  trusted_origin=${origin}"

    # 由 deploy.conf 生成 .env / config.yaml / extensions_config.json
    if ! bash "${SCRIPT_DIR}/scripts/generate-config.sh" \
            --conf "${SCRIPT_DIR}/deploy.conf" --out "${SCRIPT_DIR}" \
            --root "${root}" --secret "${secret}" --origin "${origin}"; then
        err "generate-config.sh failed. Check deploy.conf (KEY=VALUE, one per line, comments on their own line)."
        exit 1
    fi

    # F.10: 预置 nginx.conf 实体文件，防首次挂载把文件当目录创建
    if [ ! -f "${SCRIPT_DIR}/nginx/nginx.conf" ]; then
        mkdir -p "${SCRIPT_DIR}/nginx"
        cp "${SCRIPT_DIR}/docker/nginx/nginx.conf" "${SCRIPT_DIR}/nginx/nginx.conf" 2>/dev/null || true
    fi

    # 运行时目录
    mkdir -p "${SCRIPT_DIR}/data" "${SCRIPT_DIR}/logs" "${SCRIPT_DIR}/skills/custom"

    ok "Configuration ready."
    echo ""
}

# ── Start services ─────────────────────────────────────────────────────────────

start_services() {
    info "Starting DeerFlow services..."
    echo ""

    cd "${SCRIPT_DIR}"

    # Build compose command — production offline compose
    COMPOSE_CMD="docker compose -p eai-prod --project-directory ${SCRIPT_DIR}"

    # Core offline compose (no source code mounts, uses pre-built images)
    COMPOSE_CMD="${COMPOSE_CMD} -f docker/docker-compose.yaml"

    # Add extension compose files if present (all use image: not build:)
    for f in \
        docker/docker-compose.extensions.yaml \
        docker/docker-compose.ragflow.yaml \
        docker/docker-compose.business.yaml; do
        if [ -f "$f" ]; then
            COMPOSE_CMD="${COMPOSE_CMD} -f ${f}"
        fi
    done

    # Start services
    $COMPOSE_CMD up -d

    echo ""
    ok "Services started!"
    echo ""
}

# ── Wait for healthy ───────────────────────────────────────────────────────────

wait_for_healthy() {
    info "Waiting for services to become healthy (this may take 2-5 minutes)..."
    echo ""

    # Read the actual host port from .env
    ACCESS_PORT=$(grep '^PORT=' "${SCRIPT_DIR}/.env" 2>/dev/null | cut -d= -f2 || echo 4026)

    # Wait for postgres-ext
    info "  Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker exec prod-eai-flow-postgres-ext pg_isready -U agentflow &>/dev/null; then
            ok "  PostgreSQL is ready."
            break
        fi
        sleep 2
    done

    # Wait for gateway
    info "  Waiting for Gateway API..."
    for i in $(seq 1 60); do
        if curl -sf "http://localhost:${ACCESS_PORT}/api/license/status" &>/dev/null; then
            ok "  Gateway API is ready."
            break
        fi
        sleep 3
    done

    echo ""
}

# ── Post-install ───────────────────────────────────────────────────────────────

post_install() {
    # Run workflow migration
    info "Running workflow database migration..."
    docker exec prod-eai-flow-gateway python -m app.extensions.workflow.migration 2>/dev/null && \
        ok "Workflow migration complete." || \
        warn "Workflow migration skipped (may not be needed)."

    # Read the actual host port from .env
    ACCESS_PORT=$(grep '^PORT=' "${SCRIPT_DIR}/.env" 2>/dev/null | cut -d= -f2 || echo 4026)

    # Initialize default admin account
    info "Initializing admin account..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Content-Type: application/json" \
      -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}' \
      "http://localhost:${ACCESS_PORT}/api/v1/auth/initialize" 2>/dev/null || echo "000")
    case "$HTTP_CODE" in
      201) ok "Admin created: admin@eai-flow.com / Admin@2026" ;;
      409) ok "Admin already exists, skipping." ;;
      *)   warn "Admin init returned HTTP $HTTP_CODE — create manually: curl -X POST http://localhost:${ACCESS_PORT}/api/v1/auth/initialize -H 'Content-Type: application/json' -d '{\"email\":\"admin@eai-flow.com\",\"password\":\"Admin@2026\"}'" ;;
    esac

    echo ""
    echo "============================================="
    echo "  DeerFlow Installation Complete!"
    echo "============================================="
    echo ""
    echo "  Access URL:   http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost'):${ACCESS_PORT}"
    echo "  Admin:        admin@eai-flow.com / Admin@2026"
    echo ""
    echo "  ⚠️  Please change the admin password after first login!"
    echo ""
    echo "  Useful commands:"
    echo "    docker compose -p eai-prod ps          # Check service status"
    echo "    docker compose -p eai-prod logs -f      # View logs"
    echo "    docker compose -p eai-prod restart gateway  # Restart gateway"
    echo "    docker compose -p eai-prod down         # Stop all services"
    echo ""
}

# ── Main ───────────────────────────────────────────────────────────────────────

check_environment
confirm_install
setup_config
load_images
create_network
start_services
wait_for_healthy
post_install
INSTALLSCRIPT
chmod +x "${OUTPUT_DIR}/install.sh"

ok "  Generated: load-images.sh"
ok "  Generated: install.sh"
echo ""

# ── Package ────────────────────────────────────────────────────────────────────

# ── manifest.json: 版本号 + 各镜像 digest（供 --delta 比对与 IMAGE_TAG 回滚记录）──
# EAI-CUSTOM: 镜像打版本 tag，支持按版本回滚与增量升级比对。
VERSION_TAG="v${DATE}-$(git rev-parse --short HEAD)"
# EAI-CUSTOM: hash 实际 deploy.conf（用户的真实配置输入），缺失才回落到模板。
CFG_HASH=$(sha256sum deploy.conf 2>/dev/null | cut -d' ' -f1 || sha256sum deploy/offline/deploy.conf.example 2>/dev/null | cut -d' ' -f1 || echo unknown)
MANIFEST="${OUTPUT_DIR}/manifest.json"
ALL_IMGS=("${BUILT_IMAGE_NAMES[@]}" "${PUBLIC_IMAGES[@]}")
"${PYTHON}" - "$VERSION_TAG" "$DATE" "$CFG_HASH" "$MANIFEST" "${ALL_IMGS[@]}" <<'PY'
import json, subprocess, sys
ver, date, cfg, out, *imgs = sys.argv[1:]
digests = {}
for img in imgs:
    try:
        dgst = subprocess.check_output(
            ["docker", "image", "inspect", img, "--format", "{{.Id}}"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        dgst = "unknown"
    digests[img] = {"digest": dgst}
with open(out, "w") as f:
    json.dump({"version": ver, "exported_at": date, "images": digests, "config_hash": cfg}, f, indent=2, ensure_ascii=False)
print(f"  manifest.json: version={ver}, {len(imgs)} images")
PY
ok "  Generated: manifest.json (version=${VERSION_TAG})"
# 存入历史，供后续 --delta --since <VERSION_TAG> 比对基线
mkdir -p "${REPO_ROOT}/.offline-export-history/${VERSION_TAG}"
cp "$MANIFEST" "${REPO_ROOT}/.offline-export-history/${VERSION_TAG}/manifest.json"

info "Calculating package size..."
PACKAGE_SIZE=$(du -sh "${OUTPUT_DIR}" | cut -f1)
info "Package size: ${PACKAGE_SIZE}"

info "Compressing to ${PACKAGE_NAME}.tar.gz ..."
tar czf "${REPO_ROOT}/${PACKAGE_NAME}.tar.gz" -C "${REPO_ROOT}" "${PACKAGE_NAME}"

COMPRESSED_SIZE=$(du -sh "${REPO_ROOT}/${PACKAGE_NAME}.tar.gz" | cut -f1)

echo ""
echo "============================================="
echo "  Offline Package Created!"
echo "============================================="
echo ""
echo "  File:     ${PACKAGE_NAME}.tar.gz"
echo "  Size:     ${COMPRESSED_SIZE}"
echo "  Images:   ${TOTAL_IMAGES}"
echo "  RAGFlow:  ${WITH_RAGFLOW}"
echo ""
echo "  Deploy to target server:"
echo "    1. scp ${PACKAGE_NAME}.tar.gz user@target:/opt/"
echo "    2. ssh user@target"
echo "    3. cd /opt && tar xzf ${PACKAGE_NAME}.tar.gz"
echo "    4. cd ${PACKAGE_NAME} && ./install.sh"
echo ""
echo "  Environment requirements for target server:"
echo "    - Linux x86_64 (Ubuntu 22.04+ / CentOS 8+ / Debian 12+)"
echo "    - Docker Engine >= 24.0 + docker compose v2"
echo "    - 8GB RAM, 40GB disk (recommended: 16GB RAM, 100GB SSD)"
echo "    - Port 4026 (or configured PORT in .env) open for browser access"
echo "    - Internal LLM API reachable from Docker containers"
echo ""
