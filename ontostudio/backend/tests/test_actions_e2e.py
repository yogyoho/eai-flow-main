# ontostudio/backend/tests/test_actions_e2e.py
"""spec §7 端到端验收（Task 10）。需要 extensions 库可达（真库集成测试）。

判据以端到端为主：真库 + 真执行管线（``invoke_action_core`` / ``run_action_for_mcp``）
+ 真 SHACL 校验。本文件只覆盖 spec §7 的 ① ② ④ ⑤；③（无 ``ontology:action:review``
→ 403）与 ⑥（lint 真实 registry 全绿）分别由 Task 6 与 Task 9 的用例覆盖（见报告）。

**⚠️ 本文件对计划给的代码有两处有意加强，理由都写在被测断言旁边**（Task 10 自审，
2026-09-24；两处都先跑过变异确认判别力，别当装饰）：

1. ① 的"SHACL 无违规"半边**不能**由计划那行 ``all(c.passed for c in run_conformance(...))``
   证明——``kernel/conformance._c3_shacl_report_shape`` 只校验报告的**形态**（每条违规
   五字段齐备），``conforms=False`` 时它照样 ``passed=True``。实测（2026-09-24）：往断言图
   塞一个 ``status='bogus_status'`` 的实体后 ``run_shacl().conforms is False``、1 条违规，
   而计划那行断言仍为**真**。故这里直接断言 ``run_shacl(...).conforms``，且断言对象是
   **装了这一行的图**（计划那行对 ``get_kernel().store`` 求值，那是另一个问题，见 2）。
2. 计划那行的 ``run_conformance(get_kernel().store, ...)`` 在本进程里是**空图**上求值——
   动作路径的 ``project`` 原是 ``routers._project_incrementally`` → ``get_kernel().refresh()``，
   而 ``refresh()`` **不读 dg_* 行**（``kernel/service.py`` 只做 schema 重编 + 闭包 + 规则
   重跑）。即 spec §2 步骤 5「受影响行增量重投影进内核图」在当時实现下**是空转**：
   接口回 ``projected: true``，图里却没有这一行。该缺口曾由 ``test_03`` 固定（KNOWN_GAP 桩），
   **2026-09-27 人审闭环切片已实装修复**（``actions/projection.py::project_row``，双通道共享），
   原 KNOWN_GAP 用例按预案删除；现在的 ``test_03`` 钉的是修复后的行为——确认投影必须把
   **曾装载为 pending_review 的行**翻转为 active（翻转场景，全新插入抓不住的静默失败）。
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.connectors import _ext_url
from app.ontology.kernel.service import get_kernel

pytestmark = pytest.mark.integration


async def _seed(status="pending_review", etype: str = "mine") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(
                text("""INSERT INTO dg_entities (domain,etype,canonical_name,norm_name,attrs,confidence,status)
                        VALUES ('doc_graph',:et,'E2E', :n, '{}'::jsonb, 0.9, :s) RETURNING id"""),
                {"n": f"E2E-{uuid.uuid4().hex[:8]}", "s": status, "et": etype},
            )
            return r.scalar_one()
    finally:
        await engine.dispose()


async def _fetch_entity(pk: uuid.UUID) -> dict:
    """把写完的行读回来——断言走 DB（唯一真相源），不靠接口回显。"""
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text("SELECT * FROM dg_entities WHERE id = :id"), {"id": pk})
            return dict(r.mappings().one())
    finally:
        await engine.dispose()


async def _audit_rows(pk: uuid.UUID) -> list[dict]:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(
                text("SELECT action_id, source, before, after FROM dg_action_audit WHERE target_pk = :id"),
                {"id": pk},
            )
            return [dict(row) for row in r.mappings().all()]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_01_confirm_then_shacl_clean():
    """① pending_review → confirm → active，审计有行，重投影后 SHACL 无违规。

    ``run_action_for_mcp`` 是 MCP 侧整条链路（解析 → 范围 → FOR UPDATE → 前置 → UPDATE
    → 审计 → 提交后调 ``project``），与 REST 共用 ``invoke_action_core``。
    """
    pk = await _seed()
    get_kernel().refresh()  # 投影前

    from app.ontology.actions.executor import run_action_for_mcp

    result = await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    # 置信升格语义（2026-09-29 registry 变更）：confirm = status→active + confidence→0.7
    # （推理门 min_confidence=0.7 只认 confidence）——两字段都在才算声明落地
    assert result["after"] == {"status": "active", "confidence": Decimal("0.7")}
    assert result["errors"] == []

    # DB 侧：状态真的落库了（与接口回显互为印证）
    row = await _fetch_entity(pk)
    assert row["status"] == "active", row

    # 文档串里"审计有行"是 ① 的一半，计划给的代码没有断言它（Task 10 补上）
    audits = await _audit_rows(pk)
    assert len(audits) == 1, audits
    assert audits[0]["action_id"] == "review_entity.confirm" and audits[0]["source"] == "mcp"
    # 审计 jsonb 经 default=str 序列化 Decimal（保留 numeric 标度）："0.900" / "0.700"
    assert audits[0]["before"] == {"status": "pending_review", "confidence": "0.900"}
    assert audits[0]["after"] == {"status": "active", "confidence": "0.700"}

    # 国标五项（计划原有的那行，保持）
    from app.ontology.kernel.conformance import run_conformance
    from app.ontology.registry import get_registry

    checks = run_conformance(get_kernel().store, get_registry())
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]

    # SHACL 半边（见模块 docstring 第 1、2 条）：把**这一行**经真实投影桥装进图再校验。
    from app.ontology.kernel.loader import load_doc_graph_rows
    from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
    from app.ontology.kernel.validate import run_shacl

    registry = get_registry()
    store = OxStore()  # 隔离：只装本行，活库其余数据（含历史脏数据）不参与判定
    stats = load_doc_graph_rows(store, registry, entity_rows=[row], relation_rows=[], mention_rows=[])
    assert stats.entities == 1 and stats.skipped_entities == [], stats
    ttl = store.dump_turtle(ASSERTED_GRAPH)
    assert str(pk) in ttl, ttl[:400]
    assert '"active"' in ttl, ttl[:400]
    report = run_shacl(store, registry)
    assert report.conforms is True, report.violations


@pytest.mark.asyncio
async def test_02_precondition_violation_is_409():
    pk = await _seed(status="active")
    from app.ontology.actions.executor import ActionError, run_action_for_mcp

    with pytest.raises(ActionError) as e:
        await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert e.value.status_code == 409
    assert "前置条件不满足" in e.value.detail  # 中文提示（spec §7-②）
    # 被拒的动作不落审计行、不改状态
    assert (await _fetch_entity(pk))["status"] == "active"
    assert await _audit_rows(pk) == []


def _entity_iri(pk: uuid.UUID) -> str:
    """doc_graph 域词表下该行的实例 IRI（与 loader/upsert 同一构造）。"""
    from app.ontology.kernel.compile import collect_vocabularies
    from app.ontology.registry import get_registry

    return collect_vocabularies(get_registry())["doc_graph"].scheme.instance_iri(pk)


async def _load_into_kernel(pk: uuid.UUID) -> None:
    """把该行经真实投影桥装进共享 kernel（模拟「曾全量装载」的前置状态）。"""
    from app.ontology.kernel.loader import load_doc_graph_rows
    from app.ontology.registry import get_registry

    load_doc_graph_rows(get_kernel().store, get_registry(), entity_rows=[await _fetch_entity(pk)], relation_rows=[], mention_rows=[])


def _graph_status(pk: uuid.UUID) -> str | None:
    """断言图中该实体的 status 字面量（无该实体/无状态三元组 → None）。"""
    from app.ontology.kernel.graph_ops import _select
    from app.ontology.kernel.vocab import P_STATUS

    rows = get_kernel().store.query(_select("s", f"<{_entity_iri(pk)}> <{P_STATUS}> ?s"))
    if not rows:
        return None
    value = rows[0]["s"]
    return getattr(value, "value", str(value))


@pytest.mark.asyncio
async def test_03_confirm_projection_flips_graph_status():
    """③(新) 确认投影真实落图 + **翻转场景**（切片核心判据，取代已删除的 KNOWN_GAP 桩）。

    前置状态模拟「行曾被全量装载为 pending_review」——修复前 ``upsert_entity`` 的
    「缺席才写」会让确认后图里**仍是 pending_review**（静默失败，全新插入的用例
    抓不住，见设计稿成功标准 1）。``force_status`` 强转必须把断言图状态翻成 active。
    走 ``run_action_for_mcp`` = MCP 通道（与 REST 共用 ``invoke_action_core`` +
    ``projection.project_row``，同时钉住 MCP 侧不再是假 lambda——设计稿成功标准 5）。
    """
    pk = await _seed()
    await _load_into_kernel(pk)
    assert _graph_status(pk) == "pending_review"  # 前置状态确已在图（对照：量具有效）

    from app.ontology.actions.executor import run_action_for_mcp

    result = await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert result["projected"] is True and result["errors"] == [], result
    assert _graph_status(pk) == "active", "KNOWN_GAP 场景反转失败：确认后图面状态未翻转"
    assert (await _fetch_entity(pk))["status"] == "active"


@pytest.mark.asyncio
async def test_05_reject_projection_marks_rejected_in_graph():
    """⑤ 驳回投影（eng-review T2A 语义）：状态翻转为 rejected、**实体保留在图**（非移除）。

    断言图 = DB 全行忠实投影：驳回不删实体/关系/提及（悬挂引用 + mention 永不删），
    只把状态三元组翻转为 rejected。
    """
    pk = await _seed()
    await _load_into_kernel(pk)

    from app.ontology.actions.executor import run_action_for_mcp

    result = await run_action_for_mcp("review_entity.reject", str(pk), "mcp")
    assert result["projected"] is True and result["errors"] == [], result
    assert _graph_status(pk) == "rejected", "驳回后图内状态应为 rejected（非移除）"
    assert (await _fetch_entity(pk))["status"] == "rejected"


async def _purge(pk: uuid.UUID) -> None:
    """清掉本用例种下的行（含审计）——bogus etype 会污染共享真库上「全行可装载」的集成判据。"""
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM dg_action_audit WHERE target_pk = :id"), {"id": pk})
            await conn.execute(text("DELETE FROM dg_entities WHERE id = :id"), {"id": pk})
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_06_projection_degraded_on_unregistered_etype():
    """⑥ 真实路径 degraded 形状：etype 未在 registry 声明 → ``projected:false`` + errors、DB 不回滚。

    修复前的假信号在本场景是 ``projected:true``（``refresh()`` 恒成功、从不看行）——
    本用例钉住假信号根除（设计稿成功标准 3）。degraded 是自愈的：etype 补进 registry
    后重跑全量装载（force_status 对账）即入图。
    """
    pk = await _seed(etype="bogus_etype")
    try:
        from app.ontology.actions.executor import run_action_for_mcp

        result = await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
        assert result["projected"] is False and result["errors"], result
        assert "未投影" in result["errors"][0]
        assert (await _fetch_entity(pk))["status"] == "active"  # 投影失败不回滚业务状态
    finally:
        await _purge(pk)  # bogus etype 不留在共享真库（否则 loader 集成判据「全行可装载」被跳过数打破）


@pytest.mark.asyncio
async def test_04_projection_failure_recorded_not_rolled_back():
    """④ 投影失败：业务状态已提交、errors 有记录。"""
    pk = await _seed()
    from app.ontology.actions.executor import invoke_action_core
    from app.ontology.scope import FilterRule

    def boom(*a, **k):
        raise RuntimeError("proj boom")

    r = await invoke_action_core(
        "review_entity.confirm",
        {},
        target_pk=pk,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        source="api",
        scope_rule=FilterRule(operator="allow_all"),
        project=boom,
    )
    assert r["projected"] is False and r["errors"]
    assert "proj boom" in r["errors"][0]
    # 关键语义：不回滚——状态已提交、审计已落行（可据此重放投影）
    assert (await _fetch_entity(pk))["status"] == "active"
    assert len(await _audit_rows(pk)) == 1


@pytest.mark.asyncio
async def test_05_lint_reports_unbound_scope_field():
    """⑤ lint 对"模板字段无绑定"报错（用一个构造出的坏绑定）。"""
    from app.ontology.schemas import DomainFile

    with pytest.raises(ValueError, match="unknown scope binding"):
        DomainFile.model_validate(
            {
                "object_types": [
                    {
                        "api_name": "x",
                        "display_name": "x",
                        "description": "d",
                        "domain": "d",
                        "access": {"path": "postgres_ext", "table": "t"},
                        "pk": {"column": "id", "api_name": "id", "type": "uuid"},
                        "properties": [{"name": "id", "api_name": "id", "type": "uuid", "description": "p"}],
                        "scope_bindings": {"user_id": "missing_col"},
                    }
                ],
            }
        )
