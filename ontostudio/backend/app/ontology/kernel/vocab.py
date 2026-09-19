"""kernel 跨域词汇表（kernel P2）.

业务词表（类/谓词/属性）按域挂在 {domain_ns} 下（compile.DomainVocabulary）；
运营语义（状态/置信度/合并指针/审计/证据）跨域共用，固定在 kernel 命名空间。
物理三元组永不删——唯一例外是 merge 指针回翻（spec §2，审计留痕）。
"""

from __future__ import annotations

import uuid

import pyoxigraph as ox

KERNEL_NS = "https://ontology.eai-flow.com/kernel#"

# ---- 类 ----
C_MENTION = f"{KERNEL_NS}Mention"
C_RELATION = f"{KERNEL_NS}Relation"
C_MERGE_AUDIT = f"{KERNEL_NS}MergeAudit"

# ---- 属性（运营语义）----
P_STATUS = f"{KERNEL_NS}status"
P_CONFIDENCE = f"{KERNEL_NS}confidence"
P_VALID_FROM = f"{KERNEL_NS}validFrom"
P_VALID_TO = f"{KERNEL_NS}validTo"
P_CREATED_AT = f"{KERNEL_NS}createdAt"
P_NATURAL_KEY = f"{KERNEL_NS}naturalKey"
P_MERGED_INTO = f"{KERNEL_NS}mergedInto"

# 审计
P_AUDIT_SOURCE = f"{KERNEL_NS}auditSource"
P_AUDIT_TARGET = f"{KERNEL_NS}auditTarget"
P_AUDIT_ACTOR = f"{KERNEL_NS}auditActor"
P_AUDIT_REASON = f"{KERNEL_NS}auditReason"
P_AUDIT_AT = f"{KERNEL_NS}auditAt"
P_AUDIT_REVERSED = f"{KERNEL_NS}auditReversed"
P_AUDIT_MENTION = f"{KERNEL_NS}auditMention"

# 关系节点（边三元组 + 元数据锚点双轨）
P_EDGE_SUBJECT = f"{KERNEL_NS}edgeSubject"
P_EDGE_PREDICATE = f"{KERNEL_NS}edgePredicate"
P_EDGE_OBJECT = f"{KERNEL_NS}edgeObject"

# 证据链
P_MENTION_OF_ENTITY = f"{KERNEL_NS}mentionOfEntity"
P_MENTION_OF_RELATION = f"{KERNEL_NS}mentionOfRelation"
P_THREAD_ID = f"{KERNEL_NS}threadId"
P_DOCUMENT_ID = f"{KERNEL_NS}documentId"
P_DOC_SPAN = f"{KERNEL_NS}docSpan"
P_QUOTE = f"{KERNEL_NS}quote"
P_EXTRACTED_BY = f"{KERNEL_NS}extractedBy"
P_EXTRACTED_AT = f"{KERNEL_NS}extractedAt"
P_ERROR = f"{KERNEL_NS}error"


def nn(iri: str) -> ox.NamedNode:
    return ox.NamedNode(iri)


def lit(value: object) -> ox.Literal:
    return ox.Literal(str(value))


def natural_key(etype: str, norm_name: str) -> str:
    """自然键（对齐 doc_graph uq_dg_entities_natural 语义：etype + 归一名）。"""
    return f"{etype}|{norm_name}"


def new_node_iri(prefix: str) -> str:
    """审计节点等无业务主键元素的 IRI。"""
    return f"{prefix}{uuid.uuid4()}"
