#!/usr/bin/env bash
#
# serve.sh — Unified DeerFlow service launcher
#
# Usage:
#   ./scripts/serve.sh [--dev|--prod] [--gateway] [--daemon] [--stop|--restart]
#
# Modes:
#   --dev       Development mode with hot-reload (default)
#   --prod      Production mode, pre-built frontend, no hot-reload
#   --gateway   Gateway mode (experimental): skip LangGraph server,
#               agent runtime embedded in Gateway API
#   --daemon    Run all services in background (nohup), exit after startup
#
# Actions:
#   --skip-install  Skip dependency installation (faster restart)
#   --stop      Stop all running services and exit
#   --restart   Stop all services, then start with the given mode flags
#
# Examples:
#   ./scripts/serve.sh --dev                 # Standard dev (4 processes)
#   ./scripts/serve.sh --dev --gateway       # Gateway dev  (3 processes)
#   ./scripts/serve.sh --prod --gateway      # Gateway prod (3 processes)
#   ./scripts/serve.sh --dev --daemon        # Standard dev, background
#   ./scripts/serve.sh --dev --gateway --daemon  # Gateway dev, background
#   ./scripts/serve.sh --stop                # Stop all services
#   ./scripts/serve.sh --restart --dev --gateway # Restart in gateway mode
#
# Must be run from the repo root directory.

set -e

# Keep child processes alive after shell exits (important for Windows MSYS2/Git Bash)
trap '' HUP
# Enable job control so background processes work properly
set -m

REPO_ROOT="$(builtin cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
cd "$REPO_ROOT"

# ── Find nginx (handles Windows Git Bash with WinGet nginx) ───────────────────
find_nginx() {
    # Try normal nginx first
    if command -v nginx >/dev/null 2>&1; then
        echo "nginx"
        return 0
    fi
    # Try nginx.exe
    if command -v nginx.exe >/dev/null 2>&1; then
        echo "nginx.exe"
        return 0
    fi
    # On Windows Git Bash, check WinGet Links
    if [ -f "/mnt/c/Users/admin/AppData/Local/Microsoft/WinGet/Links/nginx.exe" ]; then
        echo "/mnt/c/Users/admin/AppData/Local/Microsoft/WinGet/Links/nginx.exe"
        return 0
    fi
    # Check D:\nginx-1.19.1 (common Windows installation)
    if [ -f "/mnt/d/nginx-1.19.1/nginx.exe" ]; then
        echo "/mnt/d/nginx-1.19.1/nginx.exe"
        return 0
    fi
    # Check C:\nginx (common Windows installation)
    if [ -f "/mnt/c/nginx/nginx.exe" ]; then
        echo "/mnt/c/nginx/nginx.exe"
        return 0
    fi
    return 1
}

NGINX_CMD="$(find_nginx)"
if [ -z "$NGINX_CMD" ]; then
    echo "Error: nginx not found. Please install nginx."
    echo "  Windows: winget install freenginx.nginx"
    echo "  macOS:   brew install nginx"
    echo "  Ubuntu:  sudo apt install nginx"
    exit 1
fi

# On Windows (MSYS2/Git Bash), nginx needs Windows-style paths to avoid MSYS2 path mangling.
# Convert /mnt/d/... → D:\... and /d/... → D:\... for the nginx config and prefix paths.
if [ -d /mnt/c ]; then
    _to_windows_path() {
        local p="$1"
        # /mnt/d/... → D:\...  or  /d/... → D:\... (any drive letter, uppercased)
        local d=$(echo "$p" | sed 's|/mnt/||' | cut -c1 | tr '[:lower:]' '[:upper:]')
        echo "$p" | sed "s|/mnt/[^/]*|$d:|" | sed 's|/|\\|g'
    }
    _NGINX_CONF=$(_to_windows_path "$REPO_ROOT/docker/nginx/nginx.local.conf")
    _NGINX_PREFIX=$(_to_windows_path "$REPO_ROOT")
    _NGINX_LOG="'$_NGINX_PREFIX\\logs'"
else
    _NGINX_CONF="$REPO_ROOT/docker/nginx/nginx.local.conf"
    _NGINX_PREFIX="$REPO_ROOT"
    _NGINX_LOG="logs"
fi
export NGINX_CMD

# ── Find uv (handles Windows Git Bash with Python Scripts uv) ───────────────────
find_uv() {
    # Try normal uv first
    if command -v uv >/dev/null 2>&1; then
        echo "uv"
        return 0
    fi
    # Check C:\Python314\Scripts\uv.exe (Windows Python uv)
    if [ -f "/mnt/c/Python314/Scripts/uv.exe" ]; then
        echo "/mnt/c/Python314/Scripts/uv.exe"
        return 0
    fi
    # Check other common Python Script paths
    for pyver in 312 313 314; do
        if [ -f "/mnt/c/Python${pyver}/Scripts/uv.exe" ]; then
            echo "/mnt/c/Python${pyver}/Scripts/uv.exe"
            return 0
        fi
    done
    return 1
}

UV_CMD="$(find_uv)"
if [ -z "$UV_CMD" ]; then
    echo "Error: uv not found. Please install uv."
    echo "  Visit: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi
export UV_CMD

# ── Load .env ────────────────────────────────────────────────────────────────

if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

# ── Argument parsing ─────────────────────────────────────────────────────────

DEV_MODE=true
GATEWAY_MODE=false
DAEMON_MODE=false
SKIP_INSTALL=false
ACTION="start"   # start | stop | restart

for arg in "$@"; do
    case "$arg" in
        --dev)     DEV_MODE=true ;;
        --prod)    DEV_MODE=false ;;
        --gateway) GATEWAY_MODE=true ;;
        --daemon)  DAEMON_MODE=true ;;
        --skip-install) SKIP_INSTALL=true ;;
        --stop)    ACTION="stop" ;;
        --restart) ACTION="restart" ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--dev|--prod] [--gateway] [--daemon] [--skip-install] [--stop|--restart]"
            exit 1
            ;;
    esac
done

# ── Stop helper ──────────────────────────────────────────────────────────────

_kill_port() {
    local port=$1
    local pid
    pid=$(lsof -ti :"$port" 2>/dev/null) || true
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null || true
    fi
}

stop_all() {
    echo "Stopping all services..."
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    nginx -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" -s quit 2>/dev/null || true
    sleep 1
    pkill -9 nginx 2>/dev/null || true
    # Force-kill any survivors still holding the service ports
    _kill_port 4024
    _kill_port 4001
    _kill_port 4000
    ./scripts/cleanup-containers.sh deer-flow-sandbox 2>/dev/null || true
    echo "✓ All services stopped"
}

# ── Action routing ───────────────────────────────────────────────────────────

if [ "$ACTION" = "stop" ]; then
    stop_all
    exit 0
fi

ALREADY_STOPPED=false
if [ "$ACTION" = "restart" ]; then
    stop_all
    sleep 1
    ALREADY_STOPPED=true
fi

# ── Derive runtime flags ────────────────────────────────────────────────────

if $GATEWAY_MODE; then
    export SKIP_LANGGRAPH_SERVER=1
fi

# Mode label for banner
if $DEV_MODE && $GATEWAY_MODE; then
    MODE_LABEL="DEV + GATEWAY (experimental)"
elif $DEV_MODE; then
    MODE_LABEL="DEV (hot-reload enabled)"
elif $GATEWAY_MODE; then
    MODE_LABEL="PROD + GATEWAY (experimental)"
else
    MODE_LABEL="PROD (optimized)"
fi

if $DAEMON_MODE; then
    MODE_LABEL="$MODE_LABEL [daemon]"
fi

# Frontend command (wraps sh with node.exe in PATH for MSYS2/Git Bash on Windows)
# On Windows (detected by MSYS2/Git Bash environment), frontend commands must be run via
# PowerShell because MSYS2 bash cannot resolve "C:\Program Files\nodejs\node.exe" for
# npm/pnpm (the space in the path causes MSYS2 path conversion to fail).
# We write the frontend startup command to a temp .ps1 file and execute it.
if grep -q "MSYS" <<< "$MSYSTEM" 2>/dev/null || [ -d /mnt/c ]; then
    _IS_WINDOWS=true
else
    _IS_WINDOWS=false
fi

if $_IS_WINDOWS; then
    # On Windows, use a .bat launcher with `start ""` to detach PowerShell from the bash process.
    # Directly calling `powershell.exe` via `sh -c` gets killed when the shell exits.
    _BAT_FILE="$REPO_ROOT/scripts/frontend-start.bat"
    if command -v python3 >/dev/null 2>&1; then
        _PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        _PYTHON_BIN="python"
    fi
    if $DEV_MODE; then
        FRONTEND_CMD="$_BAT_FILE"
    else
        _SECRET=$($_PYTHON_BIN -c 'import secrets; print(secrets.token_hex(16))')
        # Dynamically rewrite the .bat file to include the secret for preview mode
        cat <<BATEOF > "$_BAT_FILE"
@echo off
setlocal
set BETTER_AUTH_SECRET=$_SECRET
set PORT=4000
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$REPO_ROOT/scripts/frontend-startup.ps1" -Mode preview -Secret "%BETTER_AUTH_SECRET%"
endlocal
BATEOF
        FRONTEND_CMD="$_BAT_FILE"
    fi
else
    if $DEV_MODE; then
        FRONTEND_CMD="cd frontend && PORT=4000 pnpm run dev"
    else
        if command -v python3 >/dev/null 2>&1; then
            _PYTHON_BIN="python3"
        elif command -v python >/dev/null 2>&1; then
            _PYTHON_BIN="python"
        fi
        FRONTEND_CMD="cd frontend && env BETTER_AUTH_SECRET=$($_PYTHON_BIN -c 'import secrets; print(secrets.token_hex(16))') PORT=4000 pnpm run preview"
    fi
fi

# Extra flags for uvicorn/langgraph
LANGGRAPH_EXTRA_FLAGS="--no-reload"
if $DEV_MODE && ! $DAEMON_MODE; then
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env' --reload-exclude='*.pyc' --reload-exclude='__pycache__' --reload-exclude='sandbox/' --reload-exclude='.deer-flow/'"
else
    GATEWAY_EXTRA_FLAGS=""
fi

# ── Stop existing services (skip if restart already did it) ──────────────────

if ! $ALREADY_STOPPED; then
    stop_all
    sleep 1
fi

# ── Config check ─────────────────────────────────────────────────────────────

if ! { \
        [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ] || \
        [ -f backend/config.yaml ] || \
        [ -f config.yaml ]; \
    }; then
    echo "✗ No DeerFlow config file found."
    echo "  Run 'make setup' (recommended) or 'make config' to generate config.yaml."
    exit 1
fi

"$REPO_ROOT/scripts/config-upgrade.sh"

# ── Install dependencies ────────────────────────────────────────────────────

if ! $SKIP_INSTALL; then
    echo "Syncing dependencies..."
    (cd backend && $UV_CMD sync --quiet) || { echo "✗ Backend dependency install failed"; exit 1; }
    (cd frontend && pnpm install --silent) || { echo "✗ Frontend dependency install failed"; exit 1; }
    echo "✓ Dependencies synced"
else
    echo "⏩ Skipping dependency install (--skip-install)"
fi

# ── Sync frontend .env.local ─────────────────────────────────────────────────
# Next.js .env.local takes precedence over process env vars.
# The script manages the NEXT_PUBLIC_LANGGRAPH_BASE_URL line to ensure
# the frontend routes match the active backend mode.

FRONTEND_ENV_LOCAL="$REPO_ROOT/frontend/.env.local"
ENV_KEY="NEXT_PUBLIC_LANGGRAPH_BASE_URL"

sync_frontend_env() {
    if $GATEWAY_MODE; then
        # Point frontend to Gateway's compat API
        if [ -f "$FRONTEND_ENV_LOCAL" ] && grep -q "^${ENV_KEY}=" "$FRONTEND_ENV_LOCAL"; then
            sed -i.bak "s|^${ENV_KEY}=.*|${ENV_KEY}=/api/langgraph-compat|" "$FRONTEND_ENV_LOCAL" && rm -f "${FRONTEND_ENV_LOCAL}.bak"
        else
            echo "${ENV_KEY}=/api/langgraph-compat" >> "$FRONTEND_ENV_LOCAL"
        fi
    else
        # Remove override — frontend falls back to /api/langgraph (standard)
        if [ -f "$FRONTEND_ENV_LOCAL" ] && grep -q "^${ENV_KEY}=" "$FRONTEND_ENV_LOCAL"; then
            sed -i.bak "/^${ENV_KEY}=/d" "$FRONTEND_ENV_LOCAL" && rm -f "${FRONTEND_ENV_LOCAL}.bak"
        fi
    fi
}

sync_frontend_env

# ── Banner ───────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  Starting DeerFlow"
echo "=========================================="
echo ""
echo "  Mode: $MODE_LABEL"
echo ""
echo "  Services:"
if ! $GATEWAY_MODE; then
    echo "    LangGraph   → localhost:4024  (agent runtime)"
fi
echo "    Gateway     → localhost:4001  (REST API$(if $GATEWAY_MODE; then echo " + agent runtime"; fi))"
echo "    Frontend    → localhost:4000  (Next.js)"
echo "    Nginx       → localhost:4026  (reverse proxy)"
echo ""

# ── Cleanup handler ──────────────────────────────────────────────────────────

cleanup() {
    trap - INT TERM
    echo ""
    stop_all
    exit 0
}

trap cleanup INT TERM

# ── Helper: start a service ──────────────────────────────────────────────────

# run_service NAME COMMAND PORT TIMEOUT
# In daemon mode, wraps with nohup. Waits for port to be ready.
run_service() {
    local name="$1" cmd="$2" port="$3" timeout="$4"

    echo "Starting $name..."
    if $DAEMON_MODE; then
        nohup sh -c "$cmd" > /dev/null 2>&1 &
    else
        sh -c "$cmd" &
    fi

    ./scripts/wait-for-port.sh "$port" "$timeout" "$name" || {
        local logfile="logs/$(echo "$name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-').log"
        echo "✗ $name failed to start."
        [ -f "$logfile" ] && tail -20 "$logfile"
        cleanup
    }
    echo "✓ $name started on localhost:$port"
}

# ── Start services ───────────────────────────────────────────────────────────

mkdir -p logs
mkdir -p temp/client_body_temp temp/proxy_temp temp/fastcgi_temp temp/uwsgi_temp temp/scgi_temp

# 1. LangGraph (skip in gateway mode)
if ! $GATEWAY_MODE; then
    CONFIG_LOG_LEVEL=$(grep -m1 '^log_level:' config.yaml 2>/dev/null | awk '{print $2}' | tr -d ' ')
    LANGGRAPH_LOG_LEVEL="${LANGGRAPH_LOG_LEVEL:-${CONFIG_LOG_LEVEL:-info}}"
    LANGGRAPH_JOBS_PER_WORKER="${LANGGRAPH_JOBS_PER_WORKER:-10}"
    # On Windows, allow blocking calls (blockbuster intercepts os.unlink on SQLite)
    if [ -d /mnt/c ]; then
        LANGGRAPH_ALLOW_BLOCKING="${LANGGRAPH_ALLOW_BLOCKING:-1}"
    else
        LANGGRAPH_ALLOW_BLOCKING="${LANGGRAPH_ALLOW_BLOCKING:-0}"
    fi
    LANGGRAPH_ALLOW_BLOCKING_FLAG=""
    if [ "$LANGGRAPH_ALLOW_BLOCKING" = "1" ]; then
        LANGGRAPH_ALLOW_BLOCKING_FLAG="--allow-blocking"
    fi
    run_service "LangGraph" \
        "cd backend && NO_COLOR=1 CLICOLOR=0 CLICOLOR_FORCE=0 PY_COLORS=0 TERM=dumb $UV_CMD run langgraph dev --no-browser --port 4024 $LANGGRAPH_ALLOW_BLOCKING_FLAG --n-jobs-per-worker $LANGGRAPH_JOBS_PER_WORKER --server-log-level $LANGGRAPH_LOG_LEVEL $LANGGRAPH_EXTRA_FLAGS 2>&1 | perl -pe 's/\e\[[0-9;]*[[:alpha:]]//g' > ../logs/langgraph.log" \
        4024 60
else
    echo "⏩ Skipping LangGraph (Gateway mode — runtime embedded in Gateway)"
fi

# 2. Gateway API
run_service "Gateway" \
    "cd backend && PYTHONPATH=. $UV_CMD run uvicorn app.gateway.app:app --host 0.0.0.0 --port 4001 $GATEWAY_EXTRA_FLAGS > ../logs/gateway.log 2>&1" \
    4001 30

# 3. Frontend
run_service "Frontend" \
    "cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1" \
    4000 120

# 4. Nginx
# Note: nginx log output goes to its configured error/access logs in the prefix directory.
run_service "Nginx" \
    "$NGINX_CMD -g 'daemon off;' -c '$_NGINX_CONF' -p '$_NGINX_PREFIX'" \
    4026 10

# ── Ready ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  ✓ DeerFlow is running!  [$MODE_LABEL]"
echo "=========================================="
echo ""
echo "  🌐 http://localhost:4026"
echo ""
if $GATEWAY_MODE; then
    echo "  Routing: Frontend → Nginx → Gateway (embedded runtime)"
    echo "  API:     /api/langgraph-compat/*  →  Gateway agent runtime"
else
    echo "  Routing: Frontend → Nginx → LangGraph + Gateway"
    echo "  API:     /api/langgraph/*  →  LangGraph server (4024)"
fi
echo "           /api/*              →  Gateway REST API (4001)"
echo ""
echo "  📋 Logs: logs/{langgraph,gateway,frontend,nginx}.log"
echo ""

if $DAEMON_MODE; then
    echo "  🛑 Stop: make stop"
    # Detach — trap is no longer needed
    trap - INT TERM
else
    echo "  Press Ctrl+C to stop all services"
    wait
fi
