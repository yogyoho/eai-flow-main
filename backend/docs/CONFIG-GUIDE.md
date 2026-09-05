# config.example.yaml 全量解读 + config.yaml 差距分析

> 基准：`config.example.yaml` @ config_version **34**（2584 行） vs 本地 `config.yaml` @ config_version **11**（393 行）
> 生成日期：2026-08-19。仅分析文档，不随配置自动更新——example 升版后需人工复核。

---

## 第一部分：config.example.yaml（v34）逐项配置解读

### 1. 全局与可观测性

| 配置项 | 默认值 | 说明与作用 |
|---|---|---|
| `config_version` | 34 | 配置 schema 版本号。启动时与程序内置版本比对检测过期配置；`make config-upgrade` 据此把新增字段合并进本地 config.yaml |
| `log_level` | info | deerflow 模块日志级别（debug/info/warning/error） |
| `logging.enhance.enabled / format` | false / text | 请求级 trace 关联：给 Gateway 日志、HTTP 响应头、Langfuse 元数据注入追踪 ID。默认关闭以保持既有输出格式不变 |
| `extensions.middlewares`（注释） | — | 在 lead/subagent 中间件链尾部（安全/澄清之前）插入自定义 `AgentMiddleware` 类列表。留注释时 extensions_config.json 是该列表真源。属可信操作员配置（中间件类会执行代码） |
| Monocle 追踪（纯注释） | — | 不占 yaml 键，经环境变量（`MONOCLE_TRACING` 等）配置，默认关 |
| `token_usage.enabled` | true | 按 model 调用记录 input/output/total token 并在 workspace UI 显示用量 |
| `token_budget.*` | false / 200000 / 0.8 / 1.0 | **单 run token 预算熔断**：跨 warn 阈值（80%）给 agent 上下文内警告；跨 hard 阈值（100%）剥掉 tool_calls 强制立即产出最终答案。防 API 费用失控。可分设 input/output 上限 |
| `max_recursion_limit` | 1000 | 客户端传入 `recursion_limit` 的钳制上限（防 runaway 成本/DoS）；非法值回落 100。仅深嵌套子代理图需要调高 |

### 2. 模型（models[]）

公共字段字典（约 19 个供应商示例全部为注释，激活时按此填写）：

| 字段 | 说明与作用 |
|---|---|
| `name` / `display_name` | 内部标识 / UI 显示名 |
| `use` | `"包.模块:类"` 类路径，如 `langchain_openai:ChatOpenAI`、`deerflow.models.patched_deepseek:PatchedChatDeepSeek` |
| `model` / `api_key` / `api_base`·`base_url` | 提供商模型 ID / 凭据（`$VAR` 解析环境变量）/ 端点 |
| `request_timeout`·`timeout` / `max_retries` | 请求超时 / 重试次数 |
| `max_tokens` | **单次调用输出上限**（传给提供商） |
| `context_window` | 上下文总容量（prompt+completion），驱动聊天 UI 实时 "% context used" 指示；不设则不显示 |
| `supports_thinking / supports_vision / supports_reasoning_effort` | 思考/视觉/推理力度能力声明（控制 UI 开关与 view_image 工具） |
| `when_thinking_enabled / disabled` | 思考开关两态下注入的 extra_body（如 `thinking.type: enabled/disabled`） |
| `use_responses_api` / `output_version` | OpenAI Responses API 通道 |
| `pricing.*` | 每百万 token 单价（须全部模型同一币种），驱动工作台真实成本显示；支持 cache-hit 价 |

注释示例覆盖的供应商与关键坑：Volcengine Doubao/Coding Plan（一 key 多厂商）、OpenAI(+Responses)、**Ollama 原生**（必须 `langchain_ollama:ChatOllama`，OpenAI 兼容端点会丢 reasoning_content）、Anthropic（`budget_tokens` 必填、min 1024、< max_tokens）、Gemini 原生/网关（网关须 `PatchedChatOpenAI` 保 thought_signature）、小米 MiMo（`PatchedChatMiMo` 回放 reasoning_content）、DeepSeek V4、Kimi、Novita、StepFun（`reasoning_format: deepseek-style`）、MiniMax 国际/国区（适配器剥 name 字段防 2013 错误；M2 恒思考）、OpenRouter、Atlas Cloud、vLLM（`chat_template_kwargs.enable_thinking`）、MindIE（mock-streaming + 分项超时）。

### 3. 工具体系

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `tool_groups[]` | web / file:read / file:write / bash / **browser** | 工具分组，用于组织与访问控制 |
| `tools: web_search` | DDG 激活 | 免 key 搜索；`backend/region/safesearch` 可调。注释备选：SearXNG(自托管)/Serper/Brave/Tavily/Exa/Firecrawl/GroundRoute(6 引擎聚合)/fastCRW/InfoQuest |
| `tools: web_fetch` | **Jina 激活** | Reader API；`timeout: 10`、`proxy/trust_env`。注释备选：**Browserless**(无头 Chrome，JS 重页面)/Crawl4AI(≥0.9 强制 token)/Exa/Firecrawl/GroundRoute/fastCRW。同一时刻只能激活一个 web_fetch |
| `tools: web_capture` | 注释 | Browserless 截图成工件：output_format/full_page/viewport/等待策略；`allow_private_addresses` SSRF 守卫 |
| `tools: browser_*` 八件套 | 注释 | **Playwright 有状态浏览器自动化**（navigate/snapshot/click/type/get_text/back/screenshot/close）：保持每线程一个活浏览器，元素以 [ref] 索引寻址。需 `uv sync --extra browser`；`cdp_url` 可挂真实 Chrome；启用时须 GATEWAY_WORKERS=1 |
| `tools: ls/read_file/glob/grep/write_file/str_replace/bash` | 全激活 | 沙箱文件与命令工具；bash 仅在隔离沙箱或 `allow_host_bash: true` 时可用 |
| `tool_search.enabled / auto_promote_top_k` | false / 3 | MCP 工具**延迟加载**：启用后系统提示只列名字，运行时经 tool_search 发现（省上下文、提升选型准确度）；auto_promote 按路由元数据在模型调用前自动提升匹配 schema（1–5） |
| `tool_output.*` | enabled | 工具输出预算保护：>12k 字符持久化到 `.tool-results` 并替换为类型化摘要+文件引用（模型可 read_file 取全文）；磁盘不可用则 >30k 头尾截断。`exempt_tools` 防读类工具 persist→read→persist 死循环；`tool_overrides` 按工具调阈值 |

### 4. 输入输出治理

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `suggestions.enabled / max_suggestions` | true / 3 | 每次响应结尾自动生成后续问题建议 |
| `input_polish.*` | true / 4000 / null | 编辑器草稿发送前润色重写（`/api/input-polish`）；model_name null=默认聊天模型，建议配最低延迟快模型 |
| `loop_detection.*` | 3 / 5 / 20 / 30 / 50 | 相同工具调用循环检测与打断（窗口 20 步内重复 warn 3/hard 5）；同工具频次安全线 warn 30/hard 50；`tool_freq_overrides` 按工具放宽（如 bash 批处理流水线 150/300） |
| `tool_progress.*`（注释，RFC #3177） | off | (thread,tool) 级停滞状态机：连续"无新信息"调用→WARNED→BLOCKED；jaccard 相似度判近重复；按 recoverable_by_model 分三条转移路径 |
| `read_before_write.enabled` | **true** | **先读后写门禁**（issue #3857）：write_file/str_replace 前必须读过当前版本，写后失效早前读取强制重读。防长任务盲写重复追加 |
| `safety_finish_reason.*` | true / 内置 | 拦截因安全原因提前终止却仍带 tool_calls 的响应（OpenAI content_filter / Anthropic refusal / Gemini SAFETY 等），不执行其 tool_calls；`detectors` 可按类路径扩展（如中文网关非标 finish_reason） |

### 5. 上传与沙箱

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `uploads.max_files/max_file_size/max_total_size` | 10 / 50MiB / 100MiB | 网关执行的应用层上传限额，并供前端选文件前预检 |
| `uploads.auto_convert_documents` | **false** | Office/PDF 自动转 Markdown。**在沙箱隔离生效前的 host 侧执行**——仅当上传来自完全可信来源才开（host 侧解析器风险） |
| `uploads.pdf_converter` | auto | PDF 转换器：auto（pymupdf4llm 优先，图像/加密 PDF 回落 MarkItDown）/ pymupdf4llm / markitdown |
| `sandbox.use` | LocalSandboxProvider | 方案①本地直接执行（默认）。备选：②AIO 容器（image 建议钉 1.11.0；多实例须 redis 所有权防误杀 #4206）③BoxLite micro-VM ④Provisioner k3s Pod ⑤Tenki 云 microVM |
| `sandbox.allow_host_bash` | **false** | host bash 默认关——LocalSandboxProvider 不是 shell 的安全隔离边界，仅完全可信单用户场景开启 |
| `sandbox.mounts[]` | 注释 | 挂 host 目录进沙箱虚拟路径；Docker 模式还需 compose 同步 bind-mount（#3244） |
| `sandbox.*_output_max_chars` | 20000/50000/20000 | bash(中截断)/read_file、ls(头截断) 输出截断；0=不截断 |
| `sandbox.bash_command_timeout` | 600 | 单条 host bash 墙钟秒数上限（杀整个进程组），防前台阻塞命令挂死 agent 回合 |

### 6. 子代理与技能

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `subagents.*`（整节注释） | — | timeout_seconds 1800（自定义 agent 默认 900）；max_turns（general-purpose 150 / bash 60）；**max_total_per_run 6**（单 run 委派总数熔断，1–50）；**token_budget**（2M 默认，硬停时剥 tool_calls 自然收尾并标记 `token_capped`）；agents 按名覆盖 timeout/max_turns/model/skills 白名单；**custom_agents** 自定义子代理（description/system_prompt/tools 白名单/skills 白名单/model/max_turns/timeout_seconds），经 `task` 工具可用 |
| `acp_agents.*`（注释） | — | 外部 ACP 协议 agent（claude_code/codex 经 @zed-industries 适配器）接入 `invoke_acp_agent` 工具；auto_approve_permissions / timeout / env |
| `skills.path / container_path / deferred_discovery` | — / /mnt/skills / false | host 技能目录（默认项目根 skills，`DEER_FLOW_SKILLS_PATH` 可覆盖）；沙箱内挂载点；deferred_discovery=true 时系统提示只放名字索引，详情按需 `describe_skill`（多技能省上下文、prefix-cache 友好） |
| `skill_scan.enabled` | true | 技能安装/更新及 agent 写技能前的**确定性安全扫描**（嵌套压缩包/密钥模式等内容级检查）；安全解包（路径穿越/符号链接/可执行二进制/大小/条目数）与 LLM 扫描恒跑 |

### 7. 对话体验

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `title.*` | true / 6 / 60 / **null** | 会话标题自动生成。model_name null=**本地快回退**（用户消息前 50 字符截断加 `...`）；设模型名才走 LLM 生成 |
| `summarization.*` | enabled | 逼近上限自动压缩历史。model_name null=**用 run 实际模型**（非 models[0]），失败回落 run 模型；trigger OR 逻辑（tokens 32000 / messages 50 / fraction 0.8）；keep=压缩后保留最近 10 条消息；trim_tokens_to_summarize 15564=送入摘要的消息修剪上限；summary_prompt 自定义模板；`skill_file_read_tool_names`——SKILL.md 读取捕获进 durable skill_context 通道，压缩后重注入名字/路径/描述提醒；**legacy `preserve_recent_skill_*` 已废弃不再读取** |
| `memory.*`（**新 schema**） | deermem / middleware | 顶层：enabled / injection_enabled / shutdown_flush_timeout_seconds（关停排水预算，须 < K8s terminationGracePeriodSeconds）/ **manager_class**（deermem/mem0/noop/openviking 或点路径）/ **mode**（middleware 被动后台抽取 \| tool 模型主动 CRUD）。backend_config（DeerMem 私有）：storage_path、storage_class file、retrieval_adapter fts5、debounce 30、queue_max_depth 1000（背压，信号类永不丢）、model（抽取 LLM，全缺省=不抽取）、max_facts 100、置信度 0.7、注入预算 2000 token、token_counting tiktoken（**内网建议 char** 免 BPE 下载阻塞）、guaranteed_categories [correction]+500 保留额（高信号纠正绕过常规预算）、staleness 系列（90 天老化审查，LLM 同次调用判 KEEP/REMOVE/EXTEND；寿命上限 90×20≈5 年；延期上限 3650 天）、consolidation（默认关，有损合并同组事实）。另含 OpenViking / Honcho 后端示例 |

### 8. 存储与运行时

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `agents_api.enabled` | **false** | 网关暴露自定义 agent SOUL/USER.md 管理 API。仅可信认证管理边界后开启 |
| `skill_evolution.*` | false / null / true | agent 自主创建/改进 skills/custom/；moderation LLM 扫描；security_fail_closed=true：审查模型不可用时阻止全部写入 |
| `checkpointer`（**DEPRECATED**） | 注释 | 旧独立 checkpoint 配置，仅为兼容保留；**与 database 并存时对 LangGraph checkpointer+Store 优先**——用 database 就应删掉它 |
| `database.*` | sqlite / .deer-flow/data | 统一存储后端（checkpointer+Store+应用数据 runs/threads/feedback）。postgres 模式走 `$DATABASE_URL`；postgres_schema 只影响新表（存量迁移须连 alembic_version 一起 SET SCHEMA，漏了会重放迁移）；pool_recycle 300 / command_timeout 30（PG 连接）；**checkpoint_channel_mode full\|delta**（delta=消息增量通道→更小 checkpoint；重启生效；全库必须一致；delta 可透明读 legacy full）；snapshot_frequency 10=每 N 步写全量快照；checkpoint_graph_cache.accessor_graph_max 64；checkpoint_cache（memory\|redis，线程删除时 redis TTL 是泄漏安全网） |
| `dedupe_storage`（注释） | auto | 入站 webhook 跨 pod 去重存储：auto（PG 时共享）/ memory（每 pod 独立）/ postgres（多副本必须） |
| `run_events.*` | **memory** / 10240 / true | 运行事件（消息+执行 trace）存储：memory 不持久 / **db** SQL 全查询（生产）/ jsonl 追加文件 |
| `agent_storage.backend` | file | 自定义 agent **定义**存储：file（每用户文件，单节点）/ db（共享 SQL 行，多节点同视；迁移脚本 migrate_agents_to_db.py） |
| `scheduler.*` | false | 后台定时任务（一次性+cron）调度器：poll 5s / lease 120s（崩溃后可认领）/ 并发 3 / 一次性任务最小 60s 偏移；multi_instance=lease 感知恢复（需共享 PG+心跳+db run_events） |
| `mcp_tasks.*` | false | 长时 MCP 任务的协议中立持久任务运行时（须先配 task driver） |
| `run_ownership.*` | 30 / 10 / false | 多 worker（GATEWAY_WORKERS>1）run 租约：心跳每 lease/3 续租；grace=过期后宽限+**跨 worker 时钟偏差预算**（须 NTP）；heartbeat_enabled 多 worker 才开 |
| `stream_bridge`（注释） | memory | gateway→SSE 事件桥：memory 单进程 / **redis** Docker·多 worker 推荐（queue_maxsize 256 重连窗口、stream_ttl 86400、连接池上限）。Docker Compose 自动配 REDIS_URL。redis 桥 **fail-hard**：中途宕掉活 run 直接失败，无自动回落 |

### 9. IM 渠道

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `channel_connections`（注释） | false / true | 终端用户自有 IM 账号绑定（无公网 IP/回调；bot 凭据留在 channels.*；require_bound_identity=true 安全默认——未绑定外部用户不得创建 run）；telegram 深链、其余 `/connect <code>`；支持 8 平台 |
| `channels.*`（注释） | — | IM 渠道接入（出站 WS/轮询，免公网）：langgraph_url/gateway_url（Docker 用服务名）、inbound_queue 1000 / 并发 5 / 关停宽限 3s；session 默认 assistant_id+思考开关+按用户覆盖；wechat（iLink：QR bootstrap、state_dir 游标持久化、图像/文件大小上限、扩展名白名单）、wecom、feishu、slack、telegram、dingtalk（AI Card 流式）、discord、buzz（Nostr，deny-by-default） |

### 10. 安全与治理

| 配置项 | 默认 | 说明与作用 |
|---|---|---|
| `guardrails`（注释） | — | 工具调用**前置授权**：内置 AllowlistProvider（denied_tools）/ OAP 护照标准提供者 / 自定义类（evaluate/aevaluate）。类路径反射加载 |
| `authorization.enabled` | false | 细粒度资源授权（RBAC+，RFC #4063）：roles→tools/routes/models 的 allow/deny 矩阵；fail_closed；default_role |
| `circuit_breaker`（注释） | 5 / 60s | LLM 调用熔断：连续 5 次失败→开路 fast-fail，60s 后恢复。防供应商宕机时限流封禁/重试风暴 |
| `llm_call`（注释） | 0 / 3 / 1000ms / 8000ms / 5000ms | 进程内 LLM 并发上限（管的是**请求速率斜率**而非配额——早高峰秒级爬坡会被 burst-rate 拒；配内置 decorrelated-jitter 退避+nginx limit_req）；重试次数/退避基期/上限；burst_retry 专对 burst-rate 429 且高于常规基期。并发上限启动冻结（改需重启），按进程计（多 worker ×N） |
| `auth.local / auth.oidc`（注释） | — | 本地自注册开关（默认开，SSO 部署应关；首个 admin 恒走 /initialize 不受影响）；OIDC SSO（PKCE+nonce 默认开；provisioning：自动建用户/邮箱域白名单/自动授予 admin） |
| `plugins[]`（注释） | — | 扩展包列表（`make extension-install/list/enable/disable/remove` 管理，同步改 pyproject+uv.lock+此块）；重启生效；可贡献中间件/生命周期钩子/HTTP 路由。与 `extensions` 块分离——插件列表必须留在操作员控制的 config.yaml（extensions_config.json 可被 HTTP 热改） |

---

## 第二部分：与当前 config.yaml（v11，393 行）的差距

### 2.1 版本差距

**config_version 11 → 34，落后 23 个 schema 版本。** 本地配置能跑是因为加载器向后兼容，但大量新字段/新语义靠代码默认值兜底。

### 2.2 本地缺失的配置节（example 有、本地无）

| 缺失项 | 作用 | 缺失影响 | 建议 |
|---|---|---|---|
| `token_budget` | 单 run token 熔断 | 无费用护栏，runaway run 无硬停 | **建议采纳**（enabled: true + 限额） |
| `max_recursion_limit` | 客户端 recursion_limit 钳制 | 用代码默认值 | 低优先级，显式补上即可 |
| `read_before_write` | 先读后写门禁 | 长任务盲写重复追加无确定性防护 | **建议采纳**（example 默认 true） |
| `sandbox.bash_command_timeout` | 单条 bash 墙钟上限 | 前台阻塞命令可能挂死回合 | **建议显式补 600** |
| `logging.enhance` | 请求 trace 关联 | 排障时日志/请求无法关联 | 排障痛点存在时开 |
| `skill_scan` | 技能安装安全扫描 | 默认值（enabled）生效，无实际缺失 | 显式声明即可 |
| `tool_search.auto_promote_top_k` | 延迟工具自动提升 | 本地 tool_search 本来就 disabled，无影响 | 忽略 |
| `browser` 工具组 + `browser_*` 八件套 | Playwright 浏览器自动化 | 无浏览器交互能力（example 也是注释态） | 按需启用（需 extra 依赖 + workers=1） |
| `tool_progress` | 工具停滞状态机 | example 也是注释实验态，一致 | 忽略 |
| `database.checkpoint_graph_cache` | 访问图缓存上限 64 | 用代码默认值 | 可补 |
| `database.pool_recycle / command_timeout` | PG 连接治理 | 本地是 sqlite，**不适用** | 忽略 |
| `agent_storage / scheduler / mcp_tasks / run_ownership / stream_bridge / dedupe_storage` | 多实例/生产部署能力 | 单机单 worker 下默认值即正确 | 暂忽略；扩容前再看 |
| `guardrails / authorization / circuit_breaker / llm_call / auth.oidc / plugins / acp_agents / extensions.middlewares` | 治理与扩展 | 全部默认关闭——**当前等于 example 默认状态** | circuit_breaker/llm_call 在供应商不稳时可考虑 |
| `models.context_window / pricing` | UI 上下文百分比 + 真实成本显示 | 本地 4 个模型都没配——无 % 指示、无成本显示 | 建议补 context_window（本地模型容量已知） |
| `ui.show_tool_output`（反向） | 本地独有键 | example v34 已无此键（上游移除/改名） | 核实是否仍是有效键 |

### 2.3 同名但取值/行为分歧

| 项 | example v34 | 本地 v11 | 评估 |
|---|---|---|---|
| `uploads.auto_convert_documents` | **false**（host 侧解析器风险） | **true** | ⚠️ 安全分歧：转换发生在沙箱隔离之前的 host 上。内网可信用户群可接受，需确认为有意 |
| `sandbox.allow_host_bash` | **false**（本地沙箱非隔离边界） | **true** | ⚠️ 同上；EAI 网关跑在 Docker 容器内，风险面=容器而非宿主，属常见内网折中 |
| `summarization.trigger` | tokens **32000** | tokens **15564** | 本地压缩得早得多（约一半）——长任务历史更早被摘要替换；若当初是为小上下文模型设的，现在模型变大可放宽 |
| `summarization.preserve_recent_skill_*` | 已废弃不读取 | 仍写着（5/25000/5000） | 死配置，升级时应删除（技能保留已由 durable skill_context 通道接管） |
| `summarization.summary_prompt` | null | 中文自定义模板 | 本地有意定制，保留 |
| `tools: web_fetch` | Jina 激活 | **Browserless**（http://browserless:3000） | 本地内网自托管更合理；另本地激活了 web_capture（example 注释态） |
| `tool_groups` | 含 browser | 无 browser | 与 browser 工具未启用一致 |
| `suggestions.max_suggestions` | 3 | 缺失（默认 3） | 无实际差异 |
| `skill_evolution.security_fail_closed` | true | 缺失（默认 true） | 无实际差异 |
| `memory` | **新 schema**（manager_class: deermem + mode + backend_config，含 staleness/consolidation/guaranteed_categories/token_counting） | **旧 schema**（顶层 storage_path/debounce_seconds/model_name/max_facts/...） | **最大迁移项**。旧字段仍被兼容解析，但新能力（老化审查、correction 保底注入、char 计数、队列背压）全部没吃到。内网环境特别该用 `token_counting: char` |
| `database.checkpoint_channel_mode` | full | **delta**（EAI-CUSTOM 性能定制） | 有意为之，保留 |
| `run_events.backend` | memory | **db**（EAI-CUSTOM ops-diagnosis） | 有意为之，保留 |
| `agents_api.enabled` | false（须可信管理边界） | **true** | EAI 需要自定义 agent 管理（petrochem agent）——有意，但注意 example 的安全告警 |
| `models` | 全注释示例 | 4 激活（agnes/glm-4.7-flash/gemma-4 llama.cpp 内网/deepseek-v4-flash） | 正常差异 |

### 2.4 本地独有 —— 升级时必须保留的 EAI 定制

1. `checkpointer`（legacy 节，EAI-CUSTOM 容器路径 `/app/backend/.deer-flow/data/checkpoints.db`）——⚠️ example 明示：**与 database 并存时 checkpointer 对 LangGraph checkpointer+Store 优先**，本地两节并存，实际 checkpoint 走的是 legacy 节；升级可考虑合并进 database 后删除（路径已一致）
2. `database` 的 delta 模式 + checkpoint_cache（EAI-CUSTOM 大任务性能）
3. `run_events.backend: db`（EAI-CUSTOM route-D 运维诊断）
4. `channel_connections`（wechat/wecom 启用 + require_bound_identity: true）
5. `channels.wechat`（QR 登录 + state_dir + require_bound_identity）、`channels.wecom`（bot 凭据 + working_message）
6. `subagents.custom_agents.petrochem-utilities-agent`（石化公用工程助手）
7. 中文 `summary_prompt`、内网模型端点（192.168.2.38 llama.cpp）
8. `ui.show_tool_output: false`（需核实 v34 是否仍支持该键）

### 2.5 升级路径建议

1. **官方路径**：`make config-upgrade`（v11→v34 逐版合并新字段）——**执行前 git 提交当前 config.yaml 做快照，升级后 diff 逐项确认**，重点核对 2.4 清单未被冲掉
2. 高价值采纳项（按序）：`read_before_write` → `bash_command_timeout: 600` → `token_budget` → models 补 `context_window` → memory 迁移新 schema（内网配 `token_counting: char`）
3. 清理死配置：`preserve_recent_skill_*` 三行
4. 安全确认项（均 example 默认关、本地开的）：`auto_convert_documents: true` / `allow_host_bash: true` / `agents_api: true` —— 内网部署下大概率是有意折中，但值得留一句决策记录
