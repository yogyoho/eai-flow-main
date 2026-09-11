"""doc_graph 入库——mention 先行 → 实体幂等 upsert → 关系落库（单事务）.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-11-ontology-doc-graph-design.md §5。
写路径只在本子包。连接模式照抄 ontology/connectors.py（NullPool + 显式 URL, 复用其 _ext_url 单一真源）。
幂等键: uq_dg_entities_natural(domain,etype,norm_name)——同文档重抽/跨文档同名归并同一行。
低置信(<0.7)实体落 pending_review 不阻塞管线（spec §7）。
重入库 promote-only: status=pending_review 且新置信≥0.7 才升 active, 永不降级人工清理过的 active/merged;
confidence 取历史与新值较大者。
评审备忘落地点: (1) naive datetime 按 Asia/Shanghai(+08:00) 业务时区解释后写 timestamptz;
(2) norm_name 截断 ≤300 对齐 String(300); (3) attrs 合并用 SQL || 运算, 不在 Python 侧原地改 JSONB。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.extensions.ontology.connectors import _ext_url
from app.extensions.ontology.doc_graph.resolver import normalize_name
from app.extensions.ontology.doc_graph.schemas import BidExtraction

REVIEW_CONFIDENCE = 0.7
_CST = timezone(timedelta(hours=8))  # 业务时区 Asia/Shanghai


def _tz_aware(d: datetime | None) -> datetime | None:
    """naive datetime 按 +08:00 业务时区解释（LLM 常产出无时区时间戳）。"""
    if d is None or d.tzinfo is not None:
        return d
    return d.replace(tzinfo=_CST)


async def ingest_extraction(payload: BidExtraction) -> dict[str, Any]:
    """校验通过的抽取结果入库。返回计数供 MCP 工具向 agent 汇报。"""
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    entity_ids: dict[str, Any] = {}  # payload 内 name → entity id（DB 返回 uuid.UUID, 注解用 Any）
    counts: dict[str, Any] = {"entities_upserted": 0, "relations": 0, "mentions": 0}
    try:
        async with engine.begin() as conn:
            for e in payload.entities:
                norm = normalize_name(e.name)[:300]
                status = "pending_review" if e.confidence < REVIEW_CONFIDENCE else "active"
                row = (
                    await conn.execute(
                        text(
                            """
                            INSERT INTO dg_entities (domain, etype, canonical_name, norm_name, attrs, confidence, status, valid_from, valid_to)
                            VALUES (:domain, :etype, :name, :norm, CAST(:attrs AS jsonb), :conf, :status, :vfrom, :vto)
                            ON CONFLICT (domain, etype, norm_name)
                              DO UPDATE SET attrs = dg_entities.attrs || EXCLUDED.attrs,
                                status = CASE WHEN dg_entities.status = 'pending_review' AND EXCLUDED.confidence >= 0.7 THEN 'active' ELSE dg_entities.status END,  -- 0.7 = REVIEW_CONFIDENCE（裸 SQL 内联）
                                confidence = GREATEST(dg_entities.confidence, EXCLUDED.confidence),
                                updated_at = NOW()
                            RETURNING id
                            """
                        ),
                        {
                            "domain": payload.domain,
                            "etype": e.etype,
                            "name": e.name,
                            "norm": norm,
                            "attrs": json.dumps(e.attrs, ensure_ascii=False),
                            "conf": e.confidence,
                            "status": status,
                            "vfrom": _tz_aware(e.valid_from),
                            "vto": _tz_aware(e.valid_to),
                        },
                    )
                ).first()
                entity_ids[e.name] = row.id
                await conn.execute(
                    text(
                        """
                        INSERT INTO dg_mentions (entity_id, thread_id, document_id, doc_span, quote, extracted_by)
                        VALUES (:eid, :tid, :doc, CAST(:span AS jsonb), :quote, :by)
                        """
                    ),
                    {
                        "eid": row.id,
                        "tid": payload.thread_id,
                        "doc": e.mention.document_id,
                        "span": json.dumps(e.mention.doc_span, ensure_ascii=False),
                        "quote": e.mention.quote,
                        "by": payload.extracted_by,
                    },
                )
                counts["mentions"] += 1
            counts["entities_upserted"] = len(entity_ids)

            for r in payload.relations:
                rel_row = (
                    await conn.execute(
                        text(
                            """
                            INSERT INTO dg_relations (subject_id, predicate, object_id, attrs, confidence, valid_from, valid_to)
                            VALUES (:sid, :pred, :oid, CAST(:attrs AS jsonb), :conf, :vfrom, :vto)
                            RETURNING id
                            """
                        ),
                        {
                            "sid": entity_ids[r.subject],
                            "pred": r.predicate,
                            "oid": entity_ids[r.object],
                            "attrs": json.dumps(r.attrs, ensure_ascii=False),
                            "conf": r.confidence,
                            "vfrom": _tz_aware(r.valid_from),
                            "vto": _tz_aware(r.valid_to),
                        },
                    )
                ).first()
                await conn.execute(
                    text(
                        """
                        INSERT INTO dg_mentions (relation_id, thread_id, document_id, doc_span, quote, extracted_by)
                        VALUES (:rid, :tid, :doc, CAST(:span AS jsonb), :quote, :by)
                        """
                    ),
                    {
                        "rid": rel_row.id,
                        "tid": payload.thread_id,
                        "doc": r.mention.document_id,
                        "span": json.dumps(r.mention.doc_span, ensure_ascii=False),
                        "quote": r.mention.quote,
                        "by": payload.extracted_by,
                    },
                )
                counts["relations"] += 1
                counts["mentions"] += 1
    finally:
        await engine.dispose()
    return counts
