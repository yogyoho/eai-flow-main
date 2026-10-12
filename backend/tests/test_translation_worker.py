"""Worker tests (T4): state machine edges with injected fake translator/indexer.

在容器内跑（真实 postgres；engine 绑 session 循环）。
"""

import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask
from app.extensions.translation.worker import (
    _claim_next_task,
    boot_recovery,
    run_task,
)


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


class FakeTranslator:
    """可编程 fake：fail_blocks 丢弃占位符令牌（制造数值违例——顺带证明占位符机制挡住了天真篡改）。"""

    def __init__(self, mapping: dict[str, str] | None = None, fail_blocks: set[str] | None = None):
        self.mapping = mapping or {}
        self.fail_blocks = fail_blocks or set()
        self.calls: list[str] = []

    async def translate_block(self, block_id: str, text: str, source_lang: str) -> dict:
        self.calls.append(block_id)
        if block_id in self.fail_blocks:
            import re

            return {"translation": re.sub(r"⟦#\d+⟧", "", text), "uncertain": False, "low_confidence_spans": []}
        return {"translation": self.mapping.get(block_id, text), "uncertain": False, "low_confidence_spans": []}


async def _owner_id(db) -> uuid.UUID:
    uid = (await db.execute(select(User.id).limit(1))).scalar()
    if uid is None:
        pytest.skip("no users row")
    return uid


async def _mk_task(db, owner: uuid.UUID, file_path: str, sha: str | None = None) -> tuple[KnowledgeBase, TranslationTask]:
    kb = KnowledgeBase(name=f"tlt-worker-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow", translation_enabled=True)
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    task = TranslationTask(
        kb_id=kb.id,
        doc_sha=sha or hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        source_uri=file_path,
        source_lang="en",
        state="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return kb, task


async def _cleanup(db, kb_id) -> None:
    await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb_id))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()


def _write_docx(tmp_path, text="Output was 42 tonnes in the report.") -> str:
    from docx import Document

    p = tmp_path / "w.docx"
    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(p))
    return str(p)


async def _noop_index(task, zh_blocks, source_blocks) -> None:
    return None


@pytest.mark.asyncio(loop_scope="session")
async def test_happy_path_pending_to_delivered(_engine, tmp_path):
    """pending → running → indexed → delivered（fake translator 原样、noop 索引）。"""
    fp = _write_docx(tmp_path)
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, fp)
        task_id = str(task.id)
        try:
            final = await run_task(task_id, translator=FakeTranslator(), index_fn=_noop_index)
            assert final == "delivered"
            await db.refresh(task)
            assert task.state == "delivered"
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_numeric_gate_failure_goes_to_exceeded(_engine, tmp_path):
    """数值轴失败且重生成仍失败 → retrying×2 → exceeded（R2-1）。"""
    fp = _write_docx(tmp_path, text="Output was 42 tonnes in the report.")
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, fp)
        task_id = str(task.id)
        try:
            # fake 丢弃数字令牌（数值违例）且永不悔改 → retrying×2 → exceeded
            final = await run_task(task_id, translator=FakeTranslator(fail_blocks={"b0001"}), index_fn=_noop_index)
            assert final == "exceeded"
            await db.refresh(task)
            assert task.state == "exceeded"
            assert task.gate_failures and "numeric" in task.gate_failures
            assert task.retry_count == 0  # 机检重试计数在 attempt，非 retry_count
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_infra_failure_retries_then_fails(_engine, tmp_path):
    """解析文件缺失=基础设施失败 → 3 次后 failed 终态（R7 失败链）。"""
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, "/nonexistent/missing.docx")
        task_id = str(task.id)
        try:
            for _ in range(3):
                final = await run_task(task_id, translator=FakeTranslator(), index_fn=_noop_index)
            assert final == "failed"
            await db.refresh(task)
            assert task.state == "failed"
            assert task.error_detail["phase"] == "parse"
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_superseded_task_aborts(_engine, tmp_path):
    """superseded 任务起点即中止（R3-1）。"""
    fp = _write_docx(tmp_path)
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, fp)
        task_id = str(task.id)
        task.state = "superseded"
        await db.commit()
        try:
            final = await run_task(task_id, translator=FakeTranslator(), index_fn=_noop_index)
            assert final == "superseded"
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_claim_sets_running_and_skips_locked(_engine, tmp_path):
    """claim：pending → running；无 pending 时返回 None（D16 槽位领取）。"""
    fp = _write_docx(tmp_path)
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, fp)
        task_id = str(task.id)
        try:
            claimed = await _claim_next_task()
            assert claimed == task_id
            await db.refresh(task)
            assert task.state == "running"
            # 再 claim：无其他 pending → None
            assert await _claim_next_task() is None
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_boot_recovery_resets_running(_engine, tmp_path):
    """boot recovery：遗留 running → pending（D18/R7）。"""
    fp = _write_docx(tmp_path)
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, fp)
        task.state = "running"
        await db.commit()
        try:
            await boot_recovery()
            await db.refresh(task)
            assert task.state == "pending"
        finally:
            await _cleanup(db, kb.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_terminology_gate_goes_to_exceeded(_engine, tmp_path):
    """术语轴失败（非数值类）→ 不重生成 → exceeded（R2-1）。"""
    fp = _write_docx(tmp_path, text="ArcelorMittal signed the contract with 42 clauses.")
    async with get_session_factory()() as db:
        owner = await _owner_id(db)
        kb, task = await _mk_task(db, owner, fp)
        task_id = str(task.id)
        try:
            from app.extensions.translation.glossary import Glossary

            class RenamingTranslator(FakeTranslator):
                async def translate_block(self, block_id, text, source_lang):
                    # 把不译清单词改掉（术语轴违例；非数值类不重生成）
                    return {"translation": text.replace("ArcelorMittal", "安赛乐"), "uncertain": False, "low_confidence_spans": []}

            final = await run_task(
                task_id,
                translator=RenamingTranslator(),
                index_fn=_noop_index,
                glossary=Glossary(dont_translate={"ArcelorMittal"}),
            )
            assert final == "exceeded"
        finally:
            await _cleanup(db, kb.id)
