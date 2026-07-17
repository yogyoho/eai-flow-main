# 上游差分分类分析 2026-07-17

**状态**：`main-dev-fork` vs `bytedance/main`（tip `69350787`，本地缓存）
**方法**：`git diff --name-only --diff-filter=M` → 588 文件 → 排除 tests/docs/content/scripts → 312 代码文件

---

## 总览

| 分类 | 数量 | 处理方式 |
|------|------|----------|
| 🔵 EAI 定制（保留） | ~80 | 不动 |
| 🟢 Port 残留（已是同步态） | ~30 | 不动（功能等价） |
| 🟡 大 Config（待专项） | 3 | 专项对齐 |
| ⚪ 微小差异（ROI 趋零） | ~40 | 不动 |
| 🔴 可 Port 上游特性 | ~8 | **可获取新功能** |

---

## 一、🔵 EAI 定制 — 保留（~80 文件）

这些是 EAI 有意与上游分叉的代码。

### 1.1 IM Channels（13 文件，~2000 行差异）
EAI 自有的飞书/微信/钉钉/Telegram/Slack/Discord/WeCom 通道体系。

| 文件 | 差异行 | 说明 |
|------|--------|------|
| `backend/app/channels/manager.py` | 1194 | EAI IM 管理器（核心） |
| `backend/app/channels/feishu.py` | 429 | 飞书通道 |
| `backend/app/channels/telegram.py` | 322 | Telegram 通道 |
| `backend/app/channels/slack.py` | 254 | Slack 通道 |
| `backend/app/channels/wechat.py` | 242 | 微信通道 |
| `backend/app/channels/dingtalk.py` | 170 | 钉钉通道 |
| `backend/app/channels/discord.py` | 140 | Discord 通道 |
| `backend/app/channels/wecom.py` | 122 | 企业微信通道 |
| `backend/app/channels/service.py` | 110 | Channel 服务 |
| `backend/app/channels/base.py` | 73 | Channel 基类 |
| `backend/app/channels/commands.py` | 47 | Channel 命令 |
| `backend/app/channels/message_bus.py` | 25 | 消息总线 |
| `backend/app/channels/runtime_config_store.py` | 4 | Runtime 配置存储 |

### 1.2 EAI Sandbox（6 文件，~775 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `backend/.../community/aio_sandbox/aio_sandbox_provider.py` | 518 | EAI sandbox provider |
| `backend/.../community/aio_sandbox/local_backend.py` | 60 | 本地后端 |
| `backend/.../community/aio_sandbox/aio_sandbox.py` | 57 | Sandbox 实现 |
| `backend/.../community/aio_sandbox/remote_backend.py` | 51 | 远程后端 |
| `backend/.../community/aio_sandbox/backend.py` | 10 | 后端基类 |
| `backend/.../sandbox/local/local_sandbox.py` | 80 | 本地 sandbox |

### 1.3 EAI Skills（9 文件，~730 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `skills/public/podcast-generation/scripts/generate.py` | 349 | 播客生成 |
| `skills/public/video-generation/scripts/generate.py` | 262 | 视频生成 |
| `skills/public/image-generation/scripts/generate.py` | 258 | 图像生成 |
| `skills/public/skill-creator/SKILL.md` | 49 | Skill 创建器 |
| `skills/public/podcast-generation/SKILL.md` | 22 | 播客 SKILL |
| `skills/public/image-generation/SKILL.md` | 21 | 图像 SKILL |
| `skills/public/video-generation/SKILL.md` | 12 | 视频 SKILL |
| `skills/public/claude-to-deerflow/scripts/chat.sh` | 8 | Claude 桥接 |
| `skills/public/claude-to-deerflow/scripts/status.sh` | 4 | 状态查询 |

### 1.4 i18n 本地化（3 文件，~1387 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `frontend/src/core/i18n/locales/zh-CN.ts` | 486 | 简体中文 |
| `frontend/src/core/i18n/locales/en-US.ts` | 472 | 英文（含 EAI 自定义键） |
| `frontend/src/core/i18n/locales/types.ts` | 416 | i18n 类型定义 |

### 1.5 Landing Page（8 文件，~400 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `frontend/src/components/landing/hero.tsx` | 104 | Hero 区域 |
| `frontend/src/components/landing/progressive-skills-animation.tsx` | 46 | 技能动画 |
| `frontend/src/components/landing/sections/sandbox-section.tsx` | 16 | Sandbox 区域 |
| `frontend/src/components/landing/sections/whats-new-section.tsx` | 2 | 更新区域 |
| `frontend/src/components/landing/sections/case-study-section.tsx` | 2 | 案例区域 |
| `frontend/src/components/landing/header.tsx` | 19 | 头部导航 |
| `frontend/src/components/landing/section.tsx` | 12 | 通用 Section |
| `frontend/src/components/landing/footer.tsx` | 2 | 页脚 |

### 1.6 Docker / 部署（9 文件，~590 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `docker/provisioner/app.py` | 394 | EAI provisioner |
| `docker/nginx/nginx.conf` | 278 | Nginx 配置 |
| `docker/docker-compose-dev.yaml` | 209 | Docker Compose |
| `docker/docker-compose.yaml` | 65 | 生产 Compose |
| `docker/provisioner/README.md` | 47 | Provisioner 文档 |
| `docker/nginx/nginx.local.conf` | 38 | 本地 Nginx |
| `docker/dev-entrypoint.sh` | 34 | Dev 入口 |
| `backend/Dockerfile` | 27 | Backend Dockerfile |
| `frontend/Dockerfile` | 5 | Frontend Dockerfile |

### 1.7 EAI Gateway 定制（8 文件，~1500 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `backend/app/gateway/services.py` | 618 | 服务层（EAI 扩展） |
| `backend/app/gateway/routers/auth.py` | 376 | 认证路由（EAI auth） |
| `backend/app/gateway/app.py` | 374 | Gateway app（EAI 中间件/路由） |
| `backend/app/gateway/deps.py` | 240 | 依赖注入（EAI 扩展） |
| `backend/app/gateway/langgraph_auth.py` | 107 | LangGraph 认证 |
| `backend/app/gateway/auth_middleware.py` | 98 | Auth 中间件 |
| `backend/app/gateway/auth_disabled.py` | 68 | Auth 禁用 shim |
| `backend/app/gateway/internal_auth.py` | 60 | 内部认证 |

### 1.8 EAI Frontend 定制（~15 文件，~4000 行差异）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `frontend/src/core/threads/hooks.ts` | 1961 | 线程 hooks（核心改动） |
| `frontend/src/components/workspace/input-box.tsx` | 1727 | 输入框（EAI 定制） |
| `frontend/src/styles/globals.css` | 1147 | 全局样式 |
| `frontend/src/components/workspace/messages/message-list.tsx` | 989 | 消息列表 |
| `frontend/src/app/workspace/chats/[thread_id]/page.tsx` | 437 | 聊天页 |
| `frontend/src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx` | 401 | Agent 聊天页 |
| `frontend/src/core/streamdown/preprocess.ts` | 295 | 流预处理 |
| `frontend/src/components/workspace/chats/chat-box.tsx` | 289 | 聊天框 |
| `frontend/src/components/workspace/messages/message-list-item.tsx` | 285 | 消息项 |
| `frontend/src/components/workspace/recent-chat-list.tsx` | 274 | 最近聊天 |
| `frontend/src/components/workspace/messages/markdown-content.tsx` | 144 | Markdown 渲染 |
| `frontend/src/components/workspace/messages/message-group.tsx` | 138 | 消息分组 |
| `frontend/src/components/workspace/messages/subtask-card.tsx` | 121 | 子任务卡片 |
| `frontend/src/components/workspace/artifacts/artifact-file-detail.tsx` | 84 | 产件详情 |
| `frontend/src/components/workspace/welcome.tsx` | 64 | 欢迎页 |

### 1.9 EAI Docs / Meta / Config（~12 文件）
| 文件 | 差异行 | 说明 |
|------|--------|------|
| `CLAUDE.md` | 284 | EAI 项目指引 |
| `README_zh.md` | 270 | 中文 README |
| `README.md` | 161 | 英文 README |
| `AGENTS.md` | 175 | Agent 指引 |
| `backend/AGENTS.md` | 924 | Backend Agent 指引 |
| `backend/CLAUDE.md` | 653 | Backend CLAUDE |
| `frontend/CLAUDE.md` | 101 | Frontend CLAUDE |
| `frontend/AGENTS.md` | 183 | Frontend Agent |
| `backend/README.md` | 138 | Backend README |
| `backend/CONTRIBUTING.md` | 92 | 贡献指南 |
| `CONTRIBUTING.md` | 29 | 根贡献指南 |
| `CODE_OF_CONDUCT.md` | 2 | 行为准则 |
| `SECURITY.md` | 4 | 安全策略 |
| `.env.example` | 43 | 环境变量示例 |
| `frontend/.env.example` | 8 | 前端环境变量 |
| `backend/debug.py` | 2 | 调试脚本 |

---

## 二、🟢 Port 残留 — 已是同步态（~30 文件）

这些文件已通过 cherry-port 拿到上游功能，但仍有轻微差异（格式、import 顺序、EAI 条件分支等）。

### 2.1 Middlewares（~18 文件）
| 文件 | 差异行 | 同步状态 |
|------|--------|----------|
| `summarization_middleware.py` | 570 | ✅ 功能等价 |
| `skill_activation_middleware.py` | 364 | ✅ #4103 ported |
| `dynamic_context_middleware.py` | 339 | ✅ 功能等价 |
| `tool_error_handling_middleware.py` | 321 | ✅ 功能等价 |
| `tool_output_budget_middleware.py` | 250 | ✅ 功能等价 |
| `token_budget_middleware.py` | 206 | ✅ 功能等价 |
| `uploads_middleware.py` | 162 | ✅ 功能等价 |
| `loop_detection_middleware.py` | 146 | ✅ #4072 ported |
| `clarification_middleware.py` | 122 | ✅ 功能等价 |
| `dangling_tool_call_middleware.py` | 117 | ✅ #4080 ported |
| `llm_error_handling_middleware.py` | 104 | ✅ 功能等价 |
| `input_sanitization_middleware.py` | 101 | ✅ #4137/#4155 ported |
| `title_middleware.py` | 86 | ✅ 功能等价 |
| `delegation_ledger.py` | 70 | ✅ 功能等价 |
| `skill_context.py` | 69 | ✅ 功能等价 |
| `view_image_middleware.py` | 40 | ✅ #4140 ported  |
| `memory_middleware.py` | 23 | ✅ 功能等价 |
| `durable_context_middleware.py` | 20 | ✅ 功能等价 |
| `subagent_limit_middleware.py` | 4 | ✅ 功能等价 |
| `thread_data_middleware.py` | 2 | ✅ 功能等价 |

### 2.2 Gateway Routers（~7 文件）
| 文件 | 差异行 | 同步状态 |
|------|--------|----------|
| `routers/threads.py` | 675 | ✅ #3800 ported |
| `routers/thread_runs.py` | 604 | ✅ 功能等价 |
| `routers/skills.py` | 242 | ✅ 功能等价 |
| `routers/uploads.py` | 180 | ✅ 功能等价 |
| `routers/mcp.py` | 159 | ✅ #3552 ported |
| `routers/agents.py` | 138 | ✅ 功能等价 |
| `routers/memory.py` | 282 | ✅ 功能等价 |
| `routers/channel_connections.py` | 46 | ✅ E-续 ported |
| `routers/channels.py` | 10 | ✅ E-续 ported |
| `routers/suggestions.py` | 80 | ✅ 功能等价 |
| `routers/artifacts.py` | 16 | ✅ 功能等价 |
| `routers/__init__.py` | 28 | ✅ 功能等价 |

### 2.3 Harness Core（~10 文件）
| 文件 | 差异行 | 同步状态 |
|------|--------|----------|
| `lead_agent/agent.py` | 344 | ✅ 功能等价 |
| `lead_agent/prompt.py` | 367 | ✅ #4137 ported |
| `subagents/executor.py` | 480 | ✅ #4215 ported |
| `subagents/status_contract.py` | 284 | ✅ E-续① ported |
| `agents/thread_state.py` | 121 | ✅ #4140 ported |
| `config/agents_config.py` | 223 | ✅ #4136 ported |
| `config/app_config.py` | 150 | ✅ 功能等价 |
| `config/subagents_config.py` | 103 | ✅ 功能等价 |
| `config/paths.py` | 92 | ✅ 功能等价 |
| `config/memory_config.py` | 84 | ✅ 功能等价 |
| `config/extensions_config.py` | 1 | ✅ 功能等价 |
| `tools/builtins/tool_search.py` | 232 | ✅ 功能等价 |
| `tools/builtins/task_tool.py` | 187 | ✅ #4161 ported |
| `tools/builtins/update_agent_tool.py` | 84 | ✅ #4219 ported |
| `tools/builtins/view_image_tool.py` | 8 | ✅ #4140 ported |
| `tools/builtins/present_file_tool.py` | 35 | ✅ 功能等价 |
| `tools/builtins/__init__.py` | 8 | ✅ 功能等价 |
| `tools/tools.py` | 5 | ✅ 功能等价 |
| `mcp/tools.py` | 125 | ✅ #4154 ported |
| `mcp/cache.py` | 56 | ✅ #4124 ported |
| `mcp/client.py` | 44 | ✅ 功能等价 |
| `mcp/session_pool.py` | 19 | ✅ 功能等价 |
| `runtime/runs/worker.py` | 1024 | ✅ 功能等价 |
| `runtime/runs/manager.py` | 957 | ✅ 功能等价 |
| `runtime/journal.py` | 231 | ✅ 功能等价 |

---

## 三、🟡 大 Config — 待专项（3 文件）

| 文件 | 差异行 | 说明 |
|------|--------|------|
| `config.example.yaml` | 969 | EAI 模型/工具/沙箱/内存配置体系不同，需整体设计 |
| `docker/docker-compose-dev.yaml` | 209 | EAI 容器编排体系不同 |
| `frontend/package.json` | 52 | 依赖版本差异（EAI 前端额外依赖） |

---

## 四、🔴 可 Port 上游特性（~8 文件）

这些是有实质性功能差距、可以获取上游新特性的文件。

### 4.1 #4098 — allowed-tools 仅作用于 active skill（+2008 行/25 文件）
**上游 PR**：`65afc9b1` — 新 `SkillToolPolicyMiddleware`，将 tool policy 从"全部已启用 skill"收窄到"当前 run active 的 skill"。
**当前状态**：EAI 已有 tool_policy 基建（最近 commit `1694a45f`），但上游有更精细的 active-skill 维度。
**Port 难度**：中（+364 行 middleware，需适配 EAI 的 tool_policy 参数）
**建议**：专项评估后 port。

### 4.2 #3377 — oversized tool output 结构化摘要（+889 行）
**上游 PR**：`756eac0d` — `tool_output_synopsis.py` middleware，超大工具输出生成 LLM synopsis 替代完整粘贴。
**当前状态**：EAI 有 `tool_output_budget_middleware.py`（截断），但无 LLM synopsis 能力。
**Port 难度**：中（+635 行新中间件，需接入 LLM 调用）
**建议**：特性采纳，改进大工具输出体验。

### 4.3 `models/factory.py`（153 行差异）
**上游新增**：`_normalize_openai_base_url` / `_warn_unknown_model_settings` / `stream_chunk_timeout`。
**当前状态**：EAI 的 factory.py 较旧，缺失这些 helper。
**Port 难度**：低（逐函数 port）
**建议**：Port OpenAI-compat helpers。

### 4.4 `client.py`（285 行差异）
**上游新增**：LangGraph SDK client 新特性和修复。
**当前状态**：EAI client 落后。
**Port 难度**：中（需保留 EAI 的 contextvar 用户传播）
**建议**：Diff 对比后选择性 port。

### 4.5 `sandbox/tools.py`（559 行差异）
**上游改进**：Sandbox 工具增强。
**当前状态**：EAI sandbox 工具集不同。
**Port 难度**：中（与 EAI aio_sandbox 定制有交叉）
**建议**：评估上游新增工具，选择性采纳。

### 4.6 TUI 模块（~300 行差异，4 文件）
| 文件 | 差异行 |
|------|--------|
| `tui/view_state.py` | 120 |
| `tui/session.py` | 115 |
| `tui/runtime.py` | 57 |
| `tui/cli.py` | 6 |
| `tui/app.py` | 5 |
**当前状态**：EAI TUI 有不同 CLI 入口。
**Port 难度**：低（TUI 是开发者工具，不影响产品）
**建议**：低优先，可全量同步。

### 4.7 `guardrails/middleware.py`（110 行差异）
**上游改进**：Guardrails 中间件增强。
**当前状态**：EAI guardrails 较旧。
**Port 难度**：低（功能模块相对独立）
**建议**：Diff 对比后 port。

### 4.8 `sandbox/local/local_sandbox_provider.py`（181 行差异）
**上游改进**：本地 sandbox provider 改进。
**当前状态**：EAI 定制较多。
**Port 难度**：中
**建议**：选择性采纳非冲突部分。

---

## 五、⚪ 微小差异 — ROI 趋零（~40 文件）

差异 ≤ 5 行的文件，大部分是 import 调整、类型标注、格式化差异。

| 差异行 | 文件列表 |
|--------|----------|
| 1 | `frontend/src/core/skills/type.ts`, `frontend/src/core/skills/index.ts`, `frontend/src/core/auth/static-user.ts`, `frontend/src/components/workspace/settings/notification-settings-page.tsx`, `backend/.../config/extensions_config.py` |
| 2 | `frontend/tsconfig.json`, `frontend/src/lib/ime.ts`, `frontend/src/core/streamdown/index.ts`, `frontend/src/components/workspace/workspace-sidebar.tsx`, `frontend/src/components/workspace/settings/settings-section.tsx`, `frontend/src/components/ui/sidebar.tsx`, `frontend/src/components/ui/select.tsx`, `frontend/src/components/ui/input-group.tsx`, `frontend/src/components/ui/card.tsx`, `frontend/src/components/landing/sections/whats-new-section.tsx`, `frontend/src/components/landing/sections/case-study-section.tsx`, `frontend/src/components/landing/footer.tsx`, `frontend/src/components/ai-elements/toolbar.tsx`, `frontend/src/components/ai-elements/suggestion.tsx`, `frontend/src/components/ai-elements/panel.tsx`, `frontend/src/components/ai-elements/controls.tsx`, `frontend/public/demo/...`, `frontend/eslint.config.js`, `backend/.../community/image_search/tools.py`, `backend/.../thread_data_middleware.py`, `backend/debug.py`, `CODE_OF_CONDUCT.md` |
| 3 | `frontend/src/core/skills/hooks.ts`, `frontend/src/components/workspace/export-trigger.tsx`, `frontend/src/components/ui/sonner.tsx`, `backend/.../runtime/runs/__init__.py` |
| 4 | `skills/public/claude-to-deerflow/scripts/status.sh`, `frontend/src/core/rehype/index.ts`, `frontend/src/core/mcp/hooks.ts`, `frontend/src/components/workspace/settings/about-settings-page.tsx`, `frontend/src/components/ui/spotlight-card.css`, `frontend/src/components/ui/dropdown-menu.tsx`, `frontend/src/components/theme-provider.tsx`, `frontend/src/app/api/memory/route.ts`, `frontend/src/app/api/memory/[...path]/route.ts`, `frontend/README.md`, `backend/.../subagent_limit_middleware.py`, `backend/app/channels/runtime_config_store.py`, `SECURITY.md` |
| 5 | `frontend/src/mdx-components.ts`, `frontend/src/core/auth/types.ts`, `frontend/Dockerfile`, `backend/.../tui/app.py`, `backend/.../tools/tools.py` |

**处理建议**：全部不动。这些差异不产生功能差距，强行 port 反而增加风险。

---

## 六、建议操作

### 立即（低风险、高收益）
1. **`models/factory.py` port** — OpenAI-compat helpers（~150 行，独立模块）
2. **`guardrails/middleware.py` port** — 安全加固（~110 行，独立模块）
3. **TUI 模块全量同步** — 开发者工具，不影响产品（~300 行）

### 短期（专项评估后 port）
4. **#4098 active-skill tool policy** — 大幅改进 tool 权限粒度
5. **#3377 tool output synopsis** — 大工具输出 LLM 摘要

### 长期（架构级，需独立设计）
6. **#4064 cancel→lease** — 多 worker 稳定性
7. **#4122 memory 抽象层** — 可插拔 memory
8. **#4115 delegation cap** — 委派上限
9. **#4118 run-duration** — checkpoint 持久化时长

### 不动
- **EAI 定制**（80 文件）— IM/沙箱/前端/登录页/i18n/Docker
- **Port 残留**（30 文件）— 功能已同步
- **微小差异**（~40 文件）— ROI 趋零
- **大 Config**（3 文件）— 待专项设计

---

*维护者：本文件由 AI 辅助生成，2026-07-17。后续按此分类执行 port。*
