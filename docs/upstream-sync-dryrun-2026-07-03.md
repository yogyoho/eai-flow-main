# Deer-Flow 上游同步 Dry-Run 分析报告

- **日期**：2026-07-03
- **目标**：同步上游 `bytedance/deer-flow` `main` 分支领先本地的 130 个提交（跨 v2.0.0 release）
- **目标分支**：`main-dev-fork`（含 eai-flow 1727 个定制提交）
- **性质**：Dry-Run，**不改任何代码**。执行时另起分支逐 Tier 推进。

---

## 一、执行摘要

**直接全量 merge 不可行**：464/524（88%）上游改动文件与你的定制冲突，且 harness 层是**结构性对冲**——eai 对 harness 做减法（-13297 行），上游做加法（+10911 行），方向相反，几乎每个文件都要人工裁决。

**唯一可行路径是分 Tier 批次**。130 提交拆成 **6 个 Tier + 1 个跳过清单**，从"零风险基线"到"独立可选特性"逐层推进，每批可独立测、独立回滚。**真正的硬骨头只有两块**：中间件链（Tier 3）和 frontend（Tier 5），其余批量自动化程度高。

---

## 二、冲突事实

| 指标 | 数值 | 含义 |
|---|---|---|
| 上游改动文件 | 524 | 130 提交涉及 |
| 真实冲突文件 | **464** | merge-tree 实测，占 88% |
| 软冲突（tests） | 126（27%） | 直接取上游/忽略，不阻塞 |
| harness 结构性冲突 | eai -13297 行 ↔ 上游 +10911 行 | 方向相反，必须人工 |

**冲突重灾区：**

| 区域 | 冲突文件 | 性质 |
|---|---|---|
| `backend/packages/harness` | 98 | **同步目标**，但 eai 深度删减过，硬合并 |
| `backend/tests` | 98 | 软冲突，可批量处理 |
| `backend/app` | 37 | eai 定制层（gateway/IM），人工 |
| `frontend/src/content` | 52 | 文档 mdx，低风险批量 |
| `frontend/src/components` | 29 | 组件，人工 |
| `frontend/src/core` | 25 | 核心，人工 |
| **middleware 链** | **14 个全冲突** | **最高风险**：eai 有 17+ 中间件，上游重构链结构 + 加 3 个新中间件 |
| `docker/` | 6 | eai 部署深度定制（nginx/compose） |

### middleware 链冲突文件清单（Tier 3 重点）
```
backend/packages/harness/deerflow/agents/middlewares/
  dynamic_context / llm_error_handling / sandbox_audit / summarization /
  title / todo / token_usage / tool_error_handling / tool_output_budget / uploads
backend/packages/harness/deerflow/guardrails/middleware.py
backend/packages/harness/deerflow/sandbox/middleware.py
backend/app/gateway/auth_middleware.py
backend/app/gateway/csrf_middleware.py
```

---

## 三、Tier 拆分方案（核心交付物）

### Tier 0 — 基线依赖对齐 `chore(deps)` · 9 提交 · 风险🟢
```
cryptography≥48.0.1  aiohttp 3.14.1  starlette 1.3.1  pydantic-settings 2.14.2
langsmith 0.8.18  python-multipart 0.0.31  uv.lock sync(#3679)  groundroute extra(#3678)
```
- **做法**：手动合并 `pyproject.toml` + 重新 `uv lock`，**不要 cherry-pick**（lock 文件无法三向合并）
- **验证**：`make install` + 容器重建

### Tier 1 — 性能优化 `perf` · 9 提交 · 风险🟢
```
runtime index by run_id/thread_id(#3686 #3562)  AppConfig O(1)(#3688)
SSE resume O(1)(#3700)  sandbox path-regex cache(#3713 #3647 #3657)
subagent msg dedup(#3687)  persistence column cache(#3654)
```
- **做法**：纯加索引/缓存，逻辑增强型，冲突多为函数内追加 → 多数可半自动合并
- **验证**：`make test`（perf 提交基本都带测试）

### Tier 2 — 低冲突 fix（按模块分 4 小批）· ~45 提交 · 风险🟡
| 小批 | 提交数 | 模块 |
|---|---|---|
| 2a sandbox | 8 | bash 不阻塞、binary 提示、heredoc 审计、glob 加速 |
| 2b gateway | 6 | token 归属、upload 替换、recursion_limit、admin 鉴权、thread_id |
| 2c channels | 7 | IM 相关——**注意**：记忆显示 ③ IM Channels 还有 service/manager bot-merge 未完成，这批与之强相关 |
| 2d 其余 | ~24 | serialization/memory/title/mcp/skills/artifacts 小修 |

### Tier 3 — 中间件链对齐 · ~10 提交 · 风险🔴🔴🔴（**最硬的骨头**）
```
#3809 declarative middleware builder(重构链结构)
#3412 TokenBudgetMiddleware(新增)  #3662 input sanitization(新增)
#3630/#3661 role isolation  #3566 title  #3746 ID-swap  #3709 todo fallback
```
- **为什么最危险**：上游把 17 个中间件改成"声明式 builder + 测试 pin 顺序"，eai 也深度改了同一批 14 个文件。合并时**必须保证 eai 的中间件顺序与定制逻辑不被覆盖**，且 eai 自加的中间件（ThreadData/Uploads/Sandbox/ViewImage 等）要重新挂到新 builder 上。
- **做法**：**单独分支**，逐文件人工合并 + 跑 `tests/test_*_middleware*.py`，不 cherry-pick 整提交
- **建议**：放最后做，前面的 Tier 铺平后再碰

### Tier 4 — 新功能 feat（独立可选，按需挑）· 27 提交 · 风险🟡~🔴
| 特性 | PR | 文件数 | eai 建议 |
|---|---|---|---|
| community web search/截图 | #3821 #3866 #3881 #3675 #3575 | 各 5-13 | 按需，eai 有自己的 data_source MCP |
| OIDC SSO | #3506 | 27 | **大概率跳过**（eai 用 cookie JWT） |
| E2B sandbox provider | #3883 | 13 | **大概率跳过**（eai 用本地 sandbox） |
| alembic 迁移 | #3706 | 24 | **建议引入**（eai 用 PG，迁移框架有用） |
| subagent 历史/委派账本 | #3845 #3877 | 27 | 看产品需求 |
| durable context / prompt 历史 / 重新生成 / 思考时长 | 多个 | 小 | 低成本可挑 |

### Tier 5 — frontend 独立战线 · 16+ 提交 · 风险🔴
- `content` 52 / `components` 29 / `core` 25 全冲突
- **必须单独分支 + 容器重建**（`make rebuild-frontend`；记忆里的 BlockNote 重复 selection bug 根因）
- 含 `#3677` login i18n、math 渲染、mobile 布局、artifacts 保留等

---

## 四、建议直接跳过的提交

| 提交 | 原因 |
|---|---|
| `#3760` TUI terminal workbench（41 文件） | eai 是 Web 产品，不需要终端 workbench |
| `#3703` frontend tests → rstest（41 文件） | **eai 用 Vitest**（CLAUDE.md 明确），迁移框架无意义且高冲突 |
| `#3770` AGENTS.md as source of truth | 上游把 CLAUDE.md 改成 import AGENTS.md；eai 的 CLAUDE.md 有大量定制指令，**保留 eai 版本** |
| `#3717` locale docs（54 文件） | 几乎全是文档链接本地化，价值低、diff 大 |

---

## 五、推荐执行顺序

```
Tier 0 (deps)  →  Tier 1 (perf)  →  Tier 2a/2b (sandbox/gateway fix)
        ↓ 每批: cherry-pick 或小 merge → make test → 容器重启验证 → commit
Tier 2c/2d → Tier 4(挑中的 feat) → Tier 5(frontend) → Tier 3(middleware，最后)
                                                              ↑ 最难，单独分支
```

**每个 Tier 独立 commit 到 `main-dev-fork`**（遵循分支约定），出问题 `git revert` 单个 Tier 即可。

---

## 六、复现 Dry-Run 的命令

```bash
# 上游领先提交数
git fetch bytedance main
git rev-list --count main..bytedance/main          # = 130

# 真实冲突文件（无副作用）
git merge-tree --write-tree --no-messages main-dev-fork bytedance/main \
  | grep -E '^[0-9]{6} [0-9a-f]{40} [123]	' | awk -F'\t' '{print $2}' | sort -u

# harness 结构性对冲
git diff --shortstat bytedance/main..main-dev-fork -- backend/packages/harness/
git diff --shortstat main..bytedance/main -- backend/packages/harness/

# 冲突热点交集
comm -12 \
  <(git diff --name-only main..bytedance/main | sort) \
  <(git diff --name-only bytedance/main..main-dev-fork | sort)
```

冲突文件完整清单见临时文件 `/tmp/upstream_conflict_files.txt`（会话级，不持久）。

---

## 七、待决策

1. Tier 4 特性挑选（OIDC / E2B / community / alembic 哪些要）——需产品需求拍板。
2. 从哪个 Tier 开始执行——建议 **Tier 0 → Tier 1**（零/低风险，验证 cherry-pick 流程）。
3. 执行时切 plan mode，逐 Tier 给出具体 cherry-pick 命令与冲突解决策略。
