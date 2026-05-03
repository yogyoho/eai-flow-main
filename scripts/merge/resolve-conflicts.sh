#!/usr/bin/env bash
# =============================================================================
# resolve-conflicts.sh — Merge 冲突自动解决
#
# 用法:
#   ./scripts/merge/resolve-conflicts.sh [--dry-run]
#
# 功能:
#   1. 扫描所有冲突文件 (git diff --name-only --diff-filter=U)
#   2. keep-local 文件 → git checkout --ours && git add
#   3. accept-upstream 文件 → git checkout --theirs && git add
#   4. manual-merge 文件 → 输出清单 + 变更摘要，留给人工处理
#   5. 输出处理结果统计
#
# 注意: 必须在 git merge 产生冲突后、git commit 前运行
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/merge-rules.env"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    shift
fi

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Resolve Conflicts — 自动解决 merge 冲突${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: 检查是否处于 merge 冲突状态
# ---------------------------------------------------------------------------
if ! git rev-parse --verify MERGE_HEAD &>/dev/null 2>&1; then
    echo -e "${RED}[ERROR]${NC} 当前不处于 merge 状态 (未找到 MERGE_HEAD)。"
    echo "  请先执行 git merge 产生冲突后再运行此脚本。"
    exit 1
fi

# 获取冲突文件列表
CONFLICT_FILES=$(git diff --name-only --diff-filter=U 2>/dev/null || echo "")

if [[ -z "$CONFLICT_FILES" ]]; then
    echo -e "${GREEN}没有冲突文件。merge 成功！${NC}"
    exit 0
fi

TOTAL_CONFLICTS=$(echo "$CONFLICT_FILES" | grep -c '^' 2>/dev/null || echo "0")
echo -e "发现 ${BOLD}${TOTAL_CONFLICTS}${NC} 个冲突文件"
echo ""

# ---------------------------------------------------------------------------
# Step 2: 分类冲突文件
# ---------------------------------------------------------------------------
declare -a KEEP_LOCAL_CONFLICTS=()
declare -a ACCEPT_UPSTREAM_CONFLICTS=()
declare -a MANUAL_MERGE_CONFLICTS=()

while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    category=$(classify_file "$file")
    case "$category" in
        keep-local)
            KEEP_LOCAL_CONFLICTS+=("$file")
            ;;
        accept-upstream)
            ACCEPT_UPSTREAM_CONFLICTS+=("$file")
            ;;
        manual-merge)
            MANUAL_MERGE_CONFLICTS+=("$file")
            ;;
    esac
done <<< "$CONFLICT_FILES"

# ---------------------------------------------------------------------------
# Step 3: 自动解决
# ---------------------------------------------------------------------------

# --- keep-local: 保留本地版本 (--ours) ---
resolved_ours=0
if [[ ${#KEEP_LOCAL_CONFLICTS[@]} -gt 0 ]]; then
    echo -e "${GREEN}${BOLD}[keep-local]${NC} 自动保留本地版本 (--ours):"
    for f in "${KEEP_LOCAL_CONFLICTS[@]}"; do
        echo -e "  ${GREEN}✓${NC} $f"
        if [[ "$DRY_RUN" == "false" ]]; then
            git checkout --ours "$f" 2>/dev/null || true
            git add "$f" 2>/dev/null || true
        fi
        ((resolved_ours++)) || true
    done
    echo "  → ${resolved_ours} files resolved"
    echo ""
else
    echo -e "${GREEN}[keep-local]${NC} 无冲突文件"
    echo ""
fi

# --- accept-upstream: 接受 upstream 版本 (--theirs) ---
resolved_theirs=0
if [[ ${#ACCEPT_UPSTREAM_CONFLICTS[@]} -gt 0 ]]; then
    echo -e "${BLUE}${BOLD}[accept-upstream]${NC} 自动接受 upstream (--theirs):"
    for f in "${ACCEPT_UPSTREAM_CONFLICTS[@]}"; do
        echo -e "  ${BLUE}→${NC} $f"
        if [[ "$DRY_RUN" == "false" ]]; then
            git checkout --theirs "$f" 2>/dev/null || true
            git add "$f" 2>/dev/null || true
        fi
        ((resolved_theirs++)) || true
    done
    echo "  → ${resolved_theirs} files resolved"
    echo ""
else
    echo -e "${BLUE}[accept-upstream]${NC} 无冲突文件"
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 4: 手工处理清单
# ---------------------------------------------------------------------------
remaining=$(git diff --name-only --diff-filter=U 2>/dev/null | grep -c '^' 2>/dev/null || echo "0")

if [[ "$remaining" -gt 0 ]]; then
    echo -e "${YELLOW}${BOLD}[manual-merge]${NC} 以下 ${BOLD}${remaining}${NC} 个文件需要 ${RED}人工处理${NC}:"
    echo ""

    while IFS= read -r file; do
        [[ -z "$file" ]] && continue

        # 尝试显示每个文件上游改了什么 (仅标题)
        echo -e "  ${YELLOW}━━━${NC} ${BOLD}$file${NC}"

        # 获取冲突的 hunks 数量
        conflict_markers=$(grep -c '^<<<<<<< ' "${REPO_ROOT:-.}/$file" 2>/dev/null || echo "?")
        echo -e "      冲突块: ${conflict_markers}"

        # 显示 upstream 改了哪些行 (从 merge base 到 upstream 的变更摘要)
        if [[ -f "${REPO_ROOT:-.}/$file" ]]; then
            echo -e "      编辑方式: 打开文件搜索 '<<<<<<< HEAD' 手动解决"
        fi
        echo ""
    done <<< "$(git diff --name-only --diff-filter=U 2>/dev/null)"

    echo -e "  ${BOLD}解决所有 manual-merge 冲突后执行:${NC}"
    echo -e "    ${BOLD}git add . && git commit${NC}"
else
    echo -e "${GREEN}${BOLD}所有冲突已自动解决！${NC}"
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 5: 统计
# ---------------------------------------------------------------------------
echo -e "${BOLD}───────────────────────────────────────────────────────────────${NC}"
echo -e "  自动解决 (keep-local):     ${GREEN}${resolved_ours}${NC} files"
echo -e "  自动解决 (accept-upstream):${BLUE}${resolved_theirs}${NC} files"
echo -e "  需人工处理 (manual-merge):  ${YELLOW}${remaining}${NC} files"
echo -e "${BOLD}───────────────────────────────────────────────────────────────${NC}"

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo -e "  ${YELLOW}[DRY RUN]${NC} 未实际修改文件。去掉 --dry-run 参数执行真实操作。"
fi
