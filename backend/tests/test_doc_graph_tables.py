"""doc_graph 表模型元数据测试（无需 DB——只查 Base.metadata）."""

from app.extensions.database import Base
from app.extensions.ontology.doc_graph.tables import DgEntity, DgMention, DgMerge, DgRelation  # noqa: F401


def test_four_tables_registered():
    names = set(Base.metadata.tables)
    assert {"dg_entities", "dg_relations", "dg_mentions", "dg_merges"} <= names


def test_entity_natural_key_unique_index():
    idx = next(i for i in Base.metadata.tables["dg_entities"].indexes if i.name == "uq_dg_entities_natural")
    assert idx.unique
    assert {c.name for c in idx.columns} == {"domain", "etype", "norm_name"}


def test_entity_columns():
    cols = {c.name for c in Base.metadata.tables["dg_entities"].columns}
    assert {"id", "domain", "etype", "canonical_name", "norm_name", "attrs", "confidence", "status", "valid_from", "valid_to", "created_at"} <= cols


def test_mention_columns():
    cols = {c.name for c in Base.metadata.tables["dg_mentions"].columns}
    assert {"id", "entity_id", "relation_id", "thread_id", "document_id", "doc_span", "quote", "extracted_by", "extracted_at", "error"} <= cols


def test_mention_fk_targets():
    t = Base.metadata.tables["dg_mentions"]
    fks = {c.name: sorted(fk.column.table.name for fk in c.foreign_keys) for c in t.columns if c.foreign_keys}
    assert fks["entity_id"] == ["dg_entities"]
    assert fks["relation_id"] == ["dg_relations"]


def test_id_columns_server_default():
    """裸 SQL 写路径(ingest)不经过 ORM default——id 列必须在 DB 侧有 gen_random_uuid() 默认值."""
    for tname in ("dg_entities", "dg_relations", "dg_mentions", "dg_merges"):
        col = Base.metadata.tables[tname].columns["id"]
        sd = str(col.server_default.arg) if col.server_default is not None else ""
        assert "gen_random_uuid" in sd, f"{tname}.id missing server_default"
