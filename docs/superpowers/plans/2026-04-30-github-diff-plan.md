# 从 GitHub 拉取最新代码与本地代码差分实施方案

> **目标**：从上游 GitHub 仓库拉取最新代码，系统性地与本地代码进行差分对比，形成可操作的合并决策清单。

**当前状态**：
- 上游仓库 `bytedance`：`https://github.com/bytedance/deer-flow.git`
- 个人仓库 `origin`：`https://github.com/yogyoho/eai-flow-main.git`
- 当前分支：`merge-2.0-rc`（基于 `bytedance/release/2.0-rc` + 本地 20 个提交）
- 本地领先 `bytedance/release/2.0-rc`：**20 commits**，落后 **0 commits**
- 本地领先 `bytedance/main`：**58 commits**，落后 **0 commits**
- 存在大量未提交的修改文件和工作区未跟踪文件

---

## 第一步：环境准备与安全备份

### 1.1 保存当前工作区状态

当前有大量未提交修改和未跟踪文件，必须先保存再操作。

```bash
# 1. 查看所有未提交修改的文件列表
git status --short > /tmp/local_changes_before_pull.txt

# 2. 暂存所有当前修改（包括未跟踪文件）
git add -A
git stash push -u -m "pre-diff-snapshot-$(date +%Y%m%d-%H%M%S)"

# 3. 确认工作区干净
git status
```

### 1.2 创建备份分支

```bash
# 基于当前 merge-2.0-rc 创建备份分支
git branch backup/pre-diff-merge-2.0-rc-$(date +%Y%m%d)

# 验证备份分支创建成功
git log --oneline -1 backup/pre-diff-merge-2.0-rc-*
```

---

## 第二步：拉取上游最新代码

### 2.1 更新所有远程引用

```bash
# 拉取上游 bytedance 所有分支和标签
git fetch bytedance --tags

# 拉取个人 origin 所有分支和标签
git fetch origin --tags
```

### 2.2 确认远程分支最新状态

```bash
# 列出上游所有 release 分支
git branch -r | grep bytedance | grep release

# 列出上游所有主分支
git branch -r | grep bytedance | grep -E "main$|main-"

# 查看各分支最新 commit 时间
for branch in bytedance/main bytedance/release/2.0-rc bytedance/release/2.0-rc-1; do
  echo "=== $branch ==="
  git log -1 --format="%h %ci %s" $branch
done
```

---

## 第三步：系统差分分析

### 3.1 提交级别对比

```bash
# ===== 对比 bytedance/release/2.0-rc（最相关分支）=====

# 上游有而本地没有的提交（应该为 0）
git log --oneline HEAD..bytedance/release/2.0-rc

# 本地有而上游没有的提交（20 个本地提交）
git log --oneline bytedance/release/2.0-rc..HEAD

# 两分支分叉点
git merge-base HEAD bytedance/release/2.0-rc

# ===== 对比 bytedance/main（主分支）=====

# 上游有而本地没有的提交
git log --oneline HEAD..bytedance/main

# 本地有而上游没有的提交（58 个）
git log --oneline bytedance/main..HEAD

# ===== 对比 origin/main（个人仓库主分支）=====
git log --oneline HEAD..origin/main
git log --oneline origin/main..HEAD
```

### 3.2 文件级别差异（核心步骤）

```bash
# ===== 1. 与 bytedance/release/2.0-rc 的全量文件差异 =====
# 列出所有有差异的文件（不含内容）
git diff --name-status bytedance/release/2.0-rc..HEAD > /tmp/diff_files_release_2.0.txt

# 按变更类型分类统计
echo "=== Added (A) ===" && grep "^A" /tmp/diff_files_release_2.0.txt | wc -l
echo "=== Modified (M) ===" && grep "^M" /tmp/diff_files_release_2.0.txt | wc -l
echo "=== Deleted (D) ===" && grep "^D" /tmp/diff_files_release_2.0.txt | wc -l
echo "=== Renamed (R) ===" && grep "^R" /tmp/diff_files_release_2.0.txt | wc -l

# ===== 2. 按模块分类差异文件 =====
# 后端核心
grep -E "^[AMD].*backend/app/" /tmp/diff_files_release_2.0.txt > /tmp/diff_backend_app.txt

# 后端 harness 包
grep -E "^[AMD].*backend/packages/" /tmp/diff_files_release_2.0.txt > /tmp/diff_backend_harness.txt

# 前端
grep -E "^[AMD].*frontend/" /tmp/diff_files_release_2.0.txt > /tmp/diff_frontend.txt

# Docker / 部署
grep -E "^[AMD].*docker/|^[AMD].*Makefile|^[AMD].*manage" /tmp/diff_files_release_2.0.txt > /tmp/diff_docker.txt

# 文档
grep -E "^[AMD].*docs/" /tmp/diff_files_release_2.0.txt > /tmp/diff_docs.txt

# 技能/配置
grep -E "^[AMD].*skills/|^[AMD].*config" /tmp/diff_files_release_2.0.txt > /tmp/diff_skills_config.txt

# ===== 3. 与 bytedance/main 的全量差异 =====
git diff --name-status bytedance/main..HEAD > /tmp/diff_files_main.txt
```

### 3.3 内容级别差异（关键文件深入对比）

```bash
# 对每个关键模块生成详细 diff
mkdir -p /tmp/diffs

# 后端 Gateway 模块
git diff bytedance/release/2.0-rc..HEAD -- backend/app/gateway/ > /tmp/diffs/gateway.patch

# 后端 Extensions 模块
git diff bytedance/release/2.0-rc..HEAD -- backend/app/extensions/ > /tmp/diffs/extensions.patch

# 前端核心
git diff bytedance/release/2.0-rc..HEAD -- frontend/src/core/ > /tmp/diffs/frontend_core.patch

# 前端页面
git diff bytedance/release/2.0-rc..HEAD -- frontend/src/app/ > /tmp/diffs/frontend_pages.patch

# 前端组件
git diff bytedance/release/2.0-rc..HEAD -- frontend/src/components/ > /tmp/diffs/frontend_components.patch

# Docker 部署
git diff bytedance/release/2.0-rc..HEAD -- docker/ > /tmp/diffs/docker.patch

# 配置文件
git diff bytedance/release/2.0-rc..HEAD -- config.yaml extensions_config.json backend/pyproject.toml frontend/package.json > /tmp/diffs/config.patch
```

---

## 第四步：冲突预检

### 4.1 模拟合并测试

```bash
# 测试将 bytedance/release/2.0-rc 合并到当前分支是否会有冲突
git merge --no-commit --no-ff bytedance/release/2.0-rc
# 如果有冲突：
git diff --name-only --diff-filter=U  # 列出冲突文件
# 取消本次测试合并
git merge --abort

# 测试将 bytedance/main 合并到当前分支
git merge --no-commit --no-ff bytedance/main
git diff --name-only --diff-filter=U
git merge --abort
```

### 4.2 三方合并基准分析

```bash
# 找出本地修改与上游修改有交集的文件（潜在冲突点）
comm -12 \
  <(git diff --name-only $(git merge-base HEAD bytedance/release/2.0-rc)..HEAD | sort) \
  <(git diff --name-only $(git merge-base HEAD bytedance/release/2.0-rc)..bytedance/release/2.0-rc | sort) \
  > /tmp/potential_conflict_files.txt

echo "=== 潜在冲突文件 ($(wc -l < /tmp/potential_conflict_files.txt) 个) ==="
cat /tmp/potential_conflict_files.txt
```

---

## 第五步：生成可视化报告

### 5.1 汇总差异报告

```bash
cat > /tmp/diff_report.sh << 'SCRIPT'
#!/bin/bash
echo "============================================"
echo "  GitHub 代码差分报告"
echo "  生成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  当前分支: $(git branch --show-current)"
echo "============================================"
echo ""

echo "--- 远程仓库 ---"
git remote -v
echo ""

echo "--- 分支对比摘要 ---"
echo "vs bytedance/release/2.0-rc:"
echo "  领先: $(git rev-list --count bytedance/release/2.0-rc..HEAD) commits"
echo "  落后: $(git rev-list --count HEAD..bytedance/release/2.0-rc) commits"
echo "vs bytedance/main:"
echo "  领先: $(git rev-list --count bytedance/main..HEAD) commits"
echo "  落后: $(git rev-list --count HEAD..bytedance/main) commits"
echo ""

echo "--- 本地独有提交 (vs bytedance/release/2.0-rc) ---"
git log --oneline bytedance/release/2.0-rc..HEAD
echo ""

echo "--- 文件变更统计 (vs bytedance/release/2.0-rc) ---"
git diff --stat bytedance/release/2.0-rc..HEAD
echo ""

echo "--- 潜在冲突文件 ---"
comm -12 \
  <(git diff --name-only $(git merge-base HEAD bytedance/release/2.0-rc)..HEAD | sort) \
  <(git diff --name-only $(git merge-base HEAD bytedance/release/2.0-rc)..bytedance/release/2.0-rc | sort) \
  2>/dev/null
SCRIPT

bash /tmp/diff_report.sh | tee /tmp/full_diff_report.txt
```

### 5.2 按模块生成优先级分类

将差异文件分为四个等级：

| 优先级 | 说明 | 典型文件 |
|--------|------|----------|
| **P0 - 必须审查** | 核心业务逻辑、认证、数据库 | `backend/app/gateway/*`, `backend/app/extensions/*`, `frontend/src/core/auth/*` |
| **P1 - 重点审查** | API 路由、前端页面、配置 | `backend/app/gateway/routers/*`, `frontend/src/app/*`, `config.yaml` |
| **P2 - 一般审查** | UI 组件、工具函数 | `frontend/src/components/*`, `backend/app/channels/*` |
| **P3 - 可选审查** | 文档、样式、静态资源 | `docs/*`, `*.css`, `*.md` |

---

## 第六步：合并决策与执行

### 6.1 决策矩阵

根据差分结果，选择合并策略：

| 场景 | 策略 |
|------|------|
| 上游有新增功能，本地无冲突 | `git merge` 直接合并 |
| 上游有 BugFix，本地无修改 | `git cherry-pick` 精确拣选 |
| 上游与本地都有修改 | 手动分析 → `git merge` + 冲突解决 |
| 本地改动是定制化需求（不应推回上游） | 保留本地版本，使用 `.patch` 文件存档 |
| 本地改动应推回上游 | 整理为独立 PR，先合并上游再同步 |

### 6.2 执行合并（如确认安全）

```bash
# 方案 A：将 bytedance/release/2.0-rc 合并到当前分支
git merge bytedance/release/2.0-rc

# 方案 B：将当前分支变基到 bytedance/release/2.0-rc（保持线性历史）
git rebase bytedance/release/2.0-rc

# 方案 C：创建全新分支基于上游，然后 cherry-pick 本地提交
git checkout -b merge-2.0-rc-v2 bytedance/release/2.0-rc
git cherry-pick <commit1> <commit2> ...
```

### 6.3 冲突解决后验证

```bash
# 后端测试
cd backend && make test && make lint
cd ..

# 前端测试
cd frontend && pnpm typecheck && pnpm lint
cd ..

# 构建验证
cd frontend && pnpm build
cd ..
```

---

## 第七步：恢复工作区

```bash
# 恢复之前在 stash 中的未提交修改
git stash pop

# 如果有冲突，手动解决后
git stash drop
```

---

## 关键风险提示

1. **未提交修改**：当前有大量 modified/deleted/untracked 文件（`gateway-config.ts`, `database.py`, `auth_middleware.py` 等），必须在操作前 stash 或 commit
2. **容器内代码与本地不一致**：Docker 容器内运行的是旧版代码（commit `65776ba9` 左右），本地代码已大幅领先。差分时注意区分"本地已修改但容器未部署"和"上游新增"两类变化
3. **定制化内容**：`frontend/src/app/login/page.tsx`（华宇工程Agent 品牌）、扩展模块（知识工厂、文档空间）等属于定制化需求，不应被上游覆盖
4. **敏感信息**：`.env` 文件包含 API Key，确保在 `.gitignore` 中，不要提交到仓库
