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


@pytest.mark.asyncio
class TestPresentFilesGateV4:
    """bug-3061 v4 契约: deliverables[] 册集 + aux_md 确认门工件 + version 向前兼容。"""

    def _write_bid_manifest(self, outputs_dir: Path, **extra) -> None:
        (outputs_dir / present_file_tool_module.DELIVERY_CONTRACT_NAME).write_text("{}", encoding="utf-8")
        manifest = {
            "skill": "bid-proposal-writing",
            "version": 1,
            "deliverables": ["整体方案-01-投标函.md", "技术卷-01-总体设计.md", "0-总目录索引.md", "偏离表.md"],
            "aux_md": ["条款清单.md", "补遗diff表.md"],
            "files": {},
        }
        manifest.update(extra)
        (outputs_dir / present_file_tool_module.DELIVERY_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    async def test_bid_booklet_set_passes(self, tmp_path, monkeypatch):
        """正控: bid 册集整套 present 通过(整单判定, 册+索引+副表+门工件全放行)。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        self._write_bid_manifest(outputs_dir)
        paths = []
        for name in ["整体方案-01-投标函.md", "技术卷-01-总体设计.md", "0-总目录索引.md", "条款清单.md"]:
            f = outputs_dir / name
            f.write_text("# x", encoding="utf-8")
            paths.append(str(f))
        sync = _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(runtime=_make_runtime(outputs_dir), filepaths=paths, tool_call_id="v4-1")

        assert "Successfully presented" in result.update["messages"][0].content
        assert len(result.update["artifacts"]) == 4
        sync.assert_awaited_once()

    async def test_stray_md_whole_order_rejected_before_sync(self, tmp_path, monkeypatch):
        """反控: 一处杂散 .md 混入 → 整单拒收且不触发 docmgr 同步(C2 整单语义)。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        self._write_bid_manifest(outputs_dir)
        good = outputs_dir / "技术卷-01-总体设计.md"
        good.write_text("# x", encoding="utf-8")
        stray = outputs_dir / "hand_made.md"
        stray.write_text("# rogue", encoding="utf-8")
        sync = _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(runtime=_make_runtime(outputs_dir), filepaths=[str(good), str(stray)], tool_call_id="v4-2")

        content = result.update["messages"][0].content
        assert "交付门 FAIL" in content and "hand_made.md" in content
        assert "bid-proposal-writing" in content, "错误指引按 skill 名指向对应 build"
        assert "artifacts" not in result.update
        sync.assert_not_awaited()

    async def test_retry_same_manifest_idempotent(self, tmp_path, monkeypatch):
        """重试幂等: 同一 manifest 下重复 present 放行(拒后修正重交场景)。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        self._write_bid_manifest(outputs_dir)
        f = outputs_dir / "整体方案-01-投标函.md"
        f.write_text("# x", encoding="utf-8")
        _patch_docmgr_sync(monkeypatch)

        for _ in range(2):
            result = await present_file_tool.coroutine(runtime=_make_runtime(outputs_dir), filepaths=[str(f)], tool_call_id="v4-3")
            assert "Successfully presented" in result.update["messages"][0].content

    async def test_unknown_version_rejected(self, tmp_path, monkeypatch):
        """3A 向前兼容: version 高于平台支持 → 显式报错(不留拒/放歧义)。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        self._write_bid_manifest(outputs_dir, version=99)
        f = outputs_dir / "整体方案-01-投标函.md"
        f.write_text("# x", encoding="utf-8")
        sync = _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(runtime=_make_runtime(outputs_dir), filepaths=[str(f)], tool_call_id="v4-4")

        content = result.update["messages"][0].content
        assert "交付门 FAIL" in content and "version=99" in content
        sync.assert_not_awaited()

    async def test_schemaless_manifest_rejected(self, tmp_path, monkeypatch):
        """3A: manifest 既无 deliverables[] 也无 deliverable → 未知契约显式拒。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        self._write_bid_manifest(outputs_dir)
        manifest = {"skill": "bid-proposal-writing", "files": {}}
        (outputs_dir / present_file_tool_module.DELIVERY_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        f = outputs_dir / "整体方案-01-投标函.md"
        f.write_text("# x", encoding="utf-8")
        sync = _patch_docmgr_sync(monkeypatch)

        result = await present_file_tool.coroutine(runtime=_make_runtime(outputs_dir), filepaths=[str(f)], tool_call_id="v4-5")

        assert "交付门 FAIL" in result.update["messages"][0].content
        sync.assert_not_awaited()


class TestSandboxSyncAllowedMd:
    """bug-2225/3061 sandbox_sync 门：契约线程仅 deliverables[]∪aux_md 可同步进 workspace 文档（旧单名 deliverable 兼容为单元素集）。"""

    def test_no_marker_returns_star(self, tmp_path):
        """无契约 → "*"（不设限，维持原 report.md 字面规则）。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "report.md").write_text("# r", encoding="utf-8")

        assert sandbox_sync._pipeline_allowed_md_names(outputs_dir) == "*"

    def test_marker_with_manifest_returns_deliverable(self, tmp_path):
        """契约 + geo 旧单名 manifest → 放行集 = {manifest.deliverable}（向后兼容）。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir)

        assert sandbox_sync._pipeline_allowed_md_names(outputs_dir) == {DELIVERABLE_NAME}

    def test_marker_v4_deliverables_and_aux(self, tmp_path):
        """v4 新契约：放行集 = deliverables[] ∪ aux_md（bid 册集 + 确认门工件）。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / present_file_tool_module.DELIVERY_CONTRACT_NAME).write_text("{}", encoding="utf-8")
        manifest = {"skill": "bid-proposal-writing", "version": 1, "deliverables": ["整体方案-01-投标函.md", "技术卷-01-总体.md"], "aux_md": ["条款清单.md"]}
        (outputs_dir / present_file_tool_module.DELIVERY_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        assert sandbox_sync._pipeline_allowed_md_names(outputs_dir) == {"整体方案-01-投标函.md", "技术卷-01-总体.md", "条款清单.md"}

    def test_marker_without_or_corrupt_manifest_returns_none(self, tmp_path):
        """契约无 manifest（管线从未 build）与损坏 manifest（凭据无效）都 → None（.md 全禁）。"""
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        _write_contract(outputs_dir, deliverable=None)
        assert sandbox_sync._pipeline_allowed_md_names(outputs_dir) is None

        (outputs_dir / "delivery_manifest.json").write_text("{corrupt json", encoding="utf-8")
        assert sandbox_sync._pipeline_allowed_md_names(outputs_dir) is None

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
