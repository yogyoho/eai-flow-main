# DeerFlow - Unified Development Environment

.PHONY: help config config-upgrade check check-agent-guidance install extension-install extension-list extension-enable extension-disable extension-remove setup doctor support-bundle detect-thread-boundaries detect-blocking-io dev dev-daemon start start-daemon nginx stop up down clean docker-init docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway docker-logs-redis setup-sandbox rebuild-frontend check-frontend-deps

BASH ?= bash
# Detect uv path - prefer uv in PATH, fall back to Windows Python Scripts
UV_PATH := $(shell which uv 2>/dev/null || echo "/mnt/c/Python314/Scripts/uv.exe")
BACKEND_UV_RUN = cd backend && $(UV_PATH) run

# Detect OS for Windows compatibility
ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    PYTHON ?= python
    # Run repo shell scripts through Git Bash when Make is launched from cmd.exe / PowerShell.
    RUN_SHELL_SCRIPT = call scripts\run-with-git-bash.cmd
else
    PYTHON ?= python3
    # Invoke repo shell scripts through an explicit interpreter, so recipes keep
    # working in checkouts that lost the executable bit (zip download,
    # core.fileMode=false, non-POSIX filesystem).
    RUN_SHELL_SCRIPT = $(BASH)
endif

help:
	@echo "DeerFlow Development Commands:"
	@echo "  make setup           - Interactive setup wizard (recommended for new users)"
	@echo "  make doctor          - Check configuration and system requirements"
	@echo "  make support-bundle  - Create a redacted issue summary, AI draft, and evidence bundle"
	@echo "  make config          - Generate local config files (aborts if config already exists)"
	@echo "  make config-upgrade  - Merge new fields from config.example.yaml into config.yaml"
	@echo "  make check           - Check if all required tools are installed"
	@echo "  make detect-thread-boundaries - Inventory async/thread boundary points"
	@echo "  make detect-blocking-io        - Inventory blocking IO that may block the backend event loop"
	@echo "  make install         - Install all dependencies (frontend + backend + pre-commit hooks)"
	@echo "  make extension-install SOURCE=... - Install and enable a trusted Python extension"
	@echo "  make extension-list              - List configured Python extensions"
	@echo "  make extension-enable NAME=...   - Enable an installed extension"
	@echo "  make extension-disable NAME=...  - Disable an extension without uninstalling it"
	@echo "  make extension-remove NAME=...   - Uninstall a managed extension"
	@echo "  make setup-sandbox   - Pre-pull sandbox container image (recommended)"
	@echo "  make dev             - Start all services in development mode (with hot-reloading)"
	@echo "  make dev-daemon      - Start dev services in background (daemon mode)"
	@echo "  make start           - Start all services in production mode (optimized, no hot-reloading)"
	@echo "  make start-daemon    - Start prod services in background (daemon mode)"
	@echo "  make stop            - Stop all running services"
	@echo "  make clean           - Clean up processes and temporary files"
	@echo ""
	@echo "Docker Production Commands:"
	@echo "  make up              - Build and start production Docker services (localhost:4026)"
	@echo "  make up-pro         - Build and start production Docker in Gateway mode (experimental)"
	@echo "  make down            - Stop and remove production Docker containers"
	@echo ""
	@echo "Docker Development Commands:"
	@echo "  make docker-init     - Pull the sandbox image"
	@echo "  make docker-start    - Start Docker services (mode-aware from config.yaml, localhost:4026)"
	@echo "  make docker-start-pro - Start Docker in Gateway mode (experimental, no LangGraph container)"
	@echo "  make docker-stop     - Stop Docker development services"
	@echo "  make docker-logs     - View Docker development logs"
	@echo "  make docker-logs-frontend - View Docker frontend logs"
	@echo "  make docker-logs-gateway - View Docker gateway logs"
	@echo "  make rebuild-frontend - Rebuild frontend image after dependency changes (NOT just restart)"
	@echo "  make check-frontend-deps - Warn if host deps drifted from the frontend container"

## Setup & Diagnosis
setup:
	@$(BACKEND_UV_RUN) python ../scripts/setup_wizard.py

doctor:
	@$(BACKEND_UV_RUN) python ../scripts/doctor.py

support-bundle:
	@$(BACKEND_UV_RUN) python ../scripts/support_bundle.py --include-doctor

detect-thread-boundaries:
	@$(PYTHON) ./scripts/detect_thread_boundaries.py

detect-blocking-io:
	@$(MAKE) -C backend detect-blocking-io

# 上游同步后检查：同步的文件是否引用了未同步的缺失模块（部分同步残留）。
# 用法：每次 `git pull` 上游 / 批量同步后跑 `make sync-check`，0=一致。
sync-check:
	@$(PYTHON) ./scripts/check_import_consistency.py

config:
	@$(PYTHON) ./scripts/configure.py

config-upgrade:
	@$(RUN_SHELL_SCRIPT) ./scripts/config-upgrade.sh

# Check required tools
check:
	@$(PYTHON) ./scripts/check.py

# Install all dependencies
install:
	@echo "Installing backend dependencies..."
	@cd backend && uv sync --locked
	@echo "Installing frontend dependencies..."
	@cd frontend && pnpm install
	@echo "Installing pre-commit hooks..."
	@$(BACKEND_UV_RUN) --with pre-commit pre-commit install
	@echo "✓ All dependencies installed"
	@echo ""
	@echo "=========================================="
	@echo "  Optional: Pre-pull Sandbox Image"
	@echo "=========================================="
	@echo ""
	@echo "If you plan to use Docker/Container-based sandbox, you can pre-pull the image:"
	@echo "  make setup-sandbox"
	@echo ""

# Managed Python extensions (upstream #4780). Values travel via hidden env
# options so command-line arguments never reach a shell recipe verbatim.
extension-install: export DEER_FLOW_EXTENSION_SOURCE := $(value SOURCE)
extension-install:
	$(if $(and $(filter command line,$(origin SOURCE)),$(strip $(value SOURCE))),,$(error usage: make extension-install SOURCE=<package|git-url|dir>))
	@cd backend && uv run --frozen --no-group extensions deerflow extensions install --source-env __deerflow_extension_source__

extension-list:
	@cd backend && uv run --frozen --no-group extensions deerflow extensions list

extension-enable: export DEER_FLOW_EXTENSION_NAME := $(value NAME)
extension-enable:
	$(if $(and $(filter command line,$(origin NAME)),$(strip $(value NAME))),,$(error usage: make extension-enable NAME=<extension>))
	@cd backend && uv run --frozen --no-group extensions deerflow extensions enable --name-env __deerflow_extension_name__

extension-disable: export DEER_FLOW_EXTENSION_NAME := $(value NAME)
extension-disable:
	$(if $(and $(filter command line,$(origin NAME)),$(strip $(value NAME))),,$(error usage: make extension-disable NAME=<extension>))
	@cd backend && uv run --frozen --no-group extensions deerflow extensions disable --name-env __deerflow_extension_name__

extension-remove: export DEER_FLOW_EXTENSION_NAME := $(value NAME)
extension-remove:
	$(if $(and $(filter command line,$(origin NAME)),$(strip $(value NAME))),,$(error usage: make extension-remove NAME=<extension>))
	@cd backend && uv run --frozen --no-group extensions deerflow extensions remove --name-env __deerflow_extension_name__

# Pre-pull sandbox Docker image (optional but recommended)
setup-sandbox:
	@$(RUN_SHELL_SCRIPT) ./scripts/setup-sandbox.sh

# Start all services in development mode (with hot-reloading)
dev:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_SHELL_SCRIPT) ./scripts/serve.sh --dev

# Start all services in production mode (with optimizations).
# SKIP_FRONTEND_BUILD=1 reuses the existing frontend build instead of running
# `next build`; see scripts/serve.sh --skip-frontend-build.
start:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_SHELL_SCRIPT) ./scripts/serve.sh --prod $(if $(filter 1,$(SKIP_FRONTEND_BUILD)),--skip-frontend-build)

# Start all services in daemon mode (background)
dev-daemon:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_SHELL_SCRIPT) ./scripts/serve.sh --dev --daemon

# Start prod services in daemon mode (background)
start-daemon:
	@$(PYTHON) ./scripts/check.py
	@$(RUN_SHELL_SCRIPT) ./scripts/serve.sh --prod --daemon $(if $(filter 1,$(SKIP_FRONTEND_BUILD)),--skip-frontend-build)

# Stop all services
stop:
	@$(RUN_SHELL_SCRIPT) ./scripts/serve.sh --stop

# Clean up
clean: stop
	@echo "Cleaning up..."
	@-rm -rf backend/.deer-flow 2>/dev/null || true
	@-rm -rf backend/.langgraph_api 2>/dev/null || true
	@-rm -rf logs/*.log 2>/dev/null || true
	@echo "✓ Cleanup complete"

# ==========================================
# Docker Development Commands
# ==========================================

# Initialize Docker containers and install dependencies
docker-init:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh init

# Start Docker development environment
docker-start:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh start

# Stop Docker development environment
docker-stop:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh stop

# View Docker development logs
docker-logs:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh logs

# View Docker development logs
docker-logs-frontend:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh logs --frontend
docker-logs-gateway:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh logs --gateway

# Rebuild the frontend image after dependency changes (package.json / pnpm-lock.yaml).
# The dev container's node_modules is image-baked (NOT bind-mounted, since host=Windows
# and container=Linux), so a plain `restart`/`up` will NOT pick up dependency changes.
# EAI-CUSTOM (bug-1278): docker.sh has no rebuild-frontend subcommand — this target is
# currently BROKEN; manual path is `cd docker && docker compose -p eai-docker
# -f docker-compose-dev.yaml build frontend && ... up -d frontend`.
rebuild-frontend:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh rebuild-frontend

# Warn if host frontend/pnpm-lock.yaml differs from the deps baked into the running
# frontend container. Prevents silent regressions (e.g. BlockNote duplicate-selection crash).
check-frontend-deps:
	@$(RUN_SHELL_SCRIPT) ./scripts/docker.sh check-frontend-deps

# ==========================================
# Production Docker Commands
# ==========================================

# Build and start production services
up:
	@$(RUN_SHELL_SCRIPT) ./scripts/deploy.sh

# Stop and remove production containers
down:
	@$(RUN_SHELL_SCRIPT) ./scripts/deploy.sh down
