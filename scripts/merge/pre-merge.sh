#!/usr/bin/env bash
# =============================================================================
# pre-merge.sh — Merge 前分析与准备
#
# 用法:
#   ./scripts/merge/pre-merge.sh [upstream-remote] [upstream-branch]
#
# 默认:
#   upstream-remote = bytedance
#   upstream-branch = main
#
# 功能:
#   1. 拉取 upstream 最新代码
#   2. 列出 upstream 新增 commit 和变更文件
#   3. 按 keep-local / accept-upstream / manual-merge 分类统计
#   4. 备份所有 keep-local 文件到 .merge-backup/
#   5. 输出 merge 影响报告
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/merge-rules.env"

UPSTREAM_REMOTE="${1:-bytedance}"
UPSTREAM_BRANCH="${2:-main}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Step 1: 确认环境
# ---------------------------------------------------------------------------
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Pre-Merge 分析 — 准备从 ${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH} 合并${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${CYAN}[Step 1/5]${NC} 检查环境..."

# 确认当前分支
CURRENT_BRANCH="$(git branch --show-current)"
echo "  当前分支: ${CURRENT_BRANCH}"

# 确认无未提交修改
if ! git diff --quiet 2>/dev/null; then
    echo -e "  ${RED}[WARN]${NC} 工作区有未提交的修改:"
    git diff --name-only
    echo ""
    echo "  建议先提交或 stash 这些修改。是否继续? (y/N)"
    read -r answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        echo "  已取消。"
        exit 1
    fi
fi

if ! git diff --cached --quiet 2>/dev/null; then
    echo -e "  ${RED}[WARN]${NC} 暂存区有未提交的文件:"
    git diff --cached --name-only
    echo ""
    echo "  建议先提交。是否继续? (y/N)"
    read -r answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        echo "  已取消。"
        exit 1
    fi
fi

# 确认 upstream remote 存在
if ! git remote get-url "$UPSTREAM_REMOTE" &>/dev/null; then
    echo -e "  ${RED}[ERROR]${NC} Upstream remote '${UPSTREAM_REMOTE}' 不存在。"
    echo "  可用的 remote:"
    git remote -v
    echo ""
    echo "  用法: $0 [upstream-remote] [upstream-branch]"
    exit 1
fi
echo -e "  Upstream: ${GREEN}$(git remote get-url "$UPSTREAM_REMOTE")${NC}"
echo ""

# ---------------------------------------------------------------------------
# Step 2: 拉取 upstream
# ---------------------------------------------------------------------------
echo -e "${CYAN}[Step 2/5]${NC} 拉取 upstream 最新代码..."
git fetch "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH"
echo ""

# ---------------------------------------------------------------------------
# Step 3: 分析 upstream 变更
# ---------------------------------------------------------------------------
echo -e "${CYAN}[Step 3/5]${NC} 分析 upstream 变更..."

# 新增 commit 数
COMMIT_COUNT=$(git rev-list --count "${CURRENT_BRANCH}..${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}" 2>/dev/null || echo "0")
echo -e "  新增 commit: ${BOLD}${COMMIT_COUNT}${NC}"

# 显示 commit 列表
if [[ "$COMMIT_COUNT" -gt 0 ]]; then
    echo ""
    echo -e "  ${BOLD}Commit 列表:${NC}"
    git log --oneline --no-decorate "${CURRENT_BRANCH}..${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}"
    echo ""
fi

# 变更文件统计
echo -e "  ${BOLD}变更文件统计:${NC}"
git diff --stat "${CURRENT_BRANCH}...${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}" 2>/dev/null | tail -1
echo ""

# ---------------------------------------------------------------------------
# Step 4: 按规则分类变更文件
# ---------------------------------------------------------------------------
echo -e "${CYAN}[Step 4/5]${NC} 按规则分类变更文件..."

CHANGED_FILES=$(git diff --name-only "${CURRENT_BRANCH}...${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}" 2>/dev/null || echo "")

declare -a KEEP_LOCAL_FILES=()
declare -a ACCEPT_UPSTREAM_FILES=()
declare -a MANUAL_MERGE_FILES=()

while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    category=$(classify_file "$file")
    case "$category" in
        keep-local)
            KEEP_LOCAL_FILES+=("$file")
            ;;
        accept-upstream)
            ACCEPT_UPSTREAM_FILES+=("$file")
            ;;
        manual-merge)
            MANUAL_MERGE_FILES+=("$file")
            ;;
    esac
done <<< "$CHANGED_FILES"

# 输出分类报告
echo ""
echo -e "  ${GREEN}▌ keep-local${NC}      — 冲突时自动保留本地 (${#KEEP_LOCAL_FILES[@]} files)"
echo -e "  ${BLUE}▌ accept-upstream${NC} — 冲突时自动接受 upstream (${#ACCEPT_UPSTREAM_FILES[@]} files)"
echo -e "  ${YELLOW}▌ manual-merge${NC}    — 需人工处理 (${#MANUAL_MERGE_FILES[@]} files)"

# 详细列表
if [[ ${#KEEP_LOCAL_FILES[@]} -gt 0 ]]; then
    echo ""
    echo -e "  ${GREEN}${BOLD}[keep-local]${NC} 以下文件冲突时将自动保留本地版本:"
    for f in "${KEEP_LOCAL_FILES[@]}"; do
        echo -e "    ${GREEN}✓${NC} $f"
    done
fi

if [[ ${#ACCEPT_UPSTREAM_FILES[@]} -gt 0 ]]; then
    echo ""
    echo -e "  ${BLUE}${BOLD}[accept-upstream]${NC} 以下文件冲突时将自动接受 upstream:"
    for f in "${ACCEPT_UPSTREAM_FILES[@]}"; do
        echo -e "    ${BLUE}→${NC} $f"
    done
fi

if [[ ${#MANUAL_MERGE_FILES[@]} -gt 0 ]]; then
    echo ""
    echo -e "  ${YELLOW}${BOLD}[manual-merge]${NC} 以下文件需要 ${RED}人工处理${NC}:"
    for f in "${MANUAL_MERGE_FILES[@]}"; do
        echo -e "    ${YELLOW}⚠${NC}  $f"
    done
fi
echo ""

# ---------------------------------------------------------------------------
# Step 5: 备份 keep-local 文件
# ---------------------------------------------------------------------------
echo -e "${CYAN}[Step 5/5]${NC} 备份 keep-local 文件..."
backup_keep_local
echo ""

# ---------------------------------------------------------------------------
# 最终报告
# ---------------------------------------------------------------------------
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  准备完成 — 可以执行 merge${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  下一步:"
echo -e "    ${BOLD}git merge ${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH} --no-ff${NC}"
echo ""
echo -e "  merge 完成后执行:"
echo -e "    ${BOLD}./scripts/merge/resolve-conflicts.sh${NC}  (自动解决冲突)"
echo -e "    ${BOLD}./scripts/merge/post-merge.sh${NC}          (恢复 + 验证)"
echo ""
