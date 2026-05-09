"""Template extraction pipeline - 5-stage pipeline with callback-based progress.

Step 1: 文档解析 ← RAGFlow API
Step 2: 章节推断 ← LLM（推断章节树，动态适配不同报告类型）
Step 3: 元数据抽取 ← LLM（逐节抽取内容契约）
Step 4: 模板融合 ← LLM（多报告去重合并）
Step 5: 合规校验 ← 规则引擎

核心设计：
- Schema 不是硬编码的，由 Step 2 LLM 推断
- 不同类型报告（环评、可研、水保等）自动适配
- 多报告融合生成一份基础模板
- 返回结果而非 generator，解决 AsyncGenerator 无法传回大对象的问题
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .llm import ExtractionLLMClient
from .schemas import (
    ExtractionConfig,
    StepStatus,
    StepStatusSchema,
)

logger = logging.getLogger(__name__)

PIPELINE_STEPS = [
    "文档解析",
    "章节推断",
    "元数据抽取",
    "模板融合",
    "合规校验",
]


@dataclass
class PipelineResult:
    """Pipeline execution result containing everything needed to create a template."""
    sections: list[dict]  # Final merged section tree
    cross_section_rules: list[dict]
    completeness_score: int
    chapters: int  # Number of level-1 chapters
    total_sections: int  # Total number of sections (including nested)
    step_summaries: list[dict]  # List of {name, status, duration, detail}


def _flatten_sections(sections: list[dict]) -> list[dict]:
    """Flatten a nested section tree into a flat list."""
    flat = []
    for sec in sections:
        flat.append(sec)
        children = sec.get("children") or []
        if children:
            flat.extend(_flatten_sections(children))
    return flat


def _count_sections(sections: list[dict]) -> tuple[int, int]:
    """Count chapters (level-1) and total sections."""
    chapters = 0
    total = 0
    for sec in sections:
        if sec.get("level", 1) == 1:
            chapters += 1
        total += 1
        children = sec.get("children") or []
        if children:
            c, t = _count_sections(children)
            chapters += c
            total += t
    return chapters, total


# Patterns for detecting chapter/section headings in Chinese documents
_CHAPTER_PATTERNS = [
    # 第一章 / 第二节 / 第三条
    (re.compile(r"^第[一二三四五六七八九十百千\d]+[章节条款段]\s*[\.、\s]?\s*(.+)"), 1),
    # 1. / 1、 / 1.1 / 1.1.1
    (re.compile(r"^(\d+(?:[\.]\d+)*)\s*[\.、\s]\s*(.+)"), 1),
    # 一、 / 二、 / 十二、
    (re.compile(r"^[一二三四五六七八九十]+[、\.\s]\s*(.+)"), 1),
    # (一) / (1)
    (re.compile(r"^[（(][一二三四五六七八九十\d]+[）)]\s*(.+)"), 2),
]

def _scan_chapter_headings(chunks: list[dict]) -> list[dict]:
    """扫描所有 chunks，提取章节标题行。

    返回 [{title, line_number, chunk_index, level_guess}, ...]
    """
    headings = []
    line_no = 0
    for ci, chunk in enumerate(chunks):
        content = chunk.get("content", "")
        for line in content.split("\n"):
            line = line.strip()
            if not line or len(line) > 80:
                line_no += 1
                continue
            for pattern, default_level in _CHAPTER_PATTERNS:
                m = pattern.match(line)
                if m:
                    headings.append({
                        "title": line,
                        "line_number": line_no,
                        "chunk_index": ci,
                        "level_guess": default_level,
                    })
                    break
            line_no += 1
    return headings

def _build_structure_hint(chunks: list[dict], max_chars: int = 5000) -> str:
    """从文档 chunks 构建结构提示，发给 LLM 辅助章节推断。

    策略：
    1. 首先扫描所有 chunks，提取章节标题行
    2. 如果有章节标题，构建"目录+摘要"式的内容
    3. 如果没有，返回文档开头部分内容
    """
    headings = _scan_chapter_headings(chunks)

    if not headings:
        # 无章节标题：返回文档开头内容
        full = "\n\n".join(c.get("content", "") for c in chunks if c.get("content"))
        return full[:max_chars]

    # 收集所有 chunks 的完整内容
    full_content = "\n\n".join(c.get("content", "") for c in chunks if c.get("content"))

    # 构建结构提示：目录 + 每个章节的摘要
    parts = ["## 文档章节目录（自动识别）\n"]
    for h in headings:
        indent = "  " * (h["level_guess"] - 1)
        parts.append(f"{indent}- {h['title']}")

    parts.append("\n## 各章节内容摘要（每章节前200字）\n")

    # 为每个章节标题提取附近内容
    for h in headings:
        title = h["title"]
        # 在完整内容中查找该标题的位置
        idx = full_content.find(title)
        if idx >= 0:
            snippet = full_content[idx:idx + 300]
            parts.append(f"### {title}\n{snippet}\n")
        else:
            parts.append(f"### {title}\n（内容未找到）\n")

    result = "\n".join(parts)
    # 限制总长度
    if len(result) > max_chars:
        result = result[:max_chars] + "\n...(内容已截断)"

    return result


def _extract_keywords(title: str) -> list[str]:
    """从标题中提取关键词，用于模糊匹配。

    去除常见前缀（序号、章节词等），保留核心业务术语。
    """

    # 去除常见前缀模式
    patterns_to_remove = [
        r"^\d+[\.、]\s*",  # "1. ", "1、 "
        r"^第[一二三四五六七八九十百千\d]+[章节条款段]?\s*",  # "第一章", "第一节"
        r"^[一二三四五六七八九十]+[\.、]\s*",  # 中文序号
    ]

    cleaned = title
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned)

    # 分割为词语（按空格和标点）
    words = re.split(r"[\s,，。、；;：:（）()【】\[\]]+", cleaned)
    # 过滤太短和无意义的词
    keywords = [w for w in words if len(w) >= 2]
    return keywords


def _find_best_matching_paragraph(
    content: str,
    keywords: list[str],
    max_chars: int = 4000,
) -> str:
    """在文档内容中找到包含关键词最多的段落。

    策略：将文档按段落分割，统计每个段落中关键词出现次数，
    返回包含关键词最多的段落。
    """

    if not keywords:
        return content[:max_chars]

    # 按换行分割段落
    paragraphs = re.split(r"\n\s*\n|\n(?=[^\s])", content)
    best_paragraph = ""
    best_score = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 计算关键词得分
        score = 0
        for kw in keywords:
            # 精确匹配
            if kw in para:
                score += para.count(kw)
            # 忽略大小写匹配
            try:
                score += len(re.findall(kw, para, re.IGNORECASE))
            except re.error:
                pass

        if score > best_score:
            best_score = score
            best_paragraph = para

    # 如果找到匹配段落且得分足够高，返回该段落
    if best_score >= len(keywords):
        return best_paragraph[:max_chars]

    # 否则返回文档开头
    return content[:max_chars]


# Progress callback type
StepCallback = Callable[[StepStatusSchema], Any]


class ExtractionPipeline:
    """5阶段抽取流水线。

    直接返回 PipelineResult（而非 generator），
    通过可选 callback 报告每个阶段的进度。
    """

    def __init__(
        self,
        llm_client: Optional[ExtractionLLMClient] = None,
        max_content_chars: int = 5000,
        llm_model: Optional[str] = None,
    ):
        self._llm_client = llm_client
        self._max_content_chars = max_content_chars
        self._llm_model = llm_model
        self._llm: Optional[ExtractionLLMClient] = None

    @property
    def llm(self) -> ExtractionLLMClient:
        if self._llm is None:
            self._llm = self._llm_client or ExtractionLLMClient(
                model_name=self._llm_model or None,
                max_content_chars=self._max_content_chars,
            )
        return self._llm

    async def run(
        self,
        task_id: str,
        report_documents: list[dict],
        config: ExtractionConfig,
        domain: Optional[str] = None,
        progress_callback: Optional[StepCallback] = None,
    ) -> PipelineResult:
        """Run the 5-stage pipeline.

        Args:
            task_id: Task identifier.
            report_documents: List of dicts with keys: id, name, kb_id, chunks.
            config: Extraction configuration.
            domain: Domain identifier.
            progress_callback: Optional callback invoked after each step
                completes (for real-time progress updates in the UI).

        Returns:
            PipelineResult with the final merged template sections and metadata.
        """
        start_time = time.time()
        step_summaries: list[dict] = []

        async def _emit(name: str, status: StepStatus, duration: str, detail: str):
            schema = StepStatusSchema(
                name=name,
                status=status,
                duration=duration,
                detail=detail,
            )
            step_summaries.append(schema.model_dump())
            # 立即执行回调（不放入队列），避免流水线中途失败导致状态丢失
            if progress_callback:
                try:
                    await progress_callback(schema)
                except Exception as e:
                    logger.error(f"[Task {task_id}] Progress callback failed: {e}")

        # Context shared across stages
        ctx: dict[str, Any] = {
            "documents": report_documents,
            "_doc_schemas": [],  # Per-doc inferred schemas
            "_task_id": task_id,  # For logging
        }
        
        logger.info(f"[Task {task_id}] Starting extraction pipeline for {len(report_documents)} documents")

        def _fmt(seconds: float) -> str:
            if seconds < 60:
                return f"{int(seconds)}s"
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m}m{s}s"

        # ── Step 0: 文档解析 ──────────────────────────────────────
        t0 = time.time()
        await _emit("文档解析", StepStatus.RUNNING, "", "处理中...")
        try:
            ctx["documents"] = await self._step_parse(ctx)
        except Exception as e:
            await _emit("文档解析", StepStatus.FAILED, _fmt(time.time() - t0), f"错误: {e}")
            raise
        n_chunks = sum(d.get("chunk_count", 0) for d in ctx["documents"])
        await _emit(
            "文档解析", StepStatus.COMPLETED, _fmt(time.time() - t0),
            f"解析 {len(ctx['documents'])} 份文档，共 {n_chunks} 个文本块"
        )

        # ── Step 1: 章节推断（LLM） ───────────────────────────────
        t1 = time.time()
        await _emit("章节推断", StepStatus.RUNNING, _fmt(t1 - start_time), "处理中...")
        try:
            await self._step_infer_schema(ctx, config)
        except Exception as e:
            await _emit("章节推断", StepStatus.FAILED, _fmt(time.time() - t1), f"错误: {e}")
            raise
        doc_schemas = ctx.get("_doc_schemas", [])
        total_secs = sum(len(ds.get("sections", [])) for ds in doc_schemas)
        await _emit(
            "章节推断", StepStatus.COMPLETED, _fmt(time.time() - t1),
            f"从 {len(doc_schemas)} 份文档推断章节结构，共 {total_secs} 个章节"
        )

        # ── Step 2: 元数据抽取（LLM） ─────────────────────────────
        t2 = time.time()
        await _emit("元数据抽取", StepStatus.RUNNING, _fmt(t2 - start_time), "处理中...")
        try:
            enriched = await self._step_extract_metadata(ctx, config)
            # 将 enriched 存入 ctx，使后续步骤（融合、校验）能使用带元数据的章节
            ctx["_enriched_sections"] = enriched
        except Exception as e:
            await _emit("元数据抽取", StepStatus.FAILED, _fmt(time.time() - t2), f"错误: {e}")
            raise
        flat = _flatten_sections(enriched)
        await _emit(
            "元数据抽取", StepStatus.COMPLETED, _fmt(time.time() - t2),
            f"已抽取 {len(flat)} 节模板元数据"
        )

        # ── Step 3: 模板融合（LLM） ──────────────────────────────
        t3 = time.time()
        await _emit("模板融合", StepStatus.RUNNING, _fmt(t3 - start_time), "处理中...")
        try:
            merged = await self._step_merge(ctx, config, domain)
        except Exception as e:
            await _emit("模板融合", StepStatus.FAILED, _fmt(time.time() - t3), f"错误: {e}")
            raise
        await _emit(
            "模板融合", StepStatus.COMPLETED, _fmt(time.time() - t3),
            f"融合完成，共 {len(merged.get('sections', []))} 个章节"
        )

        # ── Step 4: 合规校验 ─────────────────────────────────────
        t4 = time.time()
        await _emit("合规校验", StepStatus.RUNNING, _fmt(t4 - start_time), "处理中...")
        try:
            validated = await self._step_validate(ctx, merged)
        except Exception as e:
            await _emit("合规校验", StepStatus.FAILED, _fmt(time.time() - t4), f"错误: {e}")
            raise
        score = validated.get("completeness_score", 50)
        await _emit(
            "合规校验", StepStatus.COMPLETED, _fmt(time.time() - t4),
            f"合规校验完成，完整度 {score}%"
        )

        # ── 最终结果 ─────────────────────────────────────────────
        sections = validated.get("sections", [])
        chapters, total = _count_sections(sections)

        # 检查是否有有效内容，如果没有则报错
        if total == 0:
            # 收集诊断信息，帮助用户定位具体原因
            doc_diagnostics = []
            for doc in ctx.get("_documents", []):
                skip_reason = doc.get("_skip_reason", "")
                chunks = doc.get("chunk_count", 0)
                doc_name = doc.get("name", "?")
                if skip_reason:
                    doc_diagnostics.append(f"  - {doc_name}: {skip_reason}")
                elif chunks == 0:
                    doc_diagnostics.append(f"  - {doc_name}: 已连接 RAGFlow 但无文本块（解析可能未完成）")
                else:
                    doc_diagnostics.append(f"  - {doc_name}: {chunks} chunks 已获取，但 LLM 未推断出章节")
            schemas_info = ctx.get("_doc_schemas", [])
            schema_diag = f", schemas_inferred: {len(schemas_info)}"

            detail = "; ".join(doc_diagnostics) if doc_diagnostics else "未知原因"
            await _emit("完成", StepStatus.FAILED, _fmt(time.time() - start_time), f"未能从文档中提取任何章节。诊断: {detail}")
            raise ValueError(
                f"Pipeline failed: no sections extracted. "
                f"Diagnostics: {detail}{schema_diag}. "
                f"Task ID: {task_id}, docs: {len(report_documents)}"
            )

        await _emit(
            "完成", StepStatus.COMPLETED, _fmt(time.time() - start_time),
            f"所有阶段完成，共 {chapters} 章 / {total} 节"
        )

        return PipelineResult(
            sections=sections,
            cross_section_rules=validated.get("cross_section_rules", []),
            completeness_score=score,
            chapters=chapters,
            total_sections=total,
            step_summaries=step_summaries,
        )

    # ── Step 0: 文档解析 ─────────────────────────────────────────

    async def _step_parse(self, ctx: dict[str, Any]) -> list[dict]:
        """Step 0: 通过 RAGFlow API 获取文本块。"""
        from app.extensions.knowledge.client import RAGFlowClient
        from app.extensions.models import KnowledgeBase, Document
        from sqlalchemy import select
        from app.extensions.database import get_db_context

        documents = ctx["documents"]
        enriched = []
        total_chunks = 0

        logger.info(f"[Task {ctx.get('_task_id', 'unknown')}] Step 0: 开始解析 {len(documents)} 份文档")

        for doc in documents:
            doc_id = doc.get("id")
            kb_id = doc.get("kb_id")
            doc_name = doc.get("name", "未知文档")
            logger.info(f"[Task {ctx.get('_task_id', 'unknown')}] 处理文档: {doc_name} (id={doc_id}, kb_id={kb_id})")
            
            if not doc_id or not kb_id:
                logger.warning(f"文档 {doc_name} 缺少 id 或 kb_id，跳过")
                enriched.append({**doc, "chunks": [], "chunk_count": 0, "_skip_reason": "缺少 id 或 kb_id"})
                continue

            try:
                # 优先使用调用方传入的 RAGFlow ID，避免冗余 DB 查询
                rf_doc_id = doc.get("ragflow_document_id")
                rf_dataset_id = doc.get("ragflow_dataset_id")

                # 如果调用方未传入，则查询 DB 作为回退
                if not rf_doc_id or not rf_dataset_id:
                    kb = None
                    doc_obj = None
                    async with get_db_context() as db:
                        result = await db.execute(
                            select(KnowledgeBase, Document)
                            .join(Document, Document.knowledge_base_id == KnowledgeBase.id)
                            .where(Document.id == doc_id)
                        )
                        row = result.first()
                        if row:
                            kb, doc_obj = row
                        else:
                            result = await db.execute(
                                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                            )
                            kb = result.scalar_one_or_none()
                    if not kb:
                        logger.warning(f"知识库 {kb_id} 不存在，跳过文档 {doc_name}")
                        enriched.append({**doc, "chunks": [], "chunk_count": 0, "_skip_reason": f"知识库 {kb_id} 不存在"})
                        continue
                    rf_doc_id = rf_doc_id or (doc_obj.ragflow_document_id if doc_obj else None)
                    rf_dataset_id = rf_dataset_id or kb.ragflow_dataset_id

                if not rf_dataset_id:
                    logger.warning(f"知识库 (id={kb_id}) 没有配置 ragflow_dataset_id，无法获取 chunks")
                    enriched.append({**doc, "chunks": [], "chunk_count": 0, "_skip_reason": "知识库未配置 RAGFlow"})
                    continue

                if not rf_doc_id:
                    logger.warning(f"文档 {doc_name} 没有 ragflow_document_id，跳过 chunks 获取")
                    enriched.append({**doc, "chunks": [], "chunk_count": 0, "_skip_reason": "文档未上传到 RAGFlow"})
                    continue

                logger.info(f"[Task {ctx.get('_task_id', 'unknown')}] 调用 RAGFlow API 获取 chunks: dataset={rf_dataset_id}, doc={rf_doc_id}")
                rf = RAGFlowClient()
                chunks_resp = await rf.list_chunks(
                    dataset_id=rf_dataset_id,
                    document_id=rf_doc_id,
                    page=1,
                    size=1000,
                )
                chunks = chunks_resp.get("data", {}).get("chunks", [])
                logger.info(f"[Task {ctx.get('_task_id', 'unknown')}] RAGFlow 返回 {len(chunks)} 个 chunks for doc {doc_name}")

                total_chunks += len(chunks)
                if not chunks:
                    logger.warning(f"文档 {doc_name} 在 RAGFlow 中没有 chunks - 报告可能尚未解析完成")
                    enriched.append({**doc, "chunks": chunks, "chunk_count": len(chunks), "_skip_reason": "无 chunks"})
                else:
                    enriched.append({**doc, "chunks": chunks, "chunk_count": len(chunks), "ragflow_document_id": rf_doc_id})
            except Exception as e:
                logger.error(f"[Task {ctx.get('_task_id', 'unknown')}] 获取文档 {doc_name} 的 chunks 失败: {e}")
                enriched.append({**doc, "chunks": [], "chunk_count": 0, "_skip_reason": f"错误: {str(e)}"})

        ctx["_documents"] = enriched
        logger.info(f"[Task {ctx.get('_task_id', 'unknown')}] Step 0 完成: 处理了 {len(enriched)} 份文档，共 {total_chunks} 个 chunks")
        return enriched

    # ── Step 1: 章节推断 ─────────────────────────────────────────

    async def _step_infer_schema(
        self, ctx: dict[str, Any], config: ExtractionConfig
    ) -> None:
        """LLM 从文档内容推断章节树，动态适配不同报告类型。"""
        documents = ctx.get("_documents", [])
        if not documents:
            logger.warning(f"[Task {ctx.get('_task_id', 'unknown')}] Step 1: 没有文档，跳过")
            ctx["_doc_schemas"] = []
            return

        all_doc_schemas: list[dict] = []
        loop = asyncio.get_event_loop()
        task_id = ctx.get("_task_id", "unknown")

        logger.info(f"[Task {task_id}] Step 1: 开始章节推断，处理 {len(documents)} 份文档")

        for doc in documents:
            doc_name = doc.get("name", "未知文档")
            doc_id = doc.get("id", "unknown")
            chunks = doc.get("chunks", [])
            chunk_count = doc.get("chunk_count", 0)
            skip_reason = doc.get("_skip_reason", "")

            if skip_reason:
                logger.warning(f"[Task {task_id}] Step 1: 文档 {doc_name} 被跳过，原因: {skip_reason}")
                continue

            if chunks:
                # 构建结构提示，帮助 LLM 识别章节
                content = _build_structure_hint(chunks, self._max_content_chars)
            else:
                content = doc.get("content", "")

            if not content.strip():
                logger.warning(f"[Task {task_id}] Step 1: 文档 {doc_name} 没有内容，跳过")
                continue

            logger.info(f"[Task {task_id}] Step 1: 正在推断文档 '{doc_name}' (chunks={chunk_count}), content length = {len(content)} chars")

            try:
                logger.info(f"[Task {task_id}] Step 1: 调用 LLM infer_schema...")
                schema = await loop.run_in_executor(
                    None,
                    lambda d=doc_name, c=content: self.llm.infer_schema(d, c)
                )
                logger.info(f"[Task {task_id}] Step 1: LLM infer_schema 返回")
                sections = schema.get("sections", [])
                logger.info(f"[Task {task_id}] Step 1: 从 '{doc_name}' 推断出 {len(sections)} 个章节")

                # Fallback: 若 LLM 未能推断出章节，尝试用自动识别的标题构建章节树
                if not sections and content.strip():
                    logger.warning(f"[Task {task_id}] Step 1: LLM 返回空章节，尝试自动识别标题")
                    auto_headings = _scan_chapter_headings(chunks)
                    if auto_headings:
                        # 用自动识别的标题构建章节
                        sections = []
                        for i, h in enumerate(auto_headings):
                            sections.append({
                                "id": f"sec_{i + 1:02d}",
                                "title": h["title"],
                                "level": h["level_guess"],
                                "required": True,
                                "purpose": f"从{doc_name}自动识别",
                            })
                        logger.info(f"[Task {task_id}] Step 1: 自动识别出 {len(sections)} 个章节")
                    else:
                        logger.warning(f"[Task {task_id}] Step 1: 无自动识别标题，回退为整文档单章节")
                        sections = [{
                            "id": "sec_01",
                            "title": doc_name,
                            "level": 1,
                            "required": True,
                            "purpose": f"从{doc_name}提取的完整内容",
                        }]

                all_doc_schemas.append({
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "sections": sections,
                })
            except Exception as e:
                logger.error(f"[Task {task_id}] Step 1: 文档 '{doc_name}' 章节推断失败: {e}")
                # 即使 LLM 调用异常，也尝试用自动识别的标题构建章节树
                if content.strip():
                    auto_headings = _scan_chapter_headings(chunks)
                    if auto_headings:
                        sections = []
                        for i, h in enumerate(auto_headings):
                            sections.append({
                                "id": f"sec_{i + 1:02d}",
                                "title": h["title"],
                                "level": h["level_guess"],
                                "required": True,
                                "purpose": f"从{doc_name}自动识别",
                            })
                        logger.info(f"[Task {task_id}] Step 1: LLM 异常，自动识别出 {len(sections)} 个章节")
                    else:
                        logger.warning(f"[Task {task_id}] Step 1: LLM 异常且无自动识别标题，回退为单章节")
                        sections = [{
                            "id": "sec_01",
                            "title": doc_name,
                            "level": 1,
                            "required": True,
                            "purpose": f"从{doc_name}提取的完整内容",
                        }]
                    all_doc_schemas.append({
                        "doc_id": doc_id,
                        "doc_name": doc_name,
                        "sections": sections,
                    })
                continue

        logger.info(f"[Task {task_id}] Step 1: 完成，共处理 {len(all_doc_schemas)} 份文档")
        ctx["_doc_schemas"] = all_doc_schemas

    # ── Step 2: 元数据抽取 ──────────────────────────────────────

    async def _step_extract_metadata(
        self, ctx: dict[str, Any], config: ExtractionConfig
    ) -> list[dict]:
        """LLM 逐节抽取 content_contract 等元数据。

        改进：按章节标题匹配文档中的对应内容，而不是简单取第一份文档。
        """
        doc_schemas = ctx.get("_doc_schemas", [])
        if not doc_schemas:
            return []

        # 取第一个有章节的文档作为基础树
        sections = []
        for ds in doc_schemas:
            secs = ds.get("sections", [])
            if secs:
                sections = secs
                break
        if not sections:
            return []

        documents = ctx.get("_documents", [])
        # 构建文档内容映射: {doc_id: {"name": doc_name, "content": full_content, "chunks": [...]}}
        doc_contents: dict[str, dict] = {}
        for doc in documents:
            doc_id = doc.get("id", "")
            chunks = doc.get("chunks", [])
            if chunks:
                full_content = "\n\n".join(
                    c.get("content", "") for c in chunks if c.get("content")
                )
                doc_contents[doc_id] = {
                    "name": doc.get("name", ""),
                    "content": full_content,
                    "chunks": chunks,
                }

        loop = asyncio.get_event_loop()

        def _find_section_content(
            section_title: str,
            section_level: int,
            doc_contents: dict[str, dict],
            max_chars: int = 4000,
        ) -> str:
            """根据章节标题在文档中查找对应的内容段落。

            匹配策略：
            1. 精确匹配章节标题
            2. 模糊匹配（标题关键词）
            3. 基于层级推断（如 "1.1" 匹配第一章第一节内容）
            """
            if not doc_contents:
                return ""

            # 清理标题用于匹配
            clean_title = section_title.strip()

            # 策略1: 在 chunks 中搜索包含该标题的内容块
            for doc_id, doc_data in doc_contents.items():
                chunks = doc_data.get("chunks", [])
                for chunk in chunks:
                    content = chunk.get("content", "")
                    # 精确匹配标题（考虑可能带序号）
                    if clean_title in content:
                        return content[:max_chars]
                    # 匹配无序号的标题
                    title_without_num = clean_title.lstrip("0123456789.、 ")
                    if title_without_num and title_without_num in content[:200]:
                        # 标题出现在内容开头附近，认为是章节开头
                        return content[:max_chars]

            # 策略2: 模糊匹配 - 搜索关键短语的段落
            keywords = _extract_keywords(clean_title)
            if keywords:
                for doc_id, doc_data in doc_contents.items():
                    content = doc_data.get("content", "")
                    # 找包含最多关键词的段落
                    best_match = _find_best_matching_paragraph(content, keywords, max_chars)
                    if best_match:
                        return best_match

            # 策略3: 降级处理 - 返回第一份文档的前 max_chars 字符
            if doc_contents:
                first_doc_content = next(iter(doc_contents.values())).get("content", "")
                return first_doc_content[:max_chars]

            return ""

        async def enrich(sec: dict) -> dict:
            sec_id = sec.get("id", "")
            title = sec.get("title", "")
            level = sec.get("level", 1)
            purpose = sec.get("purpose")

            # 查找与该章节匹配的内容
            section_content = _find_section_content(title, level, doc_contents)

            try:
                metadata = await loop.run_in_executor(
                    None,
                    lambda sid=sec_id, t=title, lv=level, p=purpose, sc=section_content:
                        self.llm.extract_metadata(sid, t, lv, p, sc)
                )
            except Exception as e:
                logger.warning(f"Metadata extraction failed for {sec_id}: {e}")
                metadata = {
                    "content_contract": {
                        "key_elements": [],
                        "structure_type": "narrative_text",
                        "style_rules": None,
                        "min_word_count": None,
                        "forbidden_phrases": [],
                    },
                    "compliance_rules": [],
                    "rag_sources": [],
                    "generation_hint": None,
                    "example_snippet": section_content[:200] if section_content else None,
                    "completeness_score": 50,
                }

            result = {
                **sec,
                "content_contract": metadata.get("content_contract"),
                "compliance_rules": metadata.get("compliance_rules"),
                "rag_sources": metadata.get("rag_sources"),
                "generation_hint": metadata.get("generation_hint"),
                "example_snippet": metadata.get("example_snippet"),
                "completeness_score": metadata.get("completeness_score"),
            }

            children = sec.get("children") or []
            if children:
                result["children"] = [await enrich(c) for c in children]

            return result

        enriched = []
        for sec in sections:
            enriched.append(await enrich(sec))

        return enriched

    # ── Step 3: 模板融合 ─────────────────────────────────────────

    async def _step_merge(
        self,
        ctx: dict[str, Any],
        config: ExtractionConfig,
        domain: Optional[str],
    ) -> dict:
        """多报告章节去重合并。

        优先使用 Step 2 产出的 enriched 章节（带元数据），
        回退到 Step 1 的原始章节结构（仅有骨架）。
        """
        doc_schemas = ctx.get("_doc_schemas", [])
        enriched_sections = ctx.get("_enriched_sections")

        if len(doc_schemas) <= 1:
            # Single doc: use enriched sections (with metadata), fallback to raw sections
            sections = enriched_sections if enriched_sections else (
                doc_schemas[0].get("sections", []) if doc_schemas else []
            )
            logger.info(
                f"Single doc merge: using {'enriched' if enriched_sections else 'raw'} sections, "
                f"{len(sections)} top-level sections"
            )
            return {"sections": sections, "cross_section_rules": []}

        # Multi-doc: use enriched sections for the first doc, raw for others
        sections_list = []
        for i, ds in enumerate(doc_schemas):
            sections = enriched_sections if (i == 0 and enriched_sections) else ds.get("sections", [])
            sections_list.append({
                "doc_name": ds.get("doc_name", "未知"),
                "sections": sections,
            })

        try:
            loop = asyncio.get_event_loop()
            merged = await loop.run_in_executor(
                None,
                lambda: self.llm.merge_sections(domain or "unknown", sections_list)
            )
            logger.info(f"Merged {len(doc_schemas)} docs into {len(merged.get('sections', []))} sections")
            return merged
        except Exception as e:
            logger.warning(f"Section merge failed: {e}, falling back to first doc")
            fallback = enriched_sections if enriched_sections else (
                doc_schemas[0].get("sections", []) if doc_schemas else []
            )
            return {
                "sections": fallback,
                "cross_section_rules": [],
            }

    # ── Step 4: 合规校验 ─────────────────────────────────────────

    async def _step_validate(
        self, ctx: dict[str, Any], merged: dict
    ) -> dict:
        """检查章节完整性，计算完整度评分。"""
        sections = merged.get("sections", [])
        cross_rules = merged.get("cross_section_rules", [])

        if not sections:
            merged["completeness_score"] = 0
            return merged

        flat = _flatten_sections(sections)
        scored = [s for s in flat if s.get("completeness_score")]

        if scored:
            avg_score = sum(s.get("completeness_score", 0) for s in scored) // len(scored)
        else:
            avg_score = 50

        merged["completeness_score"] = avg_score
        return merged
