# 上游同步差距文档（post-history-rewrite）

- **日期**：2026-07-16
- **上游**：`bytedance/deer-flow` `main`（tip `94a34f38`，2026-07-16）
- **本地分支**：`main-dev-fork`（tip `2be7b6c4`，已 push 到 `origin/main-dev-fork`）
- **性质**：本轮为**按 PR cherry-port**（非 merge），共移植 8 个 commit；记录已移植 / 已推迟 / 不适用三类清单与方法，供后续续 port 参考。
- **前置文档**：`docs/upstream-sync-dryrun-2026-07-03.md`（历史同步 dry-run，pre-history-rewrite 状态）

---

## 一、执行摘要

上游 `bytedance/main` 在 2026-07-03 前后**重写了 git 历史**：现仅 202 个 commit，根 commit `48477d86`（2026-07-03，无父节点）。我们的 `main-dev-fork`（2661 个 commit）与上游 **`git merge-base` 为空 = unrelated histories**。

**关键结论：**

| 事项 | 结论 |
|---|---|
| 能否 `git merge` / `rebase` 上游 | **否**——直接 diff 显示整个代码库 ~146 万行，无意义。只能按 PR cherry-port。 |
| 正确同步姿势 | `git fetch bytedance` → 按主题挑 commit → `git show <hash>` 看改动 → 对照我们 harness 逐处 port → 跑该模块测试 → commit → `restart gateway`。 |
| `origin/main` 状态 | 被强推到与 `bytedance/main` 同点（`94a34f38`），作上游镜像。 |
| 本轮命中情况 | 评估 ~30 个上游 PR，**8 个 clean-port**、6 个架构级 defer、8+ 个 N/A（我们 fork 无对应模块/函数）。 |

**净效果**：上游"干净定点修复"基本见底；剩余要么是架构级大件（需独立设计），要么是我们 fork 根本没有的模块（上游走了我们没有的演进路线）。

---

## 二、已移植清单（8 commit，已 push）

| Commit | 上游 PR | 文件 | 内容 | 验证 |
|---|---|---|---|---|
| `a54c7098` | #4137 #4157 #4162 #4155 | `lead_agent/prompt.py`、`memory/prompt.py`、`input_sanitization_middleware.py` | **安全 XSS**：在 `<soul>` / subagent-desc / `<conversation>` 渲染点 `html.escape(quote=False)`；输入净化否决名单 16→38（补 soul/thinking_style/critical_reminders/skill/memory/durable-context 等权威标签 + `system_reminder` 下划线拼写）。#4182 不适用（见下）。 | input-sanitization 92 + memory-updater 54 + lead-prompt 15 过 |
| `e7b52906` | #4072 #4080 #3800 | `loop_detection_middleware.py`、`dangling_tool_call_middleware.py`、`threads.py` | **稳定性**：LoopDetection 工具频率计数器改滑窗（deque + Counter，窗口取最大 hard limit）；丢弃孤儿 ToolMessage；`create_thread` 插入竞态幂等（catch `IntegrityError`）。 | loop_detection 65 + dangling 28 + threads 22 过 |
| `1ace09ed` | #4161 #4136 | `general_purpose.py`、`input_sanitization_middleware.py`、`agents_config.py` | **agent**：general-purpose subagent 系统提示加 `<tool_restrictions>` 禁用 task；`load_agent_soul` 在目录缺 config.yaml 时回退查 per-user/legacy 目录。 | subagent_prompt 6 + slash/skill 40 过 |
| `4b695047` | #4154 #4124 | `mcp/tools.py`、`lead_agent/prompt.py`、`mcp/cache.py` | **MCP 加固**：加载边界校验工具名（丢弃非 `^[A-Za-z0-9_-]+$`）+ deferred 工具名 html.escape；缓存失效改 **路径 + (mtime,size,sha256)** 内容签名（镜像 `app_config`）。 | tool_search 7 + cache smoke 过 |
| `99bbffd7` | #4140 | `thread_state.py`、`view_image_tool.py`、`view_image_middleware.py` | **checkpoint**：`ViewedImageData` 只存元数据（mime_type/size/actual_path），中间件按需从磁盘读 + `asyncio.to_thread` 编码；tool 加 TOCTOU 守卫；注入消息带 `hide_from_ui`。消除 base64 在每个 checkpoint 的 O(n·steps) 膨胀。 | view_image + thread_state 71 过 |
| `a475c790` | #4215 | `subagents/executor.py` | **subagent**：子进程 `run_config` 不再塞 checkpoint 坐标，LangGraph 从父 run 继承 → 保留 subgraph namespace。`thread_id` 改经 `context` 下发。 | subagent_executor 47 过（8 预存错误无关） |
| `bab8af3a` | #4103 | `skill_activation_middleware.py`、`runtime/secret_context.py` | **skills**：slash skill 改按 run context 去重（消息 id / 内容摘要），避免每次 model call 重读 SKILL.md / 重注入 / 重复审计。 | slash/skill 40 过 |
| `2be7b6c4` | #3552 | `app/gateway/routers/mcp.py` | **MCP IO**：MCP 配置更新的阻塞 RMW offload 到 worker 线程 + `asyncio.Lock` 串行化并发写入。 | config-update 50 过 |

**相对上游的 deliberate 修正**（因 unrelated histories 无 resync 顾虑，取正确版）：
- **#4072**：evict/reset 同时清镜像 `_tool_name_counter`（上游漏清，线程复用会残留陈旧计数）。
- **#4140**：注入消息 `hide_from_ui` 同时加到 sync + async 两条路径（上游只加 async）——与我们 delegation/durable/dynamic 中间件约定一致。

---

## 三、已推迟清单（架构级，需独立设计——勿批量 port）

每个都深改 harness core 或运行生命周期，且我们 fork 该区域定制多 / 缺前置基建，直接 cherry-port 会是死代码或灾难冲突。

| PR | 主题 | 规模 | 推迟原因 / port 前置条件 |
|---|---|---|---|
| **#4122** | 可插拔 memory 抽象层（DeerMem backend） | 大 | 引入 `MemoryManager` ABC + `DeerMem` backend，我们 fork 的 memory 模块仍是老 file-based `storage.py`，无此基座。#3556 / #4143 / #4181 / #4217 全部 on top of #4122。需先整体评估是否引入抽象层。 |
| **#4127** | 可插拔 AuthorizationProvider（Phase 0） | +1375 行/10 文件 | Phase 0 脚手架（540 测试 + 528 RFC 文档），无实际鉴权落地；与我们 `app/gateway/authz.py`（`Permissions`/`AuthContext`/`require_permission`）平行冲突。等 Phase 1+ 有功能价值再评估。 |
| **#4179** | 四类 HTTP 身份源分类 | 纯文档 | API.md / AUTH_DESIGN.md +157 行；我们 auth 模型不同，文档需重写非直移。低优先。 |
| **#4064** | cancel→lease 接管（多 worker） | ~500 行/7+ 文件 | **整个 multi-worker ownership epic 基建在我们 fork 缺失**：`owner_worker_id`/`lease_expires_at`/`update_lease`/`_renew_leases`/`heartbeat`/`RunOwnershipConfig`/`grace_seconds`/`CancelOutcome` 全部 grep 零命中。#4064 是该 epic 的 work item 4；item 1-3（lease/heartbeat/worker-id 基建）都没有。要 port 必须先整体采纳 ownership epic（含 SQL schema 加 lease 列、heartbeat 后台任务、worker 标识）——重大特性引入决策，非 cherry-port。 |
| **#4118** | checkpoint 持久化 run 时长 | 786 行 | 深改 `worker.py`(+190) / `threads.py`(+150)，运行生命周期特性，定制多。 |
| **#4115** | subagent 单 run 总委派上限 | 290 行/9 文件 | 计数依赖 delegation 条目的 `id`+`run_id` 字段，我们 `DelegationEntry` 还是老的 `{task_id,description,subagent_type,status}`——直移永远计 0（死代码）。需先 port delegation-ledger 的 run_id 打标基建。 |
| **#4193** | 清洗非法 tool-call 参数 | 中 | 依赖 #4119 的工具名清洗基础设施（`_sanitize_ai_message_tool_calls` / `_normalize_tool_name` / `_valid_tool_name`），我们 fork 缺。需先 port #4119。 |

---

## 四、不适用清单（我们 fork 无对应模块/函数）

上游走了我们没有的演进路线，目标代码在我们 fork 不存在——直移无从下手。

| PR | 缺失内容 |
|---|---|
| **#4104 / #4131 / #4218**（GitHub channels） | 我们 fork 无 `app/gateway/github/`。IM 通道是飞书/Slack/Telegram/钉钉，未集成 GitHub。 |
| **#4153**（skillscan network sinks） | 无 `skills/skillscan/` 模块。 |
| **#4146 / #4102**（model factory OpenAI-compat / stream_chunk_timeout） | 我们 `models/factory.py` 太旧，缺 `_normalize_openai_base_url` / `_warn_unknown_model_settings` / `stream_chunk_timeout`（它们重构的函数我们根本没有）。 |
| **#4090**（DB baseline backfill Index） | 无 `persistence/bootstrap.py`（legacy baseline `create_all` 路径），用了不同的 DB provisioning 方式。 |
| **#4182**（summarization html.escape） | 我们 `summarization_middleware.py` 已重构，整个 harness grep `<existing_summary>`/`<new_messages>` **0 命中**——上游修的漏洞结构在我们这儿不存在。 |
| **#4160**（skills warm-cache 冷启动） | 我们 `get_enabled_skills_for_config(None)` 直连磁盘（`_get_enabled_skills()`），无上游 #4144 的 warm-cache 冷启动空 bug——改了反而破坏 5 个测试，已回退。 |

---

## 五、方法与陷阱

### 5.1 Cherry-port 工作流

```
git fetch bytedance                              # 拉上游（不动 working tree）
git log --oneline main-dev-fork..bytedance/main  # 看上游领先 commit（注意：无 merge-base，此数=上游全部）
git show <hash> -- <path>                        # 逐个看改动
# 对照我们 fork：grep/Read 确认目标函数存在 + 是否匹配 pre-PR 状态
# port（Edit）→ py_compile → ruff → 跑该模块 tests → 若改 harness 则 docker compose -p eai-docker restart gateway
git add <files> && git commit                    # 只 add 本次相关文件，不夹带 .wolf/* 等无关 dirty
```

### 5.2 验证陷阱（重要）

host 环境 `cd backend && PYTHONPATH=. uv run pytest` 有**多处预存失败**，与 port 无关，**勿误判为回归**：

| 测试文件 | 预存失败 | 性质 |
|---|---|---|
| `test_custom_agent.py` | 29（TestAgentsAPI CRUD/404） | 需 Docker PostgreSQL DB / app fixtures |
| `test_subagent_executor.py` | 8（TracingWiring / GuardrailAttribution async fixtures） | async fixture 环境问题 |
| `test_mcp_file_migration.py` / `test_mcp_session_pool.py` | ~17 | 工具结果路径改写 / session pool cwd |

**验证一个 port 是否引入回归的正确方法**：`git stash push -- <改的文件>` → 重跑同一测试 → 比对失败数是否一致。一致 = 预存（无关）；变多 = 你的 port 有问题。已在 `.wolf/buglog.json` bug-056 记录此模式。

### 5.3 其它注意

- **重启**：harness/app 代码改动后需 `docker compose -p eai-docker restart gateway`（项目用 `-p eai-docker`，见 [[docker-compose-project]]）。健康探针：`docker exec deer-flow-gateway python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8001/health',timeout=2).status)"`。
- **ruff 误报**：`lead_agent/prompt.py` 有 2 个预存 E501（长提示文本 586/650 行）、`mcp/tools.py` 有 1 个预存 F401（未用 `Mapping`）——均非 port 引入，port 时比对"新增错误=0"即可。
- **测试缺口**：部分 port（如 #4124 cache、#4103 run-dedup）上游有专门测试但我们 fork 无对应测试文件，用 smoke 脚本或既有测试覆盖验证逻辑；如需锁定可后续补移植上游测试。

---

## 六、建议下一步

1. **挑一个 defer 项做专门设计 port**（影响面排序）：
   - **#4064 cancel→lease**：多 worker 运行稳定性，影响生产。
   - **#4122 memory 抽象层**：memory 子系统基座，后续多个 PR 依赖。
   - **#4115 delegation cap**：相对小，但需先 port delegation-ledger run_id 基建。
2. **补移植上游回归测试**：本批 port 中 #4124 / #4154 / #4103 / #4140 我们 fork 缺上游新增的测试文件，可单独一个 commit 把这些测试搬过来锁定行为。
3. **维持 cherry-port 节奏**：上游每周若干 commit，可定期（如每周）`git fetch bytedance` + 过一遍新 commit，port 干净定点修复，架构级继续 defer 记录。

---

## 七、附录：本次评估的上游 PR 全表

**已 port（8 commit，14 PR）**：#4072 #4080 #3800（stability）· #4137 #4157 #4162 #4155（security）· #4161 #4136（agent）· #4154 #4124（mcp）· #4140（checkpoint）· #4215（subagent）· #4103（skills）· #3552（mcp IO）

**已 defer（7）**：#4122 #4127 #4179 #4064 #4118 #4115 #4193

**N/A（8+）**：#4104 #4131 #4218（github）· #4153（skillscan）· #4146 #4102（factory）· #4090（db bootstrap）· #4182（summarizer）· #4160（skills warm-cache）

---

## 八、持续同步日志

### 2026-07-16（PM 续 fetch，上游 `94a34f38` → `69350787`，+7 commit）

- ✅ **#4219**（refuse empty SOUL.md in update_agent，+7 行）— 已 port（commit `44236b85`），16 测试过。
- ⏭️ **#4064** 复核：grep 确认**整个 multi-worker ownership epic 基建在我们 fork 缺失**（见第三节 #4064 行）——非"大"，而是"无基座"，需整体采纳 epic。
- ⏭️ **#4098**（allowed-tools 仅作用于 active skill）= **+2008 行/25 文件**，新 `SkillToolPolicyMiddleware`(+364)。这是我们 cerebrum bug-186 的"正解"，但是新 tool-policy 子系统的特性采纳，非 cherry-port。
- ⏭️ **#3377**（oversized tool output synopsis）= **+889 行**，新 `tool_output_synopsis.py`(+635) 中间件，特性采纳。
- N/A：#4245/#4209（frontend）、#4190（helm）、#4222（channels @mention——我们 fork 无 `extract_connect_code`，/connect 在 `manager.py` 内联解析，可改适配但非直移）。

**本轮净 port：1（#4219）。** 进一步印证第六节判断——剩余上游项以"特性采纳/epic 整体引入"为主，干净定点修复稀缺。

### 2026-07-16（PM2，#4122 评估 + #4181 适配）

- **#4122 评估结论**:memory core 是 vanilla 的(grep `eai/docmgr/contract` 零命中),冲突风险中低,是几个大件里**最可落地**的。但 56 文件/+4327/−2815、全部 memory 测试重写、config schema 变;pluggability 对我们**无即时需求**(无 fork 特性需换 backend)。**采纳 ROI 一般 → 建议暂不**,等真需要 fact 过期(#4143)或多 backend 时再做(独立分支整体迁移,~1-2 人日)。
- ✅ **#4181 数据安全收益已拿(方案 C,不走 #4122)**:在老 `MemoryUpdateQueue` 上直接加 `flush_sync(timeout)`(join 在途 worker → idle 短路 → daemon 线程 `Event.wait` 硬超时排空)+ `_processing_thread` 跟踪 + `skip_inter_item_delay`;gateway lifespan 在 channel 停后调用;新 `MemoryConfig.shutdown_flush_timeout_seconds`(默认 30)。commit `d7cd8bf0`。11 queue 测试 + flush smoke 过。
- ⏭️ ~~**#4143(per-fact 过期)** 仍需 #4122~~ → **✅ 已交付,绕开 #4122**(2026-07-16 PM3):发现 staleness review 基础特性 **#3860** 在 pre-#4122 结构(= 我们结构),于是走 #3860(base)+ #3993(id-less guard)+ #4143(per-fact 逻辑重映射到 #3860 结构)三段式,**完全不碰 #4122 的 56 文件 restructure**。LLM 给每个新 fact 赋 `expected_valid_days`(5 档,写入封顶 90×20=1800d),每个 fact 按自身窗口复审(非全局阈值);复审可 REMOVE 或 EXTEND(`new_evd=min(days_since+extend_by,3650d)`)。commits `72f10dc8`(#3860)+ `f3c3f775`(#4143+#3993)。88 memory 测试 + per-fact smoke 过。**这推翻了本节早先"#4143 绕不过 #4122"的判断**——关键是找到 #3860 在我们结构的基座。

### 2026-07-17（全量对齐 — 14 commits，118 文件差异清零）

**上游 fetch**：`bytedance/main` `bc6f1adc` → `9a4c72db`（+6 commit since last session）。

---

#### 第一轮：Harness 核心对齐（commits `2ff4ba32` ~ `16945a5a`）

| Commit | 文件 | 内容 |
|--------|------|------|
| `2ff4ba32` | 19 | items 1-6 直接 checkout（factory, guardrails, tui, sandbox, client, local_sandbox）+ 6 依赖适配 |
| `06cfa967` | 7 | #3377 tool-output-synopsis + #4098 skill-tool-policy |
| `56476a8a` | 12 | #4253 XSS 安全 + #4247 测试 + #4203 authz principal |
| `85be8de7` | 33 | cosmetic cleanup（amended：回退 4 个 gateway/router + runtime/store/base） |
| `84817dda` | 18 | 18 harness 残余（agents/mcp/persistence/runtime/sandbox/skills/tools） |
| `c9f8aa35` | 12 | aio_sandbox + worker/manager + subagents + delegation_ledger/skill_context |
| `1fc951d3` | 9 | runtime/store chain（provider/async_provider/events/base/memory/db）+ mcp/client + skills/parser |
| `d24b96f3` | 6 | persistence/run/sql + channel_connections/sql + journal + checkpointer/provider + installer + mcp/tools |
| `07d3f68a` | 18 | lead_agent（agent/prompt）+ 全量 middlewares（12 文件）+ task_tool/tool_search + skills/storage |
| `8c6095f1` | 8 | thread_state + community tools + update_agent/skill_manage + config（agents/subagents/memory） |
| `637e2411` | 2 | app_config + paths（取上游后回加 EAI UIConfig） |

**Harness 结果**：73→2（仅 `app_config.py` UIConfig + `paths.py` 细微差异）

---

#### 第二轮：Gateway 路由层对齐（commits `81c90943` ~ `0f80e667`）

| Commit | 文件 | 内容 |
|--------|------|------|
| `16945a5a` | 1 | `suggestions.py` 取上游（共享 llm_text + oneshot_llm utils） |
| `81c90943` | 9 | `skills/public/` 全部清零 |
| `f1750914` | 3 | auth shims（auth_disabled + internal_auth + utils） |
| `0f80e667` | 12 | **Phase 1+2**：deps.py +`require_admin_user` + 11 router 文件从上游 |

**Gateway 结果**：routers 13→3（仅 `auth.py` JWT 认证、`__init__.py` 路由注册、`suggestions.py` 超时保护）

---

#### 第三轮：增量上游 PR

- ✅ **#4235**（`13afef62`）: TUI /quit 中断活跃 run（commit `36d60887`）
- ⏭️ **#4231**（`9a4c72db`）: WeChat poll loop — EAI WeChat 深度定制，skip

---

#### 最终全景

| 指标 | 会话开始 | 会话结束 | 清理 |
|------|---------|---------|------|
| Python 总差异 | 289 | **171** | -118 |
| Harness 差异 | 73 | **1** | -72 |
| Gateway routers | 13 | **3** | -10 |
| skills/public | 9 | **0** | -9 |
| Gateway core | 7 | 7 | 0（全部有意保留） |
| 上游 PR 采纳 | — | **14** | — |
| Commits | — | **14** | — |
| 测试通过 | — | gateway 200 OK + 51/51 | — |

**剩余 171 个差异内部分布**：
- 138 tests（EAI 测试体系，不操作）
- 11 channels（EAI IM 产品核心，不操作）
- 10 scripts + 1 docker（EAI 运维，不操作）
- 7 gateway/core（EAI 认证/服务/DI，架构基石）
- 3 gateway/routers（有意保留）
- 1 harness（UIConfig）

**核心发现**：Harness 层 EAI 从未定制，差异全部来自落后上游版本。Gateway 层的 deps.py 已有上游 router 所需全部函数（仅缺 `require_admin_user`，已补）。Gateway core（app/services/deps/auth）是 EAI 与上游的架构分叉点，不可无脑同步。

---

*维护者：本 session 由 AI 辅助 port。续 port 时以本文件 + `.wolf/cerebrum.md` 为准；代码事实请当场复检。*
