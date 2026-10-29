"""Task 10 测试:bid_review 8 端点——httpx ASGITransport + 独立 FastAPI 子应用挂 router;
auth 依赖 current_owner 与 get_db 双 override 到 sqlite 内存库;_enqueue_docs /
_resume_after_confirm 后台旁路(monkeypatch;plan Task 10 Step 1 夹具方式)。

偏离 plan 字面(同 test_bid_review_crud.py 先例):只定点建 bid_review 五张表(共享 Base
跨模块 FK 的 DDL 排序问题);plan 夹具样例未 override get_db,此处补上(端点经
Depends(get_db) 取会话,不 override 会打到生产 extensions DB)。
"""

import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_review import crud, models, worker
from app.extensions.bid_review import routers as R
from app.extensions.database import Base, get_db


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


def _noop_enqueue(task, files):
    """同步 no-op(plan 夹具同款形态;_enqueue_docs 本体即同步 create_task 包装)。"""


async def _noop_resume(task_id, owner_id):
    return None


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    app = FastAPI()
    app.include_router(R.router)
    # current_owner = routers 内模块级 auth 依赖(必须模块级,dependency_overrides 才能打桩)
    app.dependency_overrides[R.current_owner] = lambda: "u1"
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(R, "_enqueue_docs", _noop_enqueue)  # 解析旁路
    monkeypatch.setattr(R, "_resume_after_confirm", _noop_resume)  # 续跑旁路
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.asyncio
async def test_task_lifecycle(client, db):
    """plan Task 10 Step 1 原样:创建(默认 quick)→详情含 progress→规则包清单。"""
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "quick"})
    assert r.status_code == 200 and r.json()["status"] == "created"
    tid = r.json()["id"]
    r2 = await client.get(f"/api/extensions/bid-review/tasks/{tid}")
    assert r2.json()["id"] == tid
    assert "progress" in r2.json()
    r3 = await client.get("/api/extensions/bid-review/rulepacks")
    assert r3.status_code == 200
    items = r3.json()["items"]
    assert items and items[0]["name"] == "bid-review-core" and items[0]["rule_count"] > 0
    assert all({"id", "name", "layer", "severity", "type"} <= set(rule) for rule in items[0]["rules"])


@pytest.mark.asyncio
async def test_create_task_with_files_persists_docs(client, db):
    """multipart 上传(tender+bid 各一份)→ 文档解码落 engine_meta.docs(role 逐份标注),
    任务保持 created(后台 advance 被打桩旁路)。"""
    r = await client.post(
        "/api/extensions/bid-review/tasks",
        data={"mode": "deep"},
        files=[("tender_files", ("t.txt", b"TENDER TEXT", "text/plain")), ("bid_files", ("b.txt", b"BID TEXT", "text/plain"))],
    )
    assert r.status_code == 200 and r.json()["mode"] == "deep" and r.json()["status"] == "created"
    t = await crud.get_task(db, task_id=r.json()["id"], owner_id="u1")
    docs = t.engine_meta["docs"]
    assert [d["role"] for d in docs] == ["tender", "bid"]
    assert docs[0]["doc_id"] == "t.txt" and docs[0]["text"] == "TENDER TEXT"
    assert docs[1]["text"] == "BID TEXT"


@pytest.mark.asyncio
async def test_create_task_rejects_bad_mode(client):
    r = await client.post("/api/extensions/bid-review/tasks", data={"mode": "bogus"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_tasks_owner_filter_and_cross_owner_404(client, db):
    mine = await crud.create_task(db, owner_id="u1")
    other = await crud.create_task(db, owner_id="u2")
    r = await client.get("/api/extensions/bid-review/tasks")
    assert {i["id"] for i in r.json()["items"]} == {mine.id}
    r2 = await client.get(f"/api/extensions/bid-review/tasks/{other.id}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_confirm_flips_baselines_and_owner_gate(client, db):
    """确认门(仅 UI):基线全量翻转 confirmed;他人任务 404。"""
    t = await crud.create_task(db, owner_id="u1")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {}, "materials_hash": "x"}))
    db.add(models.BaselinePackage(task_id=t.id, kind="bid", payload={"fields": {}, "materials_hash": "x"}))
    await crud.set_status(db, t, "awaiting_confirm")
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")
    assert r.status_code == 200
    baselines = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    assert all(b.confirmed for b in baselines)
    other = await crud.create_task(db, owner_id="u2")
    r2 = await client.post(f"/api/extensions/bid-review/tasks/{other.id}/confirm")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_issues_list_and_detail_owner_gated(client, db):
    t = await crud.create_task(db, owner_id="u1")
    other_t = await crud.create_task(db, owner_id="u2")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[{"doc_id": "b.pdf", "page": 1}], dedup_key="k1")
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/issues")
    assert r.status_code == 200 and r.json()["items"][0]["id"] == a.id
    r2 = await client.get(f"/api/extensions/bid-review/issues/{a.id}")
    assert r2.status_code == 200 and r2.json()["rule_id"] == "L1-009"
    # 他人任务的 issues 列表 404;他人 issue 详情 404
    assert (await client.get(f"/api/extensions/bid-review/tasks/{other_t.id}/issues")).status_code == 404
    leaked = await crud.add_issue(db, task_id=other_t.id, owner_id="u2", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="m", fix="f", evidence=[], dedup_key="k9")
    assert (await client.get(f"/api/extensions/bid-review/issues/{leaked.id}")).status_code == 404
    assert (await client.get("/api/extensions/bid-review/issues/nonexistent")).status_code == 404


@pytest.mark.asyncio
async def test_feedback_writes_row_and_rulepack_stats(client, db):
    """feedback 三连:ReviewFeedback 落行 + RulePackMeta.stats 回流(false_positive→fp+1,
    confirm→adopted+1);非法 action/new_severity 422。"""
    t = await crud.create_task(db, owner_id="u1")
    a = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "false_positive", "note": "误报"})).status_code == 200
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "confirm"})).status_code == 200
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "severity_change", "new_severity": "major"})).status_code == 200
    meta = (await db.execute(select(models.RulePackMeta).where(models.RulePackMeta.name == "bid-review-core"))).scalar_one()
    assert meta.stats["L1-009"]["fp"] == 1 and meta.stats["L1-009"]["adopted"] == 1
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "bogus"})).status_code == 422
    assert (await client.post(f"/api/extensions/bid-review/issues/{a.id}/feedback", json={"action": "severity_change", "new_severity": "huge"})).status_code == 422


# ── Task 14:issues 列表 API 汇总分级(A12 T14 集成约束①)──────────────


@pytest.mark.asyncio
async def test_issues_list_summary_grades_need_human_separately(client, db):
    """T14 A12 约束①:issues 列表 API 响应带 summary(汇总分级)——正式违规计数
    (fatal/major/minor/info)不含 need_human 条目,待人工单列;条目不删(items 仍
    全量返回,工作台待人工格与 verdict 过滤消费)。与 worker progress.summary 共用
    worker.summarize_issues,两侧口径一致。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-013", layer="L1", severity="fatal", verdict="unclear", message="材料不足", fix="补响应", evidence=[], dedup_key="k2", need_human=True)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-001", layer="L3", severity="minor", verdict="violation", message="页眉不一致", fix="替换", evidence=[], dedup_key="k3")
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/issues")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3, "need_human 条目仍在清单(单列不删除,待人工格消费)"
    assert body["summary"] == {"fatal": 1, "major": 0, "minor": 1, "info": 0, "need_human": 1}, "致命计数不含 need_human 条目(fatal sem 条目入待人工)"


# ── micro-A 2026-10-29:GET /tasks 每任务问题计数(致命数/待人工填实的数据源)──


@pytest.mark.asyncio
async def test_list_tasks_per_task_issue_counts(client, db):
    """micro-A:GET /tasks 每任务附 fatal_unhandled / need_human_count——口径对齐
    TasksView 行级致命数:fatal 且未被人工判误报(verdict≠false_positive;need_human
    的 fatal 条目计入),need_human_count=need_human 旗标计数(工作台待人工格口径);
    误报回流(apply_false_positive 置 verdict/need_human)后自然回落;他人任务的
    issues 不得串入本任务计数。"""
    t = await crud.create_task(db, owner_id="u1")
    sibling = await crud.create_task(db, owner_id="u1")  # 同 owner 兄弟任务:计数互不串
    # 正式 fatal violation(计入)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    # fatal need_human(计入 fatal_unhandled + need_human_count)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-013", layer="L1", severity="fatal", verdict="unclear", message="材料不足", fix="补响应", evidence=[], dedup_key="k2", need_human=True)
    # 已判误报 fatal(两项计数均剔除;经 feedback 端点同款 apply_false_positive 落库)
    fp = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-010", layer="L1", severity="fatal", verdict="violation", message="口径误报", fix="忽略", evidence=[], dedup_key="k3")
    await R.apply_false_positive(db, fp)
    # minor 违规(两项均不计);major need_human(仅入 need_human_count)
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-001", layer="L3", severity="minor", verdict="violation", message="页眉不一致", fix="替换", evidence=[], dedup_key="k4")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-002", layer="L3", severity="major", verdict="violation", message="缺章", fix="补", evidence=[], dedup_key="k5", need_human=True)
    # 兄弟任务的 fatal 不得串入本任务计数(逐任务聚合不得跨 task)
    await crud.add_issue(db, task_id=sibling.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="兄弟任务", fix="f", evidence=[], dedup_key="k9")

    r = await client.get("/api/extensions/bid-review/tasks")
    assert r.status_code == 200
    row = next(i for i in r.json()["items"] if i["id"] == t.id)
    assert row["fatal_unhandled"] == 2, "fatal violation + fatal need_human 各计 1,已判误报剔除,兄弟任务不串"
    assert row["need_human_count"] == 2, "fatal need_human + major need_human"
    sibling_row = next(i for i in r.json()["items"] if i["id"] == sibling.id)
    assert sibling_row["fatal_unhandled"] == 1 and sibling_row["need_human_count"] == 0


@pytest.mark.asyncio
async def test_single_task_endpoints_do_not_fill_counts(client, db):
    """计数仅 GET /tasks 列表聚合填充(micro-A 授权面=列表聚合);单任务端点
    None=未统计——禁伪零,未统计不得冒充 0。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-009", layer="L1", severity="fatal", verdict="violation", message="超限价", fix="复核", evidence=[], dedup_key="k1")
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}")
    assert r.status_code == 200
    assert r.json()["fatal_unhandled"] is None
    assert r.json()["need_human_count"] is None


# ── Task 15:确认门端点收紧 + MCP 无 confirm 断言 ─────────────────────


@pytest.mark.asyncio
async def test_confirm_gate_rejects_non_awaiting_confirm(client, db):
    """Task 15:confirm 端点校验 status==awaiting_confirm——其余状态(created/done 等)
    直接投续跑一律 409,且基线不得被翻转(确认门是唯一续跑通道,不可旁路/重复确认)。"""
    t = await crud.create_task(db, owner_id="u1")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {}, "materials_hash": "x"}))
    await db.commit()
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")
    assert r.status_code == 409, "created(未到基线确认门)不得 confirm 续跑"
    baselines = await crud.list_baselines(db, task_id=t.id, owner_id="u1")
    assert all(not b.confirmed for b in baselines), "409 时基线不得被翻转"
    await crud.set_status(db, t, "done")
    assert (await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")).status_code == 409, "done 终态重复确认拒绝"


@pytest.mark.asyncio
async def test_awaiting_confirm_needs_confirm_to_run(client, db, monkeypatch):
    """Task 15:awaiting_confirm 未 confirm 的任务——worker claim 跳过(领取集只有
    created/extracting);唯一放行通道是 POST /confirm(触发续跑后台)。"""
    t = await crud.create_task(db, owner_id="u1", mode="deep")
    db.add(models.BaselinePackage(task_id=t.id, kind="tender", payload={"fields": {}, "materials_hash": "x"}))
    await crud.set_status(db, t, "awaiting_confirm")
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    assert await worker._claim_next(factory) is None, "确认门未过的任务 claim 必须跳过"

    resumed: list[tuple[str, str]] = []
    released = asyncio.Event()

    async def _spy_resume(task_id, owner_id):
        resumed.append((task_id, owner_id))
        released.set()

    monkeypatch.setattr(R, "_resume_after_confirm", _spy_resume)
    r = await client.post(f"/api/extensions/bid-review/tasks/{t.id}/confirm")
    assert r.status_code == 200
    await asyncio.wait_for(released.wait(), timeout=2)
    assert resumed and resumed[0] == (t.id, "u1"), "confirm 必须经续跑通道把任务推向 running"


# ── Task 21:报告导出(GET /tasks/{id}/report?format=md)─────────────────


@pytest.mark.asyncio
async def test_report_md_disclaimer_sections_and_per_issue_fields(client, db):
    """Task 21 Step 1 契约:report 端点返回 md 文本——首行含免责声明(措辞照 plan/
    ui-spec §3.5 原文),按 severity 分节,每条含规则 ID/证据(doc+page)/修复建议;
    含可提交判定提示行与复核耗时占位。need_human 条目按 severity 归节标注待人工
    (不静默删除);人工误报(false_positive)不进报告正文;可提交判定口径=正式
    fatal 违规(fatal 且 verdict=violation 且非 need_human,误报剔除)。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.set_status(db, t, "done")
    await crud.add_issue(
        db,
        task_id=t.id,
        owner_id="u1",
        rule_id="L1-009",
        layer="L1",
        severity="fatal",
        verdict="violation",
        message="明细合计与总价不一致",
        fix="复核总价口径",
        evidence=[{"doc_id": "bid.md", "page": 3, "text": "投标总价:¥9,000,000"}],
        dedup_key="k1",
    )  # noqa: E501
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-001", layer="L3", severity="minor", verdict="violation", message="页眉不一致", fix="替换页眉", evidence=[], dedup_key="k2")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-013", layer="L1", severity="fatal", verdict="unclear", message="响应偏离材料不足", fix="补充响应文件", evidence=[], dedup_key="k3", need_human=True)
    fp = await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-010", layer="L1", severity="fatal", verdict="violation", message="大写口径误报", fix="忽略", evidence=[], dedup_key="k4")
    await R.apply_false_positive(db, fp)

    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report", params={"format": "md"})
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    body = r.text
    first_line = body.splitlines()[0]
    assert "本报告为辅助提示,最终责任由投标主体承担" in first_line, "免责声明必须落报告首行"
    # 按 severity 四档分节
    for label in ("致命", "主要", "次要", "提示"):
        assert label in body
    # 每条:规则 ID / 证据 doc+page / 修复建议
    assert "L1-009" in body and "bid.md" in body and "p.3" in body and "复核总价口径" in body
    assert "L3-001" in body and "替换页眉" in body
    # need_human 条目存活并标注;人工误报剔除
    assert "L1-013" in body and "待人工" in body
    assert "大写口径误报" not in body
    # 可提交判定提示行(fatal violation=1 → 命中红线措辞照 ui-spec §3.5)
    assert "命中致命红线 1 项,建议整改后重新审查" in body
    # 复核耗时占位
    assert "复核耗时" in body


@pytest.mark.asyncio
async def test_report_md_submittable_hint_when_no_fatal_violation(client, db):
    """ui-spec §3.5 可提交判定:正式 fatal 违规=0 → 「未命中致命红线,可进入人工终审」
    (fatal need_human 条目不算命中红线,单列待人工)。"""
    t = await crud.create_task(db, owner_id="u1")
    await crud.set_status(db, t, "done")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L3-001", layer="L3", severity="minor", verdict="violation", message="页眉不一致", fix="替换页眉", evidence=[], dedup_key="k1")
    await crud.add_issue(db, task_id=t.id, owner_id="u1", rule_id="L1-013", layer="L1", severity="fatal", verdict="unclear", message="材料不足", fix="补响应", evidence=[], dedup_key="k2", need_human=True)
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report", params={"format": "md"})
    assert r.status_code == 200
    assert "未命中致命红线,可进入人工终审" in r.text
    assert "命中致命红线" not in r.text.split("未命中致命红线")[1], "零红线时不得再出现命中措辞"


@pytest.mark.asyncio
async def test_report_gate_rejects_non_done_task(client, db):
    """QUAL 修复(报告导出 Minor):服务侧状态门——仅 done 任务可导出报告。
    created/running/failed 等半程任务 409:基于空/半程 issue 集算出的可提交判定行
    (「未命中致命红线,可进入人工终审」)不得冒充审查结论流出到非 UI 消费方
    (UI WorkbenchView 已有同款 done 门,服务端补同口径防御)。"""
    t = await crud.create_task(db, owner_id="u1")  # 默认 created
    r = await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")
    assert r.status_code == 409 and "任务未完成" in r.json()["detail"], "created 半程任务不得导出报告"
    for status in ("running", "failed"):
        await crud.set_status(db, t, status)
        assert (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")).status_code == 409, f"status={status} 不得导出报告"
    await crud.set_status(db, t, "done")
    assert (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")).status_code == 200


@pytest.mark.asyncio
async def test_report_rejects_html_format_and_other_owner(client, db):
    """format 白名单:html 导出属 M4 不做(422,禁静默降级 md);他人任务 404(owner
    过滤同既有端点);format 缺省=md 可用(状态门:须 done 才可导)。"""
    t = await crud.create_task(db, owner_id="u1")
    other = await crud.create_task(db, owner_id="u2")
    assert (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report", params={"format": "html"})).status_code == 422
    assert (await client.get(f"/api/extensions/bid-review/tasks/{other.id}/report")).status_code == 404
    # 半程任务缺省 format 也先撞状态门(409),翻转 done 后缺省=md 可用
    assert (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")).status_code == 409
    await crud.set_status(db, t, "done")
    assert (await client.get(f"/api/extensions/bid-review/tasks/{t.id}/report")).status_code == 200


def test_mcp_tools_expose_no_confirm_gate():
    """Task 15 静态断言:MCP 工具键集与 handler 表均无 confirm/baseline_confirm 类工具——
    基线确认门仅工作台 UI,agent 不可代确认(设计文档 §4.3/§4.8)。"""
    from app.extensions.bid_review import mcp

    assert len(mcp.TOOLS) == 7
    assert all("confirm" not in name for name in mcp.TOOLS), "MCP 绝不暴露确认门"
    assert all("confirm" not in name for name in mcp._HANDLERS), "handler 表同样不得有 confirm 类"
