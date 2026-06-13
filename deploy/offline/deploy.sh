#!/usr/bin/env bash
# =============================================================================
# EAI-Flow 生产离线部署 — 一键部署脚本
# =============================================================================
# 用法:
#   chmod +x deploy.sh
#   ./deploy.sh              # 部署全部服务
#   ./deploy.sh down          # 停止并清理全部服务
#   ./deploy.sh status        # 查看服务状态
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT_NAME="eai-prod"
NETWORK_NAME="${PROJECT_NAME}_eai-flow-net"

# Compose 文件列表
COMPOSE_FILES=(
  -f docker-compose.yaml
  -f docker-compose.extensions.yaml
  -f docker-compose.temporal.yaml
  -f docker-compose.ragflow.yaml
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 预检 ──────────────────────────────────────────────────────────────────────
preflight() {
  log_info "=== 环境预检 ==="

  # Docker
  if ! command -v docker &>/dev/null; then
    log_error "Docker 未安装，请先安装 Docker Engine >= 24.0"
    exit 1
  fi
  log_info "Docker 版本: $(docker --version)"

  # Docker Compose
  if ! docker compose version &>/dev/null; then
    log_error "docker compose 插件未安装"
    exit 1
  fi
  log_info "Docker Compose 版本: $(docker compose version)"

  # 磁盘空间
  local available_gb
  available_gb=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
  if [[ "$available_gb" -lt 20 ]]; then
    log_warn "可用磁盘空间不足 20GB（当前 ${available_gb}GB），建议至少保留 40GB"
  else
    log_info "可用磁盘空间: ${available_gb}GB"
  fi

  # 内存
  local total_mem_mb
  total_mem_mb=$(free -m | awk 'NR==2 {print $2}')
  if [[ "$total_mem_mb" -lt 8000 ]]; then
    log_warn "内存不足 8GB（当前 $((total_mem_mb / 1024))GB），建议至少 16GB"
  else
    log_info "内存: $((total_mem_mb / 1024))GB"
  fi

  # 检查必要文件
  local required_files=(
    ".env"
    "config.yaml"
    "extensions_config.json"
  )
  for f in "${required_files[@]}"; do
    if [[ ! -f "$f" ]]; then
      log_error "缺少必要文件: $f"
      log_error "请确保 $f 已创建并正确配置"
      exit 1
    fi
    # 检查是否为目录（Docker 挂载陷阱）
    if [[ -d "$f" ]]; then
      log_error "$f 是一个目录而非文件！Docker 挂载会把目录当成文件挂载导致失败。"
      log_error "请删除 $f 目录，然后创建对应的配置文件。"
      exit 1
    fi
  done

  # 检查 .env 中的关键变量
  source .env
  if [[ "${BETTER_AUTH_SECRET:-}" == "change-me-to-a-random-string" ]]; then
    log_warn "BETTER_AUTH_SECRET 未修改，请使用 openssl rand -base64 32 生成强随机字符串"
  fi
  if [[ "${DEER_FLOW_ROOT:-}" == "/opt/eai-flow-offline" ]]; then
    log_warn "DEER_FLOW_ROOT 使用了默认占位路径 /opt/eai-flow-offline"
    log_warn "请确认这是正确的部署目录，否则修改 .env 中的 DEER_FLOW_ROOT"
  fi
  if [[ -z "${DEER_FLOW_ROOT:-}" ]]; then
    log_error ".env 中 DEER_FLOW_ROOT 未设置"
    exit 1
  fi

  log_info "环境预检通过"
}

# ── 创建必要目录 ──────────────────────────────────────────────────────────────
ensure_dirs() {
  log_info "=== 创建运行时目录 ==="
  mkdir -p data logs skills mcp-server
  log_info "目录已就绪: data/ logs/ skills/ mcp-server/"
}

# ── 创建 Docker 网络 ──────────────────────────────────────────────────────────
ensure_network() {
  if docker network inspect "$NETWORK_NAME" &>/dev/null; then
    log_info "Docker 网络 $NETWORK_NAME 已存在"
  else
    log_info "创建 Docker 网络: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
  fi
}

# ── 启动全部服务 ──────────────────────────────────────────────────────────────
start_all() {
  log_info "=== 启动 EAI-Flow 生产服务 ==="

  local compose_cmd=(
    docker compose -p "$PROJECT_NAME"
    "${CORE_FILES[@]}"
  )

  # Temporal 工作流引擎
  compose_cmd+=(-f docker-compose.temporal.yaml)

  # RAGFlow 知识库（必选）
  compose_cmd+=(-f docker-compose.ragflow.yaml)

  compose_cmd+=(up -d)

  log_info "执行: ${compose_cmd[*]}"
  "${compose_cmd[@]}"

  log_info ""
  log_info "等待服务就绪..."

  # 等待 Gateway 健康检查通过
  local max_wait=120
  local waited=0
  while [[ $waited -lt $max_wait ]]; do
    if curl -sf http://localhost:8001/health &>/dev/null; then
      log_info "Gateway 健康检查通过 (${waited}s)"
      break
    fi
    sleep 5
    waited=$((waited + 5))
  done

  if [[ $waited -ge $max_wait ]]; then
    log_warn "Gateway 启动超时，请检查日志: docker compose -p $PROJECT_NAME logs gateway"
  fi

  # 运行数据库迁移（如有）
  log_info "执行数据库迁移..."
  docker exec prod-eai-flow-gateway python -m app.extensions.workflow.migration 2>&1 | tee -a logs/migration.log || log_warn "迁移执行失败，请检查 logs/migration.log"

  # 初始化管理员账号（首次部署自动创建）
  log_info "初始化管理员账号..."
  local init_result
  init_result=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@eai-flow.com","password":"Admin@2026"}' \
    "http://localhost:${PORT:-4026}/api/v1/auth/initialize" 2>/dev/null || echo "000")
  if [[ "$init_result" == "201" ]]; then
    log_info "管理员已创建: admin@eai-flow.com / Admin@2026"
  elif [[ "$init_result" == "409" ]]; then
    log_info "管理员已存在，跳过初始化"
  else
    log_warn "管理员初始化返回 HTTP $init_result，请手动执行: curl -X POST http://localhost:${PORT:-4026}/api/v1/auth/initialize -H 'Content-Type: application/json' -d '{\"email\":\"admin@eai-flow.com\",\"password\":\"Admin@2026\"}'"
  fi

  log_info ""
  log_info "=========================================="
  log_info "  部署完成！"
  log_info "  访问地址: http://localhost:${PORT:-4026}"
  log_info "  管理员: admin@eai-flow.com / Admin@2026"
  log_info "  ⚠️  首次登录后请立即修改密码！"
  log_info "=========================================="
  log_info ""
  log_info "查看日志: docker compose -p $PROJECT_NAME logs -f"
  log_info "查看状态: ./deploy.sh status"
}

# ── 停止服务 ──────────────────────────────────────────────────────────────────
stop_all() {
  log_info "=== 停止 EAI-Flow 生产服务 ==="
  docker compose -p "$PROJECT_NAME" \
    "${CORE_FILES[@]}" \
    -f docker-compose.temporal.yaml \
    -f docker-compose.ragflow.yaml \
    down "$@"
  log_info "服务已停止"
}

# ── 查看状态 ──────────────────────────────────────────────────────────────────
show_status() {
  log_info "=== EAI-Flow 服务状态 ==="
  docker compose -p "$PROJECT_NAME" \
    -f docker-compose.yaml \
    -f docker-compose.extensions.yaml \
    -f docker-compose.temporal.yaml \
    -f docker-compose.ragflow.yaml \
    ps 2>/dev/null || log_info "服务未运行"
}

# ── 查看日志 ──────────────────────────────────────────────────────────────────
show_logs() {
  docker compose -p "$PROJECT_NAME" \
    -f docker-compose.yaml \
    -f docker-compose.extensions.yaml \
    logs -f --tail=100 "${@:-}"
}

# ── 主入口 ────────────────────────────────────────────────────────────────────

case "${1:-deploy}" in
  deploy|start|up)
    preflight
    ensure_dirs
    ensure_network
    start_all
    ;;
  down|stop)
    stop_all
    ;;
  restart)
    stop_all
    preflight
    ensure_dirs
    ensure_network
    start_all
    ;;
  status|ps)
    show_status
    ;;
  logs)
    shift
    show_logs "$@"
    ;;
  network-create)
    ensure_network
    ;;
  *)
    echo "用法: $0 [deploy|down|restart|status|logs]"
    echo ""
    echo "  deploy         部署全部服务（默认）"
    echo "  down           停止并移除全部服务"
    echo "  restart        重启全部服务"
    echo "  status         查看服务状态"
    echo "  logs [svc]     查看日志（可指定服务名）"
    exit 1
    ;;
esac
