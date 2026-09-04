"""kf_search_knowledge — Agent 跨知识库检索（RAGFlow）。

EAI-CUSTOM (bug-2195): 此前 RAGFlow /retrieval 只有前端 knowledge/routers.py 调用，
Agent 无工具可达。本工具把 RAGFlowClient.chat() 包装为 MCP 工具：
知识库清单来自 extensions PG（knowledge_bases 表，ragflow_dataset_id 非空 = 已同步）。
"""

from __future__ import annotations

import json
import logging

from mcp.types import TextContent

logger = logging.getLogger(__name__)

_MAX_CHUNK_CHARS = 1500


async def handle_kf_search_knowledge(arguments: dict, _run_in_db) -> list[TextContent]:
    query = (arguments.get("query") or "").strip()
    if not query:
        return [TextContent(type="text", text=json.dumps({"error": "query is required"}, ensure_ascii=False))]
    kb_name = (arguments.get("kb_name") or "").strip()
    top_k = int(arguments.get("top_k") or 5)
    similarity_threshold = float(arguments.get("similarity_threshold") or 0.2)
    filters = arguments.get("filters") or None

    from sqlalchemy import select

    from app.extensions.models import KnowledgeBase

    async def _load_kbs(db):
        stmt = select(KnowledgeBase).where(KnowledgeBase.ragflow_dataset_id.isnot(None))
        if kb_name:
            stmt = stmt.where(KnowledgeBase.name.ilike(f"%{kb_name}%"))
        rows = (await db.execute(stmt)).scalars().all()
        return [(kb.name, kb.ragflow_dataset_id) for kb in rows]

    kbs = await _run_in_db(_load_kbs)
    if not kbs:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": "no matching knowledge base synced to RAGFlow", "kb_name_filter": kb_name}, ensure_ascii=False),
            )
        ]

    from app.extensions.config import get_extensions_config
    from app.extensions.knowledge.client import RAGFlowClient
    from app.extensions.knowledge.service import build_metadata_condition, filter_doc_ids

    if not get_extensions_config().ragflow.api_key:
        return [TextContent(type="text", text=json.dumps({"error": "RAGFlow not configured (RAGFLOW_API_KEY missing)"}, ensure_ascii=False))]

    condition = None
    try:
        condition = build_metadata_condition(filters)
    except ValueError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]

    client = RAGFlowClient()
    id_to_name = {ds_id: name for name, ds_id in kbs}

    # 有过滤时走两段式(逐库:metadata_condition 文档过滤 → document_ids 收敛检索;
    # 零命中库跳过;过滤失败库降级整库)。过滤会改变块集合,联合调用不再适用。
    per_kb_calls: list[tuple[str, list[str] | None]] | None = None
    filters_truncated = False
    if condition:
        per_kb_calls = []
        for _, ds_id in kbs:
            try:
                ids, trunc = await filter_doc_ids(client, ds_id, condition)
                filters_truncated = filters_truncated or trunc
            except Exception as e:
                logger.warning(f"kf_search_knowledge metadata 过滤失败,降级整库 ds={ds_id}: {e}")
                ids = None
            if ids is not None and not ids:
                continue  # 该库零命中,跳过
            per_kb_calls.append((ds_id, ids))
        if not per_kb_calls:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "query": query,
                            "filters_applied": condition,
                            "chunk_count": 0,
                            "chunks": [],
                            "message": "过滤条件下无匹配文档",
                        },
                        ensure_ascii=False,
                    ),
                )
            ]

    try:
        if per_kb_calls is not None:
            raw_chunks: list = []
            for ds_id, doc_ids in per_kb_calls:
                r = await client.chat(dataset_id=ds_id, query=query, top_k=top_k, similarity_threshold=similarity_threshold, document_ids=doc_ids)
                if r.get("code") == 0:
                    raw_chunks.extend((r.get("data") or {}).get("chunks", []))
        else:
            result = await client.chat(
                dataset_id=[ds_id for _, ds_id in kbs],
                query=query,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
            )
            if result.get("code") != 0 and "different embedding models" in str(result.get("message", "")):
                # RAGFlow /retrieval 拒绝混合嵌入模型的数据集联合检索 —— 退化为逐库检索后合并
                raw_chunks = []
                for _, ds_id in kbs:
                    r = await client.chat(dataset_id=ds_id, query=query, top_k=top_k, similarity_threshold=similarity_threshold)
                    if r.get("code") == 0:
                        raw_chunks.extend((r.get("data") or {}).get("chunks", []))
            else:
                raw_chunks = (result.get("data") or {}).get("chunks", [])
    except Exception as e:
        logger.error(f"kf_search_knowledge RAGFlow error: {e}")
        return [TextContent(type="text", text=json.dumps({"error": f"RAGFlow retrieval failed: {e}"}, ensure_ascii=False))]

    if per_kb_calls is None and result.get("code") != 0 and not raw_chunks:
        return [TextContent(type="text", text=json.dumps({"error": result.get("message", "RAGFlow retrieval failed")}, ensure_ascii=False))]

    chunks = []
    for c in sorted(raw_chunks, key=lambda c: float(c.get("similarity") or 0.0), reverse=True)[:top_k]:
        content = (c.get("content") or "").strip()
        if not content:
            continue
        chunks.append(
            {
                "knowledge_base": id_to_name.get(c.get("dataset_id"), "unknown"),
                "document": c.get("document_keyword") or c.get("document_id", ""),
                "similarity": round(float(c.get("similarity") or 0.0), 4),
                "content": content[:_MAX_CHUNK_CHARS],
            }
        )

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "query": query,
                    "searched_kbs": [name for name, _ in kbs],
                    "filters_applied": condition,
                    "filters_truncated": filters_truncated,
                    "chunk_count": len(chunks),
                    "chunks": chunks,
                    # 引用规范：本地文档无 URL，模型不得编造链接（bug-2197）
                    "citation_note": "本地知识库文档没有网页 URL；引用时来源写 知识库名 + 文档名，禁止编造 url 字段或虚构域名链接。",
                },
                ensure_ascii=False,
            ),
        )
    ]
