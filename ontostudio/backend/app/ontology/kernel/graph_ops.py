"""断言图写路径与运营语义（kernel P2）.

- upsert_entity：自然键幂等（对齐 doc_graph uq 语义）——命中即原位更新，uuid 不变。
- add_relation：边三元组（可直接 SPARQL 遍历）+ 关系节点（置信度/双时间/证据锚点）。
- add_mention：证据链一等节点，永不删。
- merge/unmerge：mergedInto 指针 + MergeAudit 审计节点；undo = 指针回翻 + 审计留痕。
- resolve_canonical：mergedInto+ 路径求规范实体。

所有读写限定 graph:asserted；失败 fail-closed 抛 GraphOpError。
SPARQL 一律经 _select() 构造（pattern 不含花括号，规避 f-string 转义）。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from pyoxigraph import Quad

from app.ontology.kernel.compile import DomainVocabulary
from app.ontology.kernel.store import ASSERTED_GRAPH, OxStore
from app.ontology.kernel.vocab import (
    C_MENTION,
    C_MERGE_AUDIT,
    C_RELATION,
    P_AUDIT_ACTOR,
    P_AUDIT_AT,
    P_AUDIT_MENTION,
    P_AUDIT_REASON,
    P_AUDIT_REVERSED,
    P_AUDIT_SOURCE,
    P_AUDIT_TARGET,
    P_CONFIDENCE,
    P_CREATED_AT,
    P_DOC_SPAN,
    P_DOCUMENT_ID,
    P_EDGE_OBJECT,
    P_EDGE_PREDICATE,
    P_EDGE_SUBJECT,
    P_ERROR,
    P_EXTRACTED_AT,
    P_EXTRACTED_BY,
    P_MENTION_OF_ENTITY,
    P_MENTION_OF_RELATION,
    P_MERGED_INTO,
    P_NATURAL_KEY,
    P_QUOTE,
    P_STATUS,
    P_THREAD_ID,
    P_VALID_FROM,
    P_VALID_TO,
    lit,
    natural_key,
    nn,
)

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


class GraphOpError(Exception):
    """写路径守卫失败（fail-closed）。"""


# ---- 内部小工具 ----


def _select(var: str, pattern: str) -> str:
    """单变量 SELECT，强制限定断言图（pattern 不含花括号）。"""
    return f"SELECT ?{var} WHERE {{ GRAPH <{ASSERTED_GRAPH}> {{ {pattern} }} }}"


def _add(store: OxStore, s: str, p: str, o: object, graph: str = ASSERTED_GRAPH) -> None:
    obj = nn(o) if isinstance(o, str) and o.startswith(("http://", "https://", "urn:")) else lit(o)
    store._store.add(Quad(nn(s), nn(p), obj, nn(graph)))


def _find_one(store: OxStore, sparql: str, var: str) -> str | None:
    rows = store.query(sparql)
    return rows[0][var] if rows else None


def _remove_triples(store: OxStore, subject: str, predicate: str) -> int:
    """删除指定 (s,p,*) 三元组（仅限可变字段更新/指针回翻）。"""
    quads = list(store._store.quads_for_pattern(nn(subject), nn(predicate), None, nn(ASSERTED_GRAPH)))
    for quad in quads:
        store._store.remove(quad)
    return len(quads)


def _require_entity(store: OxStore, iri: str, role: str) -> None:
    if _find_one(store, _select("t", f"<{iri}> a ?t"), "t") is None:
        raise GraphOpError(f"{role} 实体不存在：{iri}")


def _set_status(store: OxStore, iri: str, status: str) -> None:
    _remove_triples(store, iri, P_STATUS)
    _add(store, iri, P_STATUS, status)


# ---- 实体 ----


def upsert_entity(
    store: OxStore,
    vocab: DomainVocabulary,
    *,
    class_name: str,
    entity_uuid: str | uuid.UUID,
    etype: str,
    canonical_name: str,
    norm_name: str | None = None,
    attrs: dict | str | None = None,
    confidence: float | None = None,
    status: str = "active",
    valid_from: str | None = None,
    valid_to: str | None = None,
    created_at: str | None = None,
) -> str:
    """自然键（etype|norm_name）幂等 upsert；返回实体 IRI（命中复用旧 IRI）。"""
    class_ref = vocab.class_ref(class_name)
    norm = norm_name or canonical_name
    key = natural_key(etype, norm)
    existing = _find_one(store, _select("e", f'?e <{P_NATURAL_KEY}> "{key}"'), "e")
    iri = existing or vocab.scheme.instance_iri(entity_uuid)

    _add(store, iri, RDF_TYPE, str(class_ref))
    if existing is None:
        _add(store, iri, P_NATURAL_KEY, key)
        _add(store, iri, P_CREATED_AT, created_at or datetime.now(UTC).isoformat())
    # 可变字段原位刷新（naturalKey/createdAt 不动；先清旧值防 RDF 集合下新旧并存）
    _remove_triples(store, iri, f"{vocab.scheme.namespace}attr/canonical_name")
    _remove_triples(store, iri, f"{vocab.scheme.namespace}attr/norm_name")
    _add(store, iri, f"{vocab.scheme.namespace}attr/canonical_name", canonical_name)
    _add(store, iri, f"{vocab.scheme.namespace}attr/norm_name", norm)
    if confidence is not None:
        _remove_triples(store, iri, P_CONFIDENCE)
        _add(store, iri, P_CONFIDENCE, confidence)
    if valid_from:
        _add(store, iri, P_VALID_FROM, valid_from)
    if valid_to:
        _add(store, iri, P_VALID_TO, valid_to)
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except json.JSONDecodeError as e:
            raise GraphOpError(f"attrs 非法 JSON：{e}") from e
    for attr_key, value in (attrs or {}).items():
        _remove_triples(store, iri, f"{vocab.scheme.namespace}attr/{attr_key}")
        _add(store, iri, f"{vocab.scheme.namespace}attr/{attr_key}", value)
    if not _find_one(store, _select("s", f"<{iri}> <{P_STATUS}> ?s"), "s"):
        _set_status(store, iri, status)
    return iri


def find_by_natural_key(store: OxStore, etype: str, norm_name: str) -> str | None:
    return _find_one(store, _select("e", f'?e <{P_NATURAL_KEY}> "{natural_key(etype, norm_name)}"'), "e")


def resolve_canonical(store: OxStore, iri: str) -> str:
    """跟随 mergedInto+ 链到规范实体（无指针 → 自身）。"""
    rows = store.query(_select("c", f"<{iri}> <{P_MERGED_INTO}>+ ?c"))
    return rows[-1]["c"] if rows else iri


# ---- 关系 ----


def add_relation(
    store: OxStore,
    vocab: DomainVocabulary,
    *,
    relation_uuid: str | uuid.UUID,
    subject_iri: str,
    predicate: str,
    object_iri: str,
    confidence: float | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> str:
    """谓词须在本域词表（fail-closed）；返回关系节点 IRI（ns+rel/<uuid>）。"""
    pred_ref = str(vocab.predicate_ref(predicate))
    _add(store, subject_iri, pred_ref, object_iri)  # 可遍历边
    node = f"{vocab.scheme.namespace}rel/{relation_uuid}"
    _add(store, node, RDF_TYPE, C_RELATION)
    _add(store, node, P_EDGE_SUBJECT, subject_iri)
    _add(store, node, P_EDGE_PREDICATE, pred_ref)
    _add(store, node, P_EDGE_OBJECT, object_iri)
    if confidence is not None:
        _add(store, node, P_CONFIDENCE, confidence)
    if valid_from:
        _add(store, node, P_VALID_FROM, valid_from)
    if valid_to:
        _add(store, node, P_VALID_TO, valid_to)
    return node


# ---- 证据链（永不删）----


def add_mention(
    store: OxStore,
    vocab: DomainVocabulary,
    *,
    mention_uuid: str | uuid.UUID,
    entity_iri: str | None = None,
    relation_iri: str | None = None,
    thread_id: str = "",
    document_id: str = "",
    doc_span: dict | str | None = None,
    quote: str = "",
    extracted_by: str = "",
    extracted_at: str | None = None,
    error: str | None = None,
) -> str:
    if entity_iri is None and relation_iri is None:
        raise GraphOpError("mention 必须指向实体或关系之一")
    iri = f"{vocab.scheme.namespace}mention/{mention_uuid}"
    _add(store, iri, RDF_TYPE, C_MENTION)
    if entity_iri:
        _add(store, iri, P_MENTION_OF_ENTITY, entity_iri)
    if relation_iri:
        _add(store, iri, P_MENTION_OF_RELATION, relation_iri)
    if thread_id:
        _add(store, iri, P_THREAD_ID, thread_id)
    if document_id:
        _add(store, iri, P_DOCUMENT_ID, document_id)
    if doc_span is not None:
        span = doc_span if isinstance(doc_span, str) else json.dumps(doc_span, ensure_ascii=False)
        _add(store, iri, P_DOC_SPAN, span)
    if quote:
        _add(store, iri, P_QUOTE, quote)
    if extracted_by:
        _add(store, iri, P_EXTRACTED_BY, extracted_by)
    _add(store, iri, P_EXTRACTED_AT, extracted_at or datetime.now(UTC).isoformat())
    if error:
        _add(store, iri, P_ERROR, error)
    return iri


def list_mentions(store: OxStore, entity_iri: str) -> list[str]:
    """实体的直接证据 + 指向其参与关系的证据。"""
    mentions: list[str] = []
    rows = store.query(_select("m", f"?m <{P_MENTION_OF_ENTITY}> <{entity_iri}>"))
    mentions.extend(row["m"] for row in rows)
    rows = store.query(
        _select(
            "m",
            f"?rel <{P_EDGE_SUBJECT}>|<{P_EDGE_OBJECT}> <{entity_iri}> . ?m <{P_MENTION_OF_RELATION}> ?rel",
        )
    )
    mentions.extend(row["m"] for row in rows)
    return sorted(set(mentions))


# ---- 合并 / 撤销 ----


def merge_entities(
    store: OxStore,
    vocab: DomainVocabulary,
    *,
    source_iri: str,
    target_iri: str,
    actor: str,
    reason: str = "",
    mention_iris: list[str] | None = None,
) -> str:
    """source 并入 target：指针 + source 状态翻转 + 审计节点。返回审计 IRI。"""
    if source_iri == target_iri:
        raise GraphOpError("自合并被拒绝（source == target）")
    _require_entity(store, source_iri, "source")
    _require_entity(store, target_iri, "target")
    if _find_one(store, _select("t", f"<{source_iri}> <{P_MERGED_INTO}> ?t"), "t"):
        raise GraphOpError(f"source 已合并过：{source_iri}")

    _add(store, source_iri, P_MERGED_INTO, target_iri)
    _set_status(store, source_iri, "merged")

    audit = f"{vocab.scheme.namespace}audit/{uuid.uuid4()}"
    _add(store, audit, RDF_TYPE, C_MERGE_AUDIT)
    _add(store, audit, P_AUDIT_SOURCE, source_iri)
    _add(store, audit, P_AUDIT_TARGET, target_iri)
    _add(store, audit, P_AUDIT_ACTOR, actor)
    if reason:
        _add(store, audit, P_AUDIT_REASON, reason)
    _add(store, audit, P_AUDIT_AT, datetime.now(UTC).isoformat())
    _add(store, audit, P_AUDIT_REVERSED, "false")
    for mention in mention_iris or []:
        _add(store, audit, P_AUDIT_MENTION, mention)
    return audit


def unmerge(store: OxStore, vocab: DomainVocabulary, *, audit_iri: str) -> None:
    """审计回放撤销：指针移除 + 状态还原 + auditReversed 留痕。重复撤销 fail-closed。"""
    source = _find_one(store, _select("s", f"<{audit_iri}> <{P_AUDIT_SOURCE}> ?s"), "s")
    target = _find_one(store, _select("t", f"<{audit_iri}> <{P_AUDIT_TARGET}> ?t"), "t")
    if source is None or target is None:
        raise GraphOpError(f"审计不存在：{audit_iri}")
    reversed_flag = _find_one(store, _select("r", f"<{audit_iri}> <{P_AUDIT_REVERSED}> ?r"), "r")
    if reversed_flag == "true":
        raise GraphOpError(f"审计已撤销过：{audit_iri}")

    _remove_triples(store, source, P_MERGED_INTO)  # 指针回翻（唯一允许的物理删除）
    _set_status(store, source, "active")
    _remove_triples(store, audit_iri, P_AUDIT_REVERSED)
    _add(store, audit_iri, P_AUDIT_REVERSED, "true")
