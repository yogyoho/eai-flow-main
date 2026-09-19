"""SQL → 三元组装载器（kernel P2）——doc_graph 测试数据入图，兼任主系统桥接器.

纯核心 load_doc_graph_rows(store, ...) 只吃行字典（单测零 DB 依赖）；
read_doc_graph_rows() 为集成读取（sqlalchemy 同步引擎，直连 extensions 库 dg_* 表），
仅在 integration 标记下使用（验收：跑通真实 doc_graph 测试数据）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.ontology.kernel.compile import DomainVocabulary, collect_vocabularies
from app.ontology.kernel.graph_ops import add_mention, add_relation, find_by_natural_key, upsert_entity
from app.ontology.kernel.iri import etype_to_class_name
from app.ontology.kernel.store import OxStore
from app.ontology.registry import Registry


@dataclass
class LoaderStats:
    entities: int = 0
    relations: int = 0
    mentions: int = 0
    deduped_entities: int = 0  # 自然键命中复用（未新建）
    skipped_relations: list[str] = field(default_factory=list)  # 端点缺失等
    skipped_mentions: list[str] = field(default_factory=list)


def etype_class_map(registry: Registry, domain: str) -> dict[str, str]:
    """域内 etype → OWL 类名（etype_classes 显式优先，缺省 PascalCase）。"""
    mapping: dict[str, str] = {}
    for ot in registry.object_types.values():
        if ot.domain != domain:
            continue
        for prop in ot.properties:
            if prop.name == "etype" and prop.enum:
                for etype in prop.enum:
                    declared = (ot.etype_classes or {}).get(etype)
                    mapping.setdefault(etype, declared.class_name if declared and declared.class_name else etype_to_class_name(etype))
    return mapping


def load_doc_graph_rows(
    store: OxStore,
    registry: Registry,
    *,
    entity_rows: list[dict],
    relation_rows: list[dict],
    mention_rows: list[dict],
    domain: str = "doc_graph",
) -> LoaderStats:
    """dg_entities/dg_relations/dg_mentions 行 → 断言图（自然键幂等，可重复执行）。"""
    vocab: DomainVocabulary = collect_vocabularies(registry)[domain]
    classes = etype_class_map(registry, domain)
    scheme = vocab.scheme
    stats = LoaderStats()

    iri_of: dict[str, str] = {}
    for row in entity_rows:
        norm = row.get("norm_name") or row.get("canonical_name") or ""
        existed = find_by_natural_key(store, row["etype"], norm) is not None
        iri = upsert_entity(
            store,
            vocab,
            class_name=classes[row["etype"]],
            entity_uuid=row["id"],
            etype=row["etype"],
            canonical_name=row.get("canonical_name") or "",
            norm_name=row.get("norm_name"),
            attrs=row.get("attrs"),
            confidence=_as_float(row.get("confidence")),
            status=row.get("status") or "active",
            valid_from=_as_str(row.get("valid_from")),
            valid_to=_as_str(row.get("valid_to")),
            created_at=_as_str(row.get("created_at")),
        )
        iri_of[str(row["id"])] = iri
        stats.entities += 1
        if existed:
            stats.deduped_entities += 1

    for row in relation_rows:
        subject = iri_of.get(str(row.get("subject_id")))
        obj = iri_of.get(str(row.get("object_id")))
        if subject is None or obj is None:
            stats.skipped_relations.append(str(row.get("id")))
            continue
        add_relation(
            store,
            vocab,
            relation_uuid=row["id"],
            subject_iri=subject,
            predicate=row["predicate"],
            object_iri=obj,
            confidence=_as_float(row.get("confidence")),
            valid_from=_as_str(row.get("valid_from")),
            valid_to=_as_str(row.get("valid_to")),
        )
        stats.relations += 1

    for row in mention_rows:
        entity_iri = iri_of.get(str(row.get("entity_id")))
        relation_node = f"{scheme.namespace}rel/{row['relation_id']}" if row.get("relation_id") else None
        if entity_iri is None and relation_node is None:
            stats.skipped_mentions.append(str(row.get("id")))
            continue
        add_mention(
            store,
            vocab,
            mention_uuid=row["id"],
            entity_iri=entity_iri,
            relation_iri=relation_node,
            thread_id=row.get("thread_id") or "",
            document_id=row.get("document_id") or "",
            doc_span=row.get("doc_span"),
            quote=row.get("quote") or "",
            extracted_by=row.get("extracted_by") or "",
            extracted_at=_as_str(row.get("extracted_at")),
            error=row.get("error"),
        )
        stats.mentions += 1

    return stats


def _as_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _as_str(value: object) -> str | None:
    return str(value) if value is not None else None


def read_doc_graph_rows(dsn: str) -> tuple[list[dict], list[dict], list[dict]]:
    """集成读取：extensions 库 dg_* 三表全量行（sqlalchemy 同步引擎）。

    仅 integration 场景调用；行字段与 load_doc_graph_rows 输入一一对应。
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(dsn)
    with engine.connect() as conn:
        entities = [dict(row._mapping) for row in conn.execute(text("SELECT * FROM dg_entities"))]
        relations = [dict(row._mapping) for row in conn.execute(text("SELECT * FROM dg_relations"))]
        mentions = [dict(row._mapping) for row in conn.execute(text("SELECT * FROM dg_mentions"))]
    # attrs/doc_span 为 JSON 字符串列，保持原样传给纯核心（内部 json.loads 兼容 str/dict）
    for row in entities:
        if isinstance(row.get("attrs"), str):
            try:
                row["attrs"] = json.loads(row["attrs"])
            except json.JSONDecodeError:
                pass
    return entities, relations, mentions
