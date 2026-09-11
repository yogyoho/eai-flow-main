"""doc_graph 表模型元数据测试（无需 DB——只查 Base.metadata）."""

from app.extensions.database import Base
from app.extensions.ontology.doc_graph.tables import DgEntity, DgMention, DgMerge, DgRelation  # noqa: F401


def test_four_tables_registered():
    names = set(Base.metadata.tables)
    assert {"dg_entities", "dg_relations", "dg_mentions", "dg_merges"} <= names


def test_entity_natural_key_unique_index():
    idx = {i.name for i in Base.metadata.tables["dg_entities"].indexes}
    assert "uq_dg_entities_natural" in idx


def test_entity_columns():
    cols = {c.name for c in Base.metadata.tables["dg_entities"].columns}
    assert {"id", "domain", "etype", "canonical_name", "norm_name", "attrs", "confidence", "status", "valid_from", "valid_to", "created_at"} <= cols


def test_mention_columns():
    cols = {c.name for c in Base.metadata.tables["dg_mentions"].columns}
    assert {"id", "entity_id", "relation_id", "thread_id", "document_id", "doc_span", "quote", "extracted_by", "extracted_at", "error"} <= cols
