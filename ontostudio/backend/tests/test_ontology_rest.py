"""T6 集成测试：REST 6 端点（HTTP 级，真扩展库）.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T6（D16）
Auth: S1 Task 2 实装 JWT 验签（app/auth.py）——client 装置带 superadmin 测试 token
（conftest.auth_headers），聚焦语义层契约；鉴权负路径在 tests/test_main.py。
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
def client(auth_headers):
    """独立服务 app.main 全量装配（带 superadmin 测试 token——见模块 docstring）。"""
    return TestClient(ontostudio_app, headers=auth_headers)


def test_registry_meta_and_availability(client):
    r = client.get("/api/extensions/ontology/registry")
    assert r.status_code == 200
    body = r.json()
    # EAI-CUSTOM(2026-09-27 registry 缩编): 5 对象 / 6 链接（原 16/16 四域 yaml 已删）
    assert body["object_type_count"] == 5 and body["link_type_count"] == 6
    assert body["availability"]["postgres_ext:dg_entities"] is True  # 容器内扩展库可达


def test_object_types_lists_all(client):
    r = client.get("/api/extensions/ontology/object-types")
    assert r.status_code == 200
    body = r.json()
    assert len(body["object_types"]) == 5
    # 缩编后无 stub 链接（4 条跨模块 stub 随四域 yaml 退场）：全量 enabled 且不带 note
    stubs = [lk for lk in body["link_types"] if not lk["enabled"]]
    assert stubs == []
    assert len(body["link_types"]) == 6 and all(lk["enabled"] for lk in body["link_types"])


def test_list_objects_pagination_and_hidden_absent(client):
    r = client.get("/api/extensions/ontology/objects/graph_entity", params={"limit": 2, "order": "confidence", "desc": True})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) <= 2
    # keyset 翻页不炸且 pk tiebreaker 游标可用
    if body["next_cursor"]:
        r2 = client.get("/api/extensions/ontology/objects/graph_entity", params={"limit": 2, "order": "confidence", "desc": True, "cursor": body["next_cursor"]})
        assert r2.status_code == 200


def test_get_object_and_links_roundtrip(client):
    items = client.get("/api/extensions/ontology/objects/graph_entity", params={"limit": 1}).json()["data"]
    if not items:  # 空库跳过（CI 无数据时）
        pytest.skip("graph_entity 无数据")
    pk = items[0]["id"]
    r = client.get(f"/api/extensions/ontology/objects/graph_entity/{pk}")
    assert r.status_code == 200 and r.json()["id"] == pk
    # 证据链链接（graph_mention→graph_entity），从 target 侧反向遍历
    r2 = client.get(f"/api/extensions/ontology/objects/graph_entity/{pk}/links/mention_of_entity")
    assert r2.status_code == 200 and r2.json()["link_type"] == "mention_of_entity"


def test_aggregate_endpoint(client):
    r = client.post("/api/extensions/ontology/aggregate", json={"object_type": "graph_entity", "group_by": "etype", "metric": "count"})
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "count" and all("group" in row and "value" in row for row in body["data"])


def test_error_mapping_unknown(client):
    """错误映射: 未注册对象/链接 → 404（UnknownObjectError / UnknownLinkError）。

    EAI-CUSTOM(2026-09-27 registry 缩编): 原 stub 链接 400/LinkDisabledError 断言随
    cross_module.yaml 退场——路由层 404 映射对未注册链接类型成立（won_bid_contracts_project
    类型本身已不存在）；LinkDisabledError → 400 的映射保留在引擎/路由实现中，
    stub 机制由 test_ontology_engine 的合成 stub 用例守。
    """
    assert client.get("/api/extensions/ontology/objects/no_such_type").status_code == 404
    r = client.get("/api/extensions/ontology/objects/graph_entity/B1/links/won_bid_contracts_project")
    assert r.status_code == 404 and "UnknownLinkError" in r.json()["detail"]
    r2 = client.post("/api/extensions/ontology/aggregate", json={"object_type": "graph_entity"})
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


# EAI-CUSTOM(2026-09-29): mention 默认排除契约（批量入图淹没——细节与纯逻辑回归见
# test_ontology_graph_views.py 的 mention 排除契约段）；此处钉 HTTP 参数面 include=mentions。


def test_graph_nodes_mentions_excluded_by_default_and_opt_in(client):
    try:
        has_mentions = client.get("/api/extensions/ontology/objects/graph_mention", params={"limit": 1}).json()["data"]
        if not has_mentions:
            pytest.skip("库内无 mention 行（opt-in 断言需有数据, 空库跳过）")
        default = client.get("/api/extensions/ontology/graph/nodes", params={"limit": 2000})
        opted_in = client.get("/api/extensions/ontology/graph/nodes", params={"limit": 2000, "include": "mentions"})
    except (ConnectorError, OSError):
        pytest.skip("扩展库/数据源不可达（host 环境跳过, 容器内验证）")
    assert default.status_code == opted_in.status_code == 200
    default_types = {n["type"] for n in default.json()["nodes"]}
    opted_types = {n["type"] for n in opted_in.json()["nodes"]}
    assert "graph_mention" not in default_types  # 默认窗口内零 mention（行为修复主断言）
    assert "graph_mention" in opted_types  # include=mentions 恢复全集


def test_graph_edges_mentions_excluded_by_default_and_opt_in(client):
    try:
        default = client.get("/api/extensions/ontology/graph/edges", params={"limit": 5000})
        # opt-in 首窗可能被 5050+ mention 边占满（mention_* api_name 序在 relation_* 之前）——
        # 翻页取尽后比类型集，首窗对比是截断伪命题。
        opted_types: set[str] = set()
        resp, cursor = client.get("/api/extensions/ontology/graph/edges", params={"limit": 5000, "include": "mentions"}), None
        for _ in range(10):  # 防失控
            body = resp.json()
            opted_types |= {e["type"] for e in body["edges"]}
            cursor = body.get("next_cursor")
            if not cursor:
                break
            resp = client.get("/api/extensions/ontology/graph/edges", params={"limit": 5000, "include": "mentions", "cursor": cursor})
    except (ConnectorError, OSError):
        pytest.skip("扩展库/数据源不可达（host 环境跳过, 容器内验证）")
    assert default.status_code == 200
    default_types = {e["type"] for e in default.json()["edges"]}
    mention_links = {lt.api_name for lt in load_registry().link_types.values() if "mention" in lt.api_name}
    assert not (default_types & mention_links)  # 默认零 mention 边（排除在链接序构建期，任何窗口都不出现）
    assert default_types <= opted_types  # 取尽后 opt-in 是默认集的超集
    assert mention_links & opted_types  # 取尽后 mention 边在场
