"""kernel P2 golden 测试：写路径/运营语义（spec §6 P2）.

- upsert 自然键幂等；关系节点 + 证据链；merge/unmerge 全流程与守卫
- loader 纯核心：fixture 行 → 断言图（去重/跳过统计）；集成装载（integration 标记，DB 缺省跳过）
纯单元零 DB 依赖（复用 P1 的 mini 词表）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ontology.kernel.compile import collect_vocabularies
from app.ontology.kernel.graph_ops import (
    GraphOpError,
    add_mention,
    add_relation,
    find_by_natural_key,
    list_mentions,
    merge_entities,
    resolve_canonical,
    unmerge,
    upsert_entity,
)
from app.ontology.kernel.loader import load_doc_graph_rows, read_doc_graph_rows
from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
from app.ontology.registry import load_registry
from tests.test_kernel_p1 import MINI_YAML

EX = "https://example.org/mini#"


@pytest.fixture()
def env(tmp_path: Path):
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI_YAML, encoding="utf-8")
    registry = load_registry(tmp_path)
    vocab = collect_vocabularies(registry)["mini"]
    store = OxStore()
    yield store, vocab
    store.close()


def _mk_entity(store, vocab, uuid_: str, name: str, etype: str = "project", class_name: str = "Project"):
    return upsert_entity(
        store,
        vocab,
        class_name=class_name,
        entity_uuid=uuid_,
        etype=etype,
        canonical_name=name,
        confidence=0.95,
    )


# ---- upsert 自然键幂等 ----


def test_upsert_natural_key_idempotent(env):
    store, vocab = env
    first = _mk_entity(store, vocab, "11111111-1111-1111-1111-111111111111", "横城煤矿项目")
    second = _mk_entity(store, vocab, "22222222-2222-2222-2222-222222222222", "横城煤矿项目")
    assert first == second, "同自然键必须复用既有 IRI"
    rows = store.query(f"SELECT ?c WHERE {{ GRAPH <graph:asserted> {{ ?e <{EX}attr/canonical_name> ?c }} }}")
    assert len(rows) == 1
    # canonical_name 刷新为最新写入
    assert rows[0]["c"] == "横城煤矿项目"


def test_find_by_natural_key(env):
    store, vocab = env
    _mk_entity(store, vocab, "11111111-1111-1111-1111-111111111111", "山西煤机集团", etype="org", class_name="Org")
    assert find_by_natural_key(store, "org", "山西煤机集团") is not None
    assert find_by_natural_key(store, "org", "不存在") is None


# ---- 关系 + 证据链 ----


def test_relation_and_mentions(env):
    store, vocab = env
    proj = _mk_entity(store, vocab, "11111111-1111-1111-1111-111111111111", "横城煤矿项目")
    org = _mk_entity(store, vocab, "33333333-3333-3333-3333-333333333333", "山西煤机集团", etype="org", class_name="Org")
    rel = add_relation(
        store,
        vocab,
        relation_uuid="44444444-4444-4444-4444-444444444444",
        subject_iri=org,
        predicate="owned_by",
        object_iri=proj,
        confidence=0.9,
    )
    # 可遍历边三元组直接在断言图
    rows = store.query(f"SELECT ?o WHERE {{ GRAPH <graph:asserted> {{ <{org}> <{EX}predicate/owned_by> ?o }} }}")
    assert rows and rows[0]["o"] == proj

    m1 = add_mention(store, vocab, mention_uuid="55555555-5555-5555-5555-555555555555", entity_iri=proj, quote="横城煤矿由山西煤机集团总承包")
    m2 = add_mention(store, vocab, mention_uuid="66666666-6666-6666-6666-666666666666", relation_iri=rel, quote="标书 L412")
    got = list_mentions(store, proj)
    assert m1 in got and m2 in got
    with pytest.raises(GraphOpError):
        add_mention(store, vocab, mention_uuid="77777777-7777-7777-7777-777777777777")


# ---- merge / unmerge ----


def test_merge_unmerge_flow(env):
    store, vocab = env
    src = _mk_entity(store, vocab, "11111111-1111-1111-1111-111111111111", "山西煤矿机械制造有限公司", etype="org", class_name="Org")
    tgt = _mk_entity(store, vocab, "33333333-3333-3333-3333-333333333333", "山西煤机集团", etype="org", class_name="Org")
    audit = merge_entities(store, vocab, source_iri=src, target_iri=tgt, actor="管理员", reason="规范化名一致")

    assert resolve_canonical(store, src) == tgt
    status = store.query(f"SELECT ?s WHERE {{ GRAPH <graph:asserted> {{ <{src}> <https://ontology.eai-flow.com/kernel#status> ?s }} }}")
    assert status[0]["s"] == "merged"

    unmerge(store, vocab, audit_iri=audit)
    assert resolve_canonical(store, src) == src
    status = store.query(f"SELECT ?s WHERE {{ GRAPH <graph:asserted> {{ <{src}> <https://ontology.eai-flow.com/kernel#status> ?s }} }}")
    assert status[0]["s"] == "active"
    reversed_flag = store.query(f"SELECT ?r WHERE {{ GRAPH <graph:asserted> {{ <{audit}> <https://ontology.eai-flow.com/kernel#auditReversed> ?r }} }}")
    assert reversed_flag[0]["r"] == "true"

    with pytest.raises(GraphOpError, match="已撤销"):
        unmerge(store, vocab, audit_iri=audit)


def test_merge_guards(env):
    store, vocab = env
    src = _mk_entity(store, vocab, "11111111-1111-1111-1111-111111111111", "甲", etype="org", class_name="Org")
    tgt = _mk_entity(store, vocab, "33333333-3333-3333-3333-333333333333", "乙", etype="org", class_name="Org")
    with pytest.raises(GraphOpError, match="自合并"):
        merge_entities(store, vocab, source_iri=src, target_iri=src, actor="x")
    merge_entities(store, vocab, source_iri=src, target_iri=tgt, actor="x")
    third = _mk_entity(store, vocab, "88888888-8888-8888-8888-888888888888", "丙", etype="org", class_name="Org")
    with pytest.raises(GraphOpError, match="已合并"):
        merge_entities(store, vocab, source_iri=src, target_iri=third, actor="x")
    with pytest.raises(GraphOpError, match="不存在"):
        merge_entities(store, vocab, source_iri="https://example.org/mini#id/00000000-0000-0000-0000-000000000000", target_iri=tgt, actor="x")


# ---- loader 纯核心 ----


def _fixture_rows():
    entities = [
        {"id": "a1", "etype": "project", "canonical_name": "横城煤矿项目", "norm_name": "横城煤矿项目", "confidence": 0.96, "status": "active", "attrs": {"总投资": "12亿"}},
        {"id": "a2", "etype": "org", "canonical_name": "山西煤机集团", "norm_name": "山西煤机集团", "confidence": 0.94, "status": "active"},
        {"id": "a3", "etype": "org", "canonical_name": "山西煤矿机械制造有限公司", "norm_name": "山西煤机集团", "confidence": 0.91, "status": "active"},  # 与 a2 同自然键
    ]
    relations = [
        {"id": "r1", "subject_id": "a2", "predicate": "owned_by", "object_id": "a1", "confidence": 0.9},
        {"id": "r2", "subject_id": "a3", "predicate": "part_of", "object_id": "a1", "confidence": 0.8},
    ]
    mentions = [
        {"id": "m1", "entity_id": "a1", "thread_id": "t1", "document_id": "标书-2024-017", "quote": "横城煤矿项目…", "extracted_by": "llm/v3"},
        {"id": "m2", "entity_id": "a2", "relation_id": "r1", "quote": "总承包关系"},
        {"id": "m3", "entity_id": "ghost", "quote": "悬空证据"},  # 端点缺失 → skip
    ]
    return entities, relations, mentions


@pytest.fixture()
def mini_registry(tmp_path: Path):
    (tmp_path / "_manifest.yaml").write_text("schema_version: 1\nfiles:\n  - file: mini.yaml\n", encoding="utf-8")
    (tmp_path / "mini.yaml").write_text(MINI_YAML, encoding="utf-8")
    return load_registry(tmp_path)


def test_loader_rows_and_dedupe(mini_registry):
    store = OxStore()
    entities, relations, mentions = _fixture_rows()
    stats = load_doc_graph_rows(store, mini_registry, entity_rows=entities, relation_rows=relations, mention_rows=mentions, domain="mini")
    assert stats.entities == 3
    assert stats.deduped_entities == 1, "a3 与 a2 同自然键应复用"
    assert stats.relations == 2
    assert stats.mentions == 2
    assert stats.skipped_mentions == ["m3"]

    # 可重复执行（幂等再装载不翻倍）
    stats2 = load_doc_graph_rows(store, mini_registry, entity_rows=entities, relation_rows=relations, mention_rows=mentions, domain="mini")
    assert stats2.deduped_entities == 3
    assert store.count_quads(ASSERTED_GRAPH) == store.count_quads(ASSERTED_GRAPH)  # 烟囱：图可查
    org_rows = store.query(f"SELECT ?e WHERE {{ GRAPH <graph:asserted> {{ ?e <{EX}attr/norm_name> '山西煤机集团' }} }}")
    assert len(org_rows) == 1


def test_loader_attrs_flattened(mini_registry):
    store = OxStore()
    entities, relations, mentions = _fixture_rows()
    load_doc_graph_rows(store, mini_registry, entity_rows=entities, relation_rows=relations, mention_rows=mentions, domain="mini")
    rows = store.query(f"SELECT ?v WHERE {{ GRAPH <graph:asserted> {{ ?e <{EX}attr/总投资> ?v }} }}")
    assert rows and rows[0]["v"] == "12亿"


# ---- 集成装载（验收：真实 doc_graph 测试数据；DB 不可达即跳过）----


@pytest.mark.integration
def test_loader_against_real_doc_graph(tmp_path: Path):
    """验收判据：装载器跑通现 doc_graph 测试数据（extensions 库 dg_* 三表）。

    用真实 registry（doc_graph 域词表），mini 词表无该域。
    """
    from sqlalchemy import create_engine, text

    from app.config import DatabaseConfig

    dsn = DatabaseConfig.from_env().sync_url
    try:
        engine = create_engine(dsn)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - DB 不可达即跳过（本地单测常态）
        pytest.skip("extensions PostgreSQL 不可达")

    registry = load_registry()  # 真实 registry：doc_graph 域词表
    entity_rows, relation_rows, mention_rows = read_doc_graph_rows(dsn)
    assert entity_rows, "doc_graph 测试数据为空？"
    with OxStore(tmp_path / "doc_graph_store") as store:
        stats = load_doc_graph_rows(store, registry, entity_rows=entity_rows, relation_rows=relation_rows, mention_rows=mention_rows)
        assert stats.entities == len(entity_rows)
        assert stats.mentions + len(stats.skipped_mentions) == len(mention_rows)
