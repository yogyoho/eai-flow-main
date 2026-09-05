# Agent 执行监控与调试手册

> 适用范围：DeerFlow / EAI Flow（Gateway + embedded LangGraph runtime）。
> 本文覆盖**实时流式监控、运行事件回放、外部 Tracing、底层排障**四类手段。
> 相关文档：[STREAMING.md](STREAMING.md)（流式协议细节）、[CONFIGURATION.md](CONFIGURATION.md)（配置）、[API.md](API.md)（端点）。

## 1. 手段总览

| # | 手段 | 定位 | 入口 | 章节 |
|---|------|------|------|------|
| 1 | SSE 流式输出 | 运行中实时看 AI 文本 / 工具 / 子代理 | `POST /api/threads/{tid}/runs/stream`，前端 `useStream()` | [§2](#2-实时流式监控sse) |
| 2 | Run 事件回放（RunJournal） | 运行后审计完整执行轨迹 | `GET /api/threads/{tid}/runs/{rid}/events` | [§3](#3-run-事件持久化与回放) |
| 3 | Thread 状态与消息历史 | 事后查状态快照 / 消息 / 分支 | `GET /api/threads/{tid}/state`、`/messages`、`/history` | [§4](#4-thread-状态与消息历史) |
| 4 | Token 用量 | 成本与 token 消耗监控 | `GET /api/threads/{tid}/token-usage` | [§5](#5-token-用量监控) |
| 5 | LangSmith | 外部 LLM Trace（云端/自建） | env `LANGSMITH_TRACING` | [§6](#6-外部-tracinglangsmith--langfuse--monocle) |
| 6 | Langfuse | 外部 LLM Trace（云端/自建） | env `LANGFUSE_TRACING` | [§6](#6-外部-tracinglangsmith--langfuse--monocle) |
| 7 | Monocle (OTel) | 进程级 OpenTelemetry telemetry | env `MONOCLE_TRACING` | [§6](#6-外部-tracinglangsmith--langfuse--monocle) |
| 8 | Python 日志 | 最底层排障兜底 | `docker compose -p eai-docker logs -f gateway` | [§7](#7-日志) |
| 9 | Swagger `/docs` | 交互式调端点 | `GET /docs`（`GATEWAY_ENABLE_DOCS` 控制） | [§8](#8-swagger-交互式调试) |
| 10 | TUI 终端工作台 | 终端内嵌交互式 Agent 调试 | `deerflow` 命令 | [§9](#9-tui-终端工作台) |
| 11 | DeerFlowClient 嵌入式客户端 | 脚本化 / 单元级调试 | Python `deerflow.client` | [§10](#10-嵌入式客户端-deerflowclient) |
| 12 | LangGraph 兼容 API | 用 langgraph-sdk / Studio 生态 | `/api/langgraph/*` | [§11](#11-langgraph-兼容-api--sdk) |
| 13 | 自然语言诊断（ops-diagnosis 技能） | 对话式回放分析 + 契约对照报告 | 对 agent 说"分析线程 X 的执行情况" | [§13](#13-自然语言诊断ops-diagnosis-技能) |

---

## 2. 实时流式监控（SSE）

### 原理
运行时经 `StreamBridge`（asyncio Queue，memory/redis 两种实现）把 LangGraph `astream(stream_mode=[...])` 的事件推给 `sse_consumer`，以 `text/event-stream` 输出。前端 `@langchain/langgraph-sdk/react` 的 `useStream()` 自动消费并渲染。

### 支持 stream_mode
`backend/packages/harness/deerflow/runtime/stream_modes.py`：

```
values · messages-tuple · updates · debug · tasks · checkpoints · custom
```

- `values` — 每步完整 state 快照
- `messages-tuple` — token 级增量（前端逐字渲染）
- `custom` — 业务自定义事件（`emit_custom_event`）
- `debug` — LangGraph 原始 debug 事件（最细粒度）
- 未指定时默认 `["values"]`

### 操作步骤

**前端**：正常对话即实时展示（无需额外配置）。工具调用、子代理进度卡（`subtask-card`）随 SSE 自动更新。

**curl 调试**（需先登录拿 Cookie；Docker 内统一入口 `localhost:2026`）：

```bash
# 1. 新建 run 并流式（返回 SSE 帧，Content-Location 头带 run 资源 URL）
curl -N -X POST 'http://localhost:2026/api/threads/<thread_id>/runs/stream' \
  -H 'Content-Type: application/json' \
  -H "Cookie: <session_cookie>" -H "X-CSRF-Token: <csrf>" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "用 bash 列出 /mnt/user-data/workspace"}]},
    "stream_mode": ["values", "messages-tuple"],
    "context": {"model_name": "agnes-2.0-Flash"}
  }'

# 2. 加入一个已存在的 run 的 SSE（run 在后台跑着）
curl -N 'http://localhost:2026/api/threads/<thread_id>/runs/<run_id>/stream' \
  -H "Cookie: <session_cookie>"
```

请求体字段见 `backend/app/gateway/run_models.py::RunCreateRequest`：`input` / `command` / `metadata` / `config` / `context`（模型名、thinking 等覆盖）/ `checkpoint_id` / `interrupt_before|after` / `stream_mode` / `on_disconnect`（`cancel|continue`）/ `multitask_strategy`（`reject|rollback|interrupt`）。

### 注意事项
- `POST /runs`（非 stream）创建**后台 run**，可随后用 `GET /runs/{rid}/stream` 加入。
- `POST /runs/wait` 阻塞到完成并返回最终 state（适合脚本断言）。
- SSE 帧格式与 LangGraph Platform 协议兼容（详见 STREAMING.md）。

---

## 3. Run 事件持久化与回放

### 原理
`RunJournal`（`backend/packages/harness/deerflow/runtime/journal.py`，`BaseCallbackHandler`）在运行全程记录事件，写入 `RunEventStore`。这是**事后审计 Agent 干了什么**的主要手段。

### 配置（`config.yaml`，**重启 gateway 生效**）

```yaml
run_events:
  backend: memory      # memory | db | jsonl
  max_trace_content: 10240   # db 后端单条 trace 内容截断字节上限
  track_token_usage: true    # 是否累计 token 到 RunRow
```

- `memory` — 进程内存，重启即失，**仅限开发**（上游默认值；EAI 部署已于 2026-08-19 切到 `db`，ops-diagnosis 技能依赖它）
- `db` — SQLAlchemy/SQL，生产查询用（数据库 `database.backend` 决定 sqlite/postgres）
- `jsonl` — 追加式文件，单机持久化轻量方案，文件位于
  `.deer-flow/threads/{thread_id}/runs/{run_id}.jsonl`（单进程 seq 单调；多进程共享目录会重复/乱序，多进程请用 db）

### 事件类型（`runtime/events/catalog.py`）

| 事件 | 说明 |
|------|------|
| `run.start` / `run.end` / `run.error` | 生命周期 |
| `llm.human.input` / `llm.ai.response` / `llm.tool.result` | 消息类 |
| `llm.error` | LLM 异常 |
| `context:memory` | 注入的 memory 上下文（content_sha256） |
| `subagent.start` / `subagent.step` / `subagent.end` | 子代理进度（subtask-card 回放依赖） |
| `workspace-changes` | 工作区/输出文件变更 |
| `middleware.<tag>` | 中间件记录（`guardrail`、`safety_termination`、`skill_activation`、`skill_secrets` 等） |

### 操作步骤

```bash
# 拉取一次 run 的完整事件流
curl 'http://localhost:2026/api/threads/<thread_id>/runs/<run_id>/events' \
  -H "Cookie: <session_cookie>"

# 过滤类型、分页
curl 'http://localhost:2026/api/threads/<thread_id>/runs/<run_id>/events?event_types=llm.ai.response,llm.tool.result&limit=100&after_seq=0' \
  -H "Cookie: <session_cookie>"

# 只看某个子代理 task 的步骤（subtask-card 内部用法）
curl 'http://localhost:2026/api/threads/<thread_id>/runs/<run_id>/events?task_id=<task_id>&limit=500' \
  -H "Cookie: <session_cookie>"

# 一次 run 的工作区文件变更（含文件内容与 diff）
curl 'http://localhost:2026/api/threads/<thread_id>/runs/<run_id>/workspace-changes?include_files=true&include_diff=true' \
  -H "Cookie: <session_cookie>"
```

> 安全提示：`/events` 返回的 `metadata` 会经 `redact_metadata_secrets()` 脱敏，不会泄漏密钥类元数据。

---

## 4. Thread 状态与消息历史

| 端点 | 用途 |
|------|------|
| `GET /api/threads/{tid}` | thread 元数据 |
| `GET /api/threads/{tid}/state` | **ThreadState 全量快照**（messages / artifacts / todos / title / uploaded_files 等） |
| `POST /api/threads/{tid}/state` | 写回 state（调试注入用） |
| `GET /api/threads/{tid}/messages`、`/messages/page` | 分页消息 |
| `GET /api/threads/{tid}/runs/{rid}/messages` | 单 run 分页消息（`{data, has_more}`，`after_seq/before_seq` 游标） |
| `GET /api/runs/{rid}/messages` | 按 run_id 直接取（无 thread 前缀） |
| `POST /api/threads/{tid}/history` | 完整历史条目 |
| `POST /api/threads/{tid}/branches` | 分支/重生成 |
| `GET /api/threads/{tid}/goal` | 目标解析 |

排障常用套路：`GET state` 看 messages/artifacts 有没有预期之外的内容 → `GET events` 看是哪一步产生的 → `GET workspace-changes` 看文件被怎么改了。

---

## 5. Token 用量监控

### 配置

```yaml
token_usage:
  enabled: true
run_events:
  track_token_usage: true   # RunJournal 累计 token 到 RunRow
```

### 操作

```bash
# 某 thread 的聚合 token 用量
curl 'http://localhost:2026/api/threads/<thread_id>/token-usage' -H "Cookie: <session_cookie>"
```

前端：`TokenUsageIndicator` / `ContextUsageBadge`（chat-page 顶栏），可开关 inline 展示。
注意：`TokenUsageMiddleware` 仅在 `token_usage.enabled` 时激活；子代理用量按 `tool_call_id` 缓存后回填到发起它的 AIMessage。

---

## 6. 外部 Tracing：LangSmith / Langfuse / Monocle

Tracing 回调统一由 `deerflow/tracing/factory.py::build_tracing_callbacks()` 装配，挂在 **graph 调用根节点**（一次 run 一个 trace，node/LLM/tool 均为子 span）。

### 6.1 LangSmith

| 环境变量 | 说明 | 默认 |
|----------|------|------|
| `LANGSMITH_TRACING`（或 `LANGCHAIN_TRACING_V2` / `LANGCHAIN_TRACING`） | 开关 | 关 |
| `LANGSMITH_API_KEY`（或 `LANGCHAIN_API_KEY`） | API Key，必填 | — |
| `LANGSMITH_PROJECT`（或 `LANGCHAIN_PROJECT`） | project 名 | `deer-flow` |
| `LANGSMITH_ENDPOINT`（或 `LANGCHAIN_ENDPOINT`） | 自建端点 | `https://api.smith.langchain.com` |

### 6.2 Langfuse

| 环境变量 | 说明 | 默认 |
|----------|------|------|
| `LANGFUSE_TRACING` | 开关 | 关 |
| `LANGFUSE_PUBLIC_KEY` | 必填 | — |
| `LANGFUSE_SECRET_KEY` | 必填 | — |
| `LANGFUSE_BASE_URL` | 自建 host | `https://cloud.langfuse.com` |

Langfuse 元数据自动注入映射（`tracing/metadata.py`）：

| Langfuse 字段 | 来源 |
|---------------|------|
| `langfuse_session_id` | LangGraph `thread_id` |
| `langfuse_user_id` | `get_effective_user_id()`（无 auth 时为 `default`） |
| `langfuse_trace_name` | `RunRecord.assistant_id` / client `agent_name`（默认 `lead-agent`） |
| `langfuse_tags` | `env:<DEER_FLOW_ENV>` + `model:<model_name>` |

外部调用方传的 `session_id` 等键优先（`setdefault`），不会被覆盖。

### 6.3 Monocle（OpenTelemetry）

| 环境变量 | 说明 | 默认 |
|----------|------|------|
| `MONOCLE_TRACING` | 开关（Gateway lifespan 初始化） | 关 |
| `MONOCLE_EXPORTERS` | 逗号分隔：`file` `console` `okahu` `s3` `blob` `gcs` | `file` |
| `OKAHU_API_KEY` | 选 `okahu` 导出器时必填 | — |

- Monocle 与 Langfuse（v4 同为 OTel）**可共存**：共享全局 TracerProvider，互不丢 span；Monocle 的导出器也会导出 Langfuse 的 span（见 `test_coexists_with_langfuse`）。
- 内嵌 / TUI 进程不会自动跑 lifespan 初始化，需显式调 `deerflow.tracing.setup_monocle_tracing_if_enabled()`。
- 选择非本地导出器（file/console 以外）时启动会打警告：trace 数据（prompts、工具输入输出）会出机器，确认目标可信。

### 操作步骤

```bash
# Docker 环境：修改环境变量后重建/重启 gateway 容器
# 在 docker-compose.yml 对应 service 的 environment 加入上面变量后：
docker compose -p eai-docker up -d gateway

# 验证：跑一次对话，然后在
#   LangSmith  → app.smith.langchain.com（或自建）看对应 project
#   Langfuse   → cloud.langfuse.com（或自建）看新 trace（session = thread_id）
#   Monocle    → 本地 exporter 落 .monocle/ 文件，console 导出直接看 stdout
docker compose -p eai-docker logs -f gateway | grep -i -E 'trace|langfuse|langsmith|monocle'
```

> 缺 key / 配错的 provider 会在 run 启动时抛明确错误（如 `LANGSMITH_API_KEY` 未设置、`LANGFUSE_PUBLIC_KEY` 缺失、`MONOCLE_EXPORTERS` 含未知值），不会静默吞掉。

---

## 7. 日志

```yaml
# config.yaml
log_level: info    # debug / info / warning / error
```

- **Docker**：`docker compose -p eai-docker logs -f gateway`（代码改动后 `restart gateway`）
- **本地**：`make dev` 前台日志，或 `backend/.deer-flow/` 下运行数据
- 调 `debug` 级可看到更细的运行日志，但量大；排障时临时调高，恢复 `info`

---

## 8. Swagger 交互式调试

- 入口：`http://localhost:2026/api/docs`（直连 gateway 为 `http://localhost:8001/docs`）
- 生产环境可用 `GATEWAY_ENABLE_DOCS=false` 关闭 `/docs`、`/redoc`、`/openapi.json`
- 用途：逐端点点测 thread / run / events / token-usage / memory / skills / mcp 等；浏览器已登录时 cookie 自动带上，适合快速复现问题

---

## 9. TUI 终端工作台

embedded harness 之上的 Textual 终端交互界面（`backend/packages/harness/deerflow/tui/`）。

```bash
# 依赖（可选 extra）
cd backend && uv sync --extra tui
# 启动（console script，未装 Textual 时退化为 headless 一次性命令）
deerflow
```

- 支持 `/` 命令、Ctrl+C 中断、Ctrl+L 重绘
- `deerflow --help` 看参数（headless one-shot：`print` / `json` 模式可直接脚本消费）

---

## 10. 嵌入式客户端 DeerFlowClient

进程内直连，不走 HTTP，返回结构与 Gateway 对齐；适合**脚本化复现与单测级调试**。

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()
for event in client.stream("用 bash 列出当前目录", thread_id="debug-thread"):
    if event.event == "messages-tuple":
        for chunk in event.data:
            if chunk[0].content:
                print(chunk[0].content, end="")
    elif event.event == "custom":
        print("\n[custom]", event.data)
```

> `client.stream()` 订阅 `values / messages / custom`，与 Gateway 并行路径（详见 STREAMING.md）。

---

## 11. LangGraph 兼容 API / SDK

Nginx 将 `/api/langgraph/*` 重写为 Gateway 的 LangGraph 兼容运行时，wire 格式与 LangGraph Platform 对齐：

- 可用 `@langchain/langgraph-sdk` 的 `Client` / `useStream()` 直接操作
- 前端即如此工作（`NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api/langgraph`）
- 适合把 DeerFlow run 接到既有 LangGraph 调试/可视化工具

---

## 12. 典型排障流程

遇到 Agent 表现异常时，按此顺序收敛：

1. **看发生了什么**：前端对话流（SSE）→ 若已结束，`GET /api/threads/{tid}/runs/{rid}/events` 拉全量事件
2. **定位到步**：事件里找 `llm.error` / `run.error` / `llm.tool.result`；子代理问题看 `subagent.*`
3. **查状态**：`GET /api/threads/{tid}/state` 确认 messages/artifacts 是否符合预期
4. **查文件**：`GET .../workspace-changes` 看工作区被怎么改的
5. **查 token/成本**：`GET /api/threads/{tid}/token-usage`
6. **查底层**：`docker compose -p eai-docker logs -f gateway`（临时调 `log_level: debug`）
7. **外部 trace**：如已开 Langfuse/LangSmith，直接按 `session_id=thread_id` 查完整调用链

> 排障前先查 `.wolf/buglog.json` 是否已有已知修复；每次定位到根因后按 OpenWolf 规范补 buglog。

---

## 13. 自然语言诊断（ops-diagnosis 技能）

EAI-CUSTOM（route-D，2026-08-19）：把"回放分析一次 agent 执行"从手工 curl+脚本变成**一句自然语言指令**。对 agent（或 iLink/渠道 bot）说：

> 分析线程 `<thread_id>` 的执行情况 / 刚才那次任务为什么烧了这么多 token / 检查 bid-proposal-writing 有没有违反契约

Agent 激活 `ops-diagnosis` 技能后走固定流水线：**MCP 取数 → 脚本统计 → 契约对照 → 证据化报告**（数字全部来自脚本产物，每个问题带 `(run8, seq)` 事件证据）。

### 组成

| 层 | 落点 | 说明 |
|---|---|---|
| MCP 工具 | `backend/app/extensions/ops_diagnosis/mcp.py`（注册名 `ops-diagnosis`） | `ops_list_thread_runs`（run 清单+终态+token）；`ops_get_run_events`（事件流，服务端 event_type/text_match 过滤防上下文爆炸）。只读。 |
| 技能 | `skills/public/ops-diagnosis/` | SKILL.md 分阶段流程 + `scripts/`（summarize_runs / extract_failures / extract_sequences，纯 stdlib 统计脚本）+ `references/failure-signatures.md`（失败签名单一参考清单） |
| 测试 | `backend/tests/test_ops_diagnosis.py` | 过滤/截断/空态 + 脚本分类真值表（含"Exit Code 3 是成功"的 bid 契约） |

### 前置与信任边界

- **前置**：`run_events.backend: db`（已切，重启生效）——memory 后端下 MCP 工具查不到重启前的事件。
- **信任边界（v1）**：stdio MCP 会话不携带调用者身份，**启用的 server 允许任何 agent 读任何用户线程的事件**——仅限内网运维/管理员部署场景；给普通用户开放要等 per-user MCP 身份透传。要关闭：`extensions_config.json → mcpServers["ops-diagnosis"].enabled = false`。
- 已知盲区：trace 截断保**头部**，超长 bash 输出尾部的 Traceback/Exit Code 可能丢失 → 失败数是下界（报告会注明）。

### 与其它手段的关系

- §3 的事件回放 API 是"人肉版"取数；本节是 agent 自动化版（同一张 `run_events` 表）。
- FailureStreakMiddleware（设计中，bug-017）的失败分类器与 `references/failure-signatures.md` 保持同一份签名清单。
- 实时告警不归它管（事后归因，不是 watchdog）。

---

## 变更记录

- 2026-08-17 初版：盘点 12 种监控/调试手段并补齐配置与操作步骤。
- 2026-08-19 EAI-CUSTOM：§13 自然语言诊断（ops-diagnosis 技能 + MCP 工具）；`run_events.backend` 切 `db`。
