# 投标报价分析 (bid-quote) 前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给已就绪的「投标报价分析」数据层(Route B:`data_source` `bid-quote` + mock_market + SKILL.md)补上应用中心入口、科技感仪表盘、固定视图查询页 + modal 下钻,让市场部用户可视化使用。

**Architecture:** Route B 薄前端 —— 不建扩展包/不建业务表。前端直调 `data_source` 现有 REST,仅需在后端 `data_source` 路由上加 2 个只读 query 端点(复用已有 `run_readonly_query` + `assert_readonly_select` 守卫)+ seed 加 1 个罐装 dataset。前端镜像 contract-price 结构(`bqa` 命名空间),项目管理 list 浅色风格 + 图表 cyber 增强。

**Tech Stack:** FastAPI(Python 3.12)、Next.js 16 / React 19 / Tailwind 4 / TanStack Query / recharts ^3.8.1、PostgreSQL(mock_market,postgres-ext)、yaml 驱动权限。

**关联 spec:** `docs/superpowers/specs/2026-08-13-bid-quote-frontend-design.md`

---

## File Structure

**Backend(改 3 + 测试 1):**
- `backend/app/extensions/data_source/routers.py` — 加 2 个只读 query 端点(+`assert_readonly_select` import)
- `backend/app/extensions/data_source/schemas.py` — 加 `SqlQueryRequest` / `QueryResult`
- `backend/scripts/seed_mock_market.py` — `DATASETS` 加第 4 条「项目报价对比」
- `backend/tests/test_data_source_routers.py` — 加 4 个端点单测

**License / 权限(改 7):**
- `backend/app/extensions/license/service.py` — `ALL_MODULES` 加 `bid_quote`
- `frontend/src/extensions/license/labels.ts` — `MODULE_LABELS` 加 `bid_quote`
- `tools/license/license_generator.py` — `ALL_MODULES` 加 `bid_quote`
- `backend/tests/test_license_modules_sync.py` — `EXPECTED_KEYS` 加 `bid_quote`
- `config/permissions.yaml` — 加 `bid_quote:` 模块块(克隆 spare_parts)
- `config/roles_custom.yaml` — user / dept_head 角色各加 nav/page/data_scope
- `backend/app/extensions/database.py` — domains 加 `marketing`;apps 加磁贴
- `frontend/src/extensions/app-center/hooks/useApps.ts` — `deriveNavId` 加映射

**Frontend(新建 11):**
- `frontend/src/app/bid-quote/layout.tsx`
- `frontend/src/app/bid-quote/page.tsx`
- `frontend/src/app/bid-quote/query/page.tsx`
- `frontend/src/extensions/bid-quote/api.ts`
- `frontend/src/extensions/bid-quote/hooks.ts`
- `frontend/src/extensions/bid-quote/types.ts`
- `frontend/src/extensions/bid-quote/components/DashboardView.tsx`
- `frontend/src/extensions/bid-quote/components/QueryView.tsx`
- `frontend/src/extensions/bid-quote/components/StatCard.tsx`
- `frontend/src/extensions/bid-quote/components/ChartCard.tsx`
- `frontend/src/extensions/bid-quote/components/TechTooltip.tsx`
- `frontend/src/extensions/bid-quote/components/DrillDownModal.tsx`
- `frontend/src/extensions/bid-quote/components/ui/table.tsx`

---

## Task 1: Backend — 2 个只读 query 端点(TDD)

**Files:**
- Modify: `backend/app/extensions/data_source/schemas.py`(末尾追加 2 个 model)
- Modify: `backend/app/extensions/data_source/routers.py`(import 行 + 末尾追加 2 个路由)
- Test: `backend/tests/test_data_source_routers.py`(追加 4 个测试)

### - [ ] Step 1: 写失败测试

在 `backend/tests/test_data_source_routers.py` 末尾追加(复用文件已有的 `_build_app` / `_fake_ds` / `AsyncMock` / `ASGITransport` / `AsyncClient`):

```python
def _fake_dataset(**overrides):
    """fake DataSourceDataset,字段对齐 DatasetResponse。"""
    base = {
        "id": uuid4(),
        "source_id": uuid4(),
        "table_name": "bid_summary",
        "label": "投标总览",
        "description": "x",
        "key_columns": [],
        "default_query": "SELECT 1 AS n",
    }
    base.update(overrides)
    m = MagicMock()
    for k, v in base.items():
        setattr(m, k, v)
    return m


@pytest.mark.asyncio
async def test_query_dataset_runs_default_query():
    """罐装 dataset 端点:跑 dataset.default_query,返回行 + label。"""
    sid = uuid4()
    ds = _fake_ds(id=sid)
    dataset = _fake_dataset(source_id=sid, id=uuid4(), label="投标总览")
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=ds),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.get_dataset",
        AsyncMock(return_value=dataset),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.run_readonly_query",
        AsyncMock(return_value=[{"n": 1}]),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{sid}/datasets/{dataset.id}/query")
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"n": 1}], "row_count": 1, "label": "投标总览"}


@pytest.mark.asyncio
async def test_query_dataset_404_when_source_missing():
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=None),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/extensions/data-sources/{uuid4()}/datasets/{uuid4()}/query")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_query_sql_rejects_write():
    """raw-SQL 端点:DELETE 被 assert_readonly_select 拒 → 400。"""
    sid = uuid4()
    ds = _fake_ds(id=sid)
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=ds),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/extensions/data-sources/{sid}/query",
                json={"sql": "DELETE FROM mock_bid"},
            )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_query_sql_runs_readonly_select():
    """raw-SQL 端点:合法 SELECT 跑通,返回行(label=None)。"""
    sid = uuid4()
    ds = _fake_ds(id=sid)
    with patch(
        "app.extensions.data_source.routers.DataSourceService.get_by_id",
        AsyncMock(return_value=ds),
    ), patch(
        "app.extensions.data_source.routers.DataSourceService.run_readonly_query",
        AsyncMock(return_value=[{"k": 7}]),
    ):
        app = _build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/extensions/data-sources/{sid}/query",
                json={"sql": "SELECT 7 AS k"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"rows": [{"k": 7}], "row_count": 1, "label": None}
```

### - [ ] Step 2: 跑测试确认失败

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_data_source_routers.py -k "query_dataset or query_sql" -v'`
Expected: 4 个 FAIL(404 路由不存在 / 端点未定义)。

### - [ ] Step 3: 加 schemas

在 `backend/app/extensions/data_source/schemas.py` 末尾追加:

```python
class SqlQueryRequest(BaseModel):
    """前端下钻参数化只读 SQL 的请求体。"""

    sql: str = Field(..., min_length=1, max_length=4000)


class QueryResult(BaseModel):
    """只读查询结果(罐装 / 下钻共用)。"""

    rows: list[dict]
    row_count: int
    label: str | None = None
```

### - [ ] Step 4: 改 routers import 行

`backend/app/extensions/data_source/routers.py` 第 21 行:

```python
from app.extensions.data_source.service import DataSourceService
```

改为:

```python
from app.extensions.data_source.service import DataSourceService, assert_readonly_select
```

并在顶部 schemas import 块(第 9-20 行那个 `from app.extensions.data_source.schemas import (` 列表)里加 `QueryResult` 和 `SqlQueryRequest`(按字母序插入即可):

```python
from app.extensions.data_source.schemas import (
    DatasetCreate,
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdate,
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
    QueryResult,
    SqlQueryRequest,
    SyncResponse,
    TestConnectionResult,
)
```

### - [ ] Step 5: 加 2 个路由

在 `backend/app/extensions/data_source/routers.py` 末尾(`delete_dataset` 之后)追加:

```python
# ── EAI-CUSTOM: 透出已有 MCP 只读查询能力供前端仪表盘/查询页使用(模块① 投标报价分析) ──
# 仅 SELECT/WITH;写操作/多语句/SELECT INTO 由 assert_readonly_select fail-closed 拒绝。
# 不新建业务表、不改守卫语义,只是把 DataSourceService.run_readonly_query 暴露给 REST。


@router.post("/{source_id}/datasets/{dataset_id}/query", response_model=QueryResult)
async def query_dataset(
    source_id: UUID,
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """跑指定 dataset 的 default_query(罐装视图,供仪表盘/查询页固定视图)。"""
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    dataset = await DataSourceService.get_dataset(db, dataset_id)
    # 跨源隔离:dataset 必须属于该 source(防越权读)
    if dataset is None or str(dataset.source_id) != str(source_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    rows = await DataSourceService.run_readonly_query(ds, dataset.default_query)
    return QueryResult(rows=rows, row_count=len(rows), label=dataset.label)


@router.post("/{source_id}/query", response_model=QueryResult)
async def query_source_sql(
    source_id: UUID,
    body: SqlQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission("system:access")),  # EAI-CUSTOM: Add permission check
):
    """下钻参数化只读 SQL(前端按白名单维度拼接,assert_readonly_select 守卫)。"""
    ds = await DataSourceService.get_by_id(db, source_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据源不存在")
    try:
        safe_sql = assert_readonly_select(body.sql)  # fail-closed:非 SELECT/写操作/多语句 → ValueError
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    rows = await DataSourceService.run_readonly_query(ds, safe_sql)
    return QueryResult(rows=rows, row_count=len(rows))
```

### - [ ] Step 6: 跑测试确认通过

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_data_source_routers.py -v'`
Expected: 全部 PASS(含原有 + 新增 4 个)。

### - [ ] Step 7: 重启 gateway + lint

```bash
docker compose -p eai-docker restart gateway
docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && .venv/bin/ruff check app/extensions/data_source/routers.py app/extensions/data_source/schemas.py'
```

### - [ ] Step 8: Commit

```bash
git add backend/app/extensions/data_source/routers.py backend/app/extensions/data_source/schemas.py backend/tests/test_data_source_routers.py
git commit -m "feat(bid-quote): data_source 加 2 个只读 query 端点(罐装 dataset + 下钻 SQL),守卫不变"
```

---

## Task 2: Backend — seed 加第 4 个罐装 dataset

**Files:**
- Modify: `backend/scripts/seed_mock_market.py`(DATASETS 列表追加 1 条)

### - [ ] Step 1: 加 dataset 定义

在 `backend/scripts/seed_mock_market.py` 的 `DATASETS = [ ... ]` 列表里(`win_rate_by_segment` 那条之后、列表闭合 `]` 之前,约 234 行)追加:

```python
    {
        "table_name": "bqa_project_showdown",
        "label": "项目报价对比",
        "description": "项目级我方 vs 友商中标报价对比,标注我方胜负。支撑仪表盘第 3 图与报价区间建议。",
        "default_query": """
            SELECT project_name,
              MAX(winning_price) FILTER (WHERE bidder_role='ours') AS our_price,
              MAX(winning_price) FILTER (WHERE bidder_role='competitor') AS competitor_price,
              BOOL_OR(bidder_role='ours' AND won) AS we_won,
              MAX(customer) AS customer
            FROM mock_bid GROUP BY project_name ORDER BY MIN(wid)
        """.strip(),
    },
```

### - [ ] Step 2: 重跑 seed(幂等:TRUNCATE+CASCADE reseed + ON CONFLICT upsert)

```bash
docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/python scripts/seed_mock_market.py'
```
Expected: `[ok] 已 upsert 4 个 dataset`(从 3 变 4)+ 自检汇总打印。

### - [ ] Step 3: 校验第 4 条入库

```bash
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT label, table_name FROM data_source_datasets WHERE source_id=(SELECT id FROM data_sources WHERE name='bid-quote') ORDER BY label;"
```
Expected: 4 行,含 `项目报价对比 | bqa_project_showdown`。

### - [ ] Step 4: Commit

```bash
git add backend/scripts/seed_mock_market.py
git commit -m "feat(bid-quote): seed 加「项目报价对比」罐装 dataset(我方 vs 友商 per project)"
```

---

## Task 3: License 4 点同步

**Files:**
- Modify: `backend/app/extensions/license/service.py`(`ALL_MODULES`)
- Modify: `frontend/src/extensions/license/labels.ts`(`MODULE_LABELS`)
- Modify: `tools/license/license_generator.py`(`ALL_MODULES`)
- Modify: `backend/tests/test_license_modules_sync.py`(`EXPECTED_KEYS`)

### - [ ] Step 1: 先让同步测试失败(确认是这 4 处)

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_license_modules_sync.py -v'`
Expected: FAIL,提示 `bid_quote` 缺失(4 处集合不一致)。这正指出要改的位置。

### - [ ] Step 2: 4 处各加 `bid_quote`

用 grep 定位每个集合的相邻条目(以 `spare_parts` 为邻):

```bash
# 后端 service
grep -n "spare_parts" backend/app/extensions/license/service.py
# 前端 labels
grep -n "spare_parts" frontend/src/extensions/license/labels.ts
# 生成器
grep -n "spare_parts" tools/license/license_generator.py
# 测试
grep -n "spare_parts" backend/tests/test_license_modules_sync.py
```

在每处 `spare_parts` 条目旁加同形式的 `bid_quote` 条目:

- `backend/app/extensions/license/service.py` 的 `ALL_MODULES`(set/list):加 `"bid_quote"`
- `frontend/src/extensions/license/labels.ts` 的 `MODULE_LABELS`:加 `bid_quote: "投标报价分析",`(若该文件是对象字面量;保持与 `spare_parts: "备品备件价格分析",` 同格式)
- `tools/license/license_generator.py` 的 `ALL_MODULES`:加 `"bid_quote"`
- `backend/tests/test_license_modules_sync.py` 的 `EXPECTED_KEYS`:加 `"bid_quote"`

### - [ ] Step 3: 跑测试确认通过

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_license_modules_sync.py -v'`
Expected: PASS。

### - [ ] Step 4: Commit

```bash
git add backend/app/extensions/license/service.py frontend/src/extensions/license/labels.ts tools/license/license_generator.py backend/tests/test_license_modules_sync.py
git commit -m "feat(bid-quote): license 注册 bid_quote 模块(4 点同步)"
```

---

## Task 4: 权限 yaml + 应用中心磁贴 + nav 映射

**Files:**
- Modify: `config/permissions.yaml`(加 `bid_quote:` 模块块)
- Modify: `config/roles_custom.yaml`(user / dept_head 各加 nav/page/data_scope)
- Modify: `backend/app/extensions/database.py`(domains 加 marketing;apps 加磁贴)
- Modify: `frontend/src/extensions/app-center/hooks/useApps.ts`(`deriveNavId` 加映射)

### - [ ] Step 1: permissions.yaml 加 `bid_quote:` 模块块

在 `config/permissions.yaml` 的 `spare_parts:` 块之后(约 175 行 `csp_dept` 那条之后、`output:` 块之前)插入:

```yaml
  # ─── 投标报价分析（应用中心 → 市场营销；Route B 数据源只读视图）───
  bid_quote:
    display_name: "投标报价分析"
    nav_id: "nav:bid-quote"
    pages:
      - id: "bqa:page:dashboard"
        display_name: "分析仪表盘"
      - id: "bqa:page:query"
        display_name: "数据查询"
    data_scopes:
      - { id: "bqa_all", display_name: "全部投标数据", rule_template: {} }
      - { id: "bqa_dept", display_name: "本部门投标", rule_template: { dept_id IN: "$identity.dept_ids" } }
```

同时在该文件 `project_manager` 与 `dept_head` 角色块的 `data_scopes:` 列表里各加一行 `- bqa_dept`(与既有 `- cpa_dept` / `- csp_dept` 并列)。

### - [ ] Step 2: roles_custom.yaml 给 user 角色加权限点

`config/roles_custom.yaml` 里 level 60 的角色(含 `nav:` 以 `- nav:workflow-admin` 结尾、`data_scopes:` 含 `csp_dept`/`doc_project_member`、`pages:` 以 `- settings:page:license` 结尾并在下一行接 `dept_head:`)。三处插入:

**nav**(在 `- nav:workflow-admin` 后加):
```yaml
    - nav:workflow-admin
    - nav:bid-quote
    data_scopes:
```

**data_scopes**(在 `- doc_project_member` 后、`is_system: false` 前加):
```yaml
    - doc_project_member
    - bqa_dept
    is_system: false
    level: 60
```

**pages**(在 `- settings:page:license` 后、`dept_head:` 前加):
```yaml
    - settings:page:license
    - bqa:page:dashboard
    - bqa:page:query
  dept_head:
```

### - [ ] Step 3: roles_custom.yaml 给 dept_head 角色加权限点

`dept_head:` 角色块。三处插入:

**nav**(`- nav:writing` 后、`data_scopes:` 前;该组合在 dept_head 唯一):
```yaml
    - nav:writing
    - nav:bid-quote
    data_scopes:
```

**data_scopes**(`- doc_project_member` 后、`pages:` 前加):
```yaml
    - doc_project_member
    - bqa_dept
    pages:
```

**pages**(末尾 `- kf:page:extraction` 后、`is_system: false` 前加):
```yaml
    - kf:page:extraction
    - bqa:page:dashboard
    - bqa:page:query
    is_system: false
    level: 50
```

### - [ ] Step 4: database.py 加 marketing 域 + 磁贴

`backend/app/extensions/database.py` 的 domains 列表(1591-1597),在 `procurement` 后加 `marketing`:

```python
                for domain in [
                    {"key": "universal", "label": "通用工具", "accent": "blue", "sort": 0, "universal": True},
                    {"key": "admin", "label": "系统管理", "accent": "slate", "sort": 1, "universal": True},
                    {"key": "report", "label": "报告编撰", "accent": "violet", "sort": 2, "universal": False},
                    {"key": "knowledge", "label": "知识管理", "accent": "cyan", "sort": 3, "universal": False},
                    {"key": "procurement", "label": "采购管理", "accent": "amber", "sort": 4, "universal": False},
                    {"key": "marketing", "label": "市场营销", "accent": "violet", "sort": 5, "universal": False},
                ]:
```

apps 列表(1607-1641),在 `spare-parts` 磁贴之后加 `bid-quote` 磁贴:

```python
                    {"app_id": "spare-parts", "name": "备品备件价格分析", "desc": "跨客户备品备件价格聚类与统计，OCR 解析与认领归并",
                     "icon": "package", "domain": "procurement", "stage": "process",
                     "path": "/spare-parts", "license": "spare_parts", "admin": False, "sort": 11, "sort_key": "beipinbeijian"},
                    {"app_id": "bid-quote", "name": "投标报价分析", "desc": "投标中标率、我方与友商报价对比、自产外购构成分析",
                     "icon": "gavel", "domain": "marketing", "stage": "analysis",
                     "path": "/bid-quote", "license": "bid_quote", "admin": False, "sort": 12, "sort_key": "toubaoajiagenfenxi"},
```

并把 seed 完成日志 `"Seeded app-center: 5 domains + 11 apps"` 改为 `"Seeded app-center: 6 domains + 12 apps"`。

> 注意:`app_domains` seed 是 `ON CONFLICT DO NOTHING`,已有库里 marketing 不会自动补。需手动补一行(Step 6)。

### - [ ] Step 5: useApps.ts 加 nav 映射

`frontend/src/extensions/app-center/hooks/useApps.ts` 的 `deriveNavId` mapping(77-83)加一行:

```typescript
  const mapping: Record<string, string> = {
    "contract-price": "nav:contract-price",
    "bid-quote": "nav:bid-quote",
    "knowledge-factory": "nav:knowledge-factory",
    "workflow-admin": "nav:workflow-admin",
    "app-center": "nav:app-center",
  };
```

### - [ ] Step 6: 重启 gateway + 补 marketing 域(已有库)

```bash
docker compose -p eai-docker restart gateway
# 已有库 app_domains 是 ON CONFLICT DO NOTHING,手动补 marketing(幂等)
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "INSERT INTO app_domains (key,label,accent_color,sort_order,is_universal) VALUES ('marketing','市场营销','violet',5,false) ON CONFLICT DO NOTHING;"
# 补 bid-quote 磁贴(同理)
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "INSERT INTO app_definitions (id,app_id,name,description,icon_name,business_domain,stage_tag,path,license_module,admin_only,sort_order,sort_key,is_builtin) VALUES (gen_random_uuid(),'bid-quote','投标报价分析','投标中标率、我方与友商报价对比、自产外购构成分析','gavel','marketing','analysis','/bid-quote','bid_quote',false,12,'toubaoajiagenfenxi',true) ON CONFLICT (app_id) DO NOTHING;"
```

### - [ ] Step 7: 验证磁贴/权限可解析

```bash
# permission registry 热加载(mtime),校验 bid_quote 模块与角色授权
docker compose -p eai-docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "SELECT app_id,name,license_module,business_domain FROM app_definitions WHERE app_id='bid-quote';"
```
Expected: 1 行 bid-quote。前端用 admin 账号登录后应用中心应见「市场营销」域下「投标报价分析」磁贴。

### - [ ] Step 8: Commit

```bash
git add config/permissions.yaml config/roles_custom.yaml backend/app/extensions/database.py frontend/src/extensions/app-center/hooks/useApps.ts
git commit -m "feat(bid-quote): 权限点 + 市场营销域 + 应用中心磁贴 + nav 映射"
```

---

## Task 5: 前端骨架(api/hooks/types + 路由 + table + layout)

**Files:**
- Create: `frontend/src/extensions/bid-quote/types.ts`
- Create: `frontend/src/extensions/bid-quote/api.ts`
- Create: `frontend/src/extensions/bid-quote/hooks.ts`
- Create: `frontend/src/extensions/bid-quote/components/ui/table.tsx`
- Create: `frontend/src/app/bid-quote/layout.tsx`
- Create: `frontend/src/app/bid-quote/page.tsx`
- Create: `frontend/src/app/bid-quote/query/page.tsx`

### - [ ] Step 1: types.ts

`frontend/src/extensions/bid-quote/types.ts`:

```typescript
/**
 * 投标报价分析(bid-quote)类型 —— 对齐 data_source 罐装 dataset 列。
 * Decimal/numeric 经 JSON 序列化为 string;bool 为 boolean|null。
 */

export interface BidSummaryRow {
  project_count: number;
  bid_count: number;
  ours_bid: number;
  ours_won: number;
  ours_win_rate_pct: string | null;
  competitor_bid: number;
  competitor_won: number;
  avg_winning_price: string | null;
  earliest_bid: string | null;
  latest_bid: string | null;
}

export interface CompositionRow {
  goods_name: string;
  ours_self_pct: string | null;
  ours_outsourced_pct: string | null;
  ours_avg_unit_price: string | null;
  competitor_self_pct: string | null;
  competitor_outsourced_pct: string | null;
  competitor_avg_unit_price: string | null;
}

export interface SegmentRow {
  amount_segment: string;
  ours_bid: number;
  ours_won: number;
  ours_win_rate_pct: string | null;
}

export interface ShowdownRow {
  project_name: string;
  our_price: string | null;
  competitor_price: string | null;
  we_won: boolean | null;
  customer: string | null;
}

/** mock_bid / mock_bid_item 明细行:列动态,用索引签名。 */
export type BidItemRow = Record<string, string | number | boolean | null>;

export interface QueryResult<T = Record<string, unknown>> {
  rows: T[];
  row_count: number;
  label?: string | null;
}
```

### - [ ] Step 2: api.ts

`frontend/src/extensions/bid-quote/api.ts`:

```typescript
/**
 * bid-quote API client —— Route B 薄前端直调 data_source REST。
 * base=/api/extensions(authFetch 默认),data-sources 路由前缀 /data-sources。
 */

import { authFetch } from "@/extensions/api/client";

import type { QueryResult } from "./types";

const API_BASE = "/data-sources";
const SOURCE_NAME = "bid-quote";

let sourceIdCache: string | null = null;
const datasetIdCache: Record<string, string> = {};

interface ListItem {
  id: string;
  name?: string;
  label?: string;
}

/** 列出数据源,按 name 匹配拿 id(模块固定 'bid-quote'),结果缓存。 */
export async function resolveSourceId(name = SOURCE_NAME): Promise<string> {
  if (sourceIdCache) return sourceIdCache;
  const resp = await authFetch<{ items: ListItem[] }>(API_BASE);
  const hit = resp.items.find((s) => s.name === name);
  if (!hit) throw new Error(`数据源 "${name}" 未找到`);
  sourceIdCache = hit.id;
  return sourceIdCache;
}

/** 按 label 匹配拿 dataset id(罐装视图),结果缓存。 */
export async function resolveDatasetId(sourceId: string, label: string): Promise<string> {
  if (datasetIdCache[label]) return datasetIdCache[label];
  const resp = await authFetch<{ items: ListItem[] }>(`${API_BASE}/${sourceId}/datasets`);
  const hit = resp.items.find((d) => d.label === label);
  if (!hit) throw new Error(`数据集 "${label}" 未找到`);
  datasetIdCache[label] = hit.id;
  return datasetIdCache[label];
}

/** 跑罐装 dataset 的 default_query(POST,无 body)。 */
export async function queryDataset(sourceId: string, datasetId: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/datasets/${datasetId}/query`, {
    method: "POST",
  });
}

/** 跑下钻参数化只读 SQL(POST body {sql})。 */
export async function querySql(sourceId: string, sql: string): Promise<QueryResult> {
  return authFetch<QueryResult>(`${API_BASE}/${sourceId}/query`, {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

/** 清缓存(刷新按钮用)。 */
export function clearBidQuoteCache() {
  sourceIdCache = null;
  for (const k of Object.keys(datasetIdCache)) delete datasetIdCache[k];
}
```

### - [ ] Step 3: hooks.ts

`frontend/src/extensions/bid-quote/hooks.ts`:

```typescript
/**
 * bid-quote TanStack Query hooks。queryKey 统一 ["bqa", ...] 命名空间。
 * 罐装视图:resolve source/dataset id(缓存)→ queryDataset;
 * 明细/下钻:raw SQL → querySql(后端 assert_readonly_select 守卫)。
 */

import { useQuery } from "@tanstack/react-query";

import { queryDataset, querySql, resolveDatasetId, resolveSourceId } from "./api";
import type {
  BidItemRow,
  BidSummaryRow,
  CompositionRow,
  QueryResult,
  SegmentRow,
  ShowdownRow,
} from "./types";

export const KEYS = {
  summary: ["bqa", "summary"] as const,
  composition: ["bqa", "composition"] as const,
  segment: ["bqa", "segment"] as const,
  showdown: ["bqa", "showdown"] as const,
  bidlist: ["bqa", "bidlist"] as const,
  drilldown: (sql: string) => ["bqa", "drilldown", sql] as const,
};

function useDatasetQuery<T>(key: readonly string[], label: string, enabled = true) {
  return useQuery({
    queryKey: key,
    enabled,
    queryFn: async (): Promise<T[]> => {
      const sid = await resolveSourceId();
      const did = await resolveDatasetId(sid, label);
      const res = await queryDataset(sid, did);
      return res.rows as T[];
    },
  });
}

export const useBidSummary = () => useDatasetQuery<BidSummaryRow>(KEYS.summary, "投标总览");
export const useComposition = () =>
  useDatasetQuery<CompositionRow>(KEYS.composition, "货物构成对比(我方vs友商)");
export const useWinRateBySegment = () => useDatasetQuery<SegmentRow>(KEYS.segment, "按金额段我方中标率");
export const useProjectShowdown = () => useDatasetQuery<ShowdownRow>(KEYS.showdown, "项目报价对比");

export function useBidList(enabled = true) {
  return useQuery({
    queryKey: KEYS.bidlist,
    enabled,
    queryFn: async (): Promise<BidItemRow[]> => {
      const sid = await resolveSourceId();
      const res = await querySql(sid, "SELECT * FROM mock_bid ORDER BY bid_date DESC");
      return res.rows as BidItemRow[];
    },
  });
}

export function useDrillDown(sql: string | null) {
  return useQuery({
    queryKey: KEYS.drilldown(sql ?? ""),
    enabled: !!sql,
    queryFn: async (): Promise<QueryResult> => {
      const sid = await resolveSourceId();
      return querySql(sid, sql as string);
    },
  });
}
```

> **命名空间铁律**:dataset label 必须与 seed 一字不差 —— `投标总览` / `货物构成对比(我方vs友商)` / `按金额段我方中标率` / `项目报价对比`。全文件 grep 确认无 `cpa`/`csp` 残留。

### - [ ] Step 4: ui/table.tsx

`frontend/src/extensions/bid-quote/components/ui/table.tsx`(克隆 contract-price 同款 raw-HTML 原语):

```tsx
/**
 * Lightweight table primitives(raw HTML)—— bid-quote 模块用。
 * 本项目无 shadcn Table,沿用 contract-price 同款 API。
 */

import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full text-left border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("[&_tr]:border-b", className)} {...props} />;
}

export function TableBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-border transition-colors hover:bg-muted/50 cursor-pointer",
        className
      )}
      {...props}
    />
  );
}

export function TableHead({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "h-10 px-2 text-start align-middle text-xs font-medium uppercase tracking-wider text-muted-foreground",
        className
      )}
      {...props}
    />
  );
}

export function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("p-2 align-middle", className)} {...props} />;
}
```

### - [ ] Step 5: layout.tsx

`frontend/src/app/bid-quote/layout.tsx`(镜像 contract-price layout,2 个 nav):

```tsx
"use client";

import { LayoutDashboard, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { usePermission } from "@/core/permissions";
import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

// EAI-CUSTOM: 子路由映射到子页面权限点(/api/permissions/me 的 pages),供 canPage 过滤
const navItems = [
  { href: "/bid-quote", label: "分析仪表盘", icon: LayoutDashboard, exact: true, pageId: "bqa:page:dashboard" },
  { href: "/bid-quote/query", label: "数据查询", icon: Search, pageId: "bqa:page:query" },
];

function BidQuoteLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显,加载完按 canPage(pageId) 过滤
  const visibleItems = isLoading ? navItems : navItems.filter((n) => canPage(n.pageId));

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-16 shrink-0 items-center border-b border-border bg-background px-6">
        <span className="mr-8 text-lg font-bold tracking-tight text-foreground">投标报价分析</span>
        <nav className="flex h-full items-center gap-6 text-sm font-medium text-muted-foreground">
          {visibleItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 py-5 transition-colors",
                  isActive ? "border-primary text-primary" : "border-transparent hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}

export default function BidQuoteLayout({ children }: { children: ReactNode }) {
  return (
    <ShellLayout>
      <BidQuoteLayoutContent>{children}</BidQuoteLayoutContent>
    </ShellLayout>
  );
}
```

### - [ ] Step 6: 占位 page / query/page

`frontend/src/app/bid-quote/page.tsx`:

```tsx
import { DashboardView } from "@/extensions/bid-quote/components/DashboardView";

export default function BidQuoteDashboardPage() {
  return <DashboardView />;
}
```

`frontend/src/app/bid-quote/query/page.tsx`:

```tsx
import { QueryView } from "@/extensions/bid-quote/components/QueryView";

export default function BidQuoteQueryPage() {
  return <QueryView />;
}
```

> DashboardView / QueryView 在 Task 6/7 创建。本步先建文件可让 typecheck 报「模块未找到」—— 预期,Task 6/7 补齐。

### - [ ] Step 7: typecheck(预期 DashboardView/QueryView 未定义报错,先确认骨架无 import 顺序错)

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && pnpm typecheck' 2>&1 | head -40`
Expected: 仅 DashboardView/QueryView 未定义错误(Task 6/7 消除),无 api/hooks/types/table/layout 错误。

### - [ ] Step 8: Commit

```bash
git add frontend/src/extensions/bid-quote frontend/src/app/bid-quote
git commit -m "feat(bid-quote): 前端骨架(api/hooks/types + 路由 + table + layout)"
```

---

## Task 6: 仪表盘(DashboardView + StatCard/ChartCard/TechTooltip + 3 图表 cyber 增强)

**Files:**
- Create: `frontend/src/extensions/bid-quote/components/StatCard.tsx`
- Create: `frontend/src/extensions/bid-quote/components/ChartCard.tsx`
- Create: `frontend/src/extensions/bid-quote/components/TechTooltip.tsx`
- Create: `frontend/src/extensions/bid-quote/components/DashboardView.tsx`

### - [ ] Step 1: StatCard.tsx(cyber 增强)

`frontend/src/extensions/bid-quote/components/StatCard.tsx`:

```tsx
"use client";

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type StatColor = "primary" | "chart2" | "chart3" | "destructive" | "chart5";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  color?: StatColor;
}

// cyber 增强:浅底 + 角标点 + font-cyber 数字 + text-shadow-glow
const cardClasses: Record<StatColor, string> = {
  primary: "border-primary/15 bg-primary/5",
  chart2: "border-[hsl(var(--chart-2)/0.18)] bg-[hsl(var(--chart-2)/0.06)]",
  chart3: "border-[hsl(var(--chart-3)/0.18)] bg-[hsl(var(--chart-3)/0.06)]",
  destructive: "border-destructive/15 bg-destructive/5",
  chart5: "border-[hsl(var(--chart-5)/0.18)] bg-[hsl(var(--chart-5)/0.06)]",
};
const dotClasses: Record<StatColor, string> = {
  primary: "bg-primary/30",
  chart2: "bg-[hsl(var(--chart-2))]",
  chart3: "bg-[hsl(var(--chart-3))]",
  destructive: "bg-destructive/40",
  chart5: "bg-[hsl(var(--chart-5))]",
};
const textClasses: Record<StatColor, string> = {
  primary: "text-primary",
  chart2: "text-[hsl(var(--chart-2))]",
  chart3: "text-[hsl(var(--chart-3))]",
  destructive: "text-destructive",
  chart5: "text-[hsl(var(--chart-5))]",
};

export function StatCard({ label, value, icon: Icon, hint, color = "primary" }: StatCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl p-4 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] transition-all hover:scale-[1.015]",
        cardClasses[color]
      )}
    >
      <span className={cn("absolute right-0 top-0 h-2 w-2 rounded-bl-md", dotClasses[color])} />
      <div className="flex items-center gap-2 text-muted-foreground/70">
        <Icon className="h-4 w-4" />
        <p className="text-xs uppercase tracking-wide">{label}</p>
      </div>
      <p className={cn("mt-2 font-cyber text-3xl font-extrabold tracking-tight text-shadow-glow", textClasses[color])}>
        {value}
      </p>
      {hint ? <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
```

### - [ ] Step 2: ChartCard.tsx(themed-card-sci 面)

`frontend/src/extensions/bid-quote/components/ChartCard.tsx`:

```tsx
"use client";

import type { ReactNode } from "react";

interface ChartCardProps {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
}

// themed-card-sci:cyber 浅色科技感卡片面
export function ChartCard({ title, meta, children, className }: ChartCardProps) {
  return (
    <div
      className={
        "themed-card-sci rounded-xl border border-border/60 bg-card/80 p-5 shadow-[0_10px_30px_-10px_rgba(15,23,42,0.08)] backdrop-blur-sm " +
        (className ?? "")
      }
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-cyber text-sm font-semibold tracking-wide text-muted-foreground">{title}</h3>
        {meta ? (
          <span className="rounded-full border border-primary/20 bg-primary/5 px-2.5 py-0.5 text-[11px] font-bold text-primary">
            {meta}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}
```

### - [ ] Step 3: TechTooltip.tsx(cyber 自定义 tooltip)

`frontend/src/extensions/bid-quote/components/TechTooltip.tsx`:

```tsx
"use client";

import type { TooltipProps } from "recharts";

// recharts 自定义 tooltip:cyber 浅色玻璃面
export function TechTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-primary/30 bg-card/95 px-3 py-2 font-cyber text-xs text-card-foreground shadow-lg backdrop-blur">
      {label !== undefined ? (
        <p className="mb-1 font-bold text-primary text-shadow-glow">{label}</p>
      ) : null}
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}:</span>
          <span className="font-bold">{p.value}</span>
        </p>
      ))}
    </div>
  );
}
```

### - [ ] Step 4: DashboardView.tsx(KPI + 3 图表)

`frontend/src/extensions/bid-quote/components/DashboardView.tsx`:

```tsx
"use client";

import { Activity, BarChart3, Crown, Gauge, RefreshCw, Scale, TrendingUp } from "lucide-react";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { useBidSummary, useComposition, useProjectShowdown, useWinRateBySegment } from "@/extensions/bid-quote/hooks";
import { clearBidQuoteCache } from "@/extensions/bid-quote/api";
import { ChartCard } from "@/extensions/bid-quote/components/ChartCard";
import { StatCard } from "@/extensions/bid-quote/components/StatCard";
import { TechTooltip } from "@/extensions/bid-quote/components/TechTooltip";

const GRID = "rgba(100,116,139,0.22)";
const AXIS = { fontSize: 11, fontFamily: "var(--font-mono, monospace)", fill: "hsl(var(--muted-foreground))" };

// Decimal/numeric 列经 JSON 序列化为 string;recharts 需 number → 统一转。
const toNum = (v: string | null): number => (v === null ? 0 : Number(v));
function wan(v: string | null): string {
  if (v === null) return "—";
  return `${(toNum(v) / 10000).toFixed(1)}万`;
}

export function DashboardView() {
  const [tick, setTick] = useState(0);
  const refresh = () => {
    clearBidQuoteCache();
    setTick((t) => t + 1);
  };

  const summaryQ = useBidSummary();
  const segQ = useWinRateBySegment();
  const compQ = useComposition();
  const showdownQ = useProjectShowdown();

  const s = summaryQ.data?.[0];
  // 友商中标率(后端无此字段,前端算)
  const compRate =
    s && s.competitor_bid > 0
      ? Math.round((100 * s.competitor_won) / s.competitor_bid / 0.1) / 10
      : null;

  return (
    <div key={tick} className="cyber-scope space-y-5 p-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-sm border border-primary/30 bg-primary/10 p-1 text-primary">
            <Scale className="h-5 w-5" />
          </div>
          <h1 className="text-2xl font-bold text-foreground text-shadow-glow">投标报价分析</h1>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={summaryQ.isFetching}>
          <RefreshCw className={summaryQ.isFetching ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          刷新
        </Button>
      </div>

      {/* KPI 行 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="我方中标率" value={s ? `${s.ours_win_rate_pct ?? "—"}%` : "—"} icon={Gauge} color="primary" />
        <StatCard label="投标总数" value={s?.bid_count ?? "—"} icon={BarChart3} color="chart2" />
        <StatCard label="我方投 / 中" value={s ? `${s.ours_bid} / ${s.ours_won}` : "—"} icon={Activity} color="chart3" />
        <StatCard label="友商中标率" value={compRate !== null ? `${compRate}%` : "—"} icon={TrendingUp} color="destructive" />
        <StatCard label="平均中标价" value={s ? wan(s.avg_winning_price) : "—"} icon={Crown} color="chart5" />
      </div>

      {/* 图表 3 张 */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {/* 图1:按金额段我方中标率 */}
        <ChartCard title="按金额段 · 我方中标率" meta="≥2000万 段短板" className="xl:col-span-1">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={(segQ.data ?? []).map((r) => ({
                amount_segment: r.amount_segment,
                ours_win_rate_pct: toNum(r.ours_win_rate_pct),
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <defs>
                <linearGradient id="segGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0.2} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="amount_segment" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="%" width={40} />
              <Tooltip content={<TechTooltip />} cursor={{ fill: "hsl(var(--muted)/0.4)" }} />
              <Bar
                dataKey="ours_win_rate_pct"
                name="我方中标率"
                fill="url(#segGrad)"
                radius={[4, 4, 0, 0]}
                isAnimationActive
                animationDuration={900}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图2:货物构成对比 自产% */}
        <ChartCard title="货物构成对比 · 自产率(我方 vs 友商)" meta="失标根因">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={(compQ.data ?? []).map((r) => ({
                goods_name: r.goods_name,
                ours_self_pct: toNum(r.ours_self_pct),
                competitor_self_pct: toNum(r.competitor_self_pct),
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="goods_name" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="%" width={40} />
              <Tooltip content={<TechTooltip />} cursor={{ fill: "hsl(var(--muted)/0.4)" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="ours_self_pct" name="我方自产%" fill="hsl(var(--chart-1))" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
              <Bar dataKey="competitor_self_pct" name="友商自产%" fill="hsl(var(--chart-3))" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 图3:项目报价对比 我方 vs 友商(胜负 Cell 色) */}
        <ChartCard title="项目报价对比 · 我方 vs 友商(万)" meta="报价区间建议" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={(showdownQ.data ?? []).map((r) => ({
                project_name: r.project_name,
                我方: r.our_price ? Number(r.our_price) / 10000 : 0,
                友商: r.competitor_price ? Number(r.competitor_price) / 10000 : 0,
                we_won: r.we_won,
              }))}
              margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
            >
              <defs>
                <linearGradient id="ourGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--success))" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="hsl(var(--success))" stopOpacity={0.25} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID} vertical={false} />
              <XAxis dataKey="project_name" tick={{ ...AXIS, fontSize: 10 }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} angle={-12} textAnchor="end" height={50} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} />
              <Tooltip content={<TechTooltip />} cursor={{ fill: "hsl(var(--muted)/0.4)" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="我方" fill="url(#ourGrad)" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900}>
                {(showdownQ.data ?? []).map((r, i) => (
                  <Cell key={i} fill={r.we_won ? "url(#ourGrad)" : "hsl(var(--destructive)/0.55)"} />
                ))}
              </Bar>
              <Bar dataKey="友商" fill="hsl(var(--chart-3))" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={900} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
```

> 金额/比率类 Decimal 列经 JSON 序为 string,recharts 需 number → 三个图表的 `data` 均经 `toNum` 预转。showdown 的胜负用 Cell 色(胜=渐变绿/负=destructive 半透)覆盖 Bar 默认 fill。

### - [ ] Step 5: typecheck

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && pnpm typecheck' 2>&1 | head -40`
Expected: DashboardView 相关错误消失;仅 QueryView 未定义(若残留)。修掉 recharts 类型告警(如 `dataKeyFormatter` 非标准属性 → 改用 Tooltip 已显示,可删该属性)。若 `num` unused 报错则删除。

### - [ ] Step 6: 重启 frontend + 截图验证仪表盘

```bash
docker compose -p eai-docker restart frontend
```
浏览器登录 → 应用中心 → 投标报价分析 → 仪表盘应显 5 KPI + 3 图表(柱状带渐变 + cyber 字体)。若 HMR 未生效,restart frontend。

### - [ ] Step 7: Commit

```bash
git add frontend/src/extensions/bid-quote/components/StatCard.tsx frontend/src/extensions/bid-quote/components/ChartCard.tsx frontend/src/extensions/bid-quote/components/TechTooltip.tsx frontend/src/extensions/bid-quote/components/DashboardView.tsx
git commit -m "feat(bid-quote): 仪表盘(5 KPI + 3 图表,项目管理浅色 + cyber 增强)"
```

---

## Task 7: 查询页(QueryView 3 视图 + DrillDownModal)

**Files:**
- Create: `frontend/src/extensions/bid-quote/components/DrillDownModal.tsx`
- Create: `frontend/src/extensions/bid-quote/components/QueryView.tsx`

### - [ ] Step 1: DrillDownModal.tsx

`frontend/src/extensions/bid-quote/components/DrillDownModal.tsx`:

```tsx
"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

import { useDrillDown } from "@/extensions/bid-quote/hooks";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/bid-quote/components/ui/table";

interface DrillDownModalProps {
  title: string;
  /** 已拼好的参数化只读 SQL(白名单维度,值来自行数据)。null 时关闭。 */
  sql: string | null;
  onClose: () => void;
}

// 通用下钻 modal:标题 + sql → 明细 table。下钻 SQL 走后端 assert_readonly_select 守卫。
export function DrillDownModal({ title, sql, onClose }: DrillDownModalProps) {
  const { data, isLoading, error } = useDrillDown(sql);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (sql) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sql, onClose]);

  if (!sql) return null;
  const rows = data?.rows ?? [];
  const cols = rows.length ? Object.keys(rows[0]) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="font-cyber text-sm font-bold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
          ) : error ? (
            <p className="py-8 text-center text-sm text-destructive">加载失败:{String(error)}</p>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">无明细数据</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {cols.map((c) => (
                    <TableHead key={c}>{c}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i} className="cursor-default">
                    {cols.map((c) => (
                      <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
        <div className="border-t border-border px-5 py-2 text-[11px] text-muted-foreground/70">
          共 {data?.row_count ?? 0} 条 · {sql}
        </div>
      </div>
    </div>
  );
}
```

### - [ ] Step 2: QueryView.tsx(3 视图 + 行下钻)

`frontend/src/extensions/bid-quote/components/QueryView.tsx`:

```tsx
"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/bid-quote/components/ui/table";
import { DrillDownModal } from "@/extensions/bid-quote/components/DrillDownModal";
import { useBidList, useComposition, useWinRateBySegment } from "@/extensions/bid-quote/hooks";
import type { BidItemRow, CompositionRow, SegmentRow } from "@/extensions/bid-quote/types";

type TabKey = "bidlist" | "composition" | "segment";

const TABS: { key: TabKey; label: string }[] = [
  { key: "bidlist", label: "投标明细" },
  { key: "composition", label: "货物构成对比" },
  { key: "segment", label: "按金额段中标率" },
];

// 金额段定义(与 seed win_rate_by_segment 一致)→ 下钻 SQL 上下界
const SEG_BOUNDS: Record<string, [number, number]> = {
  "1_<100万": [0, 1_000_000],
  "2_100-500万": [1_000_000, 5_000_000],
  "3_500-2000万": [5_000_000, 20_000_000],
  "4_≥2000万": [20_000_000, Number.MAX_SAFE_INTEGER],
};

export function QueryView() {
  const [tab, setTab] = useState<TabKey>("bidlist");
  const [drill, setDrill] = useState<{ title: string; sql: string } | null>(null);

  const bidQ = useBidList();
  const compQ = useComposition();
  const segQ = useWinRateBySegment();

  const bidRows = bidQ.data ?? [];
  const compRows = compQ.data ?? [];
  const segRows = segQ.data ?? [];
  // 明细列动态(取首行列名);罐装视图列固定
  const bidCols = bidRows.length ? Object.keys(bidRows[0]) : [];

  const onRowDrill = (key: TabKey, row: BidItemRow | CompositionRow | SegmentRow) => {
    // 白名单维度:仅 project_name / goods_name / amount_segment;值来自行数据(数字段强制数值)
    if (key === "bidlist") {
      const v = String((row as BidItemRow).project_name ?? "").replace(/'/g, "''");
      setDrill({
        title: `项目明细 · ${v}`,
        sql: `SELECT * FROM mock_bid_item WHERE project_name='${v}' ORDER BY total_amount DESC`,
      });
    } else if (key === "composition") {
      const v = String((row as CompositionRow).goods_name ?? "").replace(/'/g, "''");
      setDrill({
        title: `货物明细 · ${v}`,
        sql: `SELECT * FROM mock_bid_item WHERE goods_name='${v}' ORDER BY total_amount DESC`,
      });
    } else {
      const seg = (row as SegmentRow).amount_segment;
      const [lo, hi] = SEG_BOUNDS[seg] ?? [0, Number.MAX_SAFE_INTEGER];
      setDrill({
        title: `金额段明细 · ${seg}`,
        sql: `SELECT * FROM mock_bid WHERE winning_price >= ${lo} AND winning_price < ${hi} ORDER BY winning_price DESC`,
      });
    }
  };

  const loading = useMemo(
    () => (tab === "bidlist" ? bidQ.isLoading : tab === "composition" ? compQ.isLoading : segQ.isLoading),
    [tab, bidQ.isLoading, compQ.isLoading, segQ.isLoading]
  );

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-3">
        <Search className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">数据查询</h1>
      </div>

      {/* 视图 tab(pill) */}
      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors " +
              (tab === t.key
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:text-foreground")
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 当前视图表(点行下钻) */}
      <div className="rounded-xl border border-border bg-card p-4">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>
        ) : tab === "bidlist" ? (
          <Table>
            <TableHeader>
              <TableRow>
                {bidCols.map((c) => (
                  <TableHead key={c}>{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {bidRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("bidlist", r)}>
                  {bidCols.map((c) => (
                    <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : tab === "composition" ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>货物</TableHead>
                <TableHead>我方自产%</TableHead>
                <TableHead>友商自产%</TableHead>
                <TableHead>我方均价</TableHead>
                <TableHead>友商均价</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {compRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("composition", r)}>
                  <TableCell>{r.goods_name}</TableCell>
                  <TableCell>{r.ours_self_pct ?? "—"}</TableCell>
                  <TableCell>{r.competitor_self_pct ?? "—"}</TableCell>
                  <TableCell>{r.ours_avg_unit_price ?? "—"}</TableCell>
                  <TableCell>{r.competitor_avg_unit_price ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>金额段</TableHead>
                <TableHead>投标数</TableHead>
                <TableHead>中标数</TableHead>
                <TableHead>中标率</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {segRows.map((r, i) => (
                <TableRow key={i} onClick={() => onRowDrill("segment", r)}>
                  <TableCell>{r.amount_segment.replace(/^\d+_/, "")}</TableCell>
                  <TableCell>{r.ours_bid}</TableCell>
                  <TableCell>{r.ours_won}</TableCell>
                  <TableCell>{r.ours_win_rate_pct ?? "—"}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <DrillDownModal title={drill?.title ?? ""} sql={drill?.sql ?? null} onClose={() => setDrill(null)} />
    </div>
  );
}
```

### - [ ] Step 3: typecheck + lint

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && pnpm typecheck && pnpm lint' 2>&1 | tail -30`
Expected: PASS(0 error)。修掉任何 unused import / 类型告警。

### - [ ] Step 4: 命名空间自查

Run: `grep -rnE "cpa:|csp:|\"cpa\"|\"csp\"" frontend/src/extensions/bid-quote frontend/src/app/bid-quote`
Expected: 无输出(无残留 cpa/csp 命名空间)。

### - [ ] Step 5: 重启 frontend + 截图验证查询页

```bash
docker compose -p eai-docker restart frontend
```
浏览器 → 投标报价分析 → 数据查询 → 3 tab 切换 → 点行出 modal 明细。

### - [ ] Step 6: Commit

```bash
git add frontend/src/extensions/bid-quote/components/DrillDownModal.tsx frontend/src/extensions/bid-quote/components/QueryView.tsx
git commit -m "feat(bid-quote): 查询页(3 固定视图 + 行下钻 modal)"
```

---

## Task 8: 联调 + 全量验证

### - [ ] Step 1: 后端全测

Run: `docker compose -p eai-docker exec gateway sh -c 'cd /app/backend && PYTHONPATH=. .venv/bin/pytest tests/test_data_source_routers.py tests/test_license_modules_sync.py -v'`
Expected: 全 PASS。

### - [ ] Step 2: 前端 check

Run: `docker compose -p eai-docker exec frontend sh -c 'cd /app/frontend && pnpm check'`
Expected: lint + typecheck 全过。

### - [ ] Step 3: 端到端手动验证(E2E)

用 `admin@eai-flow.com / Admin@2026` 登录 `localhost:2026`:
1. 应用中心 → 「市场营销」域 → 见「投标报价分析」磁贴(若无:检查 roles_custom.yaml user 角色是否含 `nav:bid-quote`,以及 admin superadmin `nav:["*"]` 是否生效)。
2. 点磁贴 → 仪表盘显:我方中标率 33.3% / 投标总数 12 / 我方投中 6/2 / 友商中标率 66.7% / 平均中标价 1727.5 万 + 3 张柱状图(渐变 + cyber)。
3. 「数据查询」tab → 3 视图切换正常 → 点任一行 → modal 弹出明细(mock_bid_item 或 mock_bid 子集)。
4. 下钻 modal 的 SQL 显示在底部,确认均为只读 SELECT。

### - [ ] Step 4: designqc 截图(可选,留档)

```bash
openwolf designqc --routes /bid-quote /bid-quote/query
```
读 `.wolf/designqc-captures/` 截图核对科技感与浅色风格。

### - [ ] Step 5: 更新 anatomy/memory + 收尾 commit

按 OpenWolf 协议:新建文件入 `.wolf/anatomy.md`;`.wolf/memory.md` 追加一行;若有踩坑入 `.wolf/buglog.json` / `.wolf/cerebrum.md`。

```bash
git add .wolf/anatomy.md .wolf/memory.md
git commit -m "docs(wolf): 记录 bid-quote 前端模块 anatomy"
```

---

## Self-Review(写完后自查)

**1. Spec 覆盖:**
- §2 后端增量(2 端点)→ Task 1 ✓;第 4 dataset → Task 2 ✓
- §3 数据流(resolve source/dataset id 缓存 → query 端点)→ Task 5 api/hooks ✓
- §4.1/4.2 端点签名 + 第 4 dataset SQL → Task 1/2 ✓
- §5 模块结构(api/hooks/types/components/路由)→ Task 5/6/7 ✓(命名空间 `bqa` 全程一致)
- §6 仪表盘(页头 + 5 KPI + 3 图表 cyber)→ Task 6 ✓(色板 KPI 表对应)
- §7 查询页(3 视图 + modal 下钻,白名单维度)→ Task 7 ✓
- §8 应用中心入口 + License 4 点 + permissions/roles_custom → Task 3/4 ✓

**2. 占位符扫描:** 无 TBD/TODO;"详见 Task N"只在占位 stub(Task 5 Step 6)显式标注预期错误,非占位。dataset label 与 seed 逐字核对。

**3. 类型一致性:** `QueryResult` / `SqlQueryRequest`(后端 schemas)↔ `QueryResult`(前端 types)字段一致(rows/row_count/label);dataset label 字符串在 seed / hooks / api 三处一致;page id `bqa:page:dashboard|query` 在 permissions.yaml / roles_custom.yaml / layout.tsx / useApps 三处一致;nav id `nav:bid-quote` 在 permissions.yaml / roles_custom.yaml / deriveNavId 一致。

**4. 风险点(执行时留意):**
- recharts `dataKeyFormatter` 非标准 → Task 6 Step 5 已提示删除若 lint 报。
- 既有库 marketing 域 / 磁贴需手动补(Task 4 Step 6),因 seed `ON CONFLICT DO NOTHING`。
- 端到端需 admin 已授权 `nav:bid-quote`(superadmin `["*"]` 自动有)。
