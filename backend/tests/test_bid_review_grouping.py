"""L2 P2 跨层实体去重(spec 2026-11-02 §7 挂账行):entity_keys 落库链 +
list_task_issues 投影归并(_cross_layer_group 纯函数直验,先例=checklist 现算不落库)。

归并规则(D7):同实体键 + 跨 ≥2 层 + 双方 violation(非 need_human)才归并;
keep = severity 升序 → 层序 L1>L2>L3 → created_at 稳定;need_human 永不隐藏。
条目不删:grouped 行标 grouped_into=keep.id(items 全量返回),keep 行带 related_issues。
"""

from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.bid_review.routers import _cross_layer_group
from app.extensions.database import Base, get_db


def _iss(id, rule_id, layer, severity, *, verdict="violation", need_human=False, keys=None, created_at="2026-11-02T00:00:00Z", message="m"):
    return SimpleNamespace(
        id=id,
        rule_id=rule_id,
        layer=layer,
        severity=severity,
        verdict=verdict,
        need_human=need_human,
        entity_keys=keys or [],
        created_at=created_at,
        message=message,
    )


def test_cross_layer_group_keeps_most_severe():
    """L2 fatal 与 L3 minor 同实体 → keep L2;L3 行 grouped_into,keep 带 related。"""
    a = _iss("a", "L2-020", "L2", "fatal", keys=["attachment:A-2"])
    b = _iss("b", "L3-005", "L3", "minor", keys=["attachment:A-2"])
    info = _cross_layer_group([a, b])
    assert info["b"]["grouped_into"] == "a"
    assert info["a"]["grouped_into"] is None
    assert info["a"]["related"] == [
        {"id": "b", "rule_id": "L3-005", "layer": "L3", "severity": "minor", "message": "m"},
    ]
    assert info["b"]["related"] == []


def test_cross_layer_severity_tie_prefers_layer_order():
    """同 severity → L1>L2>L3 层序定 keep(spec:跨层去重 L1>L2>L3)。"""
    l3 = _iss("x", "L3-010", "L3", "major", keys=["attachment:A-1"])
    l2 = _iss("y", "L2-024", "L2", "major", keys=["attachment:A-1"])
    info = _cross_layer_group([l3, l2])
    assert info["x"]["grouped_into"] == "y"  # L2 胜出
    assert info["y"]["grouped_into"] is None


def test_need_human_and_single_layer_never_group():
    """need_human 不参与归并(待人工必须可见);同层/无共享键/单实体不归并。"""
    nh = _iss("n", "L2-020", "L2", "fatal", verdict="need_human", need_human=True, keys=["attachment:A-1"])
    v_same_layer = _iss("s", "L2-024", "L2", "major", keys=["attachment:A-1"])
    v_other_key = _iss("o", "L3-010", "L3", "minor", keys=["attachment:B-1"])
    v_no_keys = _iss("k", "L1-001", "L1", "fatal", keys=[])
    info = _cross_layer_group([nh, v_same_layer, v_other_key, v_no_keys])
    assert info == {}


def test_multi_key_row_groups_into_last_sorted_key():
    """多键行被多个键命中:grouped_into 取按名字序最后命中键的 keep(确定性 last-wins),
    且该行同时出现在两个 keep 的 related 里(条目不删)。行为 pin,非驱动。"""
    m = _iss("m", "L1-001", "L1", "info", keys=["attachment:B", "attachment:A"])
    a = _iss("a", "L2-020", "L2", "fatal", keys=["attachment:A"])
    b = _iss("b", "L3-005", "L3", "minor", keys=["attachment:B"])
    info = _cross_layer_group([m, a, b])
    assert info["m"]["grouped_into"] == "b"  # "attachment:B" 按名字序在 "attachment:A" 后 → last-wins
    assert info["a"]["grouped_into"] is None
    assert info["b"]["grouped_into"] is None
    assert [r["id"] for r in info["a"]["related"]] == ["m"]
    assert [r["id"] for r in info["b"]["related"]] == ["m"]


def test_duplicated_key_row_not_self_grouped():
    """同行带重复实体键(两个 no-less req 同名)不自归并:i.id == keep.id 守卫跳过自匹配;
    恰产出一对 grouped_into,keep 的 related 恰含对方一次。行为 pin,非驱动。"""
    p = _iss("p", "L2-020", "L2", "fatal", keys=["attachment:X", "attachment:X"])
    q = _iss("q", "L3-005", "L3", "minor", keys=["attachment:X"])
    info = _cross_layer_group([p, q])
    assert info["q"]["grouped_into"] == "p"
    assert info["p"]["grouped_into"] is None
    assert [r["id"] for r in info["p"]["related"]] == ["q"]


# ── 端点接线(list_task_issues × _cross_layer_group)────────────────────────
# 夹具照 test_bid_review_checklist.py 原样(sqlite+aiosqlite 内存库 + FastAPI 依赖覆盖)。


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(
            Base.metadata.create_all,
            tables=[
                models.ReviewTask.__table__,
                models.ReviewIssue.__table__,
                models.BaselinePackage.__table__,
                models.RulePackMeta.__table__,
                models.ReviewFeedback.__table__,
            ],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.asyncio
async def test_issues_endpoint_grouping_wiring(db, client):
    """端点接线:同实体跨层两 violation → grouped 行带 grouped_into,keep 带 related;
    平凡单层行零字段(IssueOut 缺省)。条目不删(D8):items 仍 3 条,summary 口径
    不变——grouped 行照常计入严重度计数,前端隐藏由展示层负责。"""
    task = await crud.create_task(db, owner_id="u1")
    await crud.add_issue(db, task_id=task.id, owner_id="u1", rule_id="L2-020", layer="L2", severity="fatal", verdict="violation", message="缺少附件 A-2 业绩证明", dedup_key="L2-020|-|k1", entity_keys=["attachment:A-2"])
    await crud.add_issue(db, task_id=task.id, owner_id="u1", rule_id="L3-005", layer="L3", severity="minor", verdict="violation", message="业绩证明表述不一致", dedup_key="L3-005|-|k2", entity_keys=["attachment:A-2"])
    await crud.add_issue(db, task_id=task.id, owner_id="u1", rule_id="L2-024", layer="L2", severity="major", verdict="violation", message="无关问题", dedup_key="L2-024|-|k3")
    r = await client.get(f"/api/extensions/bid-review/tasks/{task.id}/issues")
    assert r.status_code == 200
    body = r.json()
    items = {i["rule_id"]: i for i in body["items"]}
    assert items["L3-005"]["grouped_into"] == items["L2-020"]["id"]
    assert items["L2-020"]["grouped_into"] is None
    assert items["L2-020"]["related_issues"][0]["rule_id"] == "L3-005"
    assert items["L2-024"]["grouped_into"] is None and items["L2-024"]["related_issues"] == []
    assert len(body["items"]) == 3  # 条目不删(D8)
    assert body["summary"] == {
        "fatal": 1,
        "major": 1,
        "minor": 1,
        "info": 0,
        "need_human": 0,
        "rules_total": None,
        "unknown_ratio": None,
        "advisory": {"total": 0, "by_severity": {"fatal": 0, "major": 0, "minor": 0, "info": 0}},  # A-续-⑥ additive
    }  # 口径不变;M5 两新键 additive(None)
