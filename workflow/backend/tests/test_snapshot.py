"""Definition/form snapshots stay frozen for the life of an instance."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from .conftest import headers

PREFIX = "/api/workflow"


def _flow(code: str, form_path: str) -> dict:
    return {
        "flowCode": code,
        "flowName": "快照测试流程",
        "modelValue": "CLASSICS",
        "category": "测试",
        "formCustom": "Y",
        "formPath": form_path,
        "nodeList": [
            {
                "nodeType": 0,
                "nodeCode": "start",
                "nodeName": "开始",
                "coordinate": "100,100|100,150",
                "skipList": [
                    {
                        "nowNodeCode": "start",
                        "nextNodeCode": "approve",
                        "skipName": "提交",
                        "skipType": "PASS",
                    }
                ],
            },
            {
                "nodeType": 1,
                "nodeCode": "approve",
                "nodeName": "主管审批",
                "permissionFlag": "u1001",
                "coordinate": "300,100|300,150",
                "formCustom": "Y",
                "formPath": form_path,
                "skipList": [
                    {
                        "nowNodeCode": "approve",
                        "nextNodeCode": "end",
                        "skipName": "通过",
                        "skipType": "PASS",
                    }
                ],
            },
            {
                "nodeType": 2,
                "nodeCode": "end",
                "nodeName": "结束",
                "coordinate": "500,100|500,150",
            },
        ],
    }


def test_instance_uses_frozen_definition_and_form(client: TestClient) -> None:
    suffix = uuid4().hex[:8]
    form_code = f"snapshot_form_{suffix}"
    form = client.post(
        f"{PREFIX}/forms",
        json={
            "form_code": form_code,
            "form_name": "快照表单",
            "form_content": '{"fields":[{"key":"title","label":"标题","type":"text","required":true}]}',
        },
        headers=headers(),
    )
    assert form.status_code == 201, form.text
    form = form.json()
    form_path = form["form_path"]
    published_form = client.post(f"{PREFIX}/forms/{form['id']}/publish", headers=headers())
    assert published_form.status_code == 200, published_form.text

    flow_code = f"snapshot_flow_{suffix}"
    saved = client.post(
        f"{PREFIX}/designer/save-json",
        json={"defJson": _flow(flow_code, form_path)},
        headers=headers(),
    )
    assert saved.status_code == 200, saved.text
    definition = saved.json()["data"]
    definition_id = definition["id"]
    published = client.post(f"{PREFIX}/definitions/{definition_id}/publish", headers=headers())
    assert published.status_code == 200, published.text

    started = client.post(
        f"{PREFIX}/instances",
        json={"flow_code": flow_code, "business_id": f"snapshot-{suffix}", "variables": {"title": "原始"}},
        headers=headers("u1004", "Zhao Liu", "employee", "d01"),
    )
    assert started.status_code == 201, started.text
    instance_id = started.json()["id"]

    tasks = client.get(
        f"{PREFIX}/tasks?instanceId={instance_id}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    ).json()["items"]
    assert len(tasks) == 1
    task_id = tasks[0]["id"]

    before = client.get(
        f"{PREFIX}/designer/execute/load/{task_id}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    )
    assert before.status_code == 200, before.text
    before = before.json()
    assert before["data"]["node"]["nodeName"] == "主管审批"
    assert '"title"' in before["formContent"]
    original_form_content = before["formContent"]

    # Mutate both the published form and the live definition after start.
    changed_form = client.post(
        f"{PREFIX}/designer/form-content",
        json={
            "id": form["id"],
            "form_content": '{"fields":[{"key":"changed","label":"已修改","type":"text"}]}',
        },
        headers=headers(),
    )
    assert changed_form.status_code == 200, changed_form.text

    live = client.get(f"{PREFIX}/designer/query-def/{definition_id}", headers=headers()).json()
    for node in live["nodeList"]:
        if node["nodeCode"] == "approve":
            node["nodeName"] = "已修改节点"
            node["permissionFlag"] = "u9999"
    changed_definition = client.post(
        f"{PREFIX}/designer/save-json",
        json={"defJson": live},
        headers=headers(),
    )
    assert changed_definition.status_code == 200, changed_definition.text

    # Loading the running task must still show the start-time node + form.
    after = client.get(
        f"{PREFIX}/designer/execute/load/{task_id}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    )
    assert after.status_code == 200, after.text
    after = after.json()
    assert after["data"]["node"]["nodeName"] == "主管审批"
    assert after["formContent"] == original_form_content
    assert '"changed"' not in after["formContent"]

    # Approval uses the frozen graph: u1001 is still the authorized handler even
    # though the live definition was changed to u9999.
    approved = client.post(
        f"{PREFIX}/tasks/{task_id}/approve",
        json={"message": "同意"},
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["flow_status"] == "8"

    history = client.get(
        f"{PREFIX}/history?instanceId={instance_id}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    ).json()["items"]
    assert history
    his = client.get(
        f"{PREFIX}/designer/execute/hisLoad/{history[0]['id']}",
        headers=headers("u1001", "Zhang San", "manager", "d01"),
    )
    assert his.status_code == 200, his.text
    assert his.json()["formContent"] == original_form_content
