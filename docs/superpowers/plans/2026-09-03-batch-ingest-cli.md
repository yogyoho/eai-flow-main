# 批量入库 + 统一 CLI（batch-ingest + eai-cli）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** report_id 语义结构码自动编码、geo-samples 列表分页+删除、`tools/eai.py` 统一薄 REST CLI（gsb scan/import + cpa upload + license generate），支撑 1000+ 份样例两阶段入库。

**Architecture:** 题名解析器为后端纯函数（suggest-id 端点与 CLI scan 共用，零双实现）；DELETE 端点复用既有互斥闸门 + MinIO best-effort 删除（审计流水保留）；CLI 为薄 REST 客户端（httpx cookie 会话 + CSRF 双提交 + 并发池 + 断点 state），子命令两类：服务端型（gsb/cpa）与本地工具型（license）。

**Tech Stack:** FastAPI + 纯 stdlib CLI（argparse+httpx）+ python-docx 无关（CLI 不解析文档，只传文件）+ TanStack Query（前端分页/删除）。

**Spec:** `docs/superpowers/specs/2026-09-03-geo-batch-ingest-cli-design.md`。

**约定（全任务通用）：** 后端测试 `cd backend && PYTHONPATH=. uv run pytest tests/<file> -v`；前端 `cd frontend && pnpm typecheck && pnpm lint`；CLI 测试 `cd backend && PYTHONPATH=. uv run pytest tests/test_eai_cli.py -v`（importlib 加载 tools/eai.py）；pathspec 提交；并发会话活跃，触碰共享文件前 `git log -1` 复核；EAI-CUSTOM 注释带 `(geo-batch-cli, spec 2026-09-03)`。

---

### Task 1: 题名解析器 title_parser.py（后端纯函数）

**Files:**
- Create: `backend/app/extensions/geo_samples/title_parser.py`
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_parse_title_full_auto():
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("云南省昆明市东川区某铜矿铜银金多金属矿勘探报告")
    assert r["region"] == "云南省昆明市东川区"
    assert r["mineral"] == "copper"
    assert r["stage"] == "exploration"
    assert r["confidence"] == "auto"


def test_parse_title_needs_review_variants():
    from app.extensions.geo_samples import title_parser

    r = title_parser.parse_title("某萤石矿详查报告")          # 词表外矿种
    assert r["stage"] == "detail" and r["mineral"] is None
    assert r["confidence"] == "needs-review"
    r2 = title_parser.parse_title("某岩金矿床地质勘查报告")    # 勘查（泛词）不映射阶段
    assert r2["mineral"] == "gold" and r2["stage"] is None
    assert r2["confidence"] == "needs-review"
    r3 = title_parser.parse_title("无任何规律的文档")
    assert r3["confidence"] == "needs-review"
    assert r3["region"] is None and r3["mineral"] is None and r3["stage"] is None


def test_parse_title_negatives_and_earliest():
    from app.extensions.geo_samples import title_parser

    assert title_parser.parse_title("某非金属矿普查报告")["mineral"] is None
    assert title_parser.parse_title("某铅锌金银多金属勘探报告")["mineral"] == "lead_zinc"  # 铅(0)最早
    assert title_parser.parse_title("某金银矿勘探报告")["mineral"] == "gold"               # 金(0)<银? 银不在词表 → gold
```

- [ ] **Step 2: 确认失败**（No module named title_parser）

- [ ] **Step 3: 实现 title_parser.py**

```python
# EAI-CUSTOM (geo-batch-cli, spec 2026-09-03): 报告题名解析器——report_id 自动编码与
# suggest-id 端点的共用纯函数。词表与技能层 build_output.MINERAL_ALIASES 语义一致
# （最早位置=主矿种、非金属/金属量负向），但两层部署域隔离须各自维护，改动须双向同步。
from __future__ import annotations

REGION_TAILS = ("省", "市", "区", "县", "旗", "盟")
STAGE_WORDS = [("普查", "survey"), ("详查", "detail"), ("勘探", "exploration")]
# 与 skills/public/geological-report/scripts/build_output.py MINERAL_ALIASES 双向同步（DNR）
MINERAL_KEYWORDS = [
    ("copper", ("铜",)), ("coal", ("煤",)), ("gold", ("金",)),
    ("iron", ("铁",)), ("lead_zinc", ("铅锌", "铅", "锌")),
]


def parse_region(title: str) -> str | None:
    for i, ch in enumerate(title):
        if ch in REGION_TAILS:
            seg = title[: i + 1]
            if 2 <= len(seg) <= 20:
                return seg
            return None
    return None


def parse_stage(title: str) -> str | None:
    """尾缀语义：取位置最大的阶段词（「勘探报告」在尾部）。勘查为泛词不映射。"""
    best_pos, best = -1, None
    for word, slug in STAGE_WORDS:
        pos = title.rfind(word)
        if pos > best_pos:
            best_pos, best = pos, slug
    return best


def parse_mineral(title: str) -> str | None:
    s = title.strip()
    if "非金属" in s:
        return None
    best_pos, best = -1, None
    for slug, keys in MINERAL_KEYWORDS:
        for k in keys:
            pos = s.find(k)
            if pos == -1:
                continue
            if k == "金" and pos + 1 < len(s) and s[pos + 1] == "属":
                continue  # 金属量/贵金属负向
            if best_pos == -1 or pos < best_pos:
                best_pos, best = pos, slug
    return best


def parse_title(title: str) -> dict:
    t = (title or "").strip().removesuffix("报告").removesuffix(".docx").removesuffix(".pdf")
    region = parse_region(t)
    mineral = parse_mineral(t)
    stage = parse_stage(t)
    confidence = "auto" if (mineral and stage) else "needs-review"
    return {"region": region, "mineral": mineral, "stage": stage, "confidence": confidence}
```

（测试「金银矿」：金 pos=1 命中 gold ✓；「铅锌金银」：铅 pos=1 < 金 pos=3 → lead_zinc ✓。）

- [ ] **Step 4: 全绿** → **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/title_parser.py backend/tests/test_geo_sample_bank_compile.py
git commit -m "feat(geo-samples): report-title parser for auto report_id coding (batch-cli T1)" -- backend/app/extensions/geo_samples/title_parser.py backend/tests/test_geo_sample_bank_compile.py
```

---

### Task 2: suggest-id 端点（解析 + 查重顺延）

**Files:**
- Modify: `backend/app/extensions/geo_samples/routers.py`（新端点 + import title_parser）
- Modify: `backend/app/extensions/geo_samples/crud.py`（next_sequence 辅助）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_suggest_id_dedup_bump(monkeypatch):
    """同组已有 gsb-kc-cu-0007 → 建议 0008；解析失败 → gsb-auto-NNNN。"""
    from unittest.mock import MagicMock

    from app.extensions.geo_samples import routers

    async def fake_next(db, prefix):
        return f"{prefix}-0008" if prefix == "gsb-kc-cu" else f"{prefix}-0002"

    monkeypatch.setattr(routers.crud, "next_report_id", fake_next)
    r1 = await routers.suggest_id_impl(MagicMock(), "云南省昆明市东川区某铜矿勘探报告")
    assert r1["report_id"] == "gsb-kc-cu-0008" and r1["confidence"] == "auto"
    r2 = await routers.suggest_id_impl(MagicMock(), "无任何规律的文档")
    assert r2["report_id"].startswith("gsb-auto-") and r2["confidence"] == "needs-review"


@pytest.mark.asyncio
async def test_next_report_id_bumps_max(tmp_path):
    """next_report_id 从 LIKE 前缀行取最大序号 +1（真实 SQLite 会话，模式同 identity-map 测试）。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.extensions.database import Base
    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "t.db"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as db:
        for rid in ("gsb-kc-cu-0001", "gsb-kc-cu-0003", "gsb-auto-0001"):
            db.add(GsbDocument(id=rid, report_id=rid, file_name="a.docx", file_hash="h" + rid,
                               file_type="docx", status="uploaded", raw_uri=f"s3://geo-samples/raw/{rid}/a.docx"))
        await db.commit()
        assert await crud.next_report_id(db, "gsb-kc-cu") == "gsb-kc-cu-0004"
        assert await crud.next_report_id(db, "gsb-xc") == "gsb-xc-0001"      # 无同行新组从 0001 起
    await engine.dispose()


@pytest.mark.asyncio
async def test_count_documents_filters(tmp_path):
    """同过滤 count：无过滤 3；stage 过滤 2；stage+status 过滤 1。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.extensions.database import Base
    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "t.db"))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as db:
        for i, (stage, status) in enumerate([("exploration", "reviewed"), ("exploration", "uploaded"),
                                             ("exploration", "reviewed"), ("survey", "uploaded")]):
            db.add(GsbDocument(id=f"d{i}", report_id=f"r{i}", file_name="a.docx", file_hash=f"h{i}",
                               file_type="docx", stage=stage, status=status))
        await db.commit()
        assert await crud.count_documents(db) == 4
        assert await crud.count_documents(db, stage="exploration") == 3
        assert await crud.count_documents(db, stage="exploration", status="reviewed") == 2
    await engine.dispose()
```

- [ ] **Step 2: 确认失败** → **Step 3: 实现**

crud.py 追加：

```python
async def next_report_id(db: AsyncSession, prefix: str) -> str:
    """同前缀最大序号 +1（4 位零填充）。prefix 形如 gsb-kc-cu / gsb-auto。"""
    stmt = select(GsbDocument.report_id).where(GsbDocument.report_id.like(prefix + "-%"))
    rows = (await db.execute(stmt)).scalars().all()
    max_seq = 0
    for rid in rows:
        tail = rid[len(prefix) + 1:]
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return f"{prefix}-{max_seq + 1:04d}"
```

routers.py 追加（实现函数与端点分离便于直测）：

```python
async def suggest_id_impl(db: AsyncSession, title: str) -> dict:
    from . import title_parser

    parsed = title_parser.parse_title(title)
    if parsed["mineral"] and parsed["stage"]:
        stage_code = {"survey": "pu", "detail": "xc", "exploration": "kc"}[parsed["stage"]]
        mineral_code = {"copper": "cu", "coal": "co", "gold": "au", "iron": "fe",
                        "lead_zinc": "pbzn", "other": "ot"}[parsed["mineral"]]
        report_id = await crud.next_report_id(db, f"gsb-{stage_code}-{mineral_code}")
    else:
        report_id = await crud.next_report_id(db, "gsb-auto")
    return {**parsed, "report_id": report_id}


@router.post("/documents/suggest-id")
async def suggest_id(title: str = Query(...), db: AsyncSession = Depends(get_db), _: object = _PERM):
    return await suggest_id_impl(db, title)
```

（Query import 已在 routers；mineral 短码表与 T4 词表键一致。）

- [ ] **Step 4: 全绿**（新 2-3 测 + 既有零回归）→ **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/routers.py backend/app/extensions/geo_samples/crud.py backend/tests/test_geo_sample_bank_compile.py
git commit -m "feat(geo-samples): suggest-id endpoint with title parsing + sequence dedup (batch-cli T2)" -- backend/app/extensions/geo_samples/routers.py backend/app/extensions/geo_samples/crud.py backend/tests/test_geo_sample_bank_compile.py
```

---

### Task 3: DELETE /documents/{document_id}

**Files:**
- Modify: `backend/app/extensions/geo_samples/storage.py`（delete_object_by_uri）
- Modify: `backend/app/extensions/geo_samples/crud.py`（delete_document）
- Modify: `backend/app/extensions/geo_samples/routers.py`（DELETE 端点）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_delete_document_compiled_blocked_and_running_blocked():
    """compiled 409 禁删；parse/redact running 409；成功路径=MinIO 三 uri 尽删+行删。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import routers
    from app.extensions.geo_samples.models import GsbDocument

    def doc_with(status, raw=None, work=None, clean=None):
        return GsbDocument(id="d1", report_id="r1", file_name="a.docx", file_hash="h",
                           file_type="docx", status=status, parse_mode="docx",
                           raw_uri=raw, work_uri=work, clean_uri=clean)

    deleted_keys = []

    async def run_route(doc, running=()):
        db = MagicMock()
        async def _get(db_, did):
            return doc
        async def _running(db_, did, rt):
            return rt in running
        async def _del(db_, did):
            deleted_keys.append(("row", did))
        monkeypatch.setattr(routers.crud, "get_document", _get)
        monkeypatch.setattr(routers.crud, "has_running_run", _running)
        monkeypatch.setattr(routers.crud, "delete_document", _del)
        monkeypatch.setattr(routers.storage, "delete_object_by_uri",
                            lambda uri: deleted_keys.append(("obj", uri)))
        err = None
        try:
            await routers.delete_document("d1", db=db)
        except routers.HTTPException as e:
            err = e
        return err

    e = await run_route(doc_with("compiled"))
    assert e is not None and e.status_code == 409
    e = await run_route(doc_with("parsed"), running={("parse",)})
    assert e is not None and e.status_code == 409
    e = await run_route(doc_with("parsed", raw="s3://geo-samples/raw/r/a.docx",
                                 work="s3://geo-samples/work/r/parsed.md"))
    assert e is None
    assert ("obj", "s3://geo-samples/raw/r/a.docx") in deleted_keys
    assert ("obj", "s3://geo-samples/work/r/parsed.md") in deleted_keys
    assert ("row", "d1") in deleted_keys
```

（端点签名设计为 `async def delete_document(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM)`——依赖默认值使直测可传 db/db mock。monkeypatch/run_route 辅助按实际函数签名微调。）

- [ ] **Step 2: 确认失败**（无 DELETE 路由）→ **Step 3: 实现**

storage.py 追加：

```python
def delete_object_by_uri(uri: str) -> None:
    """best-effort 删除：对象不存在不抛（对齐 cpa storage 同款注释）。"""
    prefix = f"s3://{BUCKET}/"
    if not uri.startswith(prefix):
        return
    from minio.error import S3Error

    try:
        _client().remove_object(BUCKET, uri[len(prefix):])
    except S3Error:
        pass
```

crud.py 追加：

```python
async def delete_document(db: AsyncSession, document_id: str) -> None:
    doc = await get_document(db, document_id)
    if doc:
        await db.delete(doc)
        await db.commit()
```

routers.py 追加：

```python
@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db), _: object = _PERM):
    doc = await crud.get_document(db, document_id)
    if doc is None:
        raise HTTPException(404, "样例不存在")
    if doc.status == "compiled":
        raise HTTPException(409, "已编译样例不可删除（编译产物在技能 references 中）")
    for rt in ("parse", "redact"):
        if await crud.has_running_run(db, document_id, rt):
            raise HTTPException(409, f"{rt} 任务在跑——稍后再删除")
    for uri in (doc.raw_uri, doc.work_uri, doc.clean_uri):
        if uri:
            await asyncio.to_thread(storage.delete_object_by_uri, uri)
    await crud.delete_document(db, document_id)
    return {"deleted": True, "report_id": doc.report_id}
```

（asyncio 已 import？routers 现 import asyncio 于 T7——确认；审计流水 gsb_redactions/gsb_run_history 保留=无 FK 既定语义，注释声明。）

- [ ] **Step 4: 全绿** → **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/storage.py backend/app/extensions/geo_samples/crud.py backend/app/extensions/geo_samples/routers.py backend/tests/test_geo_sample_bank_compile.py
git commit -m "feat(geo-samples): DELETE endpoint (compiled/running guards, MinIO best-effort, audit survives) (batch-cli T3)" -- backend/app/extensions/geo_samples/storage.py backend/app/extensions/geo_samples/crud.py backend/app/extensions/geo_samples/routers.py backend/tests/test_geo_sample_bank_compile.py
```

---

### Task 4: GET /documents 加 total + 前端分页与删除按钮

**Files:**
- Modify: `backend/app/extensions/geo_samples/crud.py`（count_documents）
- Modify: `backend/app/extensions/geo_samples/routers.py`（list_documents 响应加 total）
- Modify: `frontend/src/extensions/geo-samples/api.ts`（类型+deleteDocument+total）
- Modify: `frontend/src/extensions/geo-samples/hooks.ts`（useGsbDelete）
- Modify: `frontend/src/extensions/geo-samples/components/DocumentsView.tsx`（分页控件+删除按钮）
- Test: `backend/tests/test_geo_sample_bank_compile.py`（追加 count 测试）+ `cd frontend && pnpm typecheck && pnpm lint`

- [ ] **Step 1: 后端失败测试**

```python
@pytest.mark.asyncio
async def test_count_documents_filters(tmp_path):
    ...  # sqlite 会话插 3 行（2 exploration-copper reviewed + 1 coal uploaded）
    # count_documents(db, stage="exploration") == 2；count_documents(db) == 3
```

- [ ] **Step 2: 后端实现**——crud.py：

```python
async def count_documents(db: AsyncSession, stage=None, mineral=None, status=None) -> int:
    from sqlalchemy import func

    stmt = select(func.count(GsbDocument.id))
    if stage:
        stmt = stmt.where(GsbDocument.stage == stage)
    if mineral:
        stmt = stmt.where(GsbDocument.mineral == mineral)
    if status:
        stmt = stmt.where(GsbDocument.status == status)
    return (await db.execute(stmt)).scalar_one()
```

routers.py list_documents 响应改：

```python
    total = await crud.count_documents(db, stage=stage, mineral=mineral, status=status)
    return {"items": [...], "skip": skip, "limit": limit, "total": total}
```

- [ ] **Step 3: 前端实现**
  - api.ts：`listDocuments` 返回类型加 `total: number`；新增 `deleteDocument(id)` → `authFetch(\`\${BASE}/documents/\${id}\`, { method: "DELETE" })`
  - hooks.ts：`useGsbDelete`（onSuccess invalidate gsb-documents + gsb-runs）
  - DocumentsView：`const [page, setPage] = useState(0)` + `const [pageSize, setPageSize] = useState(50)`；列表查询 filters 加 `skip: page * pageSize, limit: pageSize`；StatCard 全量查询保持 `{limit: 200}`；表格下加分页行：`共 {total} 条 ｜ 每页 [50▾] ｜ 上一页/下一页`（`hasNext = docs.length === pageSize`）；操作列追加灰色文字按钮「删除」（compiled 行不渲染）：

```tsx
{d.status !== "compiled" && (
  <button
    onClick={() => {
      if (confirm(`确认删除 ${d.report_id}？原始文件与解析/脱敏产物将一并删除，不可恢复`)) {
        del.mutate({ id: d.id }, { onError: alertErr });
      }
    }}
    className="text-xs text-red-600 hover:underline"
  >
    删除
  </button>
)}
```

  - 筛选变更时 `setPage(0)`（防越界页）。

- [ ] **Step 4:** 后端测试绿 + `pnpm typecheck && pnpm lint` → **Step 5: Commit**

```bash
git add backend/app/extensions/geo_samples/crud.py backend/app/extensions/geo_samples/routers.py backend/tests/test_geo_sample_bank_compile.py frontend/src/extensions/geo-samples/
git commit -m "feat(geo-samples): list total + frontend pagination + delete button (batch-cli T4)" -- <上述文件>
```

---

### Task 5: tools/eai.py 骨架（会话/公共层/子命令注册表）

**Files:**
- Create: `tools/eai.py`
- Test: `backend/tests/test_eai_cli.py`（新建，importlib 加载）

- [ ] **Step 1: 写失败测试**（核心可测函数：`load_session/save_session/do_login/probe/build_session`、`fetch_all_pages`、CSV 行校验 `normalize_manifest_row`）

```python
"""统一 CLI（tools/eai.py）单元测试——importlib 加载，httpx.MockTransport 假网络。"""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

CLI_PATH = Path(__file__).resolve().parents[2] / "tools" / "eai.py"
spec = importlib.util.spec_from_file_location("eai_cli", CLI_PATH)
eai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eai)


def test_login_and_probe_contract():
    """登录拿双 cookie → csrf 头回填 → /api/v1/auth/me 200 探活。"""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, dict(request.headers)))
        if request.url.path == "/api/extensions/auth/login":
            return httpx.Response(200, json={"expires_in": 86400, "needs_setup": False},
                                  headers=[("set-cookie", "access_token=jwt123; Path=/"),
                                           ("set-cookie", "csrf_token=tok456; Path=/")])
        if request.url.path == "/api/v1/auth/me":
            assert request.headers["cookie"].count("access_token=jwt123")
            return httpx.Response(200, json={"id": "u1"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    sess = eai.login("http://x", "admin@eai-flow.com", "Admin@2026", transport=transport)
    assert sess.csrf == "tok456"
    assert eai.probe(sess, transport=transport) is True
    # 状态变更请求自动带 X-CSRF-Token
    sess.post("http://x/api/extensions/geo-samples/documents/d1/parse", transport=transport)
    m, p, h = calls[-1]
    assert h["X-CSRF-Token"] == "tok456"


def test_login_429_respects_lockout():
    def handler(request):
        return httpx.Response(429, json={"detail": "Too many login attempts. Try again later."})

    with pytest.raises(eai.LoginLocked) as e:
        eai.login("http://x", "u", "p", transport=httpx.MockTransport(handler))
```

（httpx.Client 需要 transport 注入点——`login(..., transport=None)`/`probe(..., transport=None)`/`_client(...)` 全部透传；生产 None=真网络。）

- [ ] **Step 2: 确认失败** → **Step 3: 实现 tools/eai.py 骨架**（~260 行，核心结构）：

```python
#!/usr/bin/env python3
"""eai.py — 系统统一模块运维 CLI（薄 REST 客户端，spec 2026-09-03）。
两类子命令：服务端型（gsb/cpa，需登录会话）与本地工具型（license，免会话）。
依赖：stdlib + httpx。凭据不落盘（HTTP 会话 cookie 进程内有效）。"""
import argparse
import httpx
import json
import sys
from pathlib import Path

SESSION_FILE = Path.home() / ".eai" / "session.json"
LOGIN_PATH = "/api/extensions/auth/login"
PROBE_PATH = "/api/v1/auth/me"
CSRF_HEADER = "X-CSRF-Token"


class LoginLocked(Exception):
    pass


class Session:
    def __init__(self, base_url: str, client: httpx.Client, csrf: str):
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.csrf = csrf

    def headers(self) -> dict:
        return {CSRF_HEADER: self.csrf}

    def get(self, path: str, **kw):
        return self.client.get(self.base_url + path, **kw)

    def post(self, path: str, **kw):
        return self.client.post(self.base_url + path, headers=self.headers(), **kw)

    def delete(self, path: str, **kw):
        return self.client.delete(self.base_url + path, headers=self.headers(), **kw)


def login(base_url, username, password, transport=None) -> Session:
    """登录：不发送 Origin 头（触发 403 跨站门）；429 → LoginLocked（限流桶 5 次/5 分钟共享）。"""
    client = httpx.Client(base_url=base_url, timeout=120.0, transport=transport)
    resp = client.post(LOGIN_PATH, json={"username": username, "password": password})
    if resp.status_code == 429:
        raise LoginLocked("登录限流（5 次/5 分钟，IP 共享桶）——稍后再试")
    resp.raise_for_status()
    csrf = resp.cookies.get("csrf_token") or client.cookies.get("csrf_token")
    return Session(base_url, client, csrf or "")


def probe(sess: Session, transport=None) -> bool:
    resp = sess.client.get(sess.base_url + PROBE_PATH)
    return resp.status_code == 200
```

（`client.cookies.get` 在 httpx 中从 cookie jar 取值——登录响应 Set-Cookie 自动入 jar；实测若 httpx 不自动吸 multipart 域的 set-cookie，回退手动 `resp.headers.get_list("set-cookie")` 解析——测试断言 csrf=="tok456" 为准。CSRF 头注入：为极简不重写 httpx 事件钩子，Session.post/delete 显式拼头。）

argparse 骨架 + SUBCOMMANDS 注册表：

```python
SUBCOMMANDS = {}  # name -> {"help":…, "needs_session": bool, "func": callable}


def register(name, help_text, needs_session=True):
    def deco(fn):
        SUBCOMMANDS[name] = {"help": help_text, "needs_session": needs_session, "func": fn}
        return fn
    return deco


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="eai.py", description="EAI 系统统一模块运维 CLI")
    ap.add_argument("--base-url", default="http://localhost:2026")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, meta in SUBCOMMANDS.items():
        sp = sub.add_parser(name, help=meta["help"])
        if meta["needs_session"]:
            sp.add_argument("--username", required=True)
            sp.add_argument("--password", required=True)
        meta["func"].register_args(sp)
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    meta = SUBCOMMANDS[args.command]
    kwargs = {k: v for k, v in vars(args).items() if k not in ("command", "base_url", "username", "password")}
    if meta["needs_session"]:
        sess = login(args.base_url, args.username, args.password)
        if not probe(sess):
            print("会话探活失败", file=sys.stderr)
            return 2
        return meta["func"](sess, args)
    return meta["func"](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 全绿** → **Step 5: Commit**

```bash
git add tools/eai.py backend/tests/test_eai_cli.py
git commit -m "feat(cli): unified tools/eai.py skeleton (login session/probe/subcommand registry) (batch-cli T5)" -- tools/eai.py backend/tests/test_eai_cli.py
```

---

### Task 6: gsb 子命令（scan/import）+ cpa/license 子命令

**Files:**
- Modify: `tools/eai.py`
- Test: `backend/tests/test_eai_cli.py`（追加）

- [ ] **Step 1: 写失败测试**（核心逻辑函数级）

```python
def test_gsb_scan_rows(tmp_path, monkeypatch):
    """scan：目录文件 → 调 suggest-id → CSV 行生成 + 置信度标注 + report_id 冲突顺延。"""
    (tmp_path / "云南省昆明市东川区某铜矿勘探报告.docx").write_bytes(b"x")
    (tmp_path / "无规律文件.docx").write_bytes(b"y")
    calls = []

    def fake_impl(db, title):
        calls.append(title)
        if "铜矿" in title:
            return {"region": "云南省昆明市东川区", "mineral": "copper", "stage": "exploration",
                    "confidence": "auto", "report_id": "gsb-kc-cu-0001"}
        return {"region": None, "mineral": None, "stage": None,
                "confidence": "needs-review", "report_id": "gsb-auto-0001"}

    monkeypatch.setattr(eai, "suggest_id_impl", fake_impl)
    rows = eai.gsb_scan_rows(tmp_path, suggest_fn=lambda t: fake_impl(None, t), limit=10)
    assert len(rows) == 2
    assert rows[0]["report_id"] == "gsb-kc-cu-0001"
    assert rows[1]["confidence"] == "needs-review"


def test_import_state_resume(tmp_path):
    """断点 state：已完成 report_id 重跑跳过。"""
    state = eai.ImportState(tmp_path / "state.json")
    state.mark_done("gsb-kc-cu-0001")
    assert state.is_done("gsb-kc-cu-0001")
    state2 = eai.ImportState(tmp_path / "state.json")   # 重实例=模拟重跑
    assert state2.is_done("gsb-kc-cu-0001")


def test_import_409_bumps_sequence(tmp_path, monkeypatch):
    """409 撞库 → 序号 +1 重试（上限 10 次）。"""
    attempts = []

    class FakeSess:
        def post(self, path, files=None, data=None, **kw):
            attempts.append(data["report_id"])
            if len(attempts) == 1:
                return httpx.Response(409, json={"detail": "已存在"}, request=httpx.Request("POST", path))
            return httpx.Response(200, json={"document": {"id": "d9", "report_id": data["report_id"]}, "run_id": "r"})

    row = {"file_name": "a.docx", "report_id": "gsb-kc-cu-0001", "stage": "exploration",
           "mineral": "copper", "region": "", "confidence": "auto"}
    f = tmp_path / "a.docx"; f.write_bytes(b"x")
    result = eai.upload_one(FakeSess(), str(f), row, parse=True)
    assert result["report_id"] == "gsb-kc-cu-0002" and len(attempts) == 2
```

- [ ] **Step 2: 确认失败** → **Step 3: 实现 gsb/cpa/license 三组**（要点，全部在 tools/eai.py）：

- `gsb_scan_rows(dir, suggest_fn, limit)`：glob `*.docx/*.pdf` → 题名=文件名去扩展 → suggest_fn → 行 dict；**冲突顺延**：同组重复 report_id 序号递增；`cmd_gsb_scan` = 登录 → 逐文件调 `POST /documents/suggest-id?title=…`（httpx params）→ 写 CSV（utf-8-sig 供 Excel 直开）+ stdout 汇总
- `ImportState(path)`：json 读 `{done: [rid]}`，mark_done 即写盘（断点）；`upload_one(sess, file_path, row, parse)`：multipart `files={"file": (file_name, open…)}, data={report_id/stage/mineral}` → 409 且 detail 含「已存在」→ report_id 序号 +1 重试 ≤10 → 成功后 parse=True 时调 `POST …/{id}/parse`
- `cmd_gsb_import`：读 CSV（utf-8-sig）→ 跳过 state 已完成 → ThreadPoolExecutor(max_workers=4) 上传 → 逐个 mark_done → 失败行写 `gsb_import_failed.csv` → 汇总
- `cmd_cpa_upload`：`--dir` + `--trigger-parse` flag → 逐份 POST `/api/extensions/contract-price/documents/upload`（multipart 仅 file 字段；409 内容重复计 skipped）→ `--trigger-parse` 时末尾单次 POST `/pipeline/run` body {"mode":"table","trigger":"manual"}（**全局互斥，仅末尾一次**；409 提示已有 parse 在跑）
- `cmd_license_generate`：转发 argparse 参数（request_file 必填 + --days/--permanent/--all-modules/--modules/--customer/--max-users/--features/--output）→ `sys.path.insert(0, str(tools/license))` + `import license_generator as lg` → `lg.generate_license(...)` → 校验输出文件存在（machine_id 缺失静默 return 陷阱→文件不存在时报错 rc=1）
- `SUBCOMMANDS` 注册：gsb scan/import/status（status=GET /documents?limit=200 表格摘要）、cpa upload/status、license generate（needs_session=False）

- [ ] **Step 4: 全绿**（CLI 全部测试）→ **Step 5: Commit**

```bash
git add tools/eai.py backend/tests/test_eai_cli.py
git commit -m "feat(cli): gsb scan/import + cpa upload + license generate subcommands (batch-cli T6)" -- tools/eai.py backend/tests/test_eai_cli.py
```

---

### Task 7: suggest-id「自动」按钮（UI 联动）

**Files:**
- Modify: `frontend/src/extensions/geo-samples/api.ts`（suggestId 方法）
- Modify: `frontend/src/extensions/geo-samples/components/DocumentsView.tsx`（「自动」按钮 + 回填 report_id 输入框）

- [ ] **Step 1:** api.ts 加 `suggestId(title: string)` → `authFetch(\`${BASE}/documents/suggest-id?title=\${encodeURIComponent(title)}\`)`；DocumentsView 上传区 report_id 输入框旁加「自动」小按钮：以当前所选文件名（去扩展名）为题名调用 → 成功回填 `reportIdRef.current.value = r.report_id` 并 alert 展示 stage/mineral 解析结果（needs-review 时提示人工复核）。
- [ ] **Step 2:** `pnpm typecheck && pnpm lint` → **Step 3: Commit**

```bash
git add frontend/src/extensions/geo-samples/
git commit -m "feat(geo-samples): auto report_id button wired to suggest-id (batch-cli T7)" -- frontend/src/extensions/geo-samples/
```

---

### Task 8: 端到端验收 + 全量门禁

- [ ] **Step 1:** 后端 `make lint && make test`（geo 系全绿，无关失败按 T12 归因法）；前端三闸
- [ ] **Step 2:** CLI 实跑两阶段：`python tools/eai.py gsb scan --dir <真实样例目录> --username admin@eai-flow.com --password Admin@2026` → 校正 CSV → `import --workers 4` → 断言列表分页正确（total/翻页）+ 删除按钮实删一份（含 MinIO 对象消失验证）+ 50 份级扫描性能记录
- [ ] **Step 3:** `python tools/eai.py cpa upload --dir <合同目录>` 冒烟 + `python tools/eai.py license generate <request.json> --all-modules --output test.lic` 冒烟（输出文件存在）
- [ ] **Step 4:** Commit（如有修补）+ 汇总报告

---

## 完成判据（验收）

1. 门禁全绿（geo 系测试 + CLI 测试 + 前端三闸）
2. CLI 两阶段实跑：真实文件 scan→校正→import，report_id 全部语义结构码（needs-review 行有人工修正）
3. 列表分页（total/翻页/每页条数）+ 删除按钮（confirm→删行+删对象+审计保留）实测
4. `cpa upload` 与 `license generate` 子命令冒烟通过——统一 CLI 复用性验证成立
5. `gsb-auto-NNNN` 回退路径实测（无规律文件名）

## 明确不做（Phase 4+/随需）

UI 批量对话框；count 聚合独立端点；扫描件 OCR 批量调度器；token/refresh 持久会话（进程内 cookie 即可）；--prune 接线（待文档删除已具备——下批接 compile 联动）；cpa delete/重置子命令。

## 关键风险备忘

1. **登录限流共享桶**：5 次失败/IP/5min——CLI 密码错 5 次会把 nginx:2026 整个入口锁 5 分钟（含真人）；429 必须显式报错不重试
2. **CSRF 回填勿二次解码**：cookie 值原样填 X-CSRF-Token
3. **CLI 不发 Origin 头**：发送即 403 Cross-site auth request denied
4. **会话不跨进程**：HTTP 下 cookie 会话级——批量任务单进程内完成；中断重跑重登录
5. **cpa 同名重传丢确认状态**：批量前核对 file_hash 去重（CLI 上传 409 计 skipped 不重传）
6. **geo 删除竞态**：parse/redact running 时 409（复用既有闸门）；编译产物回收机制未设计——compiled 禁删
