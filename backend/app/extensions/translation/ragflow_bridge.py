"""RAGFlow index bridge + MinIO deliverable (EAI-CUSTOM, T6).

契约（设计构件 1/3 + R6/R7）——index_translation 成功返回 = delivered 分界事件：
  1) 中文 Markdown 交付物写 MinIO 双语桶（复用 knowledge StorageProvider，R7/C-1）
  2) 中文版上传 RAGFlow dataset（chunk_method 一律经
     ``DocumentService._CHUNK_METHOD_TO_PARSER`` 映射——SC-1/learning
     kb-chunk-method-dual-enum），带 (task_id, source sha, lang) 元数据血统；
     chunk 级溯源由 chunk→document→meta→原件链承载（v1 文档级，样例闸后细化）
  3) FR 双份索引 = 原文经 index_original 入库（B1）+ 本桥追加中文版（前提 3）
  4) 幂等：按 tlt_task_id 元数据去重，重跑不重复建文档
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.extensions.database import get_session_factory
from app.extensions.knowledge.client import RAGFlowClient
from app.extensions.knowledge.service import DocumentService
from app.extensions.knowledge.storage import get_storage_provider
from app.extensions.models import KnowledgeBase
from app.extensions.translation.models import TranslationTask

logger = logging.getLogger(__name__)


def _zh_filename(task: TranslationTask) -> str:
    stem = Path(task.source_uri or "document").stem or "document"
    return f"{stem}.zh.{task.doc_sha[:8]}.md"


def _block_to_md(block: dict) -> str:
    btype = block.get("type")
    text = (block.get("text") or "").strip()
    if not text:
        return ""
    if btype == "table":
        cells = (block.get("meta") or {}).get("cells")
        if cells and isinstance(cells, list) and cells[0]:
            header = "| " + " | ".join(str(c) for c in cells[0]) + " |"
            sep = "|" + "---|" * len(cells[0])
            rows = ["| " + " | ".join(str(c) for c in r) + " |" for r in cells[1:]]
            return "\n".join([header, sep, *rows])
        return text
    if btype == "heading":
        return f"## {text}"
    return text


def build_markdown(task: TranslationTask, zh_blocks: list[dict]) -> str:
    """zh blocks → 中文 Markdown 交付物（头部携带溯源块）。"""
    header = "\n".join(
        [
            "<!-- tlt:translated-document",
            f"task_id: {task.id}",
            f"source_sha256: {task.doc_sha}",
            f"source_lang: {task.source_lang}",
            f"quality_tier: {task.quality_tier}",
            f"generated_at: {datetime.now(UTC).isoformat()}",
            "source: 见同知识库原始上传文档（sha256 对应） -->",
            "",
            f"# {Path(task.source_uri or 'document').stem}（中文译本）",
            "",
        ]
    )
    body = "\n\n".join(md for md in (_block_to_md(b) for b in zh_blocks) if md)
    return header + "\n" + body + "\n"


def _lineage_meta(task: TranslationTask) -> dict:
    return {
        "tlt_task_id": str(task.id),
        "tlt_source_sha256": task.doc_sha,
        "tlt_source_lang": task.source_lang,
        "tlt_quality_tier": task.quality_tier,
    }


async def _dataset_exists(client: RAGFlowClient, dataset_id: str) -> bool:
    """探活：兼容 RAGFlow 两种应答（HTTP 404 / HTTP 200 + body code!=0）。"""
    try:
        result = await client.get_dataset(dataset_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return False
        raise
    return result.get("code") in (None, 0)


async def ensure_dataset(kb: KnowledgeBase, *, client: RAGFlowClient | None = None) -> str:
    """返回就绪的 dataset_id；悬空/缺失则重建并回写 kb（**调用方负责 commit**）。

    C1 自愈单点：worker 索引（index_translation）、上传链（upload_assets）、
    设置页修复（asset-kb/initialize）三处共用，禁止另写第二份重建逻辑。
    """
    client = client or RAGFlowClient()
    if kb.ragflow_dataset_id and await _dataset_exists(client, kb.ragflow_dataset_id):
        return kb.ragflow_dataset_id
    embed = kb.embedding_model
    if not embed:
        available = await client.list_available_embedding_models()
        embed = available[0] if available else None
    rf = await client.create_dataset(
        name=kb.name,
        description=kb.description or "",
        embedding_model=embed,
        chunk_method=kb.chunk_method,
        parser_config=kb.parser_config,
    )
    dataset_id = (rf.get("data") or {}).get("id")
    if not dataset_id:
        raise RuntimeError(f"ragflow create_dataset returned no id: {str(rf)[:200]}")
    logger.warning("tlt dataset self-heal: kb %s old=%s -> new=%s", kb.id, kb.ragflow_dataset_id, dataset_id)
    kb.ragflow_dataset_id = dataset_id
    return dataset_id


async def index_original(
    task: TranslationTask,
    dest: Path,
    *,
    kb: KnowledgeBase,
    client: RAGFlowClient | None = None,
) -> str | None:
    """原文直传 RAGFlow（B1，tlt_source_sha256 幂等）。

    返回 doc_id（已存在则返回既有 id）；RAGFlow 侧异常向上抛——**降级是调用方职责**
    （upload_assets/backfill 捕获后 warning 继续，翻译链路不依赖 RAGFlow 原文）。
    """
    client = client or RAGFlowClient()
    dataset_id = await ensure_dataset(kb, client=client)
    existing = await _find_doc_by_meta(client, dataset_id, "tlt_source_sha256", task.doc_sha)
    if existing:
        return existing
    parser_id = DocumentService._CHUNK_METHOD_TO_PARSER.get(kb.chunk_method or "", "naive")
    rf = await client.upload_document(dataset_id, str(dest), file_name=dest.name, parser_id=parser_id or None)
    doc_id = (rf.get("data") or {}).get("id")
    if not doc_id:
        raise RuntimeError(f"ragflow upload returned no document id: {str(rf)[:200]}")
    await client.update_document_metadata(dataset_id, doc_id, {"tlt_source_sha256": task.doc_sha, "tlt_source_lang": task.source_lang})
    await client.parse_document(dataset_id, doc_id)  # C-1: RAGFlow 不自动 chunk，缺此调用原文永不被检索
    logger.info("tlt original indexed: task %s sha=%s -> doc %s (dataset %s)", task.id, task.doc_sha[:8], doc_id, dataset_id)
    return doc_id


async def _doc_exists(client: RAGFlowClient, dataset_id: str, doc_id: str) -> bool:
    """探活单个文档（B2 delivered 译本悬空判定用）。

    注意：不能照抄 _dataset_exists 的 code 判定——RAGFlowClient.get_document 内部已
    吞掉 HTTPStatusError（缺失文档返回 ``{"data": {}}``，无 code 键），按 code 判会把
    缺失误报为存在；以 data.id 为准。HTTPStatusError 分支仅作客户端实现变动的兜底。
    """
    try:
        result = await client.get_document(dataset_id, doc_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return False
        raise
    data = result.get("data")
    return isinstance(data, dict) and bool(data.get("id"))


async def reindex_deliverable(task: TranslationTask, *, kb: KnowledgeBase, client: RAGFlowClient | None = None) -> str | None:
    """C1 重建后历史译本补录：已落盘交付物重传新 dataset（tlt_task_id 幂等）。返回 doc_id 或 None（文件缺失）。"""
    client = client or RAGFlowClient()
    from app.extensions.config import get_extensions_config

    stable = Path(get_extensions_config().storage.base_path) / "translation" / "deliverables" / str(task.id) / _zh_filename(task)
    if not stable.exists():
        logger.warning("tlt reindex: deliverable missing for task %s (%s)", task.id, stable)
        return None
    dataset_id = await ensure_dataset(kb, client=client)
    existing = await _find_existing_zh_doc(client, dataset_id, str(task.id))
    if existing:
        return existing
    parser_id = DocumentService._CHUNK_METHOD_TO_PARSER.get(kb.chunk_method or "", "naive")
    rf = await client.upload_document(dataset_id, str(stable), file_name=_zh_filename(task), parser_id=parser_id or None)
    doc_id = (rf.get("data") or {}).get("id")
    if not doc_id:
        raise RuntimeError(f"ragflow upload returned no document id: {str(rf)[:200]}")
    await client.update_document_metadata(dataset_id, doc_id, _lineage_meta(task))
    await client.parse_document(dataset_id, doc_id)
    return doc_id


async def _find_doc_by_meta(client: RAGFlowClient, dataset_id: str, meta_name: str, meta_value: str) -> str | None:
    """按单个元数据键精确查重，返回 doc_id 或 None。"""
    result = await client.list_documents(
        dataset_id,
        metadata_condition={
            "logic": "and",
            "conditions": [{"name": meta_name, "comparison_operator": "=", "value": meta_value}],
        },
    )
    docs = (result.get("data") or {}).get("docs") or (result.get("data") or [])
    if isinstance(docs, list) and docs:
        first = docs[0]
        return first.get("id") if isinstance(first, dict) else None
    return None


async def _find_existing_zh_doc(client: RAGFlowClient, dataset_id: str, task_id: str) -> str | None:
    """按 tlt_task_id 元数据精确去重（worker 退避重跑不重复建文档）。"""
    return await _find_doc_by_meta(client, dataset_id, "tlt_task_id", task_id)


async def _set_deliverable(task_id: str, deliverable_uri: str, ragflow_doc_id: str) -> None:
    factory = get_session_factory()
    from sqlalchemy import update

    async with factory() as db:
        await db.execute(update(TranslationTask).where(TranslationTask.id == task_id).values(deliverable_uri=deliverable_uri, ragflow_zh_doc_id=ragflow_doc_id))
        await db.commit()


async def index_translation(
    task: TranslationTask,
    zh_blocks: list[dict],
    source_blocks: list,
    *,
    client: RAGFlowClient | None = None,
    storage=None,
) -> None:
    """机检全绿后调用：MinIO 交付 + RAGFlow 中文版入库（双份索引的 zh 侧）。

    任何异常向上抛 → worker 落 failed/退避重试（幂等：重跑按 task_id 元数据去重）。
    client/storage 可注入（测试 fake）。
    """
    client = client or RAGFlowClient()
    factory = get_session_factory()
    async with factory() as db:
        kb = await db.get(KnowledgeBase, task.kb_id)
        if kb is None:
            raise RuntimeError(f"kb vanished: {task.kb_id}")
        dataset_id = await ensure_dataset(kb, client=client)  # C1: 悬空自动重建并回写
        await db.commit()
        owner_id, kb_id_str, chunk_method = str(kb.owner_id), str(kb.id), kb.chunk_method or ""

    markdown = build_markdown(task, zh_blocks)
    zh_name = _zh_filename(task)
    task_id_str = str(task.id)

    # 交付物直写稳定路径（base_path 下，随库持久）；MinIO 部署时再由 provider 拷入桶。
    # 修复记录：曾用 mkstemp 临时路径当 uri，/tmp 清理后交付物 404（T6 验收发现）。
    from app.extensions.config import get_extensions_config

    stable_dir = Path(get_extensions_config().storage.base_path) / "translation" / "deliverables" / task_id_str
    stable_dir.mkdir(parents=True, exist_ok=True)
    stable_path = stable_dir / zh_name
    stable_path.write_text(markdown, encoding="utf-8")

    storage = storage or get_storage_provider()
    stored = await storage.upload_local_file(
        str(stable_path),
        owner_id=owner_id,
        kb_id=kb_id_str,
        filename=zh_name,
        content_type="text/markdown; charset=utf-8",
    )
    logger.info("tlt deliverable stored: %s", stored.uri)

    # SC-1: parser 配置一律经映射表（禁止裸传内部枚举）
    parser_id = DocumentService._CHUNK_METHOD_TO_PARSER.get(chunk_method, "naive")
    doc_id = await _find_existing_zh_doc(client, dataset_id, task_id_str)
    if doc_id is None:
        rf_result = await client.upload_document(
            dataset_id,
            str(stable_path),
            file_name=zh_name,
            parser_id=parser_id or None,
        )
        doc_id = (rf_result.get("data") or {}).get("id")
        if not doc_id:
            raise RuntimeError(f"ragflow upload returned no document id: {str(rf_result)[:200]}")
    else:
        logger.info("tlt zh doc already indexed for task %s: %s (idempotent rerun)", task_id_str, doc_id)

    await client.update_document_metadata(dataset_id, doc_id, _lineage_meta(task))
    await client.parse_document(dataset_id, doc_id)
    await _set_deliverable(task_id_str, stored.uri, doc_id)
    logger.info("tlt task %s: zh doc %s indexed in dataset %s (parser=%s)", task_id_str, doc_id, dataset_id, parser_id)
