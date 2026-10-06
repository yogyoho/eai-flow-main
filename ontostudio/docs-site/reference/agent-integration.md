# Agent 集成指南

> 对齐：`extensions_config.json` + 主系统 `skills/public/` @ 2026-10-06
> 本页面向把 OntoStudio 图谱接进 EAI 系统 Agent 的集成者。2026-10-05 已端到端实测通过。

## 前置条件

1. ontostudio-backend 容器在跑（MCP 服务随它提供，端口 8005）：

   ```bash
   docker compose -p eai-docker up -d ontostudio-backend   # 显式点名即激活 ontostudio profile
   ```

2. 主系统 gateway 能解析到 `ontostudio` 主机名（同一 docker 网络）。

## MCP 服务注册

主系统 `extensions_config.json` 两条服务（已 enabled）：

| 服务 | URL | 角色 |
|---|---|---|
| `ontology` | `http://ontostudio:8005/mcp/ontology` | 只读：语义层查询/推理/聚合 |
| `doc-graph` | `http://ontostudio:8005/mcp/doc-graph` | 写侧：抽取入库/复核/合并/规则推理 |

鉴权：共享内网头，两侧同值即可。

```json
"headers": { "X-Internal-Auth": "$ONTOSTUDIO_INTERNAL_AUTH_TOKEN" }
```

- 占位符在 gateway 进程解析；值放 **`docker/.env`**（compose 插值来源——只写根 `.env` 会被 gateway 侧 `environment:` 空插值条目覆盖）。
- 未设置时两侧皆空 = 内网匿名开放（ontostudio 侧打一次性 warning），仅限单机内网调试。

注册后主系统 gateway 热加载（`extensions_config.json` mtime 失效缓存），无需重启；前端 Capability Center → MCP 应看到两条服务已连接。

## 技能包装层

裸 MCP 工具之上有两个技能（主系统 `skills/public/`，extensions_config `skills` 段启用），给 Agent 注入使用纪律：

| 技能 | 侧 | 何时触发 |
|---|---|---|
| `ontology-graph-query` | 读 | "查图谱 / 实体关系梳理 / 报告取材用图谱事实 / 图谱合规体检" |
| `doc-graph-extract` | 写 | "构建图谱 / 抽取实体入库 / 图谱化这份文档" |

触发词互斥：查图谱 vs 抽取入库，不会互相误触。

## 实测路径（API 通道）

```text
1. 登录    POST /api/extensions/auth/login
           {"username": "<工号或email>", "password": "<密码>"}
           ⚠️ 必带 Origin 头（如 http://localhost:2026），否则 403 Cross-site auth request denied
           → 得 access_token + csrf_token 两个 cookie
2. 建线程  POST /api/langgraph/threads        （头：X-CSRF-Token = csrf cookie 值）
3. 投递    POST /api/langgraph/threads/{id}/runs/wait
           {"assistant_id": "lead-agent",
            "input": {"messages": [{"role": "user", "content": "..."}]},
            "config": {"recursion_limit": 250},
            "on_disconnect": "continue"}
```

**`recursion_limit` 必须显式给**：默认 100。首轮 Agent 要 `tool_search` 晋升 MCP 工具 schema（约 4 次）+ 按技能纪律巡视，实测会打穿默认值报 `GraphRecursionError`；250 + 收紧提问（指定工具、限定调用次数）后 19 秒干净返回。

## 运行时注意

- **工具名带服务前缀**：Agent 侧看到的是 `ontology_describe_ontology`、`ontology_query_entity` 等；延迟加载开启时先 `tool_search` 晋升再调用。
- **force_review 门**：抽取入库默认全量置待复核，未经消解审核确认的实体不投影进 kernel 图——Agent 查不到。先在「04 消解审核」确认（深读：[审阅闭环](../guide/review-loop)）。
- **跨域链路空是数据问题**：cross_module 四链路未补数据前，`get_links`/`traverse` 跨域返回空——如实告知，不是集成坏了。
- **写侧慎用**：`review_entity` / `invoke_action` 是受治理动作，仅在用户明确要求且确认对象清单时调用。
