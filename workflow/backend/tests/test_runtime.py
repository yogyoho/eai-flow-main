"""Runtime engine tests: gateways, reject, countersign, revoke and delegation."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import session_scope
from app.models import FlowHisTask, FlowInstance
from app.utils import from_json, to_json

from .conftest import headers

PREFIX = "/api/workflow"

ZHANG = headers("u1001", "Zhang San", "manager", "d01")
LI = headers("u1002", "Li Si", "director", "d02")
WANG = headers("u1003", "Wang Wu", "finance", "d03")
ZHAO = headers("u1004", "Zhao Liu", "employee", "d01")


def _start(client: TestClient, flow_code: str, user: dict = ZHAO, **variables) -> dict:
    response = client.post(
        f"{PREFIX}/instances",
        json={
            "flow_code": flow_code,
            "business_id": f"biz-{uuid4().hex[:8]}",
            "variables": variables,
        },
        headers=user,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _task_for(client: TestClient, instance_id: int, user: dict) -> dict:
    items = client.get(f"{PREFIX}/tasks?instanceId={instance_id}", headers=user).json()["items"]
    assert items, f"no task for {user['X-User-Id']}"
    return items[0]


def _approve(client: TestClient, task_id: int, user: dict, message: str = "同意") -> dict:
    response = client.post(f"{PREFIX}/tasks/{task_id}/approve", json={"message": message}, headers=user)
    assert response.status_code == 200, response.text
    return response.json()


def _chart_skips(chart: dict, skip_type: str | None = None) -> list[dict]:
    skips = [skip for node in chart["nodeList"] for skip in node.get("skipList") or []]
    if skip_type is None:
        return skips
    return [skip for skip in skips if skip.get("skipType") == skip_type]


def _edge_statuses(
    chart: dict,
    *,
    now_node: str,
    next_node: str,
    skip_type: str,
) -> list[int]:
    return [
        int(skip["status"])
        for skip in _chart_skips(chart, skip_type)
        if skip.get("nowNodeCode") == now_node and skip.get("nextNodeCode") == next_node
    ]


def _reset_reject_edge_status(instance_id: int) -> None:
    """Simulate a snapshot frozen before reject transitions were marked traversed."""

    async def reset() -> None:
        async with session_scope() as session:
            row = await session.get(FlowInstance, instance_id)
            assert row is not None and row.def_json
            snapshot = from_json(row.def_json, {})
            reject_nodes = set(
                (
                    await session.execute(
                        select(FlowHisTask.node_code).where(
                            FlowHisTask.instance_id == instance_id,
                            FlowHisTask.del_flag == "0",
                            FlowHisTask.skip_type == "REJECT",
                        )
                    )
                ).scalars()
            )
            for node in snapshot.get("nodeList") or []:
                if node.get("nodeCode") in reject_nodes:
                    node["status"] = 0
                for skip in node.get("skipList") or []:
                    if skip.get("skipType") == "REJECT":
                        skip["status"] = 0
            row.def_json = to_json(snapshot)

    asyncio.run(reset())


def _stored_reject_statuses(instance_id: int) -> list[int]:
    async def read() -> list[int]:
        async with session_scope() as session:
            row = await session.get(FlowInstance, instance_id)
            assert row is not None and row.def_json
            snapshot = from_json(row.def_json, {})
            return [
                skip["status"]
                for node in snapshot.get("nodeList") or []
                for skip in node.get("skipList") or []
                if skip.get("skipType") == "REJECT"
            ]

    return asyncio.run(read())


def test_leave_happy_path(client: TestClient) -> None:
    instance = _start(client, "leave", days=2, reason="回家")
    assert instance["flow_status"] == "0"
    assert instance["node_code"] == "dept"

    task = _task_for(client, instance["id"], ZHANG)
    after_first = _approve(client, task["id"], ZHANG)
    assert after_first["flow_status"] == "1"
    assert after_first["node_code"] == "director"

    task = _task_for(client, instance["id"], LI)
    done = _approve(client, task["id"], LI, "准假")
    assert done["flow_status"] == "8"
    assert done["node_code"] == "end"

    detail = client.get(f"{PREFIX}/instances/{instance['id']}", headers=ZHAO).json()
    assert detail["tasks"] == []
    assert [item["flow_status"] for item in detail["history"]][:3] == ["8", "2", "0"]
    statuses = {node["nodeCode"]: node["status"] for node in detail["chart"]["nodeList"]}
    assert statuses == {"start": 2, "dept": 2, "director": 2, "end": 2}


def test_reject_returns_to_previous_node_and_recreates_task(client: TestClient) -> None:
    instance = _start(client, "leave", days=1)
    _approve(client, _task_for(client, instance["id"], ZHANG)["id"], ZHANG)

    before = client.get(f"{PREFIX}/instances/{instance['id']}").json()
    assert {skip["status"] for skip in _chart_skips(before["chart"], "REJECT")} == {0}

    task = _task_for(client, instance["id"], LI)
    response = client.post(f"{PREFIX}/tasks/{task['id']}/reject", json={"message": "材料不全"}, headers=LI)
    assert response.status_code == 200, response.text
    rejected = response.json()
    assert rejected["flow_status"] == "9"
    assert rejected["node_code"] == "dept"

    # The department manager receives the task again, the director has nothing.
    assert _task_for(client, instance["id"], ZHANG)
    assert client.get(f"{PREFIX}/tasks?instanceId={instance['id']}", headers=LI).json()["items"] == []

    detail = client.get(f"{PREFIX}/instances/{instance['id']}").json()
    assert detail["history"][0]["skip_type"] == "REJECT"
    statuses = {node["nodeCode"]: node["status"] for node in detail["chart"]["nodeList"]}
    # The director processed the rejection here, so the node renders as done;
    # the returned-to department node is the active one.
    assert statuses["director"] == 2
    assert statuses["dept"] == 1
    reject_edges = _chart_skips(detail["chart"], "REJECT")
    assert [skip["status"] for skip in reject_edges] == [2]


def test_chart_restores_reject_edge_from_history(client: TestClient) -> None:
    instance = _start(client, "leave", days=1)
    _approve(client, _task_for(client, instance["id"], ZHANG)["id"], ZHANG)
    task = _task_for(client, instance["id"], LI)
    response = client.post(
        f"{PREFIX}/tasks/{task['id']}/reject",
        json={"message": "材料不全"},
        headers=LI,
    )
    assert response.status_code == 200, response.text

    # Rewind the frozen snapshot to the old behaviour: the traversed reject
    # edge AND the acting node were stored as not done.
    _reset_reject_edge_status(instance["id"])
    assert _stored_reject_statuses(instance["id"]) == [0]

    # History is authoritative and repairs the edge and the acting node when
    # the chart is built.
    restored = client.get(f"{PREFIX}/instances/{instance['id']}").json()
    assert [skip["status"] for skip in _chart_skips(restored["chart"], "REJECT")] == [2]
    restored_statuses = {node["nodeCode"]: node["status"] for node in restored["chart"]["nodeList"]}
    assert restored_statuses["director"] == 2
    # The returned-to node is active and must not be downgraded by the restore.
    assert restored_statuses["dept"] == 1


def test_return_to_applicant_and_resubmit(client: TestClient) -> None:
    code = f"return_flow_{uuid4().hex[:8]}"
    payload = {
        "flowCode": code,
        "flowName": "退回申请人测试",
        "modelValue": "CLASSICS",
        "category": "测试",
        "formCustom": "N",
        "nodeList": [
            {
                "nodeType": 0,
                "nodeCode": "start",
                "nodeName": "发起",
                "coordinate": "100,200|100,200",
                "skipList": [
                    {
                        "nowNodeCode": "start",
                        "nextNodeCode": "step_1",
                        "skipName": "提交",
                        "skipType": "PASS",
                        "coordinate": "128,200;212,200|170,180",
                    }
                ],
            },
            {
                "nodeType": 1,
                "nodeCode": "step_1",
                "nodeName": "区域经理审批",
                "permissionFlag": "u1001",
                "nodeRatio": "0",
                "coordinate": "300,200|300,200",
                "skipList": [
                    {
                        "nowNodeCode": "step_1",
                        "nextNodeCode": "end",
                        "skipName": "通过",
                        "skipType": "PASS",
                        "coordinate": "388,200;472,200|430,180",
                    },
                    {
                        "nowNodeCode": "step_1",
                        "nextNodeCode": "end",
                        "skipName": "驳回",
                        "skipType": "REJECT",
                        "coordinate": "300,226;300,320;500,320;500,228|400,336",
                    },
                    {
                        "nowNodeCode": "step_1",
                        "nextNodeCode": "start",
                        "skipName": "退回申请人",
                        "skipType": "REJECT",
                        "coordinate": "300,174;300,100;100,100;100,172|200,82",
                    },
                ],
            },
            {
                "nodeType": 2,
                "nodeCode": "end",
                "nodeName": "结束",
                "coordinate": "500,200|500,200",
            },
        ],
    }
    saved = client.post(f"{PREFIX}/designer/save-json", json=payload, headers=headers())
    assert saved.status_code == 200, saved.text
    definition_id = saved.json()["data"]["id"]
    published = client.post(f"{PREFIX}/definitions/{definition_id}/publish", headers=headers())
    assert published.status_code == 200, published.text

    instance = _start(client, code, reason="原始资料")
    assert instance["node_code"] == "step_1"
    manager_task = _task_for(client, instance["id"], ZHANG)

    returned = client.post(
        f"{PREFIX}/tasks/{manager_task['id']}/return-to-applicant",
        json={"message": "资料不完整"},
        headers=ZHANG,
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["flow_status"] == "9"
    assert returned.json()["node_code"] == "start"
    assert client.get(f"{PREFIX}/tasks?instanceId={instance['id']}", headers=ZHANG).json()["items"] == []

    applicant_task = _task_for(client, instance["id"], ZHAO)
    assert applicant_task["node_code"] == "start"
    assert applicant_task["flow_status"] == "0"
    assert applicant_task["assignees"] == ["u1004"]

    detail = client.get(f"{PREFIX}/instances/{instance['id']}").json()
    assert detail["history"][0]["skip_type"] == "REJECT"
    assert detail["history"][0]["target_node_code"] == "start"
    statuses = {node["nodeCode"]: node["status"] for node in detail["chart"]["nodeList"]}
    assert statuses["start"] == 1
    # The manager processed the return here, so step_1 stays visibly done.
    assert statuses["step_1"] == 2
    by_target = {skip["nextNodeCode"]: skip["status"] for skip in _chart_skips(detail["chart"], "REJECT")}
    assert by_target == {"start": 2, "end": 0}

    resubmitted = _approve(client, applicant_task["id"], ZHAO, "已补充资料")
    assert resubmitted["flow_status"] == "1"
    assert resubmitted["node_code"] == "step_1"
    resubmitted_task = _task_for(client, instance["id"], ZHANG)
    assert resubmitted_task["node_code"] == "step_1"

    final = client.post(
        f"{PREFIX}/tasks/{resubmitted_task['id']}/reject",
        json={"message": "仍不完整", "node_code": "end"},
        headers=ZHANG,
    )
    assert final.status_code == 200, final.text
    assert final.json()["flow_status"] == "8"
    assert final.json()["node_code"] == "end"

    final_detail = client.get(f"{PREFIX}/instances/{instance['id']}").json()
    assert _edge_statuses(
        final_detail["chart"],
        now_node="step_1",
        next_node="end",
        skip_type="PASS",
    ) == [0]
    assert _edge_statuses(
        final_detail["chart"],
        now_node="step_1",
        next_node="end",
        skip_type="REJECT",
    ) == [2]
    # Terminal rejection: the acting node stays visibly done.
    final_statuses = {node["nodeCode"]: node["status"] for node in final_detail["chart"]["nodeList"]}
    assert final_statuses == {"start": 2, "step_1": 2, "end": 2}

    approved_instance = _start(client, code, reason="补充后通过")
    approved_task = _task_for(client, approved_instance["id"], ZHANG)
    approved = _approve(client, approved_task["id"], ZHANG, "资料完整")
    assert approved["flow_status"] == "8"
    approved_detail = client.get(f"{PREFIX}/instances/{approved_instance['id']}").json()
    assert _edge_statuses(
        approved_detail["chart"],
        now_node="step_1",
        next_node="end",
        skip_type="PASS",
    ) == [2]
    assert _edge_statuses(
        approved_detail["chart"],
        now_node="step_1",
        next_node="end",
        skip_type="REJECT",
    ) == [0]


def test_serial_gateway_routes_by_condition(client: TestClient) -> None:
    small = _start(client, "expense", amount=300, category="办公")
    assert small["node_code"] == "finance"
    large = _start(client, "expense", amount=9000, category="差旅")
    assert large["node_code"] == "director_expense"

    # Large amount: director -> finance -> end.
    _approve(client, _task_for(client, large["id"], LI)["id"], LI)
    task = _task_for(client, large["id"], WANG)
    done = _approve(client, task["id"], WANG)
    assert done["flow_status"] == "8"

    # Small amount: finance can reject to director_expense (the branch's previous
    # regular node) while the instance returns to the rejected state.
    task = _task_for(client, small["id"], WANG)
    rejected = client.post(f"{PREFIX}/tasks/{task['id']}/reject", json={"message": "补发票"}, headers=WANG).json()
    assert rejected["flow_status"] == "9"
    assert rejected["node_code"] == "director_expense"


def test_countersign_requires_every_approver(client: TestClient) -> None:
    instance = _start(client, "purchase", amount=20000)
    assert instance["node_code"] == "review"

    first = _approve(client, _task_for(client, instance["id"], ZHANG)["id"], ZHANG)
    assert first["node_code"] == "review"
    second = _approve(client, _task_for(client, instance["id"], LI)["id"], LI)
    assert second["node_code"] == "review"
    # The same task still exists; both approvers have already voted.
    current = client.get(f"{PREFIX}/instances/{instance['id']}").json()
    assert current["tasks"][0]["assignees"] == ["u1003"]

    third = _approve(client, _task_for(client, instance["id"], WANG)["id"], WANG)
    assert third["node_code"] == "finance"
    assert third["flow_status"] == "1"

    done = _approve(client, _task_for(client, instance["id"], WANG)["id"], WANG)
    assert done["flow_status"] == "8"

    history = client.get(f"{PREFIX}/history?instanceId={instance['id']}", headers=WANG).json()["items"]
    review_votes = [item for item in history if item["node_code"] == "review"]
    assert {item["approver"] for item in review_votes} == {"u1001", "u1002", "u1003"}


def test_revoke_and_terminate(client: TestClient) -> None:
    instance = _start(client, "leave", days=3)
    revoked = client.post(
        f"{PREFIX}/instances/{instance['id']}/revoke",
        json={"message": "不请了"},
        headers=ZHAO,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["flow_status"] == "6"
    assert revoked.json()["node_code"] == "dept"
    assert _task_for(client, instance["id"], ZHANG)

    # Only the initiator may revoke.
    forbidden = client.post(f"{PREFIX}/instances/{instance['id']}/revoke", json={"message": "x"}, headers=LI)
    assert forbidden.status_code == 403

    terminated = client.post(
        f"{PREFIX}/instances/{instance['id']}/terminate",
        json={"message": "终止"},
        headers=ZHAO,
    )
    assert terminated.status_code == 200
    assert terminated.json()["flow_status"] == "4"
    assert client.get(f"{PREFIX}/tasks?instanceId={instance['id']}", headers=ZHANG).json()["items"] == []


def test_transfer_add_and_reduce_signature(client: TestClient) -> None:
    instance = _start(client, "leave", days=1)
    task = _task_for(client, instance["id"], ZHANG)

    transferred = client.post(
        f"{PREFIX}/tasks/{task['id']}/transfer",
        json={"handler": "u1001", "add_handlers": ["u1003"], "message": "请代办"},
        headers=ZHANG,
    )
    assert transferred.status_code == 200, transferred.text
    assert _task_for(client, instance["id"], WANG)
    assert client.get(f"{PREFIX}/tasks?instanceId={instance['id']}", headers=ZHANG).json()["items"] == []

    added = client.post(
        f"{PREFIX}/tasks/{task['id']}/add-signature",
        json={"handler": "u1003", "add_handlers": ["u1002", "u1004"]},
        headers=WANG,
    )
    assert added.status_code == 200, added.text

    reduced = client.post(
        f"{PREFIX}/tasks/{task['id']}/reduce-signature",
        json={"handler": "u1003", "reduce_handlers": ["u1002"]},
        headers=WANG,
    )
    assert reduced.status_code == 200, reduced.text

    done = _approve(client, task["id"], WANG)
    assert done["node_code"] == "director"


def test_depute_keeps_original_handler(client: TestClient) -> None:
    instance = _start(client, "leave", days=1)
    task = _task_for(client, instance["id"], ZHANG)
    response = client.post(
        f"{PREFIX}/tasks/{task['id']}/depute",
        json={"handler": "u1001", "add_handlers": ["u1003"], "message": "帮我看看"},
        headers=ZHANG,
    )
    assert response.status_code == 200, response.text
    assert _task_for(client, instance["id"], WANG)
    # Delegation does not remove the original handler.
    assert _task_for(client, instance["id"], ZHANG)


def test_reject_last(client: TestClient) -> None:
    instance = _start(client, "leave", days=1)
    _approve(client, _task_for(client, instance["id"], ZHANG)["id"], ZHANG)
    task = _task_for(client, instance["id"], LI)
    response = client.post(f"{PREFIX}/tasks/{task['id']}/reject-last", json={"message": "退回上一节点"}, headers=LI)
    assert response.status_code == 200, response.text
    assert response.json()["node_code"] == "dept"
    assert _task_for(client, instance["id"], ZHANG)


def test_reject_last_requires_a_previous_approval_node(client: TestClient) -> None:
    # ``director_expense`` is reached straight from the gateway: the only history
    # row points at the start node, which must never be a rejection target.
    instance = _start(client, "expense", amount=9000, category="差旅")
    task = _task_for(client, instance["id"], LI)
    response = client.post(f"{PREFIX}/tasks/{task['id']}/reject-last", json={"message": "退回"}, headers=LI)
    assert response.status_code == 400
    assert "没有可退回的审批节点" in response.json()["detail"]
    assert _task_for(client, instance["id"], LI)


def test_task_permissions(client: TestClient) -> None:
    instance = _start(client, "leave", days=1)
    task = _task_for(client, instance["id"], ZHANG)
    response = client.post(f"{PREFIX}/tasks/{task['id']}/approve", json={}, headers=WANG)
    assert response.status_code == 403
    assert "没有该任务的处理权限" in response.json()["detail"]


def test_stats_and_labels(client: TestClient) -> None:
    stats = client.get(f"{PREFIX}/meta/stats", headers=ZHANG).json()
    assert stats["definitions"] >= 3
    assert stats["tasks"] >= 0
    labels = client.get(f"{PREFIX}/status-labels").json()
    assert labels["8"] == "已完成"
    enums = client.get(f"{PREFIX}/meta/enums").json()
    assert enums["nodeTypes"]["0"] == "start"
    assert enums["models"] == {"CLASSICS": "经典模式"}
    assert "MIMIC" not in enums["chartColors"]
