"""Delivery-contract gate for present_files (bug-2225, EAI-CUSTOM).

Covers the gate in ``deerflow.tools.builtins.present_file_tool``: threads whose
outputs/ carries a ``.delivery-contract`` marker may only present the pipeline
deliverable ``.md`` named in ``outputs/delivery_manifest.json``; threads without
the marker are entirely unaffected. The gate must fire before the bug-1145
docmgr-sync callback block.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
