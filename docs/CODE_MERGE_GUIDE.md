# 代码更新差分实施方案

基于 `bytedance/deer-flow` (upstream) → `yogyoho/eai-flow-main` (origin, `merge-2.0-rc` 分支) 的持续代码同步实战经验整理。

## 自动化脚本 (推荐优先使用)

```
scripts/merge/
├── merge-rules.env        # 文件分类规则 (keep-local / accept-upstream / manual-merge)
├── pre-merge.sh           # merge 前: 分析 upstream 变更 + 分类报告 + 备份
├── resolve-conflicts.sh   # merge 时: 自动解决冲突 (keep-local→ours, accept-upstream→theirs)
└── post-merge.sh          # merge 后: 恢复 + 安装依赖 + lint + test + Docker 验证
```

快速工作流:
```bash
./scripts/merge/pre-merge.sh                    # 1. 分析 + 备份
git merge bytedance/main --no-ff                # 2. 执行合并
./scripts/merge/resolve-conflicts.sh            # 3. 自动解决冲突
# ... 手工处理 manual-merge 文件 ...
git add . && git commit -m "merge: ..."         # 4. 提交
./scripts/merge/post-merge.sh                   # 5. 恢复 + 验证
```

## 一、仓库拓扑

```
bytedance/deer-flow (upstream)     → 原始仓库
yogyoho/eai-flow-main (origin)     → 本地 fork，分支 merge-2.0-rc
                                    → 包含本地扩展模块（extensions）
```

**本地扩展模块**（不在 upstream 中）：
- `backend/app/extensions/` — auth、user、dept、docmgr、knowledge、knowledge_factory、law、settings、web_scraper
- `frontend/src/extensions/` — 对应的前端页面和 API 层
- `frontend/src/app/docmgr/`、`frontend/src/app/writing/`、`frontend/src/app/login/` — 扩展页面
- `docker/` — Docker 编排文件（docker-compose、nginx 配置）

## 二、合并前准备

### 2.1 确认当前状态

```bash
# 1. 查看当前分支和工作区状态
git status
git branch -v

# 2. 确认 upstream 远程配置
git remote -v
# 预期输出:
# bytedance  https://github.com/bytedance/deer-flow.git (fetch)
# bytedance  https://github.com/bytedance/deer-flow.git (push)
# origin     https://github.com/yogyoho/eai-flow-main.git (fetch)
# origin     https://github.com/yogyoho/eai-flow-main.git (push)

# 3. 查看本地与 upstream 的差异
git fetch bytedance
git log --oneline --graph merge-2.0-rc...bytedance/main --left-right

# 4. 确认本地无未提交修改
git stash list  # 确保没有遗忘的 stash
```

### 2.2 分析 upstream 新增内容

```bash
# 查看 upstream 新增的 commit 列表
git log --oneline merge-2.0-rc..bytedance/main

# 查看 upstream 文件变更概览
git diff --stat merge-2.0-rc...bytedance/main

# 重点检查:
# - 新增了哪些模块/服务
# - 修改了哪些 backend/ 核心文件
# - 修改了哪些 frontend/ 核心文件
# - dependencies (pyproject.toml, package.json) 是否有变化
# - config.example.yaml 是否有新增字段
# - 是否新增了 .env 变量
```

### 2.3 预判冲突区域

根据项目架构，以下区域最容易产生冲突：

| 高冲突区域 | 原因 |
|-----------|------|
| `backend/app/gateway/app.py` | 本地在 Gateway 中注册了 extensions router，upstream 可能修改 router 注册顺序或中间件 |
| `backend/config.yaml` | upstream 的 `config.example.yaml` 可能新增字段，本地 `config.yaml` 需要同步 |
| `backend/pyproject.toml` | upstream 可能新增/升级依赖，与本地扩展依赖可能冲突 |
| `frontend/src/app/` | 本地新增了 docmgr/writing/login 路由，upstream 可能修改 layout 或 shared 组件 |
| `docker/nginx/` | 本地有自定义 nginx 配置，upstream 可能引入新的路由规则 |
| `frontend/pnpm-lock.yaml` | 依赖锁文件，与 `package.json` 同步修改时冲突频繁 |

### 2.4 备份关键文件

```bash
# 备份本地关键配置（merge 失败时可以快速恢复）
cp backend/config.yaml backend/config.yaml.bak.$(date +%Y%m%d)
cp backend/extensions_config.json backend/extensions_config.json.bak.$(date +%Y%m%d)
cp -r docker/ docker.bak.$(date +%Y%m%d)/
```

## 三、合并执行

### 3.1 执行 merge

```bash
# 1. 确保在正确分支
git checkout merge-2.0-rc

# 2. 拉取 upstream 最新代码
git fetch bytedance

# 3. 执行合并（推荐使用 --no-ff 保留合并历史）
git merge bytedance/main --no-ff -m "merge: integrate bytedance/main (<本次合并的主要内容摘要>)"

# 如果出现冲突，Git 会列出冲突文件列表
```

### 3.2 冲突解决策略

#### 策略分级

```
Level 1 — 无冲突: 直接通过（大部分文件）
Level 2 — 文本冲突: Git 自动标记 <<< === >>> 部分，手动选择保留
Level 3 — 架构冲突: 两套设计范式冲突，需要重新设计（如 dual auth）
```

#### 文本冲突解决原则

```
1. backend/app/gateway/app.py:
   - 保留本地 extensions router 的 import 和 include_router
   - 接受 upstream 的新 router 注册
   - 注意 router 注册顺序

2. backend/pyproject.toml:
   - 合并双方依赖（取并集）
   - 版本号冲突时取较高版本
   - 合并后运行 uv lock --upgrade 验证

3. config.yaml / config.example.yaml:
   - 以 upstream 的 config.example.yaml 为基准
   - 将本地 config.yaml 中的自定义值覆盖回去
   - 新增字段使用 upstream 的默认值

4. frontend/src/ 下的页面文件:
   - 本地扩展页面 (docmgr/writing/login) 优先保留本地版本
   - upstream 核心页面 (workspace) 接受 upstream 版本
   - layout.tsx 冲突时需手动整合

5. docker/nginx/ 配置:
   - 保留本地的 upstream 定义和 location 规则
   - 接受 upstream 的新增路由
   - 确保 /api/extensions/* 路由不被覆盖
```

#### 架构冲突解决（以 dual auth 为例）

当 upstream 引入了一套新的 Gateway Auth 系统（`/api/v1/auth`），而本地有一套 Extensions Auth 系统（`/api/extensions/auth`），且两者使用相同的 cookie 名称 (`access_token`) 但不同的 JWT 签名密钥和用户存储时，直接合并会在运行时产生冲突。

**解决方案 A：移除本地 Auth，桥接到 upstream Auth**（本次采用）

1. **Backend**: 移除 `app/extensions/auth/routers.py` 的注册
2. **Backend**: 重写 `app/extensions/auth/middleware.py`，将 `get_current_user` 委托给 Gateway Auth 的 `get_current_user_from_request`
3. **Backend**: 通过 email 匹配建立 Gateway User (SQLite) ↔ Extensions User (PostgreSQL) 的桥接
4. **Frontend**: 移除 `authApi`，所有请求改用 `credentials: "include"`
5. **Frontend**: `login/logout` 重定向到 Gateway Auth 的登录/登出流程

**方案 B：保留两套 Auth，通过不同的 cookie 名称隔离**

适合不想改动太多代码的场景，但技术债务更高。

### 3.3 依赖更新

```bash
# Backend
cd backend
uv sync --group dev

# Frontend
cd frontend
pnpm install
```

## 四、合并后验证

### 4.1 代码级验证

```bash
# 1. Backend lint + 测试
cd backend
make lint
make test
# 确保所有测试通过（当前 178 tests passed）

# 2. Frontend lint + 类型检查
cd frontend
pnpm lint
pnpm typecheck

# 3. 检查 harss 边界规则
cd backend
PYTHONPATH=. uv run pytest tests/test_harness_boundary.py -v

# 4. 检查是否有未解决的 TODO/FIXME 标记
rg "TODO|FIXME|HACK|XXX" --glob '!node_modules' --glob '!.git'
```

### 4.2 运行时验证

```bash
# 1. 清理旧的 Docker 容器和镜像缓存
make docker-stop
docker system prune -f

# 2. 重新构建并启动
make docker-start

# 3. 验证服务健康状态
curl -s http://localhost:2026/health                    # Gateway
curl -s http://localhost:2026/api/langgraph/info        # LangGraph runtime
curl -s http://localhost:2026/                           # Frontend

# 4. 验证扩展 API 是否正常
curl -s http://localhost:2026/api/extensions/users/me   # 扩展用户端点
curl -s http://localhost:2026/api/extensions/docmgr/    # 文档管理
```

### 4.3 关键验证清单

| 验证项 | 方法 | 预期 |
|--------|------|------|
| 对话（Q&A） | 通过聊天界面发送消息 | AI 正常回复，不报错 |
| 用户认证 | 访问扩展页面（docmgr/writing） | 自动跳转到登录，登录后可访问 |
| MCP 工具加载 | 查看 gateway 日志 | 无 `asyncio.gather` 崩溃 |
| 文件上传 | 上传 PDF/图片 | 正常解析并显示 |
| 线程管理 | 创建/切换/删除对话 | 无 Date/时间错误 |
| 知识库 | 导入文档、搜索 | 正常返回结果 |
| 记忆系统 | 多次对话后查看记忆 | 正确存储和注入 |

## 五、Docker 操作要点

### 5.1 架构概览

```
Browser → Nginx (:2026)
  ├── /api/langgraph/* → Gateway (:8001) 嵌入式 LangGraph runtime
  ├── /api/*           → Gateway (:8001) FastAPI
  └── /*               → Frontend (:4000) Next.js
```

关键服务：
- `gateway` — FastAPI + LangGraph agent runtime
- `frontend` — Next.js 前端
- `nginx` — 反向代理
- `postgres-ext` — 扩展模块 PostgreSQL 数据库
- `postgres` — 业务服务 PostgreSQL
- `ragflow-*` — RAGFlow 相关服务（可选）

### 5.2 nginx 配置更新

**重要**：Docker 容器在启动时将模板配置复制到容器内部。对宿主机 nginx 配置文件的修改**不会自动生效**，必须重新构建或手动热更新。

```bash
# 方法1: 重新构建并重启（推荐）
make docker-stop
make docker-start

# 方法2: 进入容器热更新（紧急情况）
docker exec deer-flow-nginx sh -c "\
  sed -i 's|OLD_PATTERN|NEW_PATTERN|g' /etc/nginx/conf.d/default.conf && \
  nginx -t && nginx -s reload"
```

### 5.3 常见 Docker 问题

**502 Bad Gateway**：
- 原因：nginx 配置中的 `proxy_pass` 目标服务名不存在
- 检查：`docker exec deer-flow-nginx nginx -T 2>/dev/null | grep proxy_pass`
- 修复：确保 `proxy_pass http://gateway:8001`（使用服务名，非容器名）

**服务启动失败**：
```bash
# 查看具体服务日志
docker logs deer-flow-gateway --tail 100
docker logs deer-flow-frontend --tail 100
```

**端口冲突**：
```bash
# 检查端口占用
netstat -ano | grep 2026
netstat -ano | grep 8001
netstat -ano | grep 4000
```

## 六、数据库策略

### 6.1 数据库分布

| 数据库 | 用途 | 所属系统 |
|--------|------|---------|
| **SQLite** (`backend/.deer-flow/`) | 用户认证 (Gateway Auth)、线程元数据、记忆 | upstream 核心 |
| **PostgreSQL** (`postgres-ext`) | 用户管理 (RBAC)、角色、部门、知识库、文档、法规、爬虫草稿 | 本地扩展 |
| **PostgreSQL** (`postgres`) | 业务数据 | 业务服务 (RAGFlow 等) |

### 6.2 迁移注意事项

**禁止将 PostgreSQL 的扩展表迁移到 SQLite**，原因：
1. PostgreSQL 使用 `UUID(as_uuid=True)` 类型 — SQLite 不支持原生 UUID
2. PostgreSQL 使用 `ARRAY(String)` 类型 — SQLite 不支持数组列
3. PostgreSQL 使用 `JSONB` 类型 — SQLite 仅支持基本的 JSON 文本
4. PostgreSQL 的 RBAC 查询使用 `any()` 数组操作符 — SQLite 无法等价实现

**如需跨数据库关联查询**（如 Gateway User → Extensions User）：
- 使用 email 作为自然键进行桥接
- 在 middleware 层处理关联逻辑，保持两个数据库独立

## 七、错误诊断方法论

### 7.1 按症状定位

| 症状 | 最可能原因 | 排查路径 |
|------|-----------|---------|
| 前端 401/403 | Auth middleware 未正确桥接 | `backend/app/extensions/auth/middleware.py` |
| 前端 404 (API) | Router 未注册或路径冲突 | `backend/app/gateway/app.py` router include 检查 |
| 前端 RangeError: Invalid time value | 后端返回空字符串作为日期 | `thread_meta/memory.py` `_item_to_dict()` |
| 502 Bad Gateway | Nginx proxy_pass 目标错误 | `docker exec` 检查 nginx 配置 |
| MCP server 启动失败 | 配置文件中的路径不存在 | `extensions_config.json` |
| 对话无响应 | Agent 创建失败或 config 问题 | `config.yaml` → gateway 日志 |
| TypeScript 编译错误 | 依赖版本不匹配或类型定义缺失 | `pnpm typecheck` 输出 |

### 7.2 日志查看

```bash
# Gateway 日志（包含 agent 执行日志）
docker logs deer-flow-gateway --tail 200 -f

# 前端日志（浏览器 Console + Network 面板）
# 关注:
# - /api/v1/auth/me 的 HTTP 状态码
# - /api/extensions/users/me 的 HTTP 状态码
# - WebSocket/SSE 连接状态
```

### 7.3 MCP 工具加载问题

`extensions_config.json` 中的 MCP server 通过 `asyncio.gather` 并发加载。**一个 server 失败会导致整个 TaskGroup 失败**，所有 MCP 工具都无法加载。

```json
// 有问题的配置 —— filesystem server 的路径在 Docker 容器中不存在
{
  "mcpServers": {
    "filesystem": {
      "enabled": true,
      "args": ["/path/to/allowed/files"]  // ← 路径无效
    }
  }
}
```

修复：
```json
{
  "mcpServers": {
    "filesystem": {
      "enabled": false  // 禁用不需要的 server
    }
  }
}
```

### 7.4 日期/时间处理问题

`MemoryThreadMetaStore._item_to_dict()` 中如果 `created_at` / `updated_at` 字段为空，返回空字符串 `""`，前端 JavaScript `new Date("")` → `Invalid Date` → `RangeError`。

**修复模式**（已应用于 `memory.py` 和 `sql.py`）：
```python
def _format_ts(ts: float | str | None) -> str:
    """Always return a valid ISO-8601 string, never an empty string."""
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    if isinstance(ts, str) and ts:
        return ts
    return datetime.now(UTC).isoformat()
```

## 八、前端变更要点

### 8.1 Auth 体系变更清单

当 auth 体系发生变化时（如从独立 JWT 认证切换到与 Gateway Auth 桥接），需要变更以下文件：

```
frontend/src/extensions/api/index.ts        — 移除 authApi，改用 credentials: "include"
frontend/src/extensions/api/client.ts        — 移除 JWT refresh 机制
frontend/src/extensions/hooks/useAuth.tsx     — 重写 login/logout/状态检查
frontend/src/app/login/page.tsx              — 简化为纯重定向
frontend/src/app/docmgr/layout.tsx           — 更新重定向 URL
frontend/src/app/writing/layout.tsx          — 更新重定向 URL
frontend/src/app/<其他扩展>/layout.tsx        — 同上
```

### 8.2 API 请求模式

```typescript
// 变更前: 手动管理 Bearer token
const token = localStorage.getItem("access_token");
fetch(url, {
  headers: { "Authorization": `Bearer ${token}` }
});

// 变更后: 依赖 HttpOnly cookie (由 Gateway Auth 管理)
fetch(url, {
  credentials: "include"  // cookie 自动携带
});
```

### 8.3 前端构建验证

```bash
cd frontend
pnpm typecheck    # 类型检查（可能会发现 pre-existing errors）
pnpm lint         # ESLint
pnpm build        # 生产构建（需要 BETTER_AUTH_SECRET 环境变量）
```

注意：`pnpm typecheck` 可能发现 pre-existing errors（如 i18n 缺失 key、knowledge-factory 组件类型错误），不应因为新 merge 引入的已有问题阻塞上线。

## 九、测试策略

### 9.1 Backend

```bash
cd backend
# 全量测试
make test

# 重点测试文件
PYTHONPATH=. uv run pytest tests/test_harness_boundary.py -v    # harss 边界
PYTHONPATH=. uv run pytest tests/test_client.py -v              # 嵌入式客户端
PYTHONPATH=. uv run pytest tests/test_memory_updater.py -v      # 记忆系统
PYTHONPATH=. uv run pytest tests/test_dingtalk_channel.py -v    # 新频道集成（如适用）
```

### 9.2 Frontend

```bash
cd frontend
pnpm test           # Vitest 单元测试
pnpm test:e2e       # Playwright E2E 测试（修改 frontend/ 时触发）
```

### 9.3 手工冒烟测试

| 测试场景 | 操作 | 验收标准 |
|---------|------|---------|
| 登录流程 | 访问 /docmgr → 重定向到登录 → 登录 → 回到 /docmgr | 无 401/403/404 |
| 对话功能 | 创建新对话 → 发送消息 → 查看回复 | AI 正常回复，无报错 |
| 侧边栏 | 切换历史对话 | 无 RangeError，对话列表正常加载 |
| 文件上传 | 上传 PDF → 提问相关话题 | PDF 内容被正确理解和引用 |
| 扩展功能 | 访问知识库/文档管理/法规检索 | 各页面正常加载和数据交互 |

## 十、合并后 Git 操作

### 10.1 推送

```bash
# 确认所有验证通过后推送
git push origin merge-2.0-rc

# 如果需要 PR 合并到 main:
# gh pr create --title "merge: integrate bytedance/main <摘要>" --body "..."
```

### 10.2 清理

```bash
# 删除备份文件（确认合并成功后）
rm backend/config.yaml.bak.*
rm backend/extensions_config.json.bak.*
rm -rf docker.bak.*/

# 清理 Docker 资源
docker system prune -f --volumes
```

## 十一、快速参考卡片

```bash
# === 合并前 ===
git fetch bytedance
git log --oneline merge-2.0-rc..bytedance/main | wc -l  # 新增 commit 数
git diff --stat merge-2.0-rc...bytedance/main              # 变更文件
cp backend/config.yaml backend/config.yaml.bak

# === 合并 ===
git merge bytedance/main --no-ff
# 解决冲突...
cd backend && uv sync --group dev
cd frontend && pnpm install

# === 验证 ===
cd backend && make lint && make test
cd frontend && pnpm lint && pnpm typecheck

# === 部署 ===
make docker-stop && make docker-start
curl http://localhost:2026/health
curl http://localhost:2026/api/extensions/users/me

# === 提交 ===
git push origin merge-2.0-rc
```

## 附录 A：本地定制功能保护清单

以下功能为本地定制开发，**合并 upstream 时必须保留，不可被覆盖**。

### A.1 保存到文档空间（书签按钮）

**功能**：在 AI 回复旁和工件标题栏显示书签图标按钮，点击后将内容保存到文档空间。

| 文件 | 关键代码 | 说明 |
|------|---------|------|
| `frontend/src/components/workspace/save-to-doc-button.tsx` | 整个文件 | 消息保存按钮组件，调用 `docmgrApi.create()` |
| `frontend/src/components/workspace/artifacts/save-artifact-to-doc-button.tsx` | 整个文件 | 工件保存按钮组件，含 `isSavableToDoc()` 函数 |
| `frontend/src/components/workspace/messages/message-list.tsx` | `import SaveToDocButton` + `renderAssistantCopyButton` 中的 `<SaveToDocButton>` | 助手回复悬停时显示书签按钮（在复制按钮旁） |
| `frontend/src/components/workspace/messages/message-list-item.tsx` | `import SaveToDocButton` + 工具栏中的 `<SaveToDocButton>` | 非助手消息的工具栏中也包含书签按钮 |
| `frontend/src/components/workspace/artifacts/artifact-file-detail.tsx` | `<SaveArtifactToDocButton>` in `<ArtifactActions>` | 工件标题栏操作区中的书签按钮 |

**合并检查点**：
- `message-list.tsx` 的 `renderAssistantCopyButton` 必须包含 `<SaveToDocButton>`
- `artifact-file-detail.tsx` 的 `<ArtifactActions>` 中必须包含 `<SaveArtifactToDocButton>`
- 两个保存按钮组件文件本身不能被删除或覆盖

### A.2 "加载更多"对话历史

**功能**：多轮对话后，顶部显示"加载更多"按钮，允许用户手动加载旧的 run 消息，而非自动加载（自动加载会消耗 hasMore 标志）。

| 文件 | 关键代码 | 说明 |
|------|---------|------|
| `frontend/src/core/threads/hooks.ts` | `useThreadHistory` 中的 `unloadedIndex` state + effect 不调用 `loadMessages()` | 核心修复：effect 只更新 index，不自动加载 |
| `frontend/tests/unit/core/threads/thread-history.test.ts` | 整个文件 | TDD 测试覆盖 |

**合并检查点**：
- `useThreadHistory` 中的 effect **不能**调用 `loadMessages()`（旧 bug）
- `hasMore` 必须从 `useState` 的 `unloadedIndex` 派生，不能从 `useRef` 的 `indexRef` 派生
- `findLatestUnloadedRunIndex` 必须是导出函数（供测试使用）
- effect 的依赖数组是 `[threadId, runs.data]`，**不包含** `loadMessages`

```typescript
// ✅ 正确的 effect 代码（不可改为自动加载）
useEffect(() => {
  // ...threadChanged reset logic...
  if (runs.data && runs.data.length > 0) {
    runsRef.current = runs.data ?? [];
    const newIndex = findLatestUnloadedRunIndex(runs.data, loadedRunIdsRef.current);
    setUnloadedIndex(newIndex);
  }
}, [threadId, runs.data]);

const hasMore = unloadedIndex >= 0 || !runs.data;
```

### A.3 Token 统计显示

**功能**：对话页面 header 显示 token 用量指标，每条助手回复可显示 inline token 统计。

| 文件 | 关键代码 | 说明 |
|------|---------|------|
| `config.yaml`（项目根目录） | `token_usage: enabled: true` | 后端开关，控制 API 返回 `token_usage.enabled` |
| `backend/app/gateway/routers/models.py` | `token_usage=TokenUsageResponse(enabled=config.token_usage.enabled)` | Models API 返回 token_usage 状态 |
| `frontend/src/core/models/hooks.ts` | `tokenUsageEnabled: data?.token_usage.enabled ?? false` | 前端读取开关 |
| `frontend/src/components/workspace/token-usage-indicator.tsx` | 整个文件 | Header 中的 token 用量指示器 |
| `frontend/src/app/workspace/chats/[thread_id]/page.tsx` | `<TokenUsageIndicator>` + `tokenUsageInlineMode` | 页面集成 |

**合并检查点**：
- `config.yaml` 中 `token_usage.enabled` 必须为 `true`（upstream 默认可能为 `false`）
- `models.py` 中 `TokenUsageResponse` 的引用和返回不能被移除
- `page.tsx` 中 `<TokenUsageIndicator>` 和 `tokenUsageInlineMode` 的传递不能丢失

### A.4 记忆（Memory）API 用户隔离修复

**功能**：修复记忆 API 读写路径的 user_id 不一致问题，确保前端记忆 Tab 正确显示当前用户的记忆数据。

**原 Bug**：记忆中间件（写路径）使用 JWT 认证的 `user_id` 存储数据，但 API 端点（读路径）优先使用前端 `localStorage` 传来的 `user_id` 查询参数，且调用 `get_memory_data(effective_user_id)` 时将 `user_id` 错误地传给了 `agent_name` 位置参数。

| 文件 | 关键代码 | 说明 |
|------|---------|------|
| `backend/app/gateway/routers/memory.py` | `_resolve_user_id(request, user_id)` 函数 | 优先使用 `request.state.user`（JWT 认证用户），而非前端查询参数 |
| `backend/app/gateway/routers/memory.py` | 所有 `get_memory_data(user_id=effective_user_id)` 调用 | **必须使用 `user_id=` 关键字参数**，不能位置传参（否则会传给 `agent_name`） |

**合并检查点**：
- `_resolve_user_id` 必须从 `request.state.user` 获取认证用户 ID，不能直接使用查询参数
- 所有 `get_memory_data` / `reload_memory_data` / `clear_memory_data` / `delete_memory_fact` / `import_memory_data` 调用必须使用 `user_id=` 关键字参数
- 每个端点函数必须接受 `request: Request` 参数（或 `req: Request`，用于解冲突 Request 对象名）

```python
# ✅ 正确的用户 ID 解析（不可改回直接使用查询参数）
def _resolve_user_id(request: Request, user_id: str | None = None) -> str | None:
    state_user = getattr(request.state, "user", None)
    if state_user is not None:
        return str(state_user.id)
    return user_id

# ✅ 正确的存储调用（user_id 必须是关键字参数）
memory_data = get_memory_data(user_id=effective_user_id)

# ❌ 错误：位置传参会把 user_id 传给 agent_name
# memory_data = get_memory_data(effective_user_id)
```

### A.5 合并验证脚本

合并完成后，运行以下检查确认定制功能未被覆盖：

```bash
# 1. 检查书签按钮组件存在
test -f frontend/src/components/workspace/save-to-doc-button.tsx && echo "✓ save-to-doc-button" || echo "✗ MISSING"
test -f frontend/src/components/workspace/artifacts/save-artifact-to-doc-button.tsx && echo "✓ save-artifact-to-doc-button" || echo "✗ MISSING"

# 2. 检查书签按钮已集成到消息列表
grep -q "SaveToDocButton" frontend/src/components/workspace/messages/message-list.tsx && echo "✓ SaveToDocButton in message-list" || echo "✗ MISSING"

# 3. 检查加载更多修复（unloadedIndex 是 state，不是 ref）
grep -q "const \[unloadedIndex, setUnloadedIndex\]" frontend/src/core/threads/hooks.ts && echo "✓ unloadedIndex is state" || echo "✗ REGRESSION"

# 4. 检查 effect 不包含 loadMessages 调用
grep -q "loadMessages" frontend/src/core/threads/hooks.ts | head -5
# 确认 loadMessages 只在 loadMore 回调和内部使用，不在 runs.data 的 effect 中

# 5. 检查 token_usage 配置
grep -q "token_usage" config.yaml && grep -A1 "token_usage" config.yaml | grep -q "enabled: true" && echo "✓ token_usage enabled" || echo "✗ CHECK config.yaml"
grep -q "token_usage" backend/config.yaml 2>/dev/null && grep -A1 "token_usage" backend/config.yaml | grep -q "enabled: true" && echo "✓ backend/config.yaml ok" || echo "⚠ check backend/config.yaml"

# 6. 运行前端测试
cd frontend && pnpm test -- --run tests/unit/core/threads/thread-history.test.ts
```

## 附录 B：merge 冲突标记解读

```
<<<<<<< HEAD           ← 当前分支 (merge-2.0-rc) 的内容
...本地修改...
=======                ← 分界线
...upstream 修改...
>>>>>>> bytedance/main ← 被合并分支的内容
```

使用 VS Code 或其他编辑器的 merge editor 可以更直观地解决冲突。

## 附录 B：Docker Compose 文件对应关系

| 文件 | 用途 | 加载方式 |
|------|------|---------|
| `docker-compose.yaml` | 核心服务 (gateway, frontend, nginx) | 默认 |
| `docker-compose.extensions.yaml` | 扩展服务 (postgres-ext) | `-f` 参数合并 |
| `docker-compose.ragflow.yaml` | RAGFlow 服务栈 | `-f` 参数合并 |
| `docker-compose.business.yaml` | 业务服务 | `-f` 参数合并 |
| `docker-compose.external.yaml` | 外部业务服务（procurement 等） | 单独使用 |
