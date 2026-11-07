"""L4 激活后端(P1-β批二续 T4,A-续-⑥⑦):RulePack.meta 结构化消费 / worker 并列
ADVISORY_RULEPACK_PATH 合包单次 evaluate / summarize 排 L4 出正式计数 / _fatal_hits 显式
守卫 / _cross_layer_group 跳过 L4 / issues API advisory 分节 / 双渲染器竞争力建议尾节
(meta 封顶) / 反馈归属按前缀 / rulepacks 三端点双包 / golden 冻结面证明(A-续-⑦)。

合包测试自建 l4 stub 包 monkeypatch ADVISORY_RULEPACK_PATH 指向它(tmp 包不吃真 L4,
先例=test_bid_review_worker.tmp_rulepack);全部规则 det,零模型调用。"""

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models, worker
from app.extensions.bid_review import routers as R
from app.extensions.bid_review.engine.rule_runner import load_rulepack
from app.extensions.bid_review.golden import loader as golden_loader
from app.extensions.database import Base, get_db

_TABLES = [
    models.ReviewTask.__table__,
    models.ReviewIssue.__table__,
    models.BaselinePackage.__table__,
    models.RulePackMeta.__table__,
    models.ReviewFeedback.__table__,
]

_CORE_STUB = """\
conventions:
  on_missing_input: need_human
rules:
  - id: T1-001
    name: 测试总价不超限价
    layer: L1
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.total_price, tender.max_price]
    check:
      op: lte
      left: bid.total_price
      right: tender.max_price
    severity: fatal
    evidence: []
    message_tpl: "投标总价 {bid.total_price:money} 超过最高限价 {tender.max_price:money}"
    fix_tpl: 复核报价
    confidence_gate: 1.0
    enabled: true
"""

_L4_STUB = """\
conventions:
  on_missing_input: need_human
rules:
  - id: L4-T01
    name: 测试advisory承诺超额
    layer: L4
    type: deterministic
    applies_to: ["*"]
    inputs: [bid.total_price, tender.max_price]
    check:
      op: gte
      left: tender.max_price
      right: bid.total_price
    severity: major
    evidence: []
    message_tpl: "advisory承诺超额(测试桩)"
    fix_tpl: 收口承诺
    confidence_gate: 1.0
    enabled: true
"""

_FIELDS = {"bid.total_price": 2000000, "tender.max_price": 1000000}
_DOCS = [{"doc_id": "b.pdf", "role": "bid", "text": "x"}]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_enqueue_docs", lambda task, files: None)  # 后台直推旁路
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


# ── ① l4 包 meta 结构化契约 ───────────────────────────────────────────


def test_l4_pack_meta_contract():
    """load_rulepack 显式读 meta(A-续-⑥):counts_toward_bid_gate=false / cap=10 /
    gate_effect=info;core 包无 meta 键 → 空 dict(默认值零破坏)。"""
    pack = load_rulepack(worker.ADVISORY_RULEPACK_PATH)
    assert pack.meta["counts_toward_bid_gate"] is False
    assert pack.meta["max_issues_per_report"] == 10
    assert pack.meta["gate_effect"] == "info"
    core = load_rulepack(worker.RULEPACK_PATH)
    assert core.meta == {}


# ── ② worker 合包:单次 evaluate 产出 L4 条目,正式计数不含 L4 ────────────


@pytest.mark.asyncio
async def test_worker_merges_advisory_pack_full_chain(db, monkeypatch, tmp_path):
    """advance_task 全链(tmp 库):core stub + l4 stub 合一列表单次 evaluate——L4 条目
    落库,done 帧 summary.advisory.total≥1,正式 fatal/major 计数不含 L4;rules_total=Σ。"""
    core = tmp_path / "core.yaml"
    core.write_text(_CORE_STUB, encoding="utf-8")
    l4 = tmp_path / "l4.yaml"
    l4.write_text(_L4_STUB, encoding="utf-8")
    monkeypatch.setattr(worker, "RULEPACK_PATH", core)
    monkeypatch.setattr(worker, "ADVISORY_RULEPACK_PATH", l4)

    t = await crud.create_task(db, owner_id="u1", mode="deep")
    task = await worker.advance_task(db, t.id, owner_id="u1", docs=_DOCS, extract_fn=lambda d, p: {**{k: None for k in p}, **_FIELDS}, wait_confirm=False)
    assert task.status == "done"
    issues = await crud.list_issues(db, task_id=t.id, owner_id="u1")
    by_rule = {i.rule_id: i for i in issues}
    assert by_rule["T1-001"].verdict == "violation" and by_rule["T1-001"].layer == "L1", "core 规则照常"
    assert by_rule["L4-T01"].verdict == "violation" and by_rule["L4-T01"].layer == "L4", "合包后 L4 advisory 条目落库"
    summary = task.progress["summary"]
    assert summary["advisory"]["total"] >= 1, "advisory 单列 L4 条目"
    assert summary["advisory"]["by_severity"]["major"] >= 1
    assert summary["fatal"] == 1 and summary["major"] == 0, "正式 fatal/major 计数不含 L4(L4 major 不入正式)"
    assert summary["rules_total"] == 2, "合包分母 rules_total=Σ(core 1 + l4 1)"


def test_quick_prune_excludes_l4_rules():
    """quick 裁剪自动排 L4 全 sem/hyb(L4 无 det 卡,真包亦然):合并面裁剪后只剩 L1 det。"""
    from app.extensions.bid_review.worker import _prune_rules_for_mode

    merged = list(load_rulepack(worker.RULEPACK_PATH).rules) + list(load_rulepack(worker.ADVISORY_RULEPACK_PATH).rules)
    pruned = _prune_rules_for_mode(SimpleNamespace(rules=merged), "quick")
    assert pruned and all(r.layer == "L1" and r.type == "deterministic" for r in pruned)


@pytest.mark.asyncio
async def test_advisory_missing_path_falls_back_to_core_only(db, monkeypatch, tmp_path):
    """ADVISORY_RULEPACK_PATH=None → 现状 core 单包行为(fixture 打桩依赖此语义)。"""
    core = tmp_path / "core.yaml"
    core.write_text(_CORE_STUB, encoding="utf-8")
    monkeypatch.setattr(worker, "RULEPACK_PATH", core)
    monkeypatch.setattr(worker, "ADVISORY_RULEPACK_PATH", None)
    t = await crud.create_task(db, owner_id="u1", mode="deep")
    _, rules_total = await worker._run_review_stage(db, t, _FIELDS, "u1")
    assert rules_total == 1  # 仅 core 1 条,l4 未合入


# ── ③④ gate 守卫与归并跳过 ────────────────────────────────────────────


def test_fatal_hits_excludes_l4():
    """_fatal_hits 显式 L4 守卫(A-续-⑥):构造 L4 fatal violation 行不命中红线,
    同形 L1 行照常命中(守卫只针对 layer)。"""
    l4_row = SimpleNamespace(severity="fatal", verdict="violation", need_human=False, layer="L4")
    l1_row = SimpleNamespace(severity="fatal", verdict="violation", need_human=False, layer="L1")
    assert R._fatal_hits([l4_row]) == []
    assert R._fatal_hits([l1_row]) == [l1_row]


def test_cross_layer_group_skips_l4():
    """_cross_layer_group 整体跳过 L4(A-续-⑥):advisory 不参与归并、不被 formal 折叠
    ——同实体键 L4+L2 两 violation 不产生 grouped_into(无 L4 时 L2 单层不归并)。"""
    now = datetime.now(UTC)
    l4 = SimpleNamespace(id="i1", verdict="violation", need_human=False, entity_keys=["attachment:A-2"], layer="L4", severity="major", rule_id="L4-001", message="m", created_at=now)
    l2 = SimpleNamespace(id="i2", verdict="violation", need_human=False, entity_keys=["attachment:A-2"], layer="L2", severity="major", rule_id="L2-020", message="m", created_at=now)
    assert R._cross_layer_group([l4, l2]) == {}
    l3 = SimpleNamespace(id="i3", verdict="violation", need_human=False, entity_keys=["attachment:A-2"], layer="L3", severity="minor", rule_id="L3-005", message="m", created_at=now)
    assert R._cross_layer_group([l2, l3]) != {}, "非 L4 跨层归并行为不回退"


# ── ⑤ issues API advisory 分节形状 ────────────────────────────────────


@pytest.mark.asyncio
async def test_list_task_issues_advisory_section(client, db):
    """list_task_issues 响应加 advisory={items,total,by_severity}:L4 行仍在 items 全量
    返回(条目不删),advisory 单列同批条目;正式 summary 不含 L4。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L4-001", layer="L4", severity="major", verdict="violation", message="质保超额", fix="收口", evidence=[], dedup_key="k2")
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/issues")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2, "条目不删:L4 行仍在 items"
    adv = body["advisory"]
    assert adv["total"] == 1 and adv["items"][0]["rule_id"] == "L4-001" and adv["items"][0]["layer"] == "L4"
    assert adv["by_severity"]["major"] == 1 and adv["by_severity"]["fatal"] == 0
    assert body["summary"]["major"] == 0 and body["summary"]["fatal"] == 1, "正式计数不含 L4"


# ── ⑥ 双渲染器竞争力建议尾节(meta 封顶)───────────────────────────────


@pytest.mark.asyncio
async def test_renderers_advisory_tail_section_capped(client, db):
    """md/html 报告含「竞争力建议(L4,advisory)」独立尾节;L4 不入正式 severity 分节;
    条数受包 meta max_issues_per_report=10 封顶(12 条 L4 → 恰 10 条)。"""
    t = await crud.create_task(db, owner_id="u1")
    for n in range(1, 13):
        await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id=f"L4-9{n:02d}", layer="L4", severity="major", verdict="violation", message=f"建议{n:02d}号", fix="收口", evidence=[], dedup_key=f"L4-9{n:02d}|-|k{n}")
    await crud.set_status(db, t, "done")
    md = (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report?format=md")).text
    html = (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report?format=html")).text
    assert "## 竞争力建议(L4,advisory)" in md and "竞争力建议" in html
    assert "## 主要(major)——0 项" in md, "L4 排出正式 severity 分节(不计正式问题数的呈现面)"
    for n in range(1, 11):
        assert f"L4-9{n:02d}" in md, f"封顶内第 {n} 条应呈现"
    assert "L4-911" not in md and "L4-912" not in md, "超出 max_issues_per_report=10 的条目不呈现"
    assert html.count("建议") >= 10 and "L4-911" not in html, "html 同口径封顶"


# ── ⑦ 反馈归属按前缀 ──────────────────────────────────────────────────


def test_rulepack_name_for_prefix():
    assert R._rulepack_name_for("L4-001") == "bid-review-l4"
    assert R._rulepack_name_for("L4-T01") == "bid-review-l4"
    assert R._rulepack_name_for("L1-001") == "bid-review-core"
    assert R._rulepack_name_for("L2-020") == "bid-review-core"


@pytest.mark.asyncio
async def test_false_positive_attribution_records_l4_pack(db):
    """apply_false_positive 到 L4 issue → RulePackMeta.stats 记入 bid-review-l4 行
    (fp+1),core 行零串账。"""
    t = await crud.create_task(db, owner_id="u1")
    issue = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L4-001", layer="L4", severity="major", verdict="violation", message="质保超额", fix="收口", evidence=[], dedup_key="k1")
    await R.apply_false_positive(db, issue)
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == "bid-review-l4"))).scalar_one_or_none()
    assert meta is not None and meta.stats["L4-001"]["fp"] == 1
    core_meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == "bid-review-core"))).scalar_one_or_none()
    assert core_meta is None or "L4-001" not in (core_meta.stats or {}), "L4 误报不串 core 行"


# ── ⑧ rulepacks 三端点双包 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rulepacks_endpoints_two_packs(client, db):
    """list_rulepacks 两 item(core 前序=既有 items[0] 断言不破);set_rule_enabled 可
    作用于 L4 包(落 bid-review-l4 meta 行);未知包名 404 语义不变。"""
    base = "/api/extensions/bid-review"
    r = await client.get(f"{base}/rulepacks")
    assert r.status_code == 200
    names = [i["name"] for i in r.json()["items"]]
    assert names == ["bid-review-core", "bid-review-l4"]
    l4_item = r.json()["items"][1]
    assert l4_item["rule_count"] == 10 and {rule["id"] for rule in l4_item["rules"]} >= {"L4-001", "L4-010"}
    r2 = await client.post(f"{base}/rulepacks/bid-review-l4/rules/L4-001/enabled", json={"enabled": False})
    assert r2.status_code == 200 and r2.json()["rule_overrides"]["L4-001"] is False
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == "bid-review-l4"))).scalar_one()
    assert meta.rule_overrides["L4-001"] is False
    r3 = await client.get(f"{base}/rulepacks/bid-review-l4/rules")
    assert r3.status_code == 200 and r3.json()["pack"]["name"] == "bid-review-l4"
    assert any(i["id"] == "L4-001" and i["enabled"] is False for i in r3.json()["items"]), "rule_details enabled 投影 override"
    assert (await client.post(f"{base}/rulepacks/no-such-pack/rules/L4-001/enabled", json={"enabled": False})).status_code == 404
    assert (await client.get(f"{base}/rulepacks/no-such-pack/rules")).status_code == 404


# ── ⑨ golden 冻结面证明(A-续-⑦)──────────────────────────────────────


def test_golden_loader_path_frozen():
    """golden loader 的 RULEPACK_PATH 字符串未变(仍硬接线 core 单包);worker 两常量
    并列各指其包,RULEPACK_PATH 单包语义零触碰。"""
    assert "bid-review-l4" not in golden_loader.RULEPACK_PATH
    p = golden_loader.RULEPACK_PATH.replace("\\", "/")
    assert p.endswith("engine/rulepacks/bid-review-core/1.0.0.yaml")
    assert str(worker.RULEPACK_PATH).replace("\\", "/").endswith("engine/rulepacks/bid-review-core/1.0.0.yaml")
    assert str(worker.ADVISORY_RULEPACK_PATH).replace("\\", "/").endswith("engine/rulepacks/bid-review-l4/1.0.0.yaml")
    assert str(worker.RULEPACK_PATH) != str(worker.ADVISORY_RULEPACK_PATH)
