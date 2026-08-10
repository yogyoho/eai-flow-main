# Upstream Sync Manifest — 2026-08-02

- Source ref: `7025ccee` (bytedance/deer-flow main)
- Compare refs: `4582a413`（上次同步点）→ `7025ccee`
- Local: `main-dev-fork`（HEAD e2eea9dd）
- 范围：**排除 `extensions/`**（EAI 定制）。方法：blob-SHA 全量对比 + Workflow 逐文件分类 + 深核代理（83 次 git diff）。
- **已确认无新增 npm 依赖**（shiki/code-editor 未加包 → 同步后无需镜像重建，restart frontend/gateway 即可）。

## 汇总

| 组 | 数量 | 处置 |
|---|---|---|
| A. B-core 纯落后 | 97 | fork==旧上游，取新版；其中前端 35 个分属 4 个功能簇 |
| B. PORTABLE | 21 | workflow 验证，直接复制 |
| 合计 | 118 | |

## 执行分 3 阶段（先低风险后高）

### 阶段 1 — 安全直接应用（87 个）：PORTABLE 21 + 后端 B-core 64

后端 B-core 64 = gateway 10 + harness 54（`git restore` 干净，无 EAI 冲突）。
PORTABLE 21 见 Group B。`extensions_config.example.json` 也在内（纯模板）。

```bash
# DRY RUN 先看影响面
git restore --source=7025ccee --dry-run -- <Group A 后端 + Group B 全部路径>
# 确认后应用
git restore --source=7025ccee -- <同上>
# 验证
docker exec deer-flow-gateway sh -c 'cd /app/backend && .venv/bin/python -c "import deerflow"'
```

### 阶段 2 — 前端 B-core 非簇文件（23 个）

i18n/*、core/mcp/*、core/threads/{hooks,static-demo,types}、input-box、settings-dialog-host、tool-settings-page、mock routes、workspace pages、auth/callback。
`git diff 4582a413 7025ccee -- <file>` 逐个确认无意外依赖后应用。

### 阶段 3 — 4 个功能簇（opt-in，整簇移植，含新文件）

深核结论：这些不是"跳过"，而是**整簇移植**才完整。执行顺序 簇3 → 簇2 → 簇1 → 簇4。

| 簇 | 复制新文件（D 类） | 覆盖 B 类 | EAI 手工合并点 |
|---|---|---|---|
| **簇3 shiki 高亮**（最小） | `ai-elements/shiki-highlight.ts` | `ai-elements/code-block.tsx` | 无 |
| **簇2 inline artifact 编辑** #4596/#4580/#4584/#4634 | `code-editor-extensions.ts`, `core/artifacts/{api,editing}.ts` | `code-editor.tsx`, `core/artifacts/{hooks,loader,preview,index}.ts`, `artifacts/{artifact-file-detail,context}.tsx`, mock artifact route, 后端 `gateway/routers/artifacts.py` | `app.py`（CUSTOM，merge 路由挂载）+ docmgr save-artifact-to-doc |
| **簇1 消息虚拟化** #4590/#4620 | `virtual-message-list.tsx`, `core/messages/derived-state.ts`, `core/dom/render-activity.ts` | `messages/{message-list,message-group,markdown-content}.tsx`, `chats/chat-box.tsx`, `core/messages/utils.ts` | `message-list-item.tsx`（EAI 自写，验证接口） |
| **簇4 context-usage** #3125/#3183 | `context-usage-badge.tsx`, `context-usage-format.ts`, 后端 `gateway/context_usage.py`（纯辅助，无路由） | `core/threads/{token-usage,types}.ts`, `token-usage-indicator.tsx` | `services.py` + `deps.py`（EAI 重写，手工合 `build_thread_checkpoint_state_accessor` + `get_config`，并在 run 管线/sse_consumer 调 `build_context_usage`） |

> EAI 定制文件（`services.py`/`deps.py`/`app.py`/`message-list-item.tsx`）**绝不 git restore**，只手工合 symbol。

## Group A — B-core（97）

### backend/app/gateway (10)
```
backend/app/gateway/authz.py
backend/app/gateway/routers/artifacts.py   ← 簇2
backend/app/gateway/routers/browser.py
backend/app/gateway/routers/console.py
backend/app/gateway/routers/feedback.py
backend/app/gateway/routers/mcp.py
backend/app/gateway/routers/models.py
backend/app/gateway/routers/scheduled_tasks.py
backend/app/gateway/routers/skills.py
backend/app/gateway/routers/uploads.py
```

### backend/packages/harness (54)
```
backend/packages/harness/deerflow/agents/lead_agent/agent.py
backend/packages/harness/deerflow/agents/lead_agent/prompt.py
backend/packages/harness/deerflow/agents/memory/backends/deermem/deermem/core/prompts/consolidation.yaml
backend/packages/harness/deerflow/agents/memory/backends/deermem/deermem/core/prompts/memory_update.chat.yaml
backend/packages/harness/deerflow/agents/memory/backends/deermem/deermem/core/updater.py
backend/packages/harness/deerflow/agents/memory/backends/mem0/config.py
backend/packages/harness/deerflow/agents/memory/backends/mem0/mem0_manager.py
backend/packages/harness/deerflow/agents/memory/manager.py
backend/packages/harness/deerflow/agents/memory/tools.py
backend/packages/harness/deerflow/agents/middlewares/sandbox_audit_middleware.py
backend/packages/harness/deerflow/client.py
backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox.py
backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py
backend/packages/harness/deerflow/community/aio_sandbox/ownership/factory.py
backend/packages/harness/deerflow/community/boxlite/box.py
backend/packages/harness/deerflow/community/browser_automation/session.py
backend/packages/harness/deerflow/community/e2b_sandbox/__init__.py
backend/packages/harness/deerflow/community/e2b_sandbox/e2b_sandbox.py
backend/packages/harness/deerflow/community/e2b_sandbox/e2b_sandbox_provider.py
backend/packages/harness/deerflow/config/app_config.py
backend/packages/harness/deerflow/config/checkpointer_config.py
backend/packages/harness/deerflow/config/database_config.py
backend/packages/harness/deerflow/config/extensions_config.py
backend/packages/harness/deerflow/config/model_config.py
backend/packages/harness/deerflow/config/paths.py
backend/packages/harness/deerflow/config/sandbox_config.py
backend/packages/harness/deerflow/mcp/tools.py
backend/packages/harness/deerflow/models/factory.py
backend/packages/harness/deerflow/persistence/bootstrap.py
backend/packages/harness/deerflow/persistence/engine.py
backend/packages/harness/deerflow/persistence/migrations/env.py
backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py
backend/packages/harness/deerflow/runtime/checkpointer/provider.py
backend/packages/harness/deerflow/runtime/events/store/jsonl.py
backend/packages/harness/deerflow/runtime/journal.py
backend/packages/harness/deerflow/runtime/runs/schemas.py
backend/packages/harness/deerflow/runtime/store/async_provider.py
backend/packages/harness/deerflow/runtime/store/provider.py
backend/packages/harness/deerflow/sandbox/local/local_sandbox.py
backend/packages/harness/deerflow/sandbox/local/local_sandbox_provider.py
backend/packages/harness/deerflow/sandbox/sandbox.py
backend/packages/harness/deerflow/sandbox/tools.py
backend/packages/harness/deerflow/scheduler/schedules.py
backend/packages/harness/deerflow/skills/storage/local_skill_storage.py
backend/packages/harness/deerflow/skills/storage/skill_storage.py
backend/packages/harness/deerflow/skills/storage/user_scoped_skill_storage.py
backend/packages/harness/deerflow/subagents/builtins/bash_agent.py
backend/packages/harness/deerflow/subagents/builtins/general_purpose.py
backend/packages/harness/deerflow/tools/builtins/task_tool.py
backend/packages/harness/deerflow/tools/skill_manage_tool.py
backend/packages/harness/deerflow/tui/session.py
backend/packages/harness/deerflow/uploads/manager.py
```

### frontend/src (33)
```
frontend/src/app/(auth)/auth/callback/page.tsx
frontend/src/app/mock/api/threads/[thread_id]/artifacts/[[...artifact_path]]/route.ts   ← 簇2
frontend/src/app/mock/api/threads/[thread_id]/history/route.ts
frontend/src/app/mock/api/threads/search/route.ts
frontend/src/app/workspace/chats/page.tsx
frontend/src/app/workspace/page.tsx
frontend/src/components/ai-elements/code-block.tsx                                       ← 簇3
frontend/src/components/workspace/artifacts/artifact-file-detail.tsx                     ← 簇2
frontend/src/components/workspace/artifacts/context.tsx                                  ← 簇2
frontend/src/components/workspace/browser-view/api.ts
frontend/src/components/workspace/browser-view/use-browser-stream.ts
frontend/src/components/workspace/chats/chat-box.tsx                                     ← 簇1
frontend/src/components/workspace/code-editor.tsx                                        ← 簇2
frontend/src/components/workspace/input-box.tsx
frontend/src/components/workspace/messages/markdown-content.tsx                          ← 簇1
frontend/src/components/workspace/messages/message-group.tsx                             ← 簇1
frontend/src/components/workspace/messages/message-list.tsx                              ← 簇1
frontend/src/components/workspace/settings/settings-dialog-host.tsx
frontend/src/components/workspace/settings/tool-settings-page.tsx
frontend/src/components/workspace/token-usage-indicator.tsx                              ← 簇4
frontend/src/core/artifacts/hooks.ts                                                     ← 簇2
frontend/src/core/artifacts/index.ts                                                     ← 簇2
frontend/src/core/artifacts/loader.ts                                                    ← 簇2
frontend/src/core/artifacts/preview.ts                                                   ← 簇2
frontend/src/core/i18n/context.tsx
frontend/src/core/i18n/hooks.ts
frontend/src/core/i18n/server.ts
frontend/src/core/i18n/translations.ts
frontend/src/core/mcp/api.ts
frontend/src/core/mcp/hooks.ts
frontend/src/core/messages/utils.ts                                                      ← 簇1
frontend/src/core/threads/hooks.ts
frontend/src/core/threads/static-demo.ts
frontend/src/core/threads/token-usage.ts                                                 ← 簇4
frontend/src/core/threads/types.ts                                                       ← 簇4
```

## Group B — PORTABLE（21，workflow 验证）

```
backend/packages/harness/deerflow/skills/projection.py          # 新文件，app.py lifespan 会用
backend/packages/harness/deerflow/utils/thread_id.py            # 新文件，自包含
extensions_config.example.json                                  # 纯模板
frontend/src/core/messages/workspace-change-anchor.ts           # 缺，工作树副本==上游 blob
frontend/src/core/workspace-changes/api.ts                      # 本地仅差 UTF-8 BOM
scripts/_detector_cli.py
scripts/bump_version.sh
scripts/deploy.sh
scripts/detect_blocking_io_static.py
scripts/detect_thread_boundaries.py
scripts/detect_uv_extras.py
scripts/scan_changed_blocking_io.py
scripts/setup-sandbox.sh
scripts/setup_wizard.py
scripts/support_bundle.py
scripts/tool-error-degradation-detection.sh
scripts/wizard/providers.py
scripts/wizard/steps/channels.py
scripts/wizard/steps/llm.py
scripts/wizard/ui.py
scripts/wizard/writer.py
```
