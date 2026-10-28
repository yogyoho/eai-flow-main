"""Designer compatibility endpoints and execute/* helpers."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from .conftest import headers

PREFIX = "/api/workflow"


def test_query_def_skeleton(client: TestClient) -> None:
    body = client.get(f"{PREFIX}/designer/query-def", headers=headers()).json()
    assert body["id"] is None
    assert body["flowName"] == "新建流程"
    assert body["modelValue"] == "CLASSICS"
    assert body["nodeList"] == []
    assert len(body["chartStatusColor"]) == 3


def test_designer_meta_endpoints(client: TestClient) -> None:
    assert client.get(f"{PREFIX}/designer/handler-type").json() == ["用户", "角色", "部门"]

    result = client.get(f"{PREFIX}/designer/handler-result?type=角色").json()
    rows = result["handlerAuths"]["rows"]
    assert any(row["storageId"] == "role:manager" for row in rows)
    assert result["handlerAuths"]["total"] == len(rows)
    assert result["treeSelections"]

    feedback = client.get(f"{PREFIX}/designer/handler-feedback?storageIds=u1001,role:manager").json()
    assert feedback == [
        {"storageId": "u1001", "handlerName": "张三"},
        {"storageId": "role:manager", "handlerName": "部门负责人"},
    ]

    dictionary = client.get(f"{PREFIX}/designer/handler-dict").json()
    assert {"label": "张三", "value": "u1001"} in dictionary

    node_ext = client.get(f"{PREFIX}/designer/node-ext").json()
    assert any(item["code"] == "timeoutHours" for item in node_ext)
    assert client.get(f"{PREFIX}/designer/listener-list").json()


def test_published_forms_and_form_content(client: TestClient) -> None:
    forms = client.get(f"{PREFIX}/designer/published-form", headers=headers()).json()
    codes = {form["form_code"] for form in forms}
    assert {"leave_form", "expense_form"} <= codes

    form = next(item for item in forms if item["form_code"] == "leave_form")
    content = client.get(f"{PREFIX}/designer/form-content/{form['id']}", headers=headers()).json()
    assert "fields" in content

    response = client.post(
        f"{PREFIX}/designer/form-content",
        json={"id": form["id"], "form_content": '{"fields":[]}'},
        headers=headers(),
    )
    assert response.status_code == 200
    assert client.get(f"{PREFIX}/designer/form-content/{form['id']}", headers=headers()).json() == '{"fields":[]}'

    # restore the seeded schema for later tests / manual demo
    client.post(
        f"{PREFIX}/designer/form-content",
        json={"id": form["id"], "form_content": form["form_content"]},
        headers=headers(),
    )


def _start(client: TestClient, flow_code: str, variables: dict) -> dict:
    response = client.post(
        f"{PREFIX}/instances",
        json={
            "flow_code": flow_code,
            "business_id": f"designer-{uuid4().hex[:6]}",
            "variables": variables,
        },
        headers=headers("u1004", "Zhao Liu", "employee"),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_execute_load_and_handle(client: TestClient) -> None:
    instance = _start(client, "expense", {"amount": 300, "category": "办公", "remark": "钢笔"})
    tasks = client.get(
        f"{PREFIX}/tasks?instanceId={instance['id']}", headers=headers("u1003", "Wang Wu", "finance")
    ).json()["items"]
    assert len(tasks) == 1
    task_id = tasks[0]["id"]

    loaded = client.get(f"{PREFIX}/designer/execute/load/{task_id}", headers=headers()).json()
    assert loaded["id"] == task_id
    assert loaded["data"]["task"]["node_code"] == "finance"
    assert loaded["data"]["variables"]["amount"] == 300
    assert loaded["form"]["formCode"] == "expense_form"
    assert loaded["data"]["node"]["nodeCode"] == "finance"

    handled = client.post(
        f"{PREFIX}/designer/execute/handle?taskId={task_id}&skipType=PASS&message=同意",
        json={"amount": 300, "approved": True},
        headers=headers("u1003", "Wang Wu", "finance"),
    )
    assert handled.status_code == 200, handled.text
    assert handled.json()["flow_status"] == "8"

    history = client.get(f"{PREFIX}/history?instanceId={instance['id']}", headers=headers()).json()["items"]
    assert [item["flow_status"] for item in history][0] == "8"


def test_execute_his_load(client: TestClient) -> None:
    instance = _start(client, "expense", {"amount": 200})
    task = client.get(
        f"{PREFIX}/tasks?instanceId={instance['id']}", headers=headers("u1003", "Wang Wu", "finance")
    ).json()["items"][0]
    client.post(
        f"{PREFIX}/tasks/{task['id']}/approve",
        json={"message": "ok"},
        headers=headers("u1003", "Wang Wu", "finance"),
    )
    history = client.get(f"{PREFIX}/history?instanceId={instance['id']}", headers=headers()).json()["items"]
    his = history[0]
    loaded = client.get(f"{PREFIX}/designer/execute/hisLoad/{his['id']}", headers=headers()).json()
    assert loaded["id"] == his["id"]
    assert loaded["data"]["hisTask"]["approver"] == "u1003"
    assert loaded["form"]["formCode"] == "expense_form"
