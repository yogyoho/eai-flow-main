"""Tests for sync_outputs_to_docmgr and present_files callback integration."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.extensions.docmgr.service import AIDocumentService
from deerflow.tools.callbacks import (
    _present_files_callbacks,
    fire_present_files_callbacks,
    register_present_files_callback,
)


# ─── Callback registry tests ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_callbacks():
    """Ensure no callbacks leak between tests."""
    _present_files_callbacks.clear()
    yield
    _present_files_callbacks.clear()


class TestCallbackRegistry:
    """Test the deerflow.tools.callbacks module."""

    @pytest.mark.asyncio
    async def test_register_and_fire_callback(self):
        """Callback is invoked with correct arguments."""
        received_args = []

        async def mock_callback(user_id, thread_id, virtual_paths):
            received_args.append((user_id, thread_id, virtual_paths))
            return {"synced": 1}

        register_present_files_callback(mock_callback)
        assert len(_present_files_callbacks) == 1

        results = await fire_present_files_callbacks(
            "uid-1", "tid-1", ["/mnt/user-data/outputs/a.md"],
        )
        assert len(results) == 1
        assert results[0] == {"synced": 1}
        assert received_args[0] == ("uid-1", "tid-1", ["/mnt/user-data/outputs/a.md"])

    @pytest.mark.asyncio
    async def test_callback_exception_is_swallowed(self):
        """Failing callbacks return None but don't break other callbacks."""

        async def bad_callback(user_id, thread_id, virtual_paths):
            raise RuntimeError("sync exploded")

        async def good_callback(user_id, thread_id, virtual_paths):
            return {"synced": 2}

        register_present_files_callback(bad_callback)
        register_present_files_callback(good_callback)

        results = await fire_present_files_callbacks("u", "t", [])
        assert len(results) == 2
        assert results[0] is None  # bad callback
        assert results[1] == {"synced": 2}  # good callback

    @pytest.mark.asyncio
    async def test_fire_with_no_callbacks(self):
        """No callbacks registered → empty results list."""
        results = await fire_present_files_callbacks("u", "t", [])
        assert results == []


# ─── present_file_tool sync trigger tests ────────────────────────────────────


class TestPresentFileToolSyncTrigger:
    """Test that present_file_tool fires the sync callback."""

    @pytest.mark.asyncio
    async def test_try_fire_sync_callback_schedules_task(self):
        """_try_fire_sync_callback schedules an async task without raising."""
        from deerflow.tools.builtins.present_file_tool import _try_fire_sync_callback

        received = []

        async def spy_callback(user_id, thread_id, virtual_paths):
            received.append((user_id, thread_id, virtual_paths))
            return {"synced": 1}

        _present_files_callbacks.append(spy_callback)

        runtime = MagicMock()
        runtime.context = {"thread_id": "test-thread-123"}

        with (
            patch("deerflow.tools.builtins.present_file_tool.get_effective_user_id", return_value="user-abc"),
            patch("deerflow.tools.builtins.present_file_tool._get_thread_id", return_value="test-thread-123"),
        ):
            _try_fire_sync_callback(runtime, ["/mnt/user-data/outputs/report.md"])
            # Let the background task execute
            await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0][0] == "user-abc"
        assert received[0][1] == "test-thread-123"

    def test_try_fire_sync_callback_no_thread_id_is_noop(self):
        """If thread_id is None, callback is not scheduled."""
        from deerflow.tools.builtins.present_file_tool import _try_fire_sync_callback

        runtime = MagicMock()
        runtime.context = {}

        with patch("deerflow.tools.builtins.present_file_tool.get_effective_user_id", return_value="user-abc"):
            with patch("deerflow.tools.builtins.present_file_tool._get_thread_id", return_value=None):
                # Should not raise and should not schedule anything
                _try_fire_sync_callback(runtime, ["/mnt/user-data/outputs/report.md"])


# ─── sync_outputs_to_docmgr service tests ────────────────────────────────────


class TestSyncOutputsToDocmgr:
    """Test AIDocumentService.sync_outputs_to_docmgr."""

    @pytest.mark.asyncio
    async def test_sync_empty_paths(self):
        """Empty virtual_paths list returns zeros."""
        result = await AIDocumentService.sync_outputs_to_docmgr(
            user_id=uuid4(),
            thread_id="thread-1",
            virtual_paths=[],
        )
        assert result == {"synced": 0, "skipped": 0, "errors": 0}

    @pytest.mark.asyncio
    async def test_sync_non_output_paths_filtered(self):
        """Paths outside /mnt/user-data/outputs/ are filtered out."""
        result = await AIDocumentService.sync_outputs_to_docmgr(
            user_id=uuid4(),
            thread_id="thread-1",
            virtual_paths=["/mnt/user-data/workspace/something.txt"],
        )
        assert result["synced"] == 0
        assert result["errors"] == 0


# ─── _is_text_mime helper tests ──────────────────────────────────────────────


class TestIsTextMime:
    """Test the _is_text_mime helper."""

    def test_text_plain(self):
        assert AIDocumentService._is_text_mime("text/plain") is True
        assert AIDocumentService._is_text_mime("text/markdown") is True
        assert AIDocumentService._is_text_mime("text/html") is True
        assert AIDocumentService._is_text_mime("text/csv") is True

    def test_application_text_types(self):
        assert AIDocumentService._is_text_mime("application/json") is True
        assert AIDocumentService._is_text_mime("application/xml") is True
        assert AIDocumentService._is_text_mime("application/javascript") is True
        assert AIDocumentService._is_text_mime("application/x-yaml") is True

    def test_binary_types(self):
        assert AIDocumentService._is_text_mime("application/pdf") is False
        assert AIDocumentService._is_text_mime("application/vnd.openxmlformats-officedocument.wordprocessingml.document") is False
        assert AIDocumentService._is_text_mime("image/png") is False
        assert AIDocumentService._is_text_mime("application/octet-stream") is False

    def test_none_mime(self):
        assert AIDocumentService._is_text_mime(None) is False
        assert AIDocumentService._is_text_mime("") is False
