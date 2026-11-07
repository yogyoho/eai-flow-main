"""B4 评分覆盖度(spec §5)测试:compute_score_coverage 纯函数 + GET /tasks/{id}/score_coverage。

覆盖映射机制:评分办法项抽取时携带 related_paths(抽取层限定为字段字典路径),
与启用规则 inputs 求交——交集非空即覆盖。映射纯机械、可审计;related_paths 缺失
或全未知 → 该项未覆盖(诚实:映射不来就别装覆盖)。夹具照 test_bid_review_diff.py。
"""

from datetime import UTC

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models
from app.extensions.bid_review import routers as R
from app.extensions.bid_review.engine.extract import compute_score_coverage
from app.extensions.database import Base, get_db


class _FakeRule:
    def __init__(self, rule_id: str, inputs: list[str], enabled: bool = True):
        self.id = rule_id
        self.inputs = inputs
        self.enabled = enabled


# ── 纯函数 ────────────────────────────────────────────────────────────


def test_coverage_intersection_and_counts():
    """related_paths ∩ rule.inputs 非空即覆盖;covered/total 逐项计。"""
    items = [
        {"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price", "tender.bid_scope"]},
        {"name": "履约信誉分", "max_score": 10, "related_paths": ["tender.bid_scope"]},
    ]
    rules = [
        _FakeRule("L1-009", ["bid.total_price", "tender.max_price"]),
        _FakeRule("L1-002", ["bid.qual_levels"]),
    ]
    out = compute_score_coverage(items, rules)
    assert out["total"] == 2 and out["covered"] == 1
    assert out["items"][0]["covered_by_rules"] == ["L1-009"]
    assert out["items"][1]["covered_by_rules"] == []


def test_coverage_drops_junk_and_disabled_rules():
    """非 dict 项/无名项丢弃;enabled=False 规则不参与;related_paths 缺失 → 未覆盖。"""
    items = ["垃圾", {"max_score": 5}, {"name": "  "}, {"name": "方案分"}]
    rules = [_FakeRule("L3-001", ["tender.project_identity.name"], enabled=False)]
    out = compute_score_coverage(items, rules)
    assert out["total"] == 1
    assert out["items"][0] == {"name": "方案分", "max_score": None, "covered_by_rules": []}
    assert out["covered"] == 0


def test_coverage_empty():
    assert compute_score_coverage([], []) == {"total": 0, "covered": 0, "covered_max_score": None, "items": []}  # 对齐审计②新键


# ── 端点 ──────────────────────────────────────────────────────────────


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


async def _noop_resume(task_id, owner_id):
    return None


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_resume_after_confirm", _noop_resume)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _mk_baseline(db, task_id: str, scoring_items: list) -> models.BaselinePackage:
    row = models.BaselinePackage(
        task_id=task_id,
        kind="tender",
        payload={"fields": {"tender.scoring_items": scoring_items}},
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_endpoint_coverage_with_intersection(client, db):
    """基线带评分办法项 → {total, covered, items};related_paths 用生产规则包
    真实路径(tender.max_price ∈ L1-009 inputs)验证端到端接线。多行同快照按
    name 去重,不重复计数。"""
    t = await crud.create_task(db, owner_id="u1")
    items = [
        {"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price"]},
        {"name": "方案分", "max_score": 30, "related_paths": []},
    ]
    await _mk_baseline(db, t.id, items)
    await _mk_baseline(db, t.id, items)  # 第二行同快照(docx 无页拆分场景)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/score_coverage")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["covered"] == 1
    price = next(i for i in body["items"] if i["name"] == "价格分")
    assert price["covered_by_rules"] == ["L1-009"]
    assert next(i for i in body["items"] if i["name"] == "方案分")["covered_by_rules"] == []


@pytest.mark.asyncio
async def test_endpoint_no_scoring_items_zero_projection(client, db):
    """旧任务基线无评分办法项 → {total:0, covered:0, items:[]}(前端据此回落规则命中 meter)。"""
    t = await crud.create_task(db, owner_id="u1")
    await _mk_baseline(db, t.id, [])
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/score_coverage")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "covered": 0, "items": []}


@pytest.mark.asyncio
async def test_endpoint_task_not_found_404(client):
    r = await client.get("/api/extensions/bid-review/tasks/ghost/score_coverage")
    assert r.status_code == 404


def test_covered_max_score_numeric_and_none():
    """对齐审计②(2026-11-05):covered_max_score=covered 项 max_score 可数值化合计;
    「高」等不可转跳过;无可转/无 covered → None(伪零纪律)。"""
    items = [
        {"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price"]},
        {"name": "技术分", "max_score": "30.5", "related_paths": ["tender.max_price"]},
        {"name": "垃圾分", "max_score": "高", "related_paths": ["tender.max_price"]},
    ]
    rules = [_FakeRule("L1-009", ["tender.max_price"])]
    out = compute_score_coverage(items, rules)
    assert out["covered"] == 3
    assert out["covered_max_score"] == 80.5  # 50+30.5;「高」跳过
    out2 = compute_score_coverage([{"name": "x", "max_score": "高", "related_paths": ["p"]}], rules)
    assert out2["covered_max_score"] is None
    out3 = compute_score_coverage([{"name": "x", "related_paths": ["p"]}], [_FakeRule("L2-x", ["other"])])
    assert out3["covered_max_score"] is None  # 无 covered


# ── 对齐审计③⑩(2026-11-05):报告复核耗时真数据 + 偏离表节 ────────────────────


def test_feedback_summary_shapes():
    """裁决③三形态:0 条=未复核;1 条=1 次动作;≥2 条=首末动作跨度(下界)。"""
    from datetime import datetime

    from app.extensions.bid_review.routers import _feedback_summary

    assert _feedback_summary([]) == "人工复核:未复核"
    one = [type("F", (), {"created_at": datetime(2026, 11, 5, 10, 0, tzinfo=UTC)})()]
    assert "1 次动作" in _feedback_summary(one)
    two = one + [type("F", (), {"created_at": datetime(2026, 11, 5, 11, 30, tzinfo=UTC)})()]
    s = _feedback_summary(two)
    assert "≥1.5h" in s and "下界" in s


@pytest.mark.asyncio
async def test_report_review_duration_and_deviations(client, db):
    """端到端:「待补充」假占位删除;feedback 真耗时落元信息行;偏离表节渲染 counts+逐条。"""
    from datetime import datetime

    t = await crud.create_task(db, owner_id="u1")
    t.status = "done"
    await db.commit()
    issue = await crud.add_issue(
        db,
        task_id=t.id,
        owner_id="u1",
        rule_id="L1-009",
        layer="L1",
        severity="fatal",
        verdict="FAIL",
        message="总价超限价",
        fix="复核报价",
        dedup_key="k1",
    )
    db.add(
        models.ReviewFeedback(
            issue_id=issue.id,
            owner_id="u1",
            action="confirm",
            created_at=datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
        )
    )
    db.add(
        models.ReviewFeedback(
            issue_id=issue.id,
            owner_id="u1",
            action="false_positive",
            created_at=datetime(2026, 11, 5, 11, 30, tzinfo=UTC),
        )
    )
    db.add(
        models.BaselinePackage(
            task_id=t.id,
            kind="tender",
            payload={
                "fields": {
                    "deviation.items": [
                        {"item": "工期", "kind": "deviation", "tender_value": "180天", "bid_value": "150天"},
                    ]
                }
            },
        )
    )
    await db.commit()
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")
    assert r.status_code == 200
    md = r.text
    assert "待补充" not in md
    assert "人工复核:" in md and "≥1.5h" in md
    assert "响应偏离" in md and "工期" in md and "180天" in md


@pytest.mark.asyncio
async def test_report_no_feedback_no_deviations(client, db):
    """空态:未复核 + 响应偏离无记录(不假装有数据)。"""
    t = await crud.create_task(db, owner_id="u1")
    t.status = "done"
    await db.commit()
    await crud.add_issue(
        db,
        task_id=t.id,
        owner_id="u1",
        rule_id="L1-001",
        layer="L1",
        severity="info",
        verdict="UNKNOWN",
        message="缺字段",
        dedup_key="k2",
    )
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")
    assert r.status_code == 200
    md = r.text
    assert "人工复核:未复核" in md
    assert "响应偏离" in md and "无记录" in md


# ── 评分涉险面(score-risk spec 2026-11-05,挂账「score 预估另立 spec」兑付)──────


def test_derive_score_risk_sum_names_and_unresolved():
    """涉险上界三键:violation 规则命中项 max_score 合计+列名;unclear/待人工 →
    unresolved 列名不进合计;violation 优先于 unresolved(互斥)。"""
    from app.extensions.bid_review.engine.extract import derive_score_risk

    cov = {
        "items": [
            {"name": "价格分", "max_score": 50, "covered_by_rules": ["L1-009"]},
            {"name": "工期分", "max_score": "10", "covered_by_rules": ["T2-001"]},
            {"name": "方案分", "max_score": None, "covered_by_rules": []},
        ]
    }
    out = derive_score_risk(cov, {"L1-009", "T2-001"}, set())
    assert out == {"at_risk_max_score": 60.0, "at_risk_item_names": ["价格分", "工期分"], "unresolved_item_names": []}
    out2 = derive_score_risk(cov, set(), {"T2-001"})
    assert out2 == {"at_risk_max_score": 0.0, "at_risk_item_names": [], "unresolved_item_names": ["工期分"]}


def test_derive_score_risk_zero_none_and_uncovered_violation():
    """真零/伪零纪律:无涉险项 → 0.0(真零);违规规则未覆盖任何项 → 0.0 空名;
    涉险项 max_score 全不可数值化 → None(诚实不可估,不凑 0)。"""
    from app.extensions.bid_review.engine.extract import derive_score_risk

    cov = {"items": [{"name": "售后分", "max_score": None, "covered_by_rules": ["T3-001"]}]}
    assert derive_score_risk(cov, set(), set())["at_risk_max_score"] == 0.0
    assert derive_score_risk(cov, {"L1-999"}, set())["at_risk_item_names"] == []
    assert derive_score_risk(cov, {"T3-001"}, set())["at_risk_max_score"] is None


@pytest.mark.asyncio
async def test_endpoint_risk_keys_enrichment(client, db):
    """端点接线:基线评分项 + 三种 verdict issues → 三键派生;active FAIL 涉险、
    UNKNOWN → unresolved、false_positive 不进;compute 本体键(total/covered/covered_max_score)
    原样保留。空评分项短路保持旧形状全等(R5)。"""
    t = await crud.create_task(db, owner_id="u1")
    await _mk_baseline(db, t.id, [{"name": "价格分", "max_score": 50, "related_paths": ["tender.max_price"]}])
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="FAIL", message="超限价", dedup_key="k1", need_human=False)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-010", layer="L1", severity="major", verdict="FAIL", message="加总不符", dedup_key="k2", need_human=False)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-013", layer="L1", severity="major", verdict="unclear", message="材料存疑", dedup_key="k3", need_human=True)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="minor", verdict="false_positive", message="误报", dedup_key="k4", need_human=False)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/score_coverage")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["covered"] == 1 and body["covered_max_score"] == 50.0  # 本体键原样
    assert body["at_risk_max_score"] == 50.0 and body["at_risk_item_names"] == ["价格分"]
    assert body["unresolved_item_names"] == []  # L1-013 未覆盖价格分(related_paths 交集空),不硬凑
