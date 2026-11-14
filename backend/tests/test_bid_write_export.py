"""批三十三：批准修订 → DOCX 交付包（切册/manifest/门禁/审计）。"""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.bid_write import approval, crud, models
from app.extensions.bid_write import export as EX
from app.extensions.bid_write import routers as R
from app.extensions.bid_write.executor.editor import prepare_editor_ctx
from app.extensions.database import Base, get_db
from app.extensions.workflow import subject_approval as SA

NOW = datetime(2026, 11, 15, 0, 0, tzinfo=UTC)


def _para(text: str, *, slot: str = "", label: str = "") -> dict:
    return {
        "type": "para",
        "attrs": {"slot_id": slot, "label": label},
        "content": [{"type": "text", "text": text}],
    }


BUNDLE_AST = {
    "type": "doc",
    "content": [
        {"type": "toc_entry", "attrs": {"title": "目录", "page_placeholder": "—"}},
        {
            "type": "section",
            "attrs": {"level": 1, "title": "一、投标函", "section_id": "S-1"},
            "content": [
                _para("投标总价为人民币 1,280,000.00 元", slot="bl-total"),
                {
                    "type": "locked_paragraph",
                    "attrs": {"template_id": "BID-LOCK-001", "similarity_floor": 0.98},
                    "content": [{"type": "text", "text": "本投标函自开标之日起 90 日内有效。"}],
                },
                {
                    "type": "todo_block",
                    "attrs": {"missing": "法定代表人签字", "pending_item_id": "P-1", "level": "D0", "blocks_export": True},
                },
                {
                    "type": "deviation_note",
                    "attrs": {"row_id": "R-1"},
                    "content": [
                        _para("交货期晚 5 天", label="偏离原因"),
                        _para("增加专车运输", label="替代方案"),
                    ],
                },
            ],
        },
        {
            "type": "section",
            "attrs": {"level": 1, "title": "二、报价表", "section_id": "S-2"},
            "content": [
                {
                    "type": "table",
                    "attrs": {"table_type": "price"},
                    "content": [
                        {
                            "type": "table_row",
                            "attrs": {"row_id": "R-1"},
                            "content": [
                                {"type": "table_cell", "attrs": {"col_role": "name"}, "content": [{"type": "text", "text": "设备 A"}]},
                                {"type": "table_cell", "attrs": {"col_role": "qty"}, "content": [{"type": "text", "text": "4"}]},
                                {"type": "table_cell", "attrs": {"col_role": "unit"}, "content": [{"type": "text", "text": "200000.00"}]},
                                {"type": "amount_cell", "attrs": {"role": "amount"}, "content": [{"type": "text", "text": "800000.00"}]},
                            ],
                        }
                    ],
                },
                _para("详见附件", slot="attach"),
                {"type": "attachment_ref", "attrs": {"attachment_no": "A-1", "anchor": "P.12"}},
            ],
        },
    ],
}

DOC_BLOCKED = {
    "type": "doc",
    "content": [
        {
            "type": "section",
            "attrs": {"level": 1, "title": "一、投标函", "section_id": "S-1"},
            "content": [_para("投标总价待补充", slot="bl-total")],
        }
    ],
}


def _gate(**over) -> dict:
    data = {
        "blocked": False,
        "reasons": [],
        "watermark": "商务风险未确认",
        "assertion_counts": {"PASS": 43},
        "rule_counts": {"FAIL": 0},
        "l1_fatal_fail": [],
        "l4": None,
        "scope_note": "det-only",
        "schema_version": "1.0.0",
        "results": [],
    }
    data.update(over)
    return data


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        models.WriteTask.__table__,
        models.TaskDocument.__table__,
        models.BidWriteDocumentRevision.__table__,
        models.BidWriteExport.__table__,
        models.MatrixRow.__table__,
        models.MaterialEntity.__table__,
        models.MaterialProfile.__table__,
        models.BidWritePolicy.__table__,
        SA.WorkflowSubjectInstance.__table__,
        SA.WorkflowSubjectReview.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _client_as(db, user_id: str):
    app = FastAPI()
    app.include_router(R.router)
    app.dependency_overrides[R.current_owner] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest_asyncio.fixture
async def owner_client(db):
    async with _client_as(db, "u1") as client:
        yield client


async def _seed(db):
    return (await crud.create_task(db, "u1", project_name="测试投标项目")).id


async def _submit(owner_client, task_id, ast, *, reviewers=("u2",)):
    return await owner_client.post(
        f"/api/extensions/bid-write/tasks/{task_id}/approval/submit",
        json={"ast": ast, "schema_version": "0.1.0", "reviewer_ids": list(reviewers)},
    )


async def _approve(db, task_id, revision_id: str):
    async with _client_as(db, "u2") as reviewer:
        state = await reviewer.get(f"/api/extensions/bid-write/tasks/{task_id}/approval")
        instance_id = state.json()["approval"]["instance_id"]
        acted = await reviewer.post(
            f"/api/extensions/bid-write/tasks/{task_id}/approval/action",
            json={"instance_id": instance_id, "action": "approved"},
        )
        assert acted.status_code == 200, acted.text
    revision = await crud.get_revision(db, revision_id, task_id, "u1")
    assert revision is not None and revision.status == "approved"
    return revision


def _clean_snapshot(*_args, **_kwargs):
    return {"status": "ok", "blocked": False, "summary": {"d0": 0, "d1": 0, "d2": 0}}


@pytest.mark.asyncio
async def test_ast_to_markdown_strips_marks_and_renders_blocks():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "section",
                "attrs": {"level": 1, "title": "一、投标函"},
                "content": [
                    {
                        "type": "para",
                        "attrs": {"slot_id": "s1"},
                        "content": [
                            {"type": "text", "text": "金额 "},
                            {
                                "type": "text",
                                "text": "1,280,000.00",
                                "marks": [{"type": "provenance", "attrs": {"clause_id": "C-1"}}],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    md = EX.ast_to_markdown(ast)
    assert "# 一、投标函" in md
    assert "金额 1,280,000.00" in md
    assert "C-1" not in md


@pytest.mark.asyncio
async def test_ast_to_markdown_covers_todo_deviation_table_and_attachment():
    md = EX.ast_to_markdown(BUNDLE_AST)
    assert "【待补·D0】** 法定代表人签字" in md
    assert "**偏离原因：**交货期晚 5 天" in md
    assert "**替代方案：**增加专车运输" in md
    assert "| 设备 A | 4 | 200000.00 | 800000.00 |" in md
    assert "（附件 A-1）" in md
    assert "- 目录 …… —" in md


def test_ast_to_markdown_rejects_unknown_nodes():
    with pytest.raises(ValueError, match="不支持的 AST 节点"):
        EX.ast_to_markdown({"type": "doc", "content": [{"type": "image"}]})


def test_split_volumes_keeps_front_matter_in_first_volume():
    volumes = EX.split_volumes(BUNDLE_AST)
    assert [v.name for v in volumes] == ["一、投标函", "二、报价表"]
    assert volumes[0].ast["content"][0]["type"] == "toc_entry"
    assert [n["type"] for n in volumes[1].ast["content"]] == ["section"]


def test_split_volumes_without_sections_is_single_volume():
    volumes = EX.split_volumes({"type": "doc", "content": [_para("正文")]})
    assert len(volumes) == 1 and volumes[0].name == "正文"


def test_prepare_editor_ctx_overlays_frozen_ast():
    ast = {
        "type": "doc",
        "content": [
            {
                "type": "section",
                "attrs": {"level": 1, "title": "一、投标函"},
                "content": [_para("投标总价为人民币 1,280,000.00 元", slot="bl-total")],
            }
        ],
    }
    ctx = {"products": {"bid_letter": {"slots": {}}}}
    prepared, _meta = prepare_editor_ctx(ctx, ast)
    assert prepared["products"]["bid_letter"]["slots"]["total_amount_num"] == 1280000
    assert "1,280,000.00" in prepared["products"]["bid_letter"]["text"]


def test_bundle_is_deterministic_and_contains_docx_and_manifest():
    task = models.WriteTask(id="t1", owner_id="u1", project_name="测试投标项目", tender_no="T-1")
    revision = models.BidWriteDocumentRevision(
        id="rev-1",
        task_id="t1",
        owner_id="u1",
        revision_no=2,
        ast=BUNDLE_AST,
        schema_version="0.1.0",
        doc_hash=approval.canonical_hash(BUNDLE_AST),
        assertion_snapshot={"status": "ok", "blocked": False},
        status="approved",
    )
    one = EX.build_export_bundle(task=task, revision=revision, gate=_gate(), now=NOW)
    two = EX.build_export_bundle(task=task, revision=revision, gate=_gate(), now=NOW)
    assert one.payload == two.payload
    assert one.sha256 == hashlib.sha256(one.payload).hexdigest()
    assert one.file_count == 2

    with zipfile.ZipFile(io.BytesIO(one.payload)) as zf:
        names = zf.namelist()
        assert names[0] == "manifest.json"
        assert names[1].endswith("一、投标函.docx")
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["revision"]["doc_hash"] == revision.doc_hash
        assert manifest["revision"]["revision_no"] == 2
        assert manifest["export"]["watermark"] == "商务风险未确认"
        assert [f["name"] for f in manifest["files"]] == names[1:]

        with zipfile.ZipFile(io.BytesIO(zf.read(names[1]))) as docx:
            xml = docx.read("word/document.xml").decode("utf-8")
            assert "投标总价为人民币" in xml


@pytest.mark.asyncio
async def test_export_requires_approved_revision(owner_client, db):
    task_id = await _seed(db)
    submitted = await _submit(owner_client, task_id, DOC_BLOCKED)
    assert submitted.status_code == 200, submitted.text
    revision_id = submitted.json()["revision"]["id"]

    resp = await owner_client.post(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}/export")
    assert resp.status_code == 409
    assert "审批通过" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_rejects_submission_snapshot_blocked(owner_client, db):
    task_id = await _seed(db)
    submitted = await _submit(owner_client, task_id, DOC_BLOCKED)
    revision_id = submitted.json()["revision"]["id"]
    await _approve(db, task_id, revision_id)

    resp = await owner_client.post(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}/export")
    assert resp.status_code == 409
    assert "提交审批时" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_reruns_gate_and_blocks(owner_client, db, monkeypatch):
    monkeypatch.setattr(approval, "_assertion_snapshot", _clean_snapshot)
    task_id = await _seed(db)
    submitted = await _submit(owner_client, task_id, DOC_BLOCKED)
    revision_id = submitted.json()["revision"]["id"]
    await _approve(db, task_id, revision_id)

    resp = await owner_client.post(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}/export")
    assert resp.status_code == 409
    assert "导出前置校验" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_tampered_revision_is_rejected(owner_client, db, monkeypatch):
    monkeypatch.setattr(approval, "_assertion_snapshot", _clean_snapshot)
    task_id = await _seed(db)
    submitted = await _submit(owner_client, task_id, BUNDLE_AST)
    revision_id = submitted.json()["revision"]["id"]
    revision = await _approve(db, task_id, revision_id)

    revision.ast = {"type": "doc", "content": [_para("篡改")]}
    await db.commit()

    resp = await owner_client.post(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}/export")
    assert resp.status_code == 409
    assert "哈希" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_returns_zip_and_records_history(owner_client, db, monkeypatch):
    monkeypatch.setattr(approval, "_assertion_snapshot", _clean_snapshot)

    async def fake_gate(ctx, *, ast=None, l4_model_fn=None):
        assert ast is not None
        return _gate()

    monkeypatch.setattr(EX, "run_export_gate", fake_gate)
    task_id = await _seed(db)
    submitted = await _submit(owner_client, task_id, BUNDLE_AST)
    revision_id = submitted.json()["revision"]["id"]
    await _approve(db, task_id, revision_id)

    resp = await owner_client.post(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["x-export-files"] == "2"
    assert resp.headers["x-export-sha256"] == hashlib.sha256(resp.content).hexdigest()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert "manifest.json" in zf.namelist()

    history = await owner_client.get(f"/api/extensions/bid-write/tasks/{task_id}/exports")
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == resp.headers["x-export-id"]
    assert items[0]["file_count"] == 2
    assert items[0]["bundle_sha256"] == resp.headers["x-export-sha256"]


@pytest.mark.asyncio
async def test_export_is_owner_only(owner_client, db, monkeypatch):
    monkeypatch.setattr(approval, "_assertion_snapshot", _clean_snapshot)
    task_id = await _seed(db)
    submitted = await _submit(owner_client, task_id, BUNDLE_AST)
    revision_id = submitted.json()["revision"]["id"]
    await _approve(db, task_id, revision_id)

    async with _client_as(db, "u2") as reviewer:
        resp = await reviewer.post(f"/api/extensions/bid-write/tasks/{task_id}/revisions/{revision_id}/export")
        assert resp.status_code == 404
        assert (await reviewer.get(f"/api/extensions/bid-write/tasks/{task_id}/exports")).status_code == 404
