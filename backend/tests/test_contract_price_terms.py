"""货物分类术语（cpa v3, spec 2026-10-14 §2）：表注册 + CRUD 编排 + capture 改写。

编排测试镜像 M1 test_contract_price_library.py 的 asyncio.run 直调 + monkeypatch 模式，
不需要真实 DB。
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型
from app.extensions.contract_price import crud as cpa_crud
from app.extensions.contract_price.routers import (
    create_term_endpoint,
    delete_term_endpoint,
    list_terms_endpoint,
    update_term_endpoint,
)


def test_terms_table_registered_on_shared_base():
    from app.extensions.database import Base

    assert {"cpa_terms"} <= set(Base.metadata.tables)


def test_normalize_term_matches_engine():
    assert cpa_crud.normalize_term(" 锚杆 Φ22 ") == "锚杆Φ22"
    assert cpa_crud.normalize_term(None) == ""
    assert cpa_crud.normalize_term("") == ""


def test_union_aliases_dedupes_normalized():
    old = ["锚杆Φ22", "树脂锚杆"]
    out = cpa_crud.union_aliases(old, {"锚杆Φ22", "玻璃钢锚杆", ""})
    assert out == ["锚杆Φ22", "树脂锚杆", "玻璃钢锚杆"]  # 归一化重复与空名剔除,新名追加


def test_capture_creates_auto_merge_term():
    added = {}
    committed = []

    class _Names:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["锚杆Φ22", "树脂锚杆", "锚杆"])

    class _Terms:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])  # 库内无既有术语

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            return _Names() if self.calls == 1 else _Terms()

        def add(self, row):
            added["row"] = row

        async def commit(self):
            committed.append(1)

    asyncio.run(cpa_crud._capture_merge_pin(_Session(), SimpleNamespace(id=uuid4()), "锚杆"))
    row = added["row"]
    assert row.canonical == "锚杆" and row.source == "auto_merge" and row.enabled is True
    assert sorted(row.aliases) == ["树脂锚杆", "锚杆Φ22"]
    assert len(committed) == 1


def test_capture_merges_into_existing_term_keeps_source():
    existing = SimpleNamespace(id=uuid4(), canonical="锚杆", aliases=["旧别名"], enabled=False, source="manual")

    class _First:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["锚杆Φ22"])

    class _Second:
        def scalars(self):
            return SimpleNamespace(all=lambda: [existing])

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            return _First() if self.calls == 1 else _Second()

        async def commit(self):
            pass

    asyncio.run(cpa_crud._capture_merge_pin(_Session(), SimpleNamespace(id=uuid4()), "锚杆"))
    assert existing.aliases == ["旧别名", "锚杆Φ22"]  # 只并别名
    assert existing.source == "manual" and existing.enabled is False  # 不降级不改启停


def test_capture_noop_when_aliases_already_covered():
    committed = []
    existing = SimpleNamespace(id=uuid4(), canonical="锚杆", aliases=["锚杆Φ22", "树脂锚杆"], enabled=True, source="auto_merge")

    class _First:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["锚杆Φ22"])  # 新别名已被既有术语覆盖

    class _Second:
        def scalars(self):
            return SimpleNamespace(all=lambda: [existing])

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            return _First() if self.calls == 1 else _Second()

        async def commit(self):
            committed.append(1)

    asyncio.run(cpa_crud._capture_merge_pin(_Session(), SimpleNamespace(id=uuid4()), "锚杆"))
    assert committed == []  # 无变化不 commit（commit-only-on-change）
    assert existing.aliases == ["锚杆Φ22", "树脂锚杆"]  # aliases 不变


def test_capture_swallows_commit_failure_and_rolls_back():
    rolled_back = []

    class _Names:
        def scalars(self):
            return SimpleNamespace(all=lambda: ["锚杆Φ22"])

    class _Terms:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])

    class _Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            return _Names() if self.calls == 1 else _Terms()

        def add(self, row):
            pass

        async def commit(self):
            raise RuntimeError("flush failed")

        async def rollback(self):
            rolled_back.append(1)

    # 不上抛——捕获失败只记日志,不影响合并主流程
    asyncio.run(cpa_crud._capture_merge_pin(_Session(), SimpleNamespace(id=uuid4()), "锚杆"))
    assert rolled_back == [1]  # 失败路径回滚,不留 PendingRollback 态


# ---- Task 4: 路由编排测试 ----


class _Body:
    def __init__(self, fields):
        self._f = fields

    def model_dump(self, **_kw):
        return dict(self._f)


class _ListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _Db:
    """最小桩: get 按预置;execute 按 calls 序出队。"""

    def __init__(self, rows=None, get_map=None):
        self._rows = rows or []
        self._get = get_map or {}
        self.calls = 0

    async def execute(self, stmt):
        self.calls += 1
        return _ListResult(self._rows)

    async def get(self, model, obj_id):
        return self._get.get(obj_id)


def _term(**kw):
    base = dict(
        id=uuid4(), canonical="锚杆", aliases=["锚杆Φ22"], enabled=True, source="manual",
        created_at=None, updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _async_ret(v):
    async def _fn(*a, **kw):
        return v
    return _fn


def test_create_term_duplicate_canonical_409(monkeypatch):
    monkeypatch.setattr(cpa_crud, "list_terms", _async_ret([_term()]))
    body = SimpleNamespace(canonical="锚  杆", aliases=[])  # 端点走属性访问(pydantic),桩用 SimpleNamespace
    with pytest.raises(HTTPException) as ei:
        asyncio.run(create_term_endpoint(body, db=_Db(), _=None))
    assert ei.value.status_code == 409  # 归一化撞既有 canonical


def test_list_terms_with_item_counts(monkeypatch):
    monkeypatch.setattr(cpa_crud, "list_terms", _async_ret([_term(), _term(id=uuid4(), canonical="U型卡", aliases=["卡缆"])]))
    monkeypatch.setattr(cpa_crud, "term_item_count_map", _async_ret({"锚杆": 100, "锚杆Φ22": 42, "U型卡": 11}))
    out = asyncio.run(list_terms_endpoint(db=_Db(), _=None))
    by_name = {t["canonical"]: t for t in out["items"]}
    assert by_name["锚杆"]["item_count"] == 142  # canonical + 全部别名归一化求和
    assert by_name["锚杆"]["alias_count"] == 1
    assert by_name["U型卡"]["item_count"] == 11


def test_update_term_enabled_only(monkeypatch):
    t = _term()
    monkeypatch.setattr(cpa_crud, "get_term", _async_ret(t))
    monkeypatch.setattr(cpa_crud, "update_term", _async_ret(t))
    monkeypatch.setattr(cpa_crud, "list_terms", _async_ret([t]))  # 撞车循环只见自身行,按 id 跳过
    out = asyncio.run(update_term_endpoint(t.id, _Body({"enabled": False}), db=_Db(), _=None))
    assert out.id == t.id  # 形状有值即可,禁用不触碰 canonical（端点返回 TermOut 模型,M1 同款属性访问）


def test_delete_term_missing_404(monkeypatch):
    monkeypatch.setattr(cpa_crud, "delete_term", _async_ret(False))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(delete_term_endpoint(uuid4(), db=_Db(), _=None))
    assert ei.value.status_code == 404


def test_update_term_collision_with_other_409(monkeypatch):
    t = _term()
    other = _term(id=uuid4(), canonical="U型卡", aliases=[])
    calls = []

    async def _no_update(*a, **kw):
        calls.append(1)
        return t

    monkeypatch.setattr(cpa_crud, "get_term", _async_ret(t))
    monkeypatch.setattr(cpa_crud, "update_term", _no_update)
    monkeypatch.setattr(cpa_crud, "list_terms", _async_ret([t, other]))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(update_term_endpoint(t.id, _Body({"canonical": "U型卡"}), db=_Db(), _=None))
    assert ei.value.status_code == 409
    assert calls == []  # 撞车即拒,全部校验通过后才落库


def test_create_term_self_alias_conflict_422(monkeypatch):
    monkeypatch.setattr(cpa_crud, "list_terms", _async_ret([]))
    body = SimpleNamespace(canonical="锚杆", aliases=["锚  杆"])  # 归一化与 canonical 相同
    with pytest.raises(HTTPException) as ei:
        asyncio.run(create_term_endpoint(body, db=_Db(), _=None))
    assert ei.value.status_code == 422  # 请求内自撞,先于对其它术语 409


def test_create_term_dedupes_aliases(monkeypatch):
    created = {}

    async def _fake_create(db, canonical, aliases, source="manual"):
        created["aliases"] = aliases
        return SimpleNamespace(id=uuid4(), canonical=canonical, aliases=aliases, enabled=True, source=source)

    monkeypatch.setattr(cpa_crud, "list_terms", _async_ret([]))
    monkeypatch.setattr(cpa_crud, "create_term", _fake_create)
    # 注: normalize_term 只去空白不改大小写（与引擎逐字同款），"X" 与 "x" 是不同键——
    # 用 "X"/" x " 不构成归一化撞车;去重用例须选归一化同键的 ["X", " X "]。
    out = asyncio.run(create_term_endpoint(SimpleNamespace(canonical="吊环", aliases=["X", " X "]), db=_Db(), _=None))
    assert out.alias_count == 1  # 归一化去重后 alias_count 不虚高
    assert created["aliases"] == ["X"]
