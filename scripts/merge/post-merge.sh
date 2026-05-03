#!/usr/bin/env bash
# =============================================================================
# post-merge.sh — Merge 后恢复与验证
#
# 用法:
#   ./scripts/merge/post-merge.sh [options]
#
# Options:
#   --skip-restore    跳过 keep-local 文件恢复 (merge 无冲突时)
#   --skip-install    跳过依赖安装
#   --skip-test       跳过测试验证
#   --skip-docker     跳过 Docker 启动验证
#   --docker-only     仅执行 Docker 启动和健康检查
#
# 功能:
#   1. 恢复 keep-local 文件 (从 .merge-backup/)
#   2. 安装依赖 (backend + frontend)
#   3. 运行 lint + test
#   4. Docker 启动 + 健康检查 (可选)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/merge-rules.env"

REPO_ROOT="$(git rev-parse --show-toplevel)"

SKIP_RESTORE=false
SKIP_INSTALL=false
SKIP_TEST=false
SKIP_DOCKER=true   # Docker 默认不启动 (耗时且需要用户确认)
DOCKER_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-restore) SKIP_RESTORE=true; shift ;;
        --skip-install) SKIP_INSTALL=true; shift ;;
        --skip-test)    SKIP_TEST=true; shift ;;
        --skip-docker)  SKIP_DOCKER=true; shift ;;
        --with-docker)  SKIP_DOCKER=false; shift ;;
        --docker-only)  DOCKER_ONLY=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

_check_pass() {
    echo -e "  ${GREEN}✓ PASS${NC} $1"
    ((PASS_COUNT++)) || true
}

_check_fail() {
    echo -e "  ${RED}✗ FAIL${NC} $1"
    ((FAIL_COUNT++)) || true
}

echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Post-Merge 验证${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# ===========================================================================
# Step 1: 恢复 keep-local 文件
# ===========================================================================
if [[ "$DOCKER_ONLY" == "false" ]]; then
    echo -e "${CYAN}[Step 1/4]${NC} 恢复 keep-local 文件..."
    if [[ "$SKIP_RESTORE" == "true" ]]; then
        echo "  (已跳过)"
    else
        restore_keep_local
        # 将恢复的文件添加到 git
        echo ""
        echo "  将恢复的文件添加到暂存区..."
        while IFS= read -r f; do
            git add "$f" 2>/dev/null || true
        done < <(list_keep_local_files)
        echo -e "  ${GREEN}✓${NC} 恢复完成"
    fi
    echo ""

    # ===========================================================================
    # Step 2: 安装依赖
    # ===========================================================================
    echo -e "${CYAN}[Step 2/4]${NC} 安装依赖..."
    if [[ "$SKIP_INSTALL" == "true" ]]; then
        echo "  (已跳过)"
    else
        # Backend
        echo "  Backend: uv sync..."
        if (cd "${REPO_ROOT}/backend" && uv sync --group dev --quiet 2>&1 | tail -3); then
            _check_pass "backend: uv sync"
        else
            _check_fail "backend: uv sync"
        fi

        # Frontend
        echo "  Frontend: pnpm install..."
        if (cd "${REPO_ROOT}/frontend" && pnpm install --frozen-lockfile 2>&1 | tail -3); then
            _check_pass "frontend: pnpm install"
        else
            _check_fail "frontend: pnpm install"
        fi
    fi
    echo ""

    # ===========================================================================
    # Step 3: 代码验证
    # ===========================================================================
    echo -e "${CYAN}[Step 3/4]${NC} 代码验证..."
    if [[ "$SKIP_TEST" == "true" ]]; then
        echo "  (已跳过)"
    else
        # Backend lint
        echo "  Backend: ruff check..."
        if (cd "${REPO_ROOT}/backend" && ruff check . 2>&1 | tail -5); then
            _check_pass "backend: lint"
        else
            _check_fail "backend: lint"
        fi

        # Backend test
        echo "  Backend: pytest..."
        if (cd "${REPO_ROOT}/backend" && PYTHONPATH=. uv run pytest tests/ -q --tb=short 2>&1 | tail -10); then
            _check_pass "backend: tests"
        else
            _check_fail "backend: tests"
        fi

        # Harness boundary
        echo "  Backend: harness boundary..."
        if (cd "${REPO_ROOT}/backend" && PYTHONPATH=. uv run pytest tests/test_harness_boundary.py -q 2>&1 | tail -5); then
            _check_pass "backend: harness boundary"
        else
            _check_fail "backend: harness boundary"
        fi

        # Frontend lint
        echo "  Frontend: eslint..."
        if (cd "${REPO_ROOT}/frontend" && pnpm lint 2>&1 | tail -5); then
            _check_pass "frontend: lint"
        else
            _check_fail "frontend: lint"
        fi

        # Frontend typecheck
        echo "  Frontend: typecheck..."
        if (cd "${REPO_ROOT}/frontend" && pnpm typecheck 2>&1 | tail -10); then
            _check_pass "frontend: typecheck"
        else
            _check_fail "frontend: typecheck (pre-existing errors may exist)"
        fi
    fi
    echo ""
fi

# ===========================================================================
# Step 4: Docker 验证 (可选)
# ===========================================================================
echo -e "${CYAN}[Step 4/4]${NC} Docker 验证..."

DOCKER_STARTED=false

docker_health_check() {
    local url="$1"
    local desc="$2"
    if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

if [[ "$SKIP_DOCKER" == "true" ]]; then
    echo "  (已跳过 — 使用 --with-docker 启用 Docker 验证)"
else
    echo ""
    echo "  启动 Docker 服务..."
    if (cd "${REPO_ROOT}" && make docker-stop 2>&1 | tail -3); then
        echo "  已停止旧容器"
    fi

    if (cd "${REPO_ROOT}" && make docker-start 2>&1 | tail -10); then
        echo ""
        echo "  等待服务就绪 (最多 60s)..."
        for i in $(seq 1 30); do
            if docker_health_check "http://localhost:2026/health" "Gateway"; then
                break
            fi
            sleep 2
            echo -n "."
        done
        echo ""

        # 健康检查
        if docker_health_check "http://localhost:2026/health" "Gateway"; then
            _check_pass "Gateway health: /health"
        else
            _check_fail "Gateway health: /health"
        fi

        if docker_health_check "http://localhost:2026/" "Frontend"; then
            _check_pass "Frontend: /"
        else
            _check_fail "Frontend: /"
        fi

        if docker_health_check "http://localhost:2026/api/langgraph/info" "LangGraph"; then
            _check_pass "LangGraph: /api/langgraph/info"
        else
            _check_fail "LangGraph: /api/langgraph/info"
        fi

        # 扩展 API 验证 (可能需要登录, 仅检查路由可达)
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:2026/api/extensions/users/me" 2>/dev/null || echo "000")
        if [[ "$HTTP_CODE" != "000" ]]; then
            echo -e "  ${GREEN}✓${NC}  Extensions API 可达 (HTTP ${HTTP_CODE})"
        else
            echo -e "  ${YELLOW}⚠${NC}  Extensions API 不可达 (可能需要启动完整服务)"
        fi

        DOCKER_STARTED=true
    else
        _check_fail "Docker 启动失败"
    fi
fi
echo ""

# ===========================================================================
# 最终报告
# ===========================================================================
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  验证结果${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}PASS: ${PASS_COUNT}${NC}"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo -e "  ${RED}FAIL: ${FAIL_COUNT}${NC}"
fi
echo ""

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    echo -e "${YELLOW}存在失败项，请检查上述输出。${NC}"
    echo ""
    echo -e "常见问题排查:"
    echo -e "  ${BOLD}502 Bad Gateway${NC} → 检查 nginx proxy_pass 目标服务名"
    echo -e "  ${BOLD}401/403${NC}       → 检查 auth middleware 桥接逻辑"
    echo -e "  ${BOLD}RangeError${NC}    → 检查日期字段是否返回空字符串"
    echo -e "  ${BOLD}MCP 加载失败${NC}  → 检查 extensions_config.json 中 server 路径"
    echo ""
    echo -e "详细排查见: ${BOLD}docs/CODE_MERGE_GUIDE.md${NC} 第七章"
    exit 1
fi

echo -e "${GREEN}${BOLD}所有验证通过！${NC}"
echo ""

if [[ "$DOCKER_STARTED" == "true" ]]; then
    echo "Docker 服务运行中: http://localhost:2026"
    echo "停止服务: make docker-stop"
fi

if [[ "$DOCKER_ONLY" == "false" ]]; then
    echo ""
    echo -e "下一步:"
    echo -e "  ${BOLD}git push origin ${CURRENT_BRANCH:-merge-2.0-rc}${NC}"
fi
