# GitHub 代码差分报告

> **生成时间**: 2026-04-30
> **当前分支**: `merge-2.0-rc` (HEAD: `a3b9cc2c`)
> **对比基线**: `bytedance/release/2.0-rc` (merge base: `64f4dc16`)

---

## 一、分支拓扑总览

| 对比维度 | bytedance/release/2.0-rc | bytedance/main | origin/main |
|----------|--------------------------|----------------|-------------|
| 本地领先 | **20 commits** | **20 commits** | **20 commits** |
| 本地落后 | **0 commits** | **8 commits** | **3 commits** |
| 合并模拟 | Already up to date | **4 个冲突** | 未测试 |

### 远程分支最新状态

| 分支 | 最新提交 | 时间 |
|------|----------|------|
| `bytedance/main` | `38714b6c` refactor: thread app_config through middleware factories | 2026-04-30 |
| `bytedance/release/2.0-rc` | `64f4dc16` fixed the CI build errors | 2026-04-28 |
| `origin/main` | `f7b10d42` fix(frontend): create thread on first submit | 2026-04-30 |

---

## 二、上游领先的 8 个提交 (bytedance/main)

| # | Commit | 描述 | 影响范围 |
|---|--------|------|----------|
| 1 | `38714b6c` | refactor: thread app_config through middleware factories (#2652) | 后端 harness |
| 2 | `74081a85` | **[安全]** fix(sandbox): bind local Docker ports to loopback (#2633) | Docker |
| 3 | `24a5a006` | fix: avoid duplicate call to extractReasoningContentFromMessage (#2661) | 后端 harness |
| 4 | `08afdcb9` | feat(channels): add DingTalk channel integration (#2628) | 后端 channels |
| 5 | `0691c4dd` | **[安全]** fix(security): allow disabling API docs in production via GATEWAY_ENABLE_DOCS (#2651) | Gateway |
| 6 | `f7b10d42` | fix(frontend): create thread on first submit in new-agent page (#2656) | 前端 |
| 7 | `4a9f1d54` | Merge pull request #2566 from bytedance/release/2.0-rc | 合并提交 |
| 8 | `11afd324` | Fix the log Injection error of skills.py | 安全修复 |

---

## 三、合并冲突分析

### 3.1 模拟合并 bytedance/main → merge-2.0-rc：4 个冲突

#### 冲突 1: `.env.example` — 内容冲突 (P0)

- **我们**: 添加了 EAIFlow 微服务配置（JWT_SECRET_KEY, PROCUREMENT/ASSET/PROJECT 数据库连接）
- **上游**: 修改了 CORS 端口（3000→4000）、删除了 DINGTALK 变量、添加了 GATEWAY_ENABLE_DOCS 注释
- **风险**: 中等。双方改动不重叠，手动合并即可

#### 冲突 2-5: `README_*.md` (fr/ja/ru/zh) — 删除/修改冲突 (P2)

- **我们**: 删除了这些多语言 README
- **上游**: 修改了这些 README 的内容
- **风险**: 低。需要选择保留上游版本还是保持删除

#### 冲突 6: `backend/app/gateway/config.py` — 内容冲突 (P0)

- **我们**: 保留了 `enable_docs` 字段、默认端口 8001、CORS origins localhost:3000
- **上游**: 删除了 `enable_docs` 字段（改为环境变量控制）、默认端口改为 4001、CORS origins 改为 localhost:4000
- **风险**: **高**。端口变更影响所有配置，enable_docs 安全功能需要保留但实现方式不同

#### 冲突 7: `backend/pyproject.toml` — 内容冲突 (P0)

- **我们**: 保留了 `dingtalk-stream`, `bcrypt>=4.0.0`, `pyjwt>=2.9.0`
- **上游**: 升级了 `bcrypt>=4.2.0`, `PyJWT>=2.9.0`，新增了 `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `aiofiles`, `minio`, `langchain-ollama`
- **风险**: **高**。上游新增了持久化依赖栈（sqlalchemy+asyncpg+alembic），这是重大架构变更

### 3.2 潜在冲突文件（双方都有修改，共 11 个）

| 文件 | 我们的改动 | 上游改动 | 风险 |
|------|-----------|----------|------|
| `.env.example` | 添加微服务配置 | 修改端口/删除DINGTALK | 中 |
| `README_*.md` (x4) | 删除 | 修改内容 | 低 |
| `backend/CLAUDE.md` | 添加项目文档 | 修改内容 | 低 |
| `backend/app/channels/manager.py` | 扩展通道 | 添加 DingTalk | 中 |
| `backend/app/gateway/app.py` | 添加扩展路由 | 新增 auth/feedback 路由 | **高** |
| `backend/app/gateway/config.py` | 端口/CORS/enable_docs | 端口变更/移除enable_docs | **高** |
| `backend/pyproject.toml` | 钉钉依赖 | 新增持久化栈 | **高** |
| `frontend/.../message-group.tsx` | UI 改进 | 上游修改 | 低 |

---

## 四、文件变更全量统计 (vs bytedance/main)

```
380 files changed, 52,452 insertions(+), 6,580 deletions(-)
```

### 按变更类型

| 类型 | 数量 |
|------|------|
| Added (新增) | 256 |
| Modified (修改) | 113 |
| Deleted (删除) | 11 |

### 按模块分类

| 模块 | 变更文件数 | 说明 |
|------|-----------|------|
| 后端核心 (`backend/app/`) | 73 | Gateway、扩展模块、channels |
| 后端 harness (`backend/packages/`) | 11 | Agent 框架 |
| 前端 (`frontend/`) | 176 | 页面、组件、扩展 |
| Docker/部署 | 18 | Compose 文件、nginx 配置 |
| 根目录配置 | 30+ | .env, Makefile, scripts, test |

### 上游删除的本地扩展（重要！）

上游在 `bytedance/main` 中**删除了**我们移植的扩展模块：
- `backend/app/extensions/auth/` — 认证扩展
- `backend/app/extensions/dept/` — 部门管理
- `backend/app/extensions/docmgr/` — 文档管理
- `backend/app/extensions/knowledge/` — 知识库
- `frontend/src/app/admin/` — 管理后台页面
- `frontend/src/app/login/` — 登录页面（我们有定制品牌版本）
- `frontend/src/app/knowledge-factory/` — 知识工厂

**这意味着合并上游代码会删除这些扩展功能。必须保留本地版本。**

---

## 五、按优先级分类的合并审查清单

### P0 - 必须手工审查（核心冲突）

| 文件 | 冲突类型 | 建议 |
|------|----------|------|
| `backend/app/gateway/config.py` | 内容冲突 | 保留本地 enable_docs + 端口配置，手动合并上游端口变更 |
| `backend/pyproject.toml` | 内容冲突 | 保留双方依赖，加入上游持久化栈 |
| `backend/app/gateway/app.py` | 双方修改 | 保留本地扩展路由，加入上游 auth/feedback 路由 |

### P1 - 重点审查（功能影响）

| 文件/目录 | 说明 | 建议 |
|-----------|------|------|
| `backend/app/channels/manager.py` | 上游新增 DingTalk | 合并上游改动 |
| `backend/app/extensions/` (整个目录) | 上游删除，本地需要保留 | **拒绝上游删除** |
| `frontend/src/app/(auth)/` | 上游新增认证页面 | 与本地 login 页面并存 |
| `.env.example` | 双方添加不同配置 | 手动合并 |

### P2 - 一般审查（可自动化）

| 文件 | 说明 |
|------|------|
| `README_*.md` | 选择保留或删除 |
| `backend/CLAUDE.md` | 保留双方改动 |
| `frontend/.../message-group.tsx` | 手动合并 |

### P3 - 可选审查（低风险）

| 类型 | 数量 | 说明 |
|------|------|------|
| Docker compose 文件 | 6 | 独立新增，无冲突 |
| nginx 配置 | 4 | 独立新增 |
| scripts/ 脚本 | 15+ | 上游工具脚本 |
| 文档/docs | 10+ | 纯新增 |

---

## 六、推荐合并策略

### 方案：分阶段合并（推荐）

考虑到有 4 个实际冲突和大量扩展代码需要保留，建议分 3 个阶段执行：

**阶段 1: 安全修复优先 (cherry-pick)**
```bash
# 拣选安全相关提交
git cherry-pick 74081a85  # Docker loopback bind
git cherry-pick 0691c4dd  # GATEWAY_ENABLE_DOCS
git cherry-pick 11afd324  # Log injection fix
```

**阶段 2: 功能合并 (merge + 手动解决)**
```bash
git merge bytedance/main
# 手动解决 4 个冲突：
#   - .env.example: 保留双方配置
#   - README_*.md: 保留上游版本
#   - gateway/config.py: 保留本地端口/CORS + enable_docs
#   - pyproject.toml: 合并双方依赖
# 拒绝所有删除扩展文件的变更
```

**阶段 3: 调试验证**
```bash
cd backend && make test && make lint
cd frontend && pnpm typecheck && pnpm lint && pnpm build
```

### 备选方案：Cherry-pick 仅安全修复

如果不想处理大量冲突，可以仅拣选 2 个安全修复 + DingTalk 集成：
```bash
git cherry-pick 74081a85 0691c4dd 08afdcb9 11afd324 24a5a006
```

---

## 七、关键风险提示

1. **上游删除了扩展模块**: 我们的 extensions 代码（auth, dept, docmgr, knowledge）在上游不存在，merge 会触发删除。合并时必须 `git checkout --ours` 保留这些文件
2. **端口变更**: 上游默认端口改为 4001，但我们使用 8001，需保留本地配置
3. **持久化架构**: 上游新增 sqlalchemy+asyncpg+alembic，与新 gateway 的持久化层相关
4. **定制化内容**: `frontend/src/app/login/page.tsx`（华宇工程Agent 品牌）等定制化需求，不能被上游覆盖
5. **敏感信息**: `.env` 包含真实 API Key，当前不在 gitignore 中
