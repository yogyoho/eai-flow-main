"""Delivery-contract gate for present_files (bug-2225, EAI-CUSTOM).

Covers the gate in ``deerflow.tools.builtins.present_file_tool``: threads whose
outputs/ carries a ``.delivery-contract`` marker may only present the pipeline
deliverable ``.md`` named in ``outputs/delivery_manifest.json``; threads without
the marker are entirely unaffected. The gate must fire before the bug-1145
docmgr-sync callback block.

Also covers the app-layer twin gates (Task 4):
``app.extensions.workspace.sandbox_sync._pipeline_allowed_md_name`` and its wiring
into ``sync_sandbox_outputs``' outputs loop.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import app.extensions.workspace.sandbox_sync as sandbox_sync
from app.extensions.models import AIDocument
from app.extensions.workspace.models import CollabProject

# importlib (not ``import ... as``): the builtins package __init__ re-exports the
# StructuredTool ``present_file_tool`` under the same name as this submodule, so an
# ``import x.y.present_file_tool as m`` binds the tool, not the module.
present_file_tool_module = importlib.import_module("deerflow.tools.builtins.present_file_tool")
present_file_tool = present_file_tool_module.present_file_tool

DELIVERABLE_NAME = "X-勘探-地质勘查报告.md"


def _make_runtime(outputs_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        state={"thread_data": {"outputs_path": str(outputs_dir)}},
        context={"thread_id": "thread-gate-1"},
        config={},
    )


def _patch_docmgr_sync(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Keep the bug-1145 callback fire hermetic and observable.

    The registry is normally empty in unit tests (app registers at startup),
    but patching guarantees isolation from any other test that registers a
    callback, and lets rejection tests assert the gate fires *before* sync.
    """
    sync = AsyncMock(return_value=[])
    monkeypatch.setattr(present_file_tool_module, "fire_present_files_callbacks", sync)
    return sync


def _write_contract(outputs_dir: Path, deliverable: str | None = DELIVERABLE_NAME) -> None:
    """Plant the ingest-time contract marker and (optionally) the build manifest."""
    (outputs_dir / present_file_tool_module.DELIVERY_CONTRACT_NAME).write_text("{}", encoding="utf-8")
    if deliverable is not None:
        manifest = {"bug": 2225, "deliverable": deliverable, "sha256": "ab" * 32, "bytes": 8, "formula_state_sha256": "cd" * 32, "chapters": []}
        (outputs_dir / present_file_tool_module.DELIVERY_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
class TestPresentFilesGate:
    async def test_no_marker_passthrough(self, tmp_path, monkeypatch):
        """Unmarked threads are entirely outside the gate: any .md presents normally."""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        hand_made = outputs_dir / "hand_made.md"
        hand_made.write_text("# hand-made", encoding="utf-8")

        result = await present_file_tool.coroutine(
            runtime=_make_runtime(outputs_dir),
            filepaths=[str(hand_made)],
            tool_call_id="t1",
        )

        assert result.update["messages"][0].content == "Successfully presented files"
        assert result.update["artifacts"] == ["/mnt/user-data/outputs/hand_made.md"]

    async def test_marker_without_manifest_rejected(self, tmp_path, monkeypatch):
        """Marker but no manifest means the pipeline never built — hand-made .md is rejected."""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir, deliverable=None)
        hand_made = outputs_dir / "hand_made.md"
        hand_made.write_text("# hand-made", encoding="utf-8")
        sync = _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(
            runtime=_make_runtime(outputs_dir),
            filepaths=[str(hand_made)],
            tool_call_id="t2",
        )

        content = result.update["messages"][0].content
        assert "交付门 FAIL" in content
        assert "build_output.py" in content
        assert "BUILD_READY" in content
        assert "artifacts" not in result.update
        sync.assert_not_awaited()  # gate sits before the bug-1145 docmgr sync

    async def test_manifest_deliverable_and_json_pass(self, tmp_path, monkeypatch):
        """Marked thread: the manifest deliverable plus non-.md files pass untouched."""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir)
        deliverable = outputs_dir / DELIVERABLE_NAME
        deliverable.write_text("# 报告", encoding="utf-8")
        note = outputs_dir / "note.json"
        note.write_text("{}", encoding="utf-8")
        _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(
            runtime=_make_runtime(outputs_dir),
            filepaths=[str(deliverable), str(note)],
            tool_call_id="t3",
        )

        assert result.update["messages"][0].content == "Successfully presented files"
        assert result.update["artifacts"] == [
            f"/mnt/user-data/outputs/{DELIVERABLE_NAME}",
            "/mnt/user-data/outputs/note.json",
        ]

    async def test_deliverable_plus_rogue_md_rejected(self, tmp_path, monkeypatch):
        """Marked thread with manifest: a rogue .md alongside the deliverable is rejected."""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir)
        deliverable = outputs_dir / DELIVERABLE_NAME
        deliverable.write_text("# 报告", encoding="utf-8")
        hand_made = outputs_dir / "hand_made.md"
        hand_made.write_text("# hand-made", encoding="utf-8")
        sync = _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(
            runtime=_make_runtime(outputs_dir),
            filepaths=[str(deliverable), str(hand_made)],
            tool_call_id="t4",
        )

        content = result.update["messages"][0].content
        assert "交付门 FAIL" in content
        assert "hand_made.md" in content
        assert DELIVERABLE_NAME in content
        assert "artifacts" not in result.update
        sync.assert_not_awaited()


class TestSandboxSyncAllowedMd:
    """bug-2225 sandbox_sync 门：契约线程仅 manifest.deliverable 可同步进 workspace 文档。"""

    def test_no_marker_returns_star(self, tmp_path):
        """无契约 → "*"（不设限，维持原 report.md 字面规则）。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "report.md").write_text("# r", encoding="utf-8")

        assert sandbox_sync._pipeline_allowed_md_name(outputs_dir) == "*"

    def test_marker_with_manifest_returns_deliverable(self, tmp_path):
        """契约 + manifest → 唯一放行名 = manifest.deliverable。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir)

        assert sandbox_sync._pipeline_allowed_md_name(outputs_dir) == DELIVERABLE_NAME

    def test_marker_without_or_corrupt_manifest_returns_none(self, tmp_path):
        """契约无 manifest（管线从未 build）与损坏 manifest（凭据无效）都 → None（.md 全禁）。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir, deliverable=None)
        assert sandbox_sync._pipeline_allowed_md_name(outputs_dir) is None

        (outputs_dir / "delivery_manifest.json").write_text("{corrupt json", encoding="utf-8")
        assert sandbox_sync._pipeline_allowed_md_name(outputs_dir) is None

    @pytest.mark.asyncio
    async def test_sync_skips_rogue_and_syncs_deliverable(self, tmp_path, monkeypatch):
        """集成：契约线程 sync 只吃 deliverable，rogue .md 不同步进文档。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir)
        (outputs_dir / DELIVERABLE_NAME).write_text("# 报告", encoding="utf-8")
        (outputs_dir / "hand_made.md").write_text("# hand-made", encoding="utf-8")

        async def fake_resolve_outputs_dir(_thread_id, _owner_user_id):
            return outputs_dir

        pushed: list[str] = []

        async def fake_push_version(_db, _doc_id, content):
            pushed.append(content)

        monkeypatch.setattr(sandbox_sync, "_resolve_outputs_dir", fake_resolve_outputs_dir)
        monkeypatch.setattr(sandbox_sync, "_push_version", fake_push_version)

        project_id = uuid4()
        project = SimpleNamespace(kind="quickdoc", doc_id=uuid4())
        doc = SimpleNamespace(content="")

        class _FakeDB:
            async def get(self, model, _pk):
                if model is CollabProject:
                    return project
                if model is AIDocument:
                    return doc
                return None

            async def flush(self):
                pass

        result = await sandbox_sync.sync_sandbox_outputs(_FakeDB(), project_id, "thread-gate-1", "user-1", "agent")

        assert result == {"synced": 1, "skipped": 0}
        assert doc.content == "# 报告"  # deliverable 同步进文档；rogue 未覆盖
        assert pushed == ["# 报告"]  # 版本推送也只发生一次（rogue 被跳过）
