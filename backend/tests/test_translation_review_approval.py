"""P0 regressions: review approval delivery + task list filters.

容器/宿主真库跑（EXTENSIONS_DB_HOST=localhost 或容器网络）。
"""

import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select

import app.extensions.translation.routers as routers
from app.extensions.database import get_session_factory, init_engine
from app.extensions.models import KnowledgeBase, User
from app.extensions.translation.models import TranslationTask
from app.extensions.translation.routers import (
    BatchTranslateRequest,
    TransitionRequest,
    batch_translate_tasks,
    delete_task,
    download_deliverable,
    get_task_draft,
    list_tasks,
    transition_task,
)

_DRAFT = [{"id": "b0001", "type": "paragraph", "text": "译文草稿", "meta": {}}]


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def _engine():
    await init_engine()
    yield


async def _owner(db) -> uuid.UUID:
    owner = (await db.execute(select(User.id).limit(1))).scalar()
    if owner is None:
        pytest.skip("no users row")
    return owner


async def _mk_kb_task(
    db,
    owner: uuid.UUID,
    *,
    state: str,
    draft: list | None = None,
    lang: str = "en",
    tier: str = "draft",
    kb: KnowledgeBase | None = None,
):
    if kb is None:
        kb = KnowledgeBase(name=f"kb-p0-{uuid.uuid4().hex[:8]}", owner_id=owner, kb_type="ragflow")
        db.add(kb)
        await db.flush()
    task = TranslationTask(
        kb_id=kb.id,
        doc_sha=uuid.uuid4().hex + uuid.uuid4().hex,
        source_uri="/data/p0.docx",
        source_lang=lang,
        quality_tier=tier,
        state=state,
        draft_blocks=draft,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return kb, task


async def _cleanup(db, kb_id, task_id) -> None:
    await db.execute(delete(TranslationTask).where(TranslationTask.id == task_id))
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_review_approval_indexes_draft_and_delivers(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    called: dict = {}

    async def _fake_index(task, zh_blocks, source_blocks):
        called["task_id"] = task.id
        called["blocks"] = zh_blocks

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)
    monkeypatch.setattr(routers, "index_translation", _fake_index)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="exceeded", draft=_DRAFT)
        try:
            resp = await transition_task(task.id, TransitionRequest(target="indexed"), SimpleNamespace(id=owner), db)
            assert resp["state"] == "delivered"
            assert called["task_id"] == task.id
            assert called["blocks"] == _DRAFT
            await db.refresh(task)
            assert task.state == "delivered"
        finally:
            await _cleanup(db, kb.id, task.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_review_approval_without_draft_is_rejected(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="exceeded", draft=None)
        try:
            with pytest.raises(HTTPException) as exc:
                await transition_task(task.id, TransitionRequest(target="indexed"), SimpleNamespace(id=owner), db)
            assert exc.value.status_code == 409
            await db.refresh(task)
            assert task.state == "exceeded"
        finally:
            await _cleanup(db, kb.id, task.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_review_approval_index_failure_reverts_to_exceeded(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    async def _boom(task, zh_blocks, source_blocks):
        raise RuntimeError("ragflow down")

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)
    monkeypatch.setattr(routers, "index_translation", _boom)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="exceeded", draft=_DRAFT)
        try:
            with pytest.raises(HTTPException) as exc:
                await transition_task(task.id, TransitionRequest(target="indexed"), SimpleNamespace(id=owner), db)
            assert exc.value.status_code == 502
            await db.refresh(task)
            assert task.state == "exceeded"  # 可重试，不丢草稿
            assert task.draft_blocks == _DRAFT
        finally:
            await _cleanup(db, kb.id, task.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_list_tasks_filters_language_and_quality_tier(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, en_task = await _mk_kb_task(db, owner, state="delivered", lang="en", tier="draft")
        _, fr_task = await _mk_kb_task(db, owner, state="delivered", lang="fr", tier="reviewed", kb=kb)
        try:
            resp = await list_tasks(
                page=1,
                page_size=50,
                kb_id=kb.id,
                folder_id=None,
                state=None,
                source_lang="fr",
                quality_tier="reviewed",
                q=None,
                current_user=SimpleNamespace(id=owner),
                db=db,
            )
            assert resp["total"] == 1
            assert resp["items"][0]["id"] == str(fr_task.id)
            assert resp["items"][0]["source_lang"] == "fr"
            assert resp["items"][0]["quality_tier"] == "reviewed"

            with pytest.raises(HTTPException) as exc:
                await list_tasks(
                    page=1,
                    page_size=50,
                    kb_id=kb.id,
                    folder_id=None,
                    state=None,
                    source_lang="de",
                    quality_tier=None,
                    q=None,
                    current_user=SimpleNamespace(id=owner),
                    db=db,
                )
            assert exc.value.status_code == 400
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.id.in_([en_task.id, fr_task.id])))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_task_draft_endpoint_pairs_source_and_translation(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="exceeded", draft=_DRAFT)
        task.draft_source_blocks = [{"id": "b0001", "type": "paragraph", "text": "源文"}]
        task.uncertainty = [{"block": "b0001", "spans": ["某段"]}]
        await db.commit()
        try:
            resp = await get_task_draft(task.id, SimpleNamespace(id=owner), db)
            assert resp["translated"] == _DRAFT
            assert resp["source"][0]["text"] == "源文"
            assert resp["uncertainty"][0]["block"] == "b0001"
        finally:
            await _cleanup(db, kb.id, task.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_batch_translate_queues_stored_and_failed(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, stored = await _mk_kb_task(db, owner, state="stored")
        _, failed = await _mk_kb_task(db, owner, state="failed", kb=kb)
        _, delivered = await _mk_kb_task(db, owner, state="delivered", kb=kb)
        try:
            resp = await batch_translate_tasks(
                BatchTranslateRequest(task_ids=[stored.id, failed.id, delivered.id, stored.id]),
                SimpleNamespace(id=owner),
                db,
            )
            assert resp["queued"] == 2
            assert resp["skipped"] == [{"task_id": str(delivered.id), "reason": "state:delivered"}]
            await db.refresh(stored)
            await db.refresh(failed)
            await db.refresh(delivered)
            assert stored.state == "pending"
            assert failed.state == "pending"
            assert delivered.state == "delivered"
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.id.in_([stored.id, failed.id, delivered.id])))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_task_offlines_ragflow_docs_and_archives(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    class _FakeClient:
        def __init__(self):
            self.deleted: list[tuple[str, str]] = []

        async def delete_document(self, dataset_id: str, document_id: str) -> None:
            self.deleted.append((dataset_id, document_id))

    fake = _FakeClient()
    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)
    monkeypatch.setattr(routers, "RAGFlowClient", lambda: fake)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="delivered")
        kb.ragflow_dataset_id = "ds-p1"
        task.ragflow_source_doc_id = "src-1"
        task.ragflow_zh_doc_id = "zh-1"
        await db.commit()
        try:
            resp = await delete_task(task.id, SimpleNamespace(id=owner), db)
            assert resp["state"] == "archived"
            assert ("ds-p1", "src-1") in fake.deleted
            assert ("ds-p1", "zh-1") in fake.deleted
            await db.refresh(task)
            assert task.state == "archived"
        finally:
            await _cleanup(db, kb.id, task.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_s3_deliverable_download_uses_storage_provider(_engine, monkeypatch):
    async def _fake_superadmin(db, user_id):
        return True

    fd, tmp_name = tempfile.mkstemp(suffix=".md")
    Path(tmp_name).write_text("远程交付物", encoding="utf-8")
    import os

    os.close(fd)

    class _FakeStorage:
        async def download_to_temp(self, uri: str) -> Path:
            return Path(tmp_name)

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)
    monkeypatch.setattr(routers, "get_storage_provider", lambda: _FakeStorage())

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="delivered")
        task.deliverable_uri = "s3://bucket/key.md"
        await db.commit()
        try:
            resp = await download_deliverable(task.id, SimpleNamespace(id=owner), db)
            assert Path(resp.path) == Path(tmp_name)
            assert resp.background is not None
        finally:
            await _cleanup(db, kb.id, task.id)
            Path(tmp_name).unlink(missing_ok=True)


@pytest.mark.asyncio(loop_scope="session")
async def test_task_stats_and_folder_move(_engine, monkeypatch):
    """P2-16: 任务页指标聚合 + 拖拽移动 folder_id。"""
    from app.extensions.translation.models import TltFolder
    from app.extensions.translation.routers import TaskFolderPatch, patch_task_folder, task_stats

    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, delivered = await _mk_kb_task(db, owner, state="delivered")
        _, running = await _mk_kb_task(db, owner, state="running", kb=kb)
        folder = TltFolder(name=f"p2-{uuid.uuid4().hex[:8]}", parent_id=None)
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        try:
            stats = await task_stats(kb_id=kb.id, current_user=SimpleNamespace(id=owner), db=db)
            assert stats["total"] == 2
            assert stats["delivered"] == 1
            assert stats["running"] == 1

            moved = await patch_task_folder(delivered.id, TaskFolderPatch(folder_id=folder.id), SimpleNamespace(id=owner), db)
            assert moved["folder_id"] == str(folder.id)
            await db.refresh(delivered)
            assert delivered.folder_id == folder.id

            moved_root = await patch_task_folder(delivered.id, TaskFolderPatch(folder_id=None), SimpleNamespace(id=owner), db)
            assert moved_root["folder_id"] is None
        finally:
            await db.execute(delete(TranslationTask).where(TranslationTask.id.in_([delivered.id, running.id])))
            await db.execute(delete(TltFolder).where(TltFolder.id == folder.id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_backfill_job_batches_stored_tasks(_engine, monkeypatch):
    """P2 scheduled backfill: 每 tick 放一批，游标耗尽后 done。"""
    from app.extensions.translation.models import TltBackfillJob
    from app.extensions.translation.worker import run_backfill_tick

    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, first = await _mk_kb_task(db, owner, state="stored")
        tasks = [first]
        for _ in range(4):
            _, task = await _mk_kb_task(db, owner, state="stored", kb=kb)
            tasks.append(task)
        _, delivered = await _mk_kb_task(db, owner, state="delivered", kb=kb)
        job = TltBackfillJob(
            kb_id=kb.id,
            owner_id=owner,
            task_ids=[str(task.id) for task in tasks] + [str(delivered.id)],
            chunk_size=2,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        try:
            for _ in range(8):
                await run_backfill_tick(str(job.id))
                await db.refresh(job)
                if job.state == "done":
                    break
            assert job.state == "done"
            assert job.cursor == 6
            for task in tasks:
                await db.refresh(task)
                assert task.state == "pending"
            await db.refresh(delivered)
            assert delivered.state == "delivered"
        finally:
            await db.execute(delete(TltBackfillJob).where(TltBackfillJob.id == job.id))
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb.id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_backfill_job_create_list_cancel(_engine, monkeypatch):
    """P2 backfill API：显式 id 过滤非 eligible、列表、取消。"""
    from app.extensions.translation.models import TltBackfillJob
    from app.extensions.translation.routers import (
        BackfillJobCreate,
        cancel_backfill_job,
        create_backfill_job,
        list_backfill_jobs,
    )

    async def _fake_superadmin(db, user_id):
        return True

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, a = await _mk_kb_task(db, owner, state="stored")
        _, b = await _mk_kb_task(db, owner, state="failed", kb=kb)
        _, delivered = await _mk_kb_task(db, owner, state="delivered", kb=kb)
        try:
            created = await create_backfill_job(
                BackfillJobCreate(task_ids=[a.id, b.id, delivered.id], chunk_size=10),
                SimpleNamespace(id=owner),
                db,
            )
            assert created["total"] == 2

            listing = await list_backfill_jobs(20, SimpleNamespace(id=owner), db)
            assert any(item["id"] == created["id"] for item in listing["items"])

            cancelled = await cancel_backfill_job(uuid.UUID(created["id"]), SimpleNamespace(id=owner), db)
            assert cancelled["state"] == "cancelled"
        finally:
            await db.execute(delete(TltBackfillJob).where(TltBackfillJob.kb_id == kb.id))
            await db.execute(delete(TranslationTask).where(TranslationTask.kb_id == kb.id))
            await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb.id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_reviewed_mtpe_requires_gate_pass_and_delivers_edited_draft(_engine, monkeypatch):
    """P2 MTPE: reviewed 档交付前复检；人工修正数字后交付编辑稿。"""
    from app.extensions.translation.routers import DraftUpdateBody, update_task_draft

    async def _fake_superadmin(db, user_id):
        return True

    called: dict = {}

    async def _fake_index(task, zh_blocks, source_blocks):
        called["blocks"] = zh_blocks

    monkeypatch.setattr(routers, "is_superadmin", _fake_superadmin)
    monkeypatch.setattr(routers, "index_translation", _fake_index)

    async with get_session_factory()() as db:
        owner = await _owner(db)
        kb, task = await _mk_kb_task(db, owner, state="exceeded", tier="reviewed")
        task.draft_source_blocks = [{"id": "b0001", "type": "paragraph", "text": "Output is 42 tonnes."}]
        task.draft_blocks = [{"id": "b0001", "type": "paragraph", "text": "Output is 43 tonnes.", "meta": {}}]
        await db.commit()
        try:
            with pytest.raises(HTTPException) as exc:
                await transition_task(task.id, TransitionRequest(target="indexed"), SimpleNamespace(id=owner), db)
            assert exc.value.status_code == 409
            await db.refresh(task)
            assert task.state == "exceeded"
            assert task.gate_failures and "numeric" in task.gate_failures

            saved = await update_task_draft(
                task.id,
                DraftUpdateBody(blocks=[{"id": "b0001", "text": "Output is 42 tonnes."}]),
                SimpleNamespace(id=owner),
                db,
            )
            assert saved["gate_failures"] == {}
            await db.refresh(task)
            assert task.draft_edited_at is not None
            assert task.draft_blocks_original
            assert task.draft_blocks_original[0]["text"] == "Output is 43 tonnes."

            resp = await transition_task(task.id, TransitionRequest(target="indexed"), SimpleNamespace(id=owner), db)
            assert resp["state"] == "delivered"
            assert called["blocks"][0]["text"] == "Output is 42 tonnes."
        finally:
            await _cleanup(db, kb.id, task.id)
