# 数据源 Tier 1:Agent 感知 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Agent 写报告时主动使用用户已连的数据源 —— 加 `description` 字段 + MCP 输出带 description + 系统提示静态指令。

**Architecture:** Option A(静态指令,不跨 harness/app 边界)。3 处改动:模型加 `description` 列(经 `migrate_db` 幂等 ALTER 升级既有表)、`list_data_sources`/`get_data_source_schema` 输出带 description、`SYSTEM_PROMPT_TEMPLATE` 加一段静态"数据源工具使用"指令。

**Tech Stack:** Python 3.12 · SQLAlchemy 2.0 · FastAPI · MCP SDK · Next.js/React/TS。pytest + Vitest/类型检查。

**关键约束:** 提交只用 pathspec(活跃分支有并发 agent);后端 pytest 从 `backend/` 跑 `PYTHONPATH=. uv run pytest`;前端改完 `docker compose -p eai-docker restart frontend`。

---

## 文件结构

修改:
- `backend/app/extensions/models/__init__.py` — `DataSource` 加 `description`
- `backend/app/extensions/database.py` — `migrate_db()` 加 `ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS description TEXT`
- `backend/app/extensions/data_source/schemas.py` — 3 个 schema 加 `description`
- `backend/app/extensions/data_source/mcp.py` — list/schema 输出带 description
- `backend/packages/harness/deerflow/agents/lead_agent/prompt.py` — 静态指令段 + 模板占位
- `frontend/src/extensions/data-source/types.ts` — DataSource/CreateRequest 加 `description`
- `frontend/src/extensions/data-source/api.ts` — transform + create/update body 带 description
- `frontend/src/extensions/data-source/components/DataSourceForm.tsx` — description textarea
- `frontend/src/extensions/data-source/components/DataSourceCard.tsx` — 显示 description(可选一行)

测试:
- `backend/tests/test_data_source_models.py`(追加)
- `backend/tests/test_data_source_routers.py`(追加)
- `backend/tests/test_data_source_mcp.py`(追加)
- `backend/tests/test_prompt_template.py`(新建,断言静态段存在)

---

## Task 1: `DataSource.description` 字段(模型 + 迁移 + schemas)

**Files:** models/__init__.py · database.py(migrate_db) · data_source/schemas.py · tests/test_data_source_models.py · tests/test_data_source_routers.py

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_data_source_models.py` 的 `test_defaults` 末尾加断言:
```python
        assert ds.description is None
```
并在 `test_data_source_routers.py` 的 `_fake_ds` helper 的 `base` dict 加 `"description": None,`,再加一个新测试:
```python
@pytest.mark.asyncio
async def test_create_with_description():
    created = _fake_ds(name="n", )  # reuse helper
    created.description = "厂界噪声2024"
    with patch("app.extensions.data_source.routers.DataSourceService.get_by_name",
               AsyncMock(return_value=None)), patch(
        "app.extensions.data_source.routers.DataSourceService.create",
        AsyncMock(return_value=created)):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/extensions/data-sources",
                json={"name": "n", "type": "api", "connection_config": {}, "description": "厂界噪声2024"})
    assert resp.status_code == 201
    assert resp.json()["description"] == "厂界噪声2024"
```
(Note:`_fake_ds` 已把所有 DataSourceResponse 字段铺满;加 description 键即可。若 `_fake_ds` 用 `**ov` 覆盖,直接传 description。)

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_models.py tests/test_data_source_routers.py -q`
Expected: model 失败(`description` 属性不存在)/ router 失败(响应无 description)。

- [ ] **Step 3a: 模型** — 在 `backend/app/extensions/models/__init__.py` 的 `DataSource` 类 `name` 字段后加:
```python
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
```
(`Text` 已在文件顶部导入。)

- [ ] **Step 3b: 迁移** — 在 `backend/app/extensions/database.py` 的 `migrate_db()` 内(任意幂等位置,建议紧跟 role_permissions 块之后)加:
```python
        await conn.execute(text(
            "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS description TEXT"
        ))
```

- [ ] **Step 3c: schemas** — 在 `backend/app/extensions/data_source/schemas.py`:
  - `DataSourceCreate` 加:`    description: str | None = None`
  - `DataSourceUpdate` 加:`    description: str | None = None`
  - `DataSourceResponse` 加(在 `name` 后):`    description: str | None = None`
  - service `create`/`update` 已用 `req.model_dump()`/字段传递;确认 `create` 传 `description=req.description`(在 `DataSourceService.create` 里:`description=req.description,`)。

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_models.py tests/test_data_source_routers.py tests/test_data_source_service.py -q`
Expected: 全绿(含新断言/新测试)。

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/models/__init__.py backend/app/extensions/database.py backend/app/extensions/data_source/schemas.py backend/app/extensions/data_source/service.py backend/tests/test_data_source_models.py backend/tests/test_data_source_routers.py
git commit -m "feat(data-source): add description field (model + migrate ALTER + schemas)"
```

---

## Task 2: MCP list/schema 输出带 description

**Files:** data_source/mcp.py · tests/test_data_source_mcp.py

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_data_source_mcp.py` 的 `test_list_data_sources_handler` 里,把 fake 的 `description` 设上并断言返回含它:
```python
    fake.description = "厂界噪声2024"
```
(在 `fake = MagicMock()` 之后),并在断言段加:
```python
    assert payload["data_sources"][0]["description"] == "厂界噪声2024"
```

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_mcp.py::test_list_data_sources_handler -q`
Expected: KeyError / 返回无 description。

- [ ] **Step 3: 实现** — `backend/app/extensions/data_source/mcp.py`:
  - `_handle_list_data_sources` 的 `_q` 返回 dict 加:`"description": r.description,`
  - `_handle_get_data_source_schema` 的 database 分支返回 dict 加:`"description": src.description,`;非 database 分支返回 dict 也加:`"description": src.description,`

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_mcp.py -q`
Expected: 全绿。

- [ ] **Step 5: 提交**
```bash
git add backend/app/extensions/data_source/mcp.py backend/tests/test_data_source_mcp.py
git commit -m "feat(data-source): MCP list/schema output includes description"
```

---

## Task 3: 系统提示静态数据源指令(harness prompt)

**Files:** deerflow/agents/lead_agent/prompt.py · tests/test_prompt_template.py(新建)

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_prompt_template.py`:
```python
"""Verify the static data-source instruction is present in the rendered system prompt."""

from deerflow.agents.lead_agent.prompt import apply_prompt_template


def test_system_prompt_mentions_data_source_tools():
    prompt = apply_prompt_template(agent_name="EAIFlow")
    assert "list_data_sources" in prompt
    assert "query_data_source" in prompt
    assert "外部数据源" in prompt
```

- [ ] **Step 2: 运行确认失败**
`cd backend && PYTHONPATH=. uv run pytest tests/test_prompt_template.py -q`
Expected: AssertionError(当前 prompt 无这些串)。

- [ ] **Step 3: 实现** — `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`:

(a) 在 `SYSTEM_PROMPT_TEMPLATE = """` 之后(模块级,模板字符串定义之前)加常量:
```python
DATA_SOURCES_PROMPT_SECTION = """<data_sources>
## 外部数据源(可选)
如果当前任务(尤其是写报告、回答涉及真实数据)需要真实数据,你可以查询用户已配置的外部数据源:
- 先调 list_data_sources 查看有哪些数据源(注意每个源的 description,据此选择最相关的)。
- 用 get_data_source_schema 了解其表/字段或接口结构。
- 用 query_data_source 取数(database 为只读 SQL,强制 SELECT/WITH、自动 LIMIT 200;api 为 GET)。
把取到的真实数据写进报告/回答,并标注来源(数据源名称 + 查询时间)。若这些工具未直接可见,用 tool_search 检索。没有相关数据源时忽略本段。
</data_sources>"""
```

(b) 在 `SYSTEM_PROMPT_TEMPLATE` 内,`{deferred_tools_section}`(约 line 450)之后加一行:
```
{data_sources_section}
```

(c) 在 `apply_prompt_template` 的 `return SYSTEM_PROMPT_TEMPLATE.format(`(约 line 797)的参数列表加:
```python
        data_sources_section=DATA_SOURCES_PROMPT_SECTION,
```

- [ ] **Step 4: 运行确认通过**
`cd backend && PYTHONPATH=. uv run pytest tests/test_prompt_template.py -q`
Expected: 1 passed。

- [ ] **Step 5: 提交**
```bash
git add backend/packages/harness/deerflow/agents/lead_agent/prompt.py backend/tests/test_prompt_template.py
git commit -m "feat(prompt): static data-source tools instruction in system prompt"
```

---

## Task 4: 前端 description 输入/显示

**Files:** data-source/types.ts · data-source/api.ts · components/DataSourceForm.tsx · components/DataSourceCard.tsx

- [ ] **Step 1: types.ts** — `DataSource` 接口加 `description: string | null;`;`CreateDataSourceRequest` 加 `description?: string;`

- [ ] **Step 2: api.ts** — `transformDataSource` 返回对象加:
```ts
    description: (data.description as string) ?? null,
```
`create` 与 `update` 的 JSON body 各加:
```ts
        description: req.description,
```

- [ ] **Step 3: DataSourceForm.tsx** — 加 state(与 name 同处):`const [description, setDescription] = useState("");`;在 `useEffect` 回填里 `setDescription(initialData.description ?? "");`;在「名称」输入框的 `<div>` 之后插入:
```tsx
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  描述 <span className="text-xs text-muted-foreground">(给 AI:这个数据源里是什么)</span>
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="例如:厂界噪声 2024 年监测值"
                  rows={2}
                  className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
```
并在 `handleSubmit` 的 `onSubmit({ ... })` 里加 `description,`(或 `description: description || undefined,`)。

- [ ] **Step 4: DataSourceCard.tsx**(可选,显示一行)— 在 name 下方加:
```tsx
{source.description && (
  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{source.description}</p>
)}
```

- [ ] **Step 5: 类型检查 + 重启前端**
```bash
cd frontend && pnpm typecheck
```
Expected: 0 errors。然后 `docker compose -p eai-docker restart frontend`(若 HMR 没生效)。

- [ ] **Step 6: 提交**
```bash
git add frontend/src/extensions/data-source/types.ts frontend/src/extensions/data-source/api.ts frontend/src/extensions/data-source/components/DataSourceForm.tsx frontend/src/extensions/data-source/components/DataSourceCard.tsx
git commit -m "feat(data-source): frontend description field (form/card/types/api)"
```

---

## Task 5: 落地验证

- [ ] **Step 1: 重启 gateway,触发 ALTER 加列**
```bash
docker compose -p eai-docker restart gateway && sleep 16
PG=$(docker ps --format "{{.Names}}" | grep -iE "postgres.*ext" | head -1)
docker exec "$PG" psql -U agentflow -d agentflow -c "\d data_sources" | grep description
```
Expected: 出现 `description | text |`(列已加)。

- [ ] **Step 2: 全量后端测试**
`cd backend && PYTHONPATH=. uv run pytest tests/test_data_source_models.py tests/test_data_source_service.py tests/test_data_source_routers.py tests/test_data_source_mcp.py tests/test_prompt_template.py -q`
Expected: 全绿。

- [ ] **Step 3: 渲染的系统提示含指令(在容器内验证)**
```bash
docker compose -p eai-docker exec -T -w /app/backend gateway /app/backend/.venv/bin/python -c "
from deerflow.agents.lead_agent.prompt import apply_prompt_template
p = apply_prompt_template(agent_name='EAIFlow')
print('has list_data_sources:', 'list_data_sources' in p)
print('has query_data_source:', 'query_data_source' in p)
"
```
Expected: 两个都 True。

- [ ] **Step 4: 端到端(人工,经 UI)** — 设置→数据源→添加→填名称 + **描述**→创建(卡片显示描述)→测连接/同步正常。在报告对话里要一个用数据的章节,观察 Agent 是否主动 list→选源→取数(人工判断)。

---

## Self-Review

- **Spec 覆盖**:spec §4(description 字段)→ Task 1;§5(MCP 输出)→ Task 2;§6(静态指令)→ Task 3;§4.4(前端)→ Task 4;§9(验收)→ Task 5。全覆盖。
- **占位符**:无 TBD;每步含完整代码;Task 1 的 `_fake_ds` 复用已在文件中定义。
- **类型一致**:`description` 字段名在 model/schema/MCP/prompt-test/前端 types/api 全程一致;api.ts transform `description` 单字直通(snake/camel 无差异)。
- **边界**:Task 3 纯 harness 静态文本,不 import app;不破坏 prefix-cache(整段静态)。
