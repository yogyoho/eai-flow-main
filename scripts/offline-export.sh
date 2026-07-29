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

for arg in "$@"; do
    case "$arg" in
        --with-ragflow)   WITH_RAGFLOW=true ;;
        --no-ragflow)     WITH_RAGFLOW=false ;;
        --with-business)  WITH_BUSINESS=true ;;
        --help|-h)
            echo "Usage: $0 [--with-ragflow] [--no-ragflow] [--with-business]"
            echo ""
            echo "Options:"
            echo "  --with-ragflow    Include RAGFlow knowledge base images (default)"
            echo "  --no-ragflow      Exclude RAGFlow images"
            echo "  --with-business   Include business microservice images"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--with-ragflow] [--no-ragflow] [--with-business]"
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
        "infiniflow/ragflow:v0.25.3"
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
info "  Building: frontend (prod target, direct Dockerfile build)"
if ! docker build --target prod --progress=plain \
     --build-arg APP_VERSION="${VERSION}" \
     -t "${FRONTEND_PROD_IMAGE}" \
     -f frontend/Dockerfile .; then
    err "  Build failed for: frontend (prod)"
    err "  Run 'make docker-start' on this dev machine first to populate base layers, then re-run."
    exit 1
fi
ok "  Built:    frontend (prod) → ${FRONTEND_PROD_IMAGE}"

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
cp "deploy/offline/docker-compose.temporal.yaml"   "${OUTPUT_DIR}/docker/"
cp "deploy/offline/docker-compose.mcp-cad.yaml"    "${OUTPUT_DIR}/docker/"
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
    # Check that pre-configured files exist (they are included in the offline package)
    local NEED_EDIT=false

    # .env file — pre-configured, verify key variables
    if [ ! -f "${SCRIPT_DIR}/.env" ]; then
        err ".env file is missing! This should have been included in the offline package."
        exit 1
    fi
    # Source .env to check critical vars
    source "${SCRIPT_DIR}/.env"
    if [ "${BETTER_AUTH_SECRET:-}" = "change-me-to-a-random-string" ]; then
        warn "BETTER_AUTH_SECRET is still the default value. Please change it."
        warn "  Run: openssl rand -base64 32"
        NEED_EDIT=true
    fi
    if [ -z "${DEER_FLOW_ROOT:-}" ]; then
        warn "DEER_FLOW_ROOT is not set in .env. Update it to this directory's absolute path."
        NEED_EDIT=true
    fi

    # config.yaml — pre-configured, check LLM endpoint
    if [ ! -f "${SCRIPT_DIR}/config.yaml" ]; then
        err "config.yaml is missing! This should have been included in the offline package."
        exit 1
    fi
    if grep -q "your-model-name-here" "${SCRIPT_DIR}/config.yaml" 2>/dev/null; then
        warn "config.yaml still has placeholder model name. Please configure your intranet LLM."
        warn "  Edit config.yaml → models section:"
        warn "    model: <your-model-name>"
        warn "    base_url: http://<YOUR_LLM_IP>:<PORT>/v1"
        NEED_EDIT=true
    fi

    # extensions_config.json
    if [ ! -f "${SCRIPT_DIR}/extensions_config.json" ]; then
        warn "extensions_config.json not found, creating empty config."
        echo '{"mcpServers": {}, "skills": {}}' > "${SCRIPT_DIR}/extensions_config.json"
    fi

    if $NEED_EDIT; then
        echo ""
        echo "  Edit configuration files now? [Y/n]"
        read -p "> " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            ${EDITOR:-vi} "${SCRIPT_DIR}/.env"
            ${EDITOR:-vi} "${SCRIPT_DIR}/config.yaml"
        fi
    fi

    # Create data directories (mapped by docker compose volumes)
    mkdir -p "${SCRIPT_DIR}/data"          # .deer-flow persistent data
    mkdir -p "${SCRIPT_DIR}/logs"          # runtime logs
    mkdir -p "${SCRIPT_DIR}/skills/custom" # custom skills

    ok "Configuration files ready."
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
        docker/docker-compose.temporal.yaml \
        docker/docker-compose.ragflow.yaml \
        docker/docker-compose.mcp-cad.yaml \
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
load_images
create_network
setup_config
start_services
wait_for_healthy
post_install
INSTALLSCRIPT
chmod +x "${OUTPUT_DIR}/install.sh"

ok "  Generated: load-images.sh"
ok "  Generated: install.sh"
echo ""

# ── Package ────────────────────────────────────────────────────────────────────

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
