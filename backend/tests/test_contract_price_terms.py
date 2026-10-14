"""货物分类术语（cpa v3, spec 2026-10-14 §2）：表注册 + CRUD 编排 + capture 改写。

编排测试镜像 M1 test_contract_price_library.py 的 asyncio.run 直调 + monkeypatch 模式，
不需要真实 DB。
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import app.extensions.contract_price  # noqa: F401 — 导入即注册模型
from app.extensions.contract_price import crud as cpa_crud


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
