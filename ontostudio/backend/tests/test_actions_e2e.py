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
   动作路径的 ``project`` 是 ``routers._project_incrementally`` → ``get_kernel().refresh()``，
   而 ``refresh()`` **不读 dg_* 行**（``kernel/service.py`` 只做 schema 重编 + 闭包 + 规则
   重跑）。即 spec §2 步骤 5「受影响行增量重投影进内核图」在当前实现下**是空转**：
   接口回 ``projected: true``，图里却没有这一行。该缺口由 ``test_03`` 固定（**修复后它会
   变红 → 删掉它**），① 的 SHACL 半边因此改走**真实投影桥**（``kernel/loader.py`` 的
   ``load_doc_graph_rows``，与 ``POST /formal/load`` 同一条），只装本行、不受活库其余数据
   影响。
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.connectors import _ext_url
from app.ontology.kernel.service import get_kernel

pytestmark = pytest.mark.integration


async def _seed(status="pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            r = await conn.execute(
                text("""INSERT INTO dg_entities (domain,etype,canonical_name,norm_name,attrs,confidence,status)
                        VALUES ('doc_graph','mine','E2E', :n, '{}'::jsonb, 0.9, :s) RETURNING id"""),
                {"n": f"E2E-{uuid.uuid4().hex[:8]}", "s": status},
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
    assert result["after"] == {"status": "active"}
    assert result["errors"] == []

    # DB 侧：状态真的落库了（与接口回显互为印证）
    row = await _fetch_entity(pk)
    assert row["status"] == "active", row

    # 文档串里"审计有行"是 ① 的一半，计划给的代码没有断言它（Task 10 补上）
    audits = await _audit_rows(pk)
    assert len(audits) == 1, audits
    assert audits[0]["action_id"] == "review_entity.confirm" and audits[0]["source"] == "mcp"
    assert audits[0]["before"] == {"status": "pending_review"} and audits[0]["after"] == {"status": "active"}

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


@pytest.mark.asyncio
async def test_03_action_projection_does_not_reach_the_graph_KNOWN_GAP():
    """**已知缺口固定桩**（Task 10 自审，2026-09-24 实测定案）。

    spec §2 步骤 5 写「提交后：受影响行**增量重投影**进内核图」，而本仓的 ``project`` 是
    ``routers._project_incrementally`` → ``get_kernel().refresh()``；``refresh()`` 只做
    schema 重编 + 闭包 + 规则重跑，**从不读 dg_* 行**。于是一次 confirm 之后：DB 行已
    ``active``、接口回 ``projected: true``——而断言图里**没有这一行**。

    为什么把"现状"钉成用例：这是唯一能让下一个人*当场*看到缺口的东西（本计划的取向是
    「如实标注，不假装已增量」——见 ``routers._project_incrementally`` 的 docstring，它
    只承认"非增量"，没承认"根本没投影"）。**修好 spec §2 步骤 5 的那次改动会让本用例
    变红——届时删掉本用例即可**，它存在的全部意义就是"失效即报"。
    """
    from app.ontology.kernel.store import ASSERTED_GRAPH

    pk = await _seed()
    kernel = get_kernel()
    kernel.refresh()
    before = kernel.store.dump_turtle(ASSERTED_GRAPH)
    assert str(pk) not in before

    from app.ontology.actions.executor import run_action_for_mcp

    result = await run_action_for_mcp("review_entity.confirm", str(pk), "mcp")
    assert result["projected"] is True and result["errors"] == []

    after = kernel.store.dump_turtle(ASSERTED_GRAPH)
    assert str(pk) not in after, "投影已实装？→ 删掉本用例（它钉的是缺口存在时的行为）"

    # 对照（防空断言假绿）：同一张断言图**装得进**这一行——经真实投影桥装一次，
    # 必须看得见。没有这一步，"不在图里" 与 "图根本装不进/量具坏了" 无从区分。
    from app.ontology.kernel.loader import load_doc_graph_rows
    from app.ontology.registry import get_registry

    load_doc_graph_rows(kernel.store, get_registry(), entity_rows=[await _fetch_entity(pk)], relation_rows=[], mention_rows=[])
    assert str(pk) in kernel.store.dump_turtle(ASSERTED_GRAPH), "对照组失效：量具或投影桥坏了，上面那条断言无判别力"


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
