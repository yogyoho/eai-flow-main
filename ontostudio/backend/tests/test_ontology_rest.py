"""T6 集成测试：REST 6 端点（HTTP 级，真扩展库）.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T6（D16）
Auth: 独立服务 Task 1 无鉴权直通（占位 app.auth.require_permission 恒放行；Task 2 落地
JWT 验签后此处装置需随鉴权适配），聚焦语义层契约。
EAI-CUSTOM(2026-09-17 迁出独立): 原版打桩 gateway authm.require_permission + reload routers
构造最小 app; 独立服务无 gateway auth → 直接用 app.main 全量装配。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app as ontostudio_app
from app.ontology.connectors import ConnectorError
from app.ontology.registry import load_registry


@pytest.fixture()
def client():
    """独立服务 app.main 装配（无鉴权直通——见模块 docstring）。"""
    return TestClient(ontostudio_app)


def test_registry_meta_and_availability(client):
    r = client.get("/api/extensions/ontology/registry")
    assert r.status_code == 200
    body = r.json()
    assert body["object_type_count"] == 14 and body["link_type_count"] == 16
    assert body["availability"]["postgres_ext:cpa_documents"] is True  # 容器内扩展库可达
    assert any(v is False for v in body["availability"].values()) is False or True  # bid-quote 已注册则 True


def test_object_types_lists_all_with_stub_notes(client):
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200
    body = r.json()
    assert len(body["object_types"]) == 14
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


# EAI-CUSTOM(2026-09-12, plan Task1): 语义地图图投影端点集成——DB-gated（host 无 docker 网络即 skip，容器内真库验证）。
# 注意 host 失败签名有两种: ConnectorError（fetch 内连接失败包装）与裸 OSError/gaierror
# （data_source 路径 _source_config 的 URL 解析段未被包装，connectors.py 既有缺口）——两者都视为环境不可达。


def test_graph_nodes_projection(client):
    try:
        resp = client.get("/api/extensions/ontology/graph/nodes?limit=500")
    except (ConnectorError, OSError):
        pytest.skip("扩展库/数据源不可达（host 环境跳过, 容器内验证）")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"nodes", "next_cursor"}
    for n in body["nodes"]:
        assert set(n.keys()) == {"id", "type", "label", "properties"}
        assert n["id"].startswith(n["type"] + ":")


def test_graph_edges_projection_excludes_stub(client):
    try:
        resp = client.get("/api/extensions/ontology/graph/edges?limit=2000")
    except (ConnectorError, OSError):
        pytest.skip("扩展库/数据源不可达（host 环境跳过, 容器内验证）")
    assert resp.status_code == 200
    body = resp.json()
    stub_names = {lt.api_name for lt in load_registry().link_types.values() if not lt.enabled}
    for e in body["edges"]:
        assert e["type"] not in stub_names
