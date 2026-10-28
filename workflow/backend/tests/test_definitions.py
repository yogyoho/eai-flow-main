"""Definition CRUD, designer save, publish lifecycle and import/export."""

from __future__ import annotations

import math
from uuid import uuid4

from fastapi.testclient import TestClient

from .conftest import headers

PREFIX = "/api/workflow"


def _edge_points(coordinate: str | None) -> list[tuple[int, int]]:
    if not coordinate:
        return []
    points = coordinate.split("|")[0].split(";")
    return [tuple(int(part) for part in point.split(",", 1)) for point in points]


def _node_geometry(node: dict) -> tuple[int, int, int, int]:
    x_text, y_text = str(node["coordinate"]).split("|")[0].split(",", 1)
    node_type = int(node["nodeType"])
    if node_type in (0, 2):
        return int(x_text), int(y_text), 28, 28
    if node_type >= 3:
        return int(x_text), int(y_text), 30, 30
    return int(x_text), int(y_text), 88, 26


def _distance_to_node(point: tuple[int, int], node: dict) -> float:
    x, y, half_width, half_height = _node_geometry(node)
    dx = max(abs(point[0] - x) - half_width, 0)
    dy = max(abs(point[1] - y) - half_height, 0)
    return math.hypot(dx, dy)


def _flow(code: str, name: str = "测试流程") -> dict:
    return {
        "flowCode": code,
        "flowName": name,
        "modelValue": "CLASSICS",
        "category": "测试",
        "formCustom": "N",
        "nodeList": [
            {
                "nodeType": 0,
                "nodeCode": "start",
                "nodeName": "发起",
                "coordinate": "120,160|120,205",
                "skipList": [
                    {
                        "nowNodeCode": "start",
                        "nextNodeCode": "approve",
                        "skipName": "提交",
                        "skipType": "PASS",
                        "coordinate": "220,180;340,180|280,160",
                    }
                ],
            },
            {
                "nodeType": 1,
                "nodeCode": "approve",
                "nodeName": "审批",
                "permissionFlag": "u1001",
                "coordinate": "440,160|440,205",
                "nodeRatio": "0",
                "skipList": [
                    {
                        "nowNodeCode": "approve",
                        "nextNodeCode": "end",
                        "skipName": "通过",
                        "skipType": "PASS",
                        "coordinate": "540,180;660,180|600,160",
                    }
                ],
            },
            {
                "nodeType": 2,
                "nodeCode": "end",
                "nodeName": "结束",
                "coordinate": "760,160|760,205",
            },
        ],
    }


def _save(client: TestClient, payload: dict) -> dict:
    response = client.post(f"{PREFIX}/designer/save-json", json=payload, headers=headers())
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_seeded_demo_definitions(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/definitions", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 3
    seeded = {item["flow_code"]: item for item in body["items"]}
    assert {"leave", "expense", "purchase"} <= set(seeded)
    assert all(seeded[code]["is_publish"] == 1 for code in ("leave", "expense", "purchase"))
    assert all(item["model_value"] == "CLASSICS" for item in body["items"])


def test_sales_seed_edges_connect_their_nodes(client: TestClient) -> None:
    for flow_code in ("sales_r4_exception", "sales_r6_related_party"):
        listing = client.get(f"{PREFIX}/definitions?flowCode={flow_code}", headers=headers()).json()
        definition = next(item for item in listing["items"] if item["flow_code"] == flow_code)
        detail = client.get(f"{PREFIX}/designer/query-def/{definition['id']}", headers=headers()).json()
        nodes = {node["nodeCode"]: node for node in detail["nodeList"]}
        assert len(nodes) >= 4
        for node in detail["nodeList"]:
            point, _, label = str(node["coordinate"]).partition("|")
            assert label == point
            for skip in node.get("skipList", []):
                target = nodes[skip["nextNodeCode"]]
                assert skip["coordinate"] != "250,220;350,220|300,200"
                points = _edge_points(skip["coordinate"])
                assert len(points) >= 2
                assert _distance_to_node(points[0], node) <= 64
                assert _distance_to_node(points[-1], target) <= 64
        for code, node in nodes.items():
            if not code.startswith("step_"):
                continue
            rejects = {
                skip["nextNodeCode"]: skip for skip in node.get("skipList", []) if skip.get("skipType") == "REJECT"
            }
            assert rejects["end"]["skipName"] == "驳回"
            assert rejects["start"]["skipName"] == "退回申请人"


def test_save_query_and_roundtrip(client: TestClient) -> None:
    code = f"roundtrip_{uuid4().hex[:8]}"
    saved = _save(client, _flow(code, "往返流程"))
    assert saved["flowCode"] == code
    assert saved["version"] == "1"
    assert saved["isPublish"] == 0
    assert len(saved["nodeList"]) == 3

    skip = saved["nodeList"][0]["skipList"][0]
    assert skip["coordinate"] == "220,180;340,180|280,160"
    assert saved["nodeList"][1]["coordinate"] == "440,160|440,205"

    definition_id = saved["id"]
    queried = client.get(f"{PREFIX}/designer/query-def/{definition_id}", headers=headers()).json()
    assert queried["flowCode"] == code
    assert [node["nodeCode"] for node in queried["nodeList"]] == ["start", "approve", "end"]

    # Saving again with the id updates in place instead of creating a version.
    payload = dict(queried)
    payload["flowName"] = "往返流程 v1.1"
    updated = _save(client, payload)
    assert updated["id"] == definition_id
    assert updated["flowName"] == "往返流程 v1.1"
    assert updated["version"] == "1"


def test_legacy_mimic_save_is_normalized_to_classics(client: TestClient) -> None:
    payload = _flow(f"legacy_{uuid4().hex[:8]}", "旧仿钉钉流程")
    payload["modelValue"] = "MIMIC"
    saved = _save(client, payload)
    assert saved["modelValue"] == "CLASSICS"
    assert saved["chartStatusColor"] == ["56,161,105", "245,158,11", "107,114,128"]


def test_save_json_rejects_invalid_graph(client: TestClient) -> None:
    payload = _flow(f"invalid_{uuid4().hex[:8]}")
    payload["nodeList"] = [node for node in payload["nodeList"] if node["nodeType"] != 0]
    response = client.post(f"{PREFIX}/designer/save-json", json=payload, headers=headers())
    assert response.status_code == 400
    assert "开始节点" in response.json()["detail"]


def test_only_node_skip_keeps_metadata(client: TestClient) -> None:
    code = f"onlynodes_{uuid4().hex[:8]}"
    saved = _save(client, _flow(code, "只存节点"))
    payload = dict(saved)
    payload["flowName"] = "不应写入的名称"
    payload["nodeList"][1]["nodeName"] = "审批（改名）"
    response = client.post(
        f"{PREFIX}/designer/save-json",
        json=payload,
        headers={**headers(), "onlyNodeSkip": "true"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["flowName"] == "只存节点"
    assert data["nodeList"][1]["nodeName"] == "审批（改名）"


def test_version_copy_publish_and_expire(client: TestClient) -> None:
    code = f"lifecycle_{uuid4().hex[:8]}"
    saved = _save(client, _flow(code, "生命周期"))
    definition_id = saved["id"]

    published = client.post(f"{PREFIX}/definitions/{definition_id}/publish", headers=headers())
    assert published.status_code == 200
    assert published.json()["is_publish"] == 1

    copied = client.post(f"{PREFIX}/definitions/{definition_id}/copy", headers=headers())
    assert copied.status_code == 201
    clone = copied.json()
    assert clone["version"] == "2"
    assert clone["is_publish"] == 0
    assert clone["flow_code"] == code

    # The copy carries the whole graph.
    clone_json = client.get(f"{PREFIX}/designer/query-def/{clone['id']}", headers=headers()).json()
    assert len(clone_json["nodeList"]) == 3

    # Give version 1 an instance, then publish version 2: v1 must expire (9).
    started = client.post(
        f"{PREFIX}/instances",
        json={"flow_code": code, "business_id": "lifecycle-1"},
        headers=headers("u1004", "Zhao Liu", "employee"),
    )
    assert started.status_code == 201, started.text
    assert started.json()["definition_id"] == definition_id

    published_v2 = client.post(f"{PREFIX}/definitions/{clone['id']}/publish", headers=headers())
    assert published_v2.status_code == 200

    v1 = client.get(f"{PREFIX}/definitions/{definition_id}", headers=headers()).json()
    assert v1["is_publish"] == 9
    listing = client.get(f"{PREFIX}/definitions?flowCode={code}", headers=headers()).json()["items"]
    by_version = {item["version"]: item["is_publish"] for item in listing}
    assert by_version == {"1": 9, "2": 1}

    # Unpublish and delete are refused once instances exist.
    assert client.post(f"{PREFIX}/definitions/{definition_id}/unpublish", headers=headers()).status_code == 409
    assert client.delete(f"{PREFIX}/definitions/{definition_id}", headers=headers()).status_code == 409


def test_activate_suspend_and_publish_guard(client: TestClient) -> None:
    code = f"activity_{uuid4().hex[:8]}"
    created = client.post(
        f"{PREFIX}/definitions",
        json={"flow_code": code, "flow_name": "挂起测试"},
        headers=headers(),
    ).json()

    # Cannot publish an empty definition.
    assert client.post(f"{PREFIX}/definitions/{created['id']}/publish", headers=headers()).status_code == 400

    payload = _flow(code, "挂起测试")
    payload["id"] = created["id"]
    _save(client, payload)
    assert client.post(f"{PREFIX}/definitions/{created['id']}/publish", headers=headers()).status_code == 200

    suspended = client.post(f"{PREFIX}/definitions/{created['id']}/suspend", headers=headers())
    assert suspended.status_code == 200
    assert suspended.json()["activity_status"] == 0

    response = client.post(f"{PREFIX}/instances", json={"flow_code": code}, headers=headers())
    assert response.status_code == 400
    assert "挂起" in response.json()["detail"]

    activated = client.post(f"{PREFIX}/definitions/{created['id']}/activate", headers=headers())
    assert activated.status_code == 200
    assert activated.json()["activity_status"] == 1


def test_export_import(client: TestClient) -> None:
    code = f"export_{uuid4().hex[:8]}"
    saved = _save(client, _flow(code, "导出流程"))
    exported = client.get(f"{PREFIX}/definitions/{saved['id']}/export", headers=headers())
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["flowCode"] == code
    assert payload["isPublish"] is None

    payload["flowCode"] = f"{code}_copy"
    payload["flowName"] = "导入流程"
    imported = client.post(f"{PREFIX}/definitions/import", json={"payload": payload}, headers=headers())
    assert imported.status_code == 201, imported.text
    assert imported.json()["flow_code"] == f"{code}_copy"
    assert imported.json()["version"] == "1"


def test_delete_unused_definition(client: TestClient) -> None:
    code = f"delete_{uuid4().hex[:8]}"
    saved = _save(client, _flow(code))
    response = client.delete(f"{PREFIX}/definitions/{saved['id']}", headers=headers())
    assert response.status_code == 204
    assert client.get(f"{PREFIX}/definitions/{saved['id']}", headers=headers()).status_code == 404
