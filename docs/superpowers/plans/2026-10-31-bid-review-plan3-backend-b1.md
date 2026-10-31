# bid-review Plan 3:后端 B1 批 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 spec §5 B1——TaskOut 扩展(biz_no/项目/标段/编号/created_by_name/updated_at/done_at/main_unhandled)+ 项目标段抽取回填(裁定 12),为 Plan 4(s1 九列全量对齐)供数。

**Architecture:** 纯 `app/extensions/bid_review/` 边界内增量。ReviewTask 加六列(ORM + database.py migrate_db 轻量补丁,PG `ADD COLUMN IF NOT EXISTS` 惯例);biz_no 创建时生成(TBR-{YYYYMMDD}-{seq},当日序号 max+1,存量迁移回填);worker 抽取完成后同处回填 project/lot/tender_no;list_tasks 聚合循环扩 main_unhandled + created_by_name 防御性 join(测试库无 users 表须容错)。created_by_name 不落列——读时 join(COALESCE(full_name, username))。

**Tech Stack:** SQLAlchemy async + PostgreSQL(生产)/sqlite+aiosqlite(测试)、Pydantic v2、pytest-asyncio。

**系列位置:** Plan 3(本批,后端)→ Plan 4(s1 前端九列/标题 biz_no/审查用时真值/搜索升级)。

**关键侦察结论(执行者必读):**
- 测试库只建 bid_review 五张表(见 test_bid_review_routers.py 夹具注释),**无 users 表**——created_by_name 查询必须容错(catch OperationalError 返回空映射)。
- `migrate_db()` 仅 PG 执行(测试不跑);测试列经 create_all 从 ORM 来,加列零夹具改动。
- worker `_write_baselines` 内部已 commit;回填赋值后跟一次 `await db.commit()` 即可。
- `tender.project_identity.name/code` 已在 extract.py 基础字段集;仅 `lot_section` 是新增。
- TaskOut 聚合字段口径:**仅 list_tasks 填充,单任务端点 None=未统计**(micro-A 既有纪律,禁伪零)。
- mcp.py 不投影 TaskOut 字段,本批零改动。

---

### Task 1: ORM 六列 + PG 迁移

**Files:**
- Modify: `backend/app/extensions/bid_review/models.py:25-36`(ReviewTask)
- Modify: `backend/app/extensions/database.py`(migrate_db 尾部加段)
- Test: `backend/tests/test_bid_review_models.py`(追加)

- [x] **Step 1: 写失败测试**(models 列存在性,sqlite create_all 直验)

在 `test_bid_review_models.py` 追加:

```python
def _task_columns():
    return {c.name for c in models.ReviewTask.__table__.columns}


def test_review_task_b1_columns_exist():
    """B1(2026-10-31):六新列在 ORM 与 create_all 产物中存在。"""
    cols = _task_columns()
    assert {"biz_no", "project_name", "lot_name", "tender_no", "updated_at", "done_at"} <= cols


def test_review_task_updated_at_onupdate():
    """updated_at 行级 onupdate 挂钩(读时刷新即变)。"""
    col = models.ReviewTask.__table__.columns["updated_at"]
    assert col.onupdate is not None
```

(若文件已有 import `models` 则复用;无则 `from app.extensions.bid_review import models`。)

- [x] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_models.py -k b1_columns -x -q`
Expected: FAIL(KeyError 或集合断言失败)

- [x] **Step 3: 最小实现**

models.py ReviewTask 追加(placed after `created_at`):

```python
    # ── B1 扩展(EAI-CUSTOM 2026-10-31,spec §5 B1/裁定12)──────────────
    # biz_no 业务号 TBR-{YYYYMMDD}-{seq:04d},创建时 crud 生成;存量迁移回填;
    # 唯一性由 migrate_db 的唯一索引收口(PG;sqlite 测试不跑迁移,单测断言生成序而非约束)。
    biz_no: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # 项目/标段/招标编号:抽取回填(worker.advance_task 基线落库后,裁定12=从投标文件抽,
    # 非向导手填);创建时 null,伪零纪律显 —。
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lot_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tender_no: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # crud.set_status(done) 落
```

database.py `migrate_db()` 内、既有段落之后追加(函数末尾前):

```python
        # === bid_review B1 扩展(EAI-CUSTOM 2026-10-31,spec §5 B1/裁定12)===
        await conn.execute(text("ALTER TABLE bid_review_tasks ADD COLUMN IF NOT EXISTS biz_no VARCHAR(20)"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_bid_review_tasks_biz_no ON bid_review_tasks(biz_no)"))
        await conn.execute(text("ALTER TABLE bid_review_tasks ADD COLUMN IF NOT EXISTS project_name VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE bid_review_tasks ADD COLUMN IF NOT EXISTS lot_name VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE bid_review_tasks ADD COLUMN IF NOT EXISTS tender_no VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE bid_review_tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"))
        await conn.execute(text("ALTER TABLE bid_review_tasks ADD COLUMN IF NOT EXISTS done_at TIMESTAMPTZ"))
        # biz_no 存量回填:按创建日分区,日内按 created_at,id 决胜,序号 0001 起。
        await conn.execute(text("""
            UPDATE bid_review_tasks t SET biz_no = sub.b FROM (
                SELECT id,
                       'TBR-' || TO_CHAR(created_at, 'YYYYMMDD') || '-' ||
                       LPAD((ROW_NUMBER() OVER (
                           PARTITION BY TO_CHAR(created_at, 'YYYYMMDD')
                           ORDER BY created_at, id
                       ))::text, 4, '0') AS b
                FROM bid_review_tasks WHERE biz_no IS NULL
            ) sub WHERE t.id = sub.id
        """))
```

(ORM `unique=True` 不加——迁移索引收口唯一性,避免新装库 create_all 约束+迁移索引双份。)

- [x] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_models.py -x -q`
Expected: PASS(全文件)

- [x] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/models.py backend/app/extensions/database.py backend/tests/test_bid_review_models.py
git commit -m "feat(bid-review): B1 ReviewTask 六新列(biz_no/项目/标段/编号/updated_at/done_at)+PG迁移存量回填"
```

---

### Task 2: biz_no 生成(crud)

**Files:**
- Modify: `backend/app/extensions/bid_review/crud.py:20-26`(create_task + 新 helper)
- Test: `backend/tests/test_bid_review_crud.py`(追加)

- [x] **Step 1: 写失败测试**

追加到 `test_bid_review_crud.py`(复用既有 db 夹具;若文件夹具名不同,按现状适配):

```python
@pytest.mark.asyncio
async def test_create_task_biz_no_format_and_sequence(db):
    """B1:biz_no=TBR-{当日}-{seq:04d},同日递增,跨日独立从 0001。"""
    t1 = await crud.create_task(db, owner_id="u1")
    t2 = await crud.create_task(db, owner_id="u1")
    today = datetime.now(UTC).strftime("%Y%m%d")
    prefix = f"TBR-{today}-"
    assert t1.biz_no == f"{prefix}0001"
    assert t2.biz_no == f"{prefix}0002"


def test_next_biz_no_parses_seq():
    """max(biz_no) 尾段解析:非当日前缀返回 None→0001。"""
    assert crud._seq_of("TBR-20261031-0007") == 7
    assert crud._seq_of(None) is None
    assert crud._seq_of("junk") is None
```

(若测试文件无 `from datetime import UTC, datetime` 则补。)

- [x] **Step 2: 跑失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_crud.py -k biz_no -x -q`
Expected: FAIL(AttributeError: no `_seq_of` / biz_no None)

- [x] **Step 3: 实现**

crud.py:

```python
def _seq_of(biz_no: str | None) -> int | None:
    """'TBR-YYYYMMDD-NNNN' 尾段序号;None/畸形返回 None(从 0001 重开)。"""
    if not biz_no:
        return None
    parts = biz_no.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


async def _next_biz_no(session: AsyncSession) -> str:
    """TBR-{YYYYMMDD}-{seq:04d}:当日 max 尾段+1,零填充;唯一性由迁移索引兜底。"""
    prefix = f"TBR-{datetime.now(UTC).strftime('%Y%m%d')}-"
    row = await session.execute(select(func.max(ReviewTask.biz_no)).where(ReviewTask.biz_no.like(prefix + "%")))
    seq = _seq_of(row.scalar_one_or_none())
    return f"{prefix}{(seq or 0) + 1:04d}"


async def create_task(session: AsyncSession, owner_id: str, mode: str = "quick") -> ReviewTask:
    task = ReviewTask(owner_id=owner_id, mode=mode, biz_no=await _next_biz_no(session))
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task
```

import 补:`from datetime import UTC, datetime` 与 `from sqlalchemy import func, select`。

- [x] **Step 4: 跑通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_crud.py -x -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/crud.py backend/tests/test_bid_review_crud.py
git commit -m "feat(bid-review): B1 biz_no 生成——TBR-{YYYYMMDD}-{seq:04d} 当日序号"
```

---

### Task 3: done_at 落点(crud.set_status)

**Files:**
- Modify: `backend/app/extensions/bid_review/crud.py:38-57`(set_status)
- Test: `backend/tests/test_bid_review_crud.py`(追加)

- [x] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_set_status_done_at(db):
    """B1:done 落 done_at 一次(幂等,非 done 不动)。"""
    t = await crud.create_task(db, owner_id="u1")
    t = await crud.set_status(db, t, "running", progress={"stage": "x", "pct": 1})
    assert t.done_at is None
    t = await crud.set_status(db, t, "done")
    done1 = t.done_at
    assert done1 is not None
    t = await crud.set_status(db, t, "done")  # 重放幂等
    assert t.done_at == done1
```

- [x] **Step 2: 跑失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_crud.py -k done_at -x -q`
Expected: FAIL(done_at None)

- [x] **Step 3: 实现**

set_status 内、`task.status = status` 后:

```python
    if status == "done" and task.done_at is None:
        task.done_at = datetime.now(UTC)
```

- [x] **Step 4: 跑通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_crud.py -x -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/crud.py backend/tests/test_bid_review_crud.py
git commit -m "feat(bid-review): B1 done_at——set_status(done) 一次性落点(幂等)"
```

---

### Task 4: 抽取回填(裁定 12)

**Files:**
- Modify: `backend/app/extensions/bid_review/engine/extract.py:34-35`(基础字段集加 lot_section)
- Modify: `backend/app/extensions/bid_review/engine/labels.py:14`(label)
- Modify: `backend/app/extensions/bid_review/worker.py`(advance_task 基线落库后回填)
- Test: `backend/tests/test_bid_review_extract.py`(追加)、`backend/tests/test_bid_review_worker.py`(追加)

- [x] **Step 1: 写失败测试**

test_bid_review_extract.py 追加:

```python
def test_lot_section_in_field_paths():
    """裁定12:标段入基础字段字典(提取 prompt 自动可见)。"""
    assert "tender.project_identity.lot_section" in extract.collect_field_paths()
    assert "tender.project_identity.lot_section" in labels.FIELD_LABELS
```

(按文件既有 import 名适配:`extract`/`labels`。)

test_bid_review_worker.py 追加(按既有 advance_task 驱动夹具形态;核心断言:走完 advance_task 后 task.project_name/lot_name/tender_no 来自 fields):

```python
@pytest.mark.asyncio
async def test_advance_task_backfills_project_identity(db, monkeypatch):
    """裁定12:基线落库后回填 task.project_name/lot_name/tender_no(仅收标量)。"""
    # 复用本文件既有 fake extract_fn/advance 驱动方式(见既有用例);
    # fake fields 注入:
    #   tender.project_identity.name → "XX数据中心一期采购项目"
    #   tender.project_identity.lot_section → "标段一(机电设备)"
    #   tender.project_identity.code → "TND-2026-114"
    #   tender.max_price → {"value": 100}  (非标量→不回填)
    # 断言 task.project_name == "XX数据中心一期采购项目" 等,且 max_price 不落列。
```

(执行时按该文件现有 advance_task 测试的夹具/驱动逐字改写;计划不预写未知夹具名——以现有用例为模板,断言块如上。)

- [x] **Step 2: 跑失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py -k lot_section -x -q`
Expected: FAIL(KeyError / not in)

- [x] **Step 3: 实现**

extract.py 基础字段集(紧邻 tender.project_identity.code 行)加:

```python
        "tender.project_identity.lot_section",
```

labels.py 紧邻项目编号行加:

```python
    "tender.project_identity.lot_section": "标段",
```

worker.py advance_task,`await _write_baselines(...)` 行后加:

```python
    # B1 抽取回填(裁定12:项目/标段从投标文件抽,非向导手填):基线落库后同处
    # 写 task 三列;仅收标量(str/int/float),dict/list 等结构化值不回填(伪零纪律:
    # 抽不到保持 null,前端显 —)。
    def _scalar(v: object) -> str | None:
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
        return None

    task.project_name = _scalar(fields.get("tender.project_identity.name"))
    task.lot_name = _scalar(fields.get("tender.project_identity.lot_section"))
    task.tender_no = _scalar(fields.get("tender.project_identity.code"))
    await db.commit()
    await db.refresh(task)
```

(局部函数体最短;若该文件已有同类 helper 则复用。)

- [x] **Step 4: 跑通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_extract.py tests/test_bid_review_worker.py -x -q`
Expected: PASS(注意既有 worker 用例若 fake fields 无这些键,回填 None 不破坏断言)

- [x] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/engine/extract.py backend/app/extensions/bid_review/engine/labels.py backend/app/extensions/bid_review/worker.py backend/tests/test_bid_review_extract.py backend/tests/test_bid_review_worker.py
git commit -m "feat(bid-review): B1 抽取回填——lot_section 新字段+项目/标段/编号落 task 列(裁定12)"
```

---

### Task 5: TaskOut 扩展 + list 聚合(main_unhandled + created_by_name)

**Files:**
- Modify: `backend/app/extensions/bid_review/schemas.py:21-38`(TaskOut)
- Modify: `backend/app/extensions/bid_review/crud.py`(creator_names helper)
- Modify: `backend/app/extensions/bid_review/routers.py:130-146`(list_tasks 聚合)
- Test: `backend/tests/test_bid_review_routers.py`(追加)

- [x] **Step 1: 写失败测试**

test_bid_review_routers.py 追加:

```python
@pytest.mark.asyncio
async def test_list_tasks_b1_fields(db, client):
    """B1:list_tasks 带 biz_no/project_name/lot_name/tender_no/updated_at/done_at/
    main_unhandled(major 且未误报)/created_by_name(无 users 表→None)。"""
    t = await crud.create_task(db, owner_id="u1")
    t.project_name = "某项目"
    t.lot_name = "标段一"
    t.tender_no = "TND-1"
    t.biz_no = "TBR-20261031-0001"
    await db.commit()
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-001", layer="L1",
                         severity="major", verdict="violation", message="m", evidence=[], dedup_key="d1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-002", layer="L1",
                         severity="major", verdict="false_positive", message="m", evidence=[], dedup_key="d2")
    r = await client.get("/tasks")
    item = r.json()["items"][0]
    assert item["biz_no"] == "TBR-20261031-0001"
    assert item["project_name"] == "某项目"
    assert item["lot_name"] == "标段一"
    assert item["tender_no"] == "TND-1"
    assert item["main_unhandled"] == 1
    assert item["created_by_name"] is None  # 测试库无 users 表→防御空映射
    assert item["updated_at"] is not None
```

(add_issue 签名按 crud 现状适配——执行时以 `crud.add_issue` 真实参数为准,计划里为示意。)

created_by_name 正值路径(独立小测试,建 users 表):

```python
@pytest.mark.asyncio
async def test_creator_names_with_users_table(db):
    """B1:users 表存在时 owner_id(uuid 串)→COALESCE(full_name, username)。"""
    from sqlalchemy import text as _text
    from app.extensions.models import User
    import uuid as _uuid
    async with db.get_bind().begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    uid = _uuid.uuid4()
    db.add(User(id=uid, username="zhang.san", email="z@x.com", password_hash="x", full_name="张工"))
    await db.commit()
    names = await crud.creator_names(db, [str(uid)])
    assert names == {str(uid): "张工"}
```

(User 建表在 sqlite 含 REFERENCES departments——sqlite 建表期不校验,可直建。)

- [x] **Step 2: 跑失败**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_routers.py -k b1_fields -x -q`
Expected: FAIL(TaskOut 无 main_unhandled / created_by_name 键)

- [x] **Step 3: 实现**

schemas.py TaskOut 追加:

```python
    # ── B1 扩展(EAI-CUSTOM 2026-10-31,spec §5 B1/裁定12)──────────────
    biz_no: str | None = None
    project_name: str | None = None
    lot_name: str | None = None
    tender_no: str | None = None
    updated_at: datetime | None = None
    done_at: datetime | None = None
    main_unhandled: int | None = None  # 仅 list_tasks 聚合填充(major 且未误报,与 fatal_unhandled 同纪律)
    created_by_name: str | None = None  # 仅 list_tasks 填充(users join;无行/表缺失→None)
```

crud.py 追加:

```python
async def creator_names(session: AsyncSession, owner_ids: list[str]) -> dict[str, str]:
    """owner_id → 显示名(COALESCE(full_name, username));users 表缺失(单测子集库)
    或无行时安全返回 {}。单查询 IN,非逐任务 N+1。"""
    if not owner_ids:
        return {}
    try:
        from app.extensions.models import User

        rows = await session.execute(
            select(func.cast(User.id, String).label("oid"), func.coalesce(User.full_name, User.username))
            .where(func.cast(User.id, String).in_(owner_ids))
        )
        return {oid: name for oid, name in rows.all() if name}
    except Exception:
        return {}
```

(import `String` from sqlalchemy;粗 except 收窄为 OperationalError/NoReferencedTableError 更佳——执行时收窄到 `sqlalchemy.exc.SQLAlchemyError`。)

routers.py list_tasks 循环内补一行 + 循环外一次 creator_names:

```python
    tasks = await crud.list_tasks(db, owner_id=owner_id)
    names = await crud.creator_names(db, [t.owner_id for t in tasks])
    items = []
    for t in tasks:
        out = TaskOut.model_validate(t)
        issues = await crud.list_issues(db, task_id=t.id, owner_id=owner_id)
        out.fatal_unhandled = sum(1 for i in issues if i.severity == "fatal" and i.verdict != "false_positive")
        out.need_human_count = sum(1 for i in issues if bool(i.need_human))
        out.main_unhandled = sum(1 for i in issues if i.severity == "major" and i.verdict != "false_positive")
        out.created_by_name = names.get(t.owner_id)
        items.append(out)
```

- [x] **Step 4: 跑通过**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_routers.py tests/test_bid_review_crud.py -x -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/extensions/bid_review/schemas.py backend/app/extensions/bid_review/crud.py backend/app/extensions/bid_review/routers.py backend/tests/test_bid_review_routers.py
git commit -m "feat(bid-review): B1 TaskOut 扩展+list 聚合 main_unhandled/created_by_name"
```

---

### Task 6: 全量验证 + 重启 + 记账

- [x] **Step 1: bid_review 全量 + ruff**

```bash
cd backend && PYTHONPATH=. uv run pytest tests/test_bid_review_crud.py tests/test_bid_review_models.py tests/test_bid_review_routers.py tests/test_bid_review_worker.py tests/test_bid_review_extract.py tests/test_bid_review_mcp.py tests/test_bid_review_feedback.py -q
uv run ruff check app/extensions/bid_review/ app/extensions/database.py
uv run ruff format --check app/extensions/bid_review/
```

Expected: 全绿。

- [ ] **Step 2: gateway 重启**

```bash
docker compose -p eai-docker restart gateway
```

(migrate_db 在 PG 实跑:重启后查 `docker exec eai-docker-postgres-ext-1 psql -U agentflow -d agentflow -c "\d bid_review_tasks"` 确认六列+唯一索引+存量 biz_no 非空。)

- [x] **Step 3: OpenWolf 记账 + 提交计划文档**

计划文档先随 Task 1 commit 一并 `git add -f` 入库。

---

## Self-Review 记录

- 契约一致性:TaskOut 新字段名(models ↔ schemas ↔ routers)逐一核对一致;`_seq_of`/`creator_names` 在 Task 2/5 定义后才被引用。
- 占位符:Task 4 Step 1 的 worker 测试断言块与 Task 5 add_issue 签名标注「按现状适配」——两者均为既有文件既有夹具,执行时以真实夹具为准,不预写未知名(写作纪律:不确定的夹具名宁标适配点不虚构)。
- 伪零纪律:所有聚合字段 None=未统计;回填仅收标量;lot_section 抽不到保持 null。
