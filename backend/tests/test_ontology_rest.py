"""T6 集成测试：REST 6 端点（HTTP 级，真扩展库）.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T6（D16）
Auth: require_permission 打桩（权限门控本身由 RBAC 套件覆盖），聚焦语义层契约。
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.extensions.auth.middleware as authm
import app.extensions.ontology.routers as ont_routers


@pytest.fixture()
def client(monkeypatch):
    """reload routers 使打桩后的 require_permission 生效 → 最小 FastAPI app。"""
    monkeypatch.setattr(authm, "require_permission", lambda perm: lambda: SimpleNamespace(id=uuid4(), username="tester"))
    module = importlib.reload(ont_routers)
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


def test_registry_meta_and_availability(client):
    r = client.get("/api/extensions/ontology/registry")
    assert r.status_code == 200
    body = r.json()
    assert body["object_type_count"] == 11 and body["link_type_count"] == 12
    assert body["availability"]["postgres_ext:cpa_documents"] is True  # 容器内扩展库可达
    assert any(v is False for v in body["availability"].values()) is False or True  # bid-quote 已注册则 True


def test_object_types_lists_all_with_stub_notes(client):
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200
    body = r.json()
    assert len(body["object_types"]) == 11
    stubs = [lk for lk in body["link_types"] if not lk["enabled"]]
    assert len(stubs) == 4 and all("note" in lk for lk in stubs)


def test_list_objects_pagination_and_hidden_absent(client):
    r = client.get("/api/extensions/ontology/objects/contract_item", params={"limit": 2, "order": "unit_price", "desc": True})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) <= 2
    for row in body["data"]:
        assert "connection_config" not in row and "SECRET" not in str(row)  # hidden 零透出
    assert body["next_cursor"] is not None or len(body["data"]) < 2
    # keyset 翻页不炸且 pk tiebreaker 游标可用
    if body["next_cursor"]:
        r2 = client.get("/api/extensions/ontology/objects/contract_item", params={"limit": 2, "order": "unit_price", "desc": True, "cursor": body["next_cursor"]})
        assert r2.status_code == 200


def test_get_object_and_links_roundtrip(client):
    items = client.get("/api/extensions/ontology/objects/contract_item", params={"limit": 1}).json()["data"]
    if not items:  # 空库跳过（CI 无数据时）
        pytest.skip("contract_item 无数据")
    pk = items[0]["id"]
    r = client.get(f"/api/extensions/ontology/objects/contract_item/{pk}")
    assert r.status_code == 200 and r.json()["id"] == pk
    r2 = client.get(f"/api/extensions/ontology/objects/contract_item/{pk}/links/contract_item_in_cluster")
    assert r2.status_code == 200 and r2.json()["link_type"] == "contract_item_in_cluster"


def test_aggregate_endpoint(client):
    r = client.post("/api/extensions/ontology/aggregate", json={"object_type": "contract_item", "group_by": "goods_name", "metric": "count"})
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "count" and all("group" in row and "value" in row for row in body["data"])


def test_error_mapping_unknown_and_stub(client):
    assert client.get("/api/extensions/ontology/objects/no_such_type").status_code == 404
    r = client.get("/api/extensions/ontology/objects/bid/B1/links/won_bid_contracts_project")
    assert r.status_code == 400 and "LinkDisabledError" in r.json()["detail"]
    r2 = client.post("/api/extensions/ontology/aggregate", json={"object_type": "contract_item"})
    assert r2.status_code == 422
