"""MCP 暴露面：``invoke_action`` + ``review_entity``（计划 Task 8）。

设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §4。

本文件覆盖**暴露面自己**的东西：工具声明（名字/必填/枚举）、动作 id 与 registry 的一致性、
分派与两条 handler 的接线（decision→action_id 映射、透传的 source/scope/投影钩子）、
以及 ``_ok`` 对非 JSON 原生类型的容忍（``now: true`` 列的 ``after`` 是 datetime）。

真库路径（``ScopeDenied`` 404 / 前置条件 409 / 审计行 / 懒建）由
``tests/test_actions_executor.py`` 覆盖，本文件一律不碰库——MCP 这一层要做对的
是"接线"（范围/身份/来源三处），SQL 语义不是它的事。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.ontology import mcp as ontomcp
from app.ontology.mcp import TOOLS
from app.ontology.scope import FilterRule


def _tool(name):
    return next((t for t in TOOLS if t.name == name), None)


def test_invoke_action_tool_registered():
    t = _tool("invoke_action")
    assert t is not None
    assert set(t.inputSchema["required"]) == {"action_id", "pk"}


def test_review_entity_tool_registered():
    t = _tool("review_entity")
    assert t is not None
    assert set(t.inputSchema["required"]) == {"pk", "decision"}
    assert set(t.inputSchema["properties"]["decision"]["enum"]) == {"confirm", "reject"}


def test_action_ids_match_registry():
    """工具暴露的动作 id 必须与 registry 声明一致（防手写清单漂移）。"""
    from app.ontology.registry import get_registry

    declared = set(get_registry().actions)
    assert "review_entity.confirm" in declared
    assert "review_entity.reject" in declared


# ── describe_ontology 附动作清单（计划 Step 5）────────────────────────────


@pytest.mark.asyncio
async def test_describe_lists_actions_without_handwritten_ids():
    """清单必须**来自 registry**（断言 `== registry.actions`，不是手写那两个 id）。

    计划 Step 5 改的是 describe 的返回体，而计划给的 3 条用例一条都没碰它——删掉那一段
    全绿。变异检验（实测）：删掉 payload 里的 ``"actions"`` 键 → 本用例红。
    """
    from app.ontology.registry import get_registry

    declared = set(get_registry().actions)
    for args in ({}, {"full": True}):  # 两个分支都要带：full=true 是在要更多细节，不是要更少的写入口
        payload = json.loads((await ontomcp._describe(args))[0].text)
        assert {a["id"] for a in payload["actions"]} == declared
    one = next(a for a in json.loads((await ontomcp._describe({}))[0].text)["actions"] if a["id"] == "review_entity.confirm")
    # agent 靠这几个字段决定怎么调：目标对象、要什么权限、前置条件（不满足会 409）
    assert one["target"] == "graph_entity"
    assert one["required_permissions"] == ["ontology:action:review"]
    assert one["preconditions"] == [{"field": "status", "op": "eq", "value": "pending_review"}]
    # StateChange.model_dump() 带 now 默认值（False = 由动作给值，不是 DB NOW()）——
    # 这个字段不是噪音：now=true 的行会往 after 里塞 datetime（见本文件末尾那条用例）
    assert one["postconditions"] == [{"field": "status", "set": "active", "now": False}]


# ── 分派与 handler 接线 ──────────────────────────────────────────────────


def _stub_run_action_for_mcp(monkeypatch, result: dict) -> list[tuple[str, str, str]]:
    """把执行体换成记录器（模块属性替换——handler 是**逐调用**导入它的）。"""
    seen: list[tuple[str, str, str]] = []

    async def _fake(action_id: str, pk: str, source: str) -> dict:
        seen.append((action_id, pk, source))
        return result

    monkeypatch.setattr("app.ontology.actions.executor.run_action_for_mcp", _fake)
    return seen


@pytest.mark.asyncio
async def test_review_entity_forwards_mapped_action_id(monkeypatch):
    """``decision`` → action_id 的映射必须两个方向都对，且未知 decision **不**触达执行体。

    走 ``call_tool``（真实分派路径）而不是直调 ``_review_entity``：这样"handler 没注册进
    handlers 字典"也会红。变异检验（实测）：把映射表两个值对调 → 本用例红；删掉
    ``action_id is None`` 那一支（改成默认 confirm）→ 未知 decision 那次调用也进 seen → 红。
    """
    seen = _stub_run_action_for_mcp(monkeypatch, {"action_id": "x"})
    pk = str(uuid.uuid4())

    for decision in ("confirm", "reject"):
        out = await ontomcp.call_tool("review_entity", {"pk": pk, "decision": decision})
        assert json.loads(out[0].text)["success"] is True

    assert [s[0] for s in seen] == ["review_entity.confirm", "review_entity.reject"]
    assert [s[1] for s in seen] == [pk, pk]
    assert [s[2] for s in seen] == ["mcp", "mcp"], "审计要能把 MCP 通道与 api 分开"

    out = await ontomcp.call_tool("review_entity", {"pk": pk, "decision": "approve"})
    payload = json.loads(out[0].text)
    assert payload["success"] is False and "decision" in payload["error"]
    assert len(seen) == 2, "未知 decision 必须被拒，绝不能猜一个方向去写"


@pytest.mark.asyncio
async def test_invoke_action_result_survives_datetime(monkeypatch):
    """``_ok` 必须能序列化 ``datetime``——Task 5 交接的前向风险（``now: true`` 列）。

    ``after`` 自 Task 5 起取自 ``UPDATE ... RETURNING`` 的**真值**，故声明 ``{field: updated_at,
    now: true}`` 的列在返回体里是 ``datetime`` 对象。当前 registry 没有这种声明（不可达），
    但声明是热加载的——``json.dumps`` 缺 ``default=`` 会抛 TypeError，而它**会被 call_tool
    的兜底 catch 成一条 success:false**，症状是"审核莫名其妙失败"，不是崩溃。

    变异检验（实测）：把 ``mcp._ok`` 的 ``default=str`` 删掉 → 本用例红（success 变 False、
    error 是 "TypeError: Object of type datetime is not JSON serializable"）。
    """
    stamp = datetime(2026, 9, 23, 4, 5, 6, tzinfo=UTC)
    _stub_run_action_for_mcp(monkeypatch, {"action_id": "review_entity.confirm", "after": {"updated_at": stamp}})

    out = await ontomcp.call_tool("invoke_action", {"action_id": "review_entity.confirm", "pk": str(uuid.uuid4())})
    payload = json.loads(out[0].text)
    assert payload["success"] is True
    assert payload["after"]["updated_at"] == str(stamp)


# ── run_action_for_mcp 的接线（MCP 通道没有 REST 那两层，参数写错无人拦截）────


@pytest.mark.asyncio
async def test_run_action_for_mcp_wires_identity_scope_source_and_projector(monkeypatch):
    """一次调用钉住三处只在 MCP 通道存在的接线 + 投影钩子。

    为什么值得单独钉：REST 侧写错 range/source 会被上层（``_authz_for_action``）拦下或
    被其它用例发现；MCP 侧**没有那一层**——``scope_rule`` 写成 ``none_allow`` 是整条通道
    静默全拒（每个动作 404「目标不存在或不在可见范围内」），``source`` 写成 ``api`` 是审计
    把 MCP 写记成人工写（追溯断掉），投影钩子写成 async 是"静默算作成功"。
    三者都不会被任何其它用例发现。

    变异检验（实测）：``source`` 改成 ``"api"`` → 红；``actor_role`` 改成 ``None`` → 红；
    ``scope_rule`` 换成 ``FilterRule(operator="none_allow")`` → 红；``project`` 换成
    ``async def`` → 红（调用返回协程、refreshes 为空）。
    """
    captured: dict = {}
    refreshes: list[int] = []

    async def _fake_core(action_id, params, **kw):  # noqa: ANN001, ANN003
        captured.update(kw, action_id=action_id, params=params)
        return {"action_id": action_id}

    monkeypatch.setattr("app.ontology.actions.executor.invoke_action_core", _fake_core)
    monkeypatch.setattr("app.ontology.actions.executor.get_kernel", lambda: SimpleNamespace(refresh=lambda: refreshes.append(1)))

    pk = str(uuid.uuid4())
    out = await ontomcp.call_tool("invoke_action", {"action_id": "review_entity.confirm", "pk": pk})
    assert json.loads(out[0].text)["success"] is True

    assert captured["action_id"] == "review_entity.confirm"
    assert captured["params"] == {}, "MCP 工具没有 params 入口，传空而不是 None"
    assert captured["target_pk"] == uuid.UUID(pk)
    assert captured["actor_id"] == uuid.UUID(int=0), "MCP 无调用者身份——用零 UUID 而不是假 id"
    assert captured["actor_role"] == "mcp"
    assert captured["source"] == "mcp"
    assert captured["scope_rule"] == FilterRule(operator="allow_all")

    # 投影钩子：按 executor 的用法**同步**调用（传 action_id, pk），必须真的 refresh
    assert captured["project"]("review_entity.confirm", uuid.UUID(pk)) is None
    assert refreshes == [1]
