"""TDD tests for missing activities from spec §4.4.

Covers:
- check_reviews_complete — query DB, return all-approved/rejected/pending counts
- handle_rejection — on rejection, find rollback target and reset review status
- gather_phase_context — collect project+chapter data for downstream context
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckReviewsComplete:
    """check_reviews_complete queries phase_reviews and returns aggregate status."""

    @pytest.mark.asyncio
    async def test_all_approved_returns_complete(self):
        from app.extensions.workflow.temporal.activities import check_reviews_complete

        node_id = "review-1"
        proj_id = str(uuid.uuid4())

        mock1 = MagicMock(status="approved")
        mock2 = MagicMock(status="approved")
        mock3 = MagicMock(status="approved")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock1, mock2, mock3]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_reviews_complete(node_id, proj_id)

        assert result["status"] == "ok"
        assert result["all_done"] is True
        assert result["all_approved"] is True

    @pytest.mark.asyncio
    async def test_mixed_status_returns_not_done(self):
        from app.extensions.workflow.temporal.activities import check_reviews_complete

        node_id = "review-2"
        proj_id = str(uuid.uuid4())

        mock1 = MagicMock(status="approved")
        mock2 = MagicMock(status="pending")
        mock3 = MagicMock(status="rejected")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock1, mock2, mock3]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_reviews_complete(node_id, proj_id)

        assert result["all_done"] is False
        assert result["total"] == 3
        assert result["approved"] == 1
        assert result["rejected"] == 1
        assert result["pending"] == 1

    @pytest.mark.asyncio
    async def test_empty_reviews_returns_done(self):
        from app.extensions.workflow.temporal.activities import check_reviews_complete

        node_id = "review-3"
        proj_id = str(uuid.uuid4())

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await check_reviews_complete(node_id, proj_id)

        assert result["all_done"] is True
        assert result["total"] == 0


class TestHandleRejection:
    """handle_rejection finds rollback target and resets reviews."""

    @pytest.mark.asyncio
    async def test_resets_rejected_reviews_to_pending(self):
        from app.extensions.workflow.temporal.activities import handle_rejection

        node_id = "review-1"
        proj_id = str(uuid.uuid4())
        rollback_target = "phase-1"

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.get = AsyncMock()

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await handle_rejection(node_id, proj_id, rollback_target)

        assert result["status"] == "ok"
        assert result["rollback_to"] == rollback_target

    @pytest.mark.asyncio
    async def test_updates_project_current_phase_node(self):
        from app.extensions.workflow.temporal.activities import handle_rejection

        node_id = "review-1"
        proj_id = str(uuid.uuid4())
        rollback_target = "phase-2"

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.get = AsyncMock()

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await handle_rejection(node_id, proj_id, rollback_target)

        assert result["rollback_to"] == rollback_target


class TestGatherPhaseContext:
    """gather_phase_context collects project and chapter data."""

    @pytest.mark.asyncio
    async def test_collects_chapter_summaries(self):
        from app.extensions.workflow.temporal.activities import gather_phase_context

        proj_id = str(uuid.uuid4())
        phase_id = "phase-1"

        chapter1 = MagicMock()
        chapter1.id = uuid.uuid4()
        chapter1.title = "Chapter 1"
        chapter1.content = "Content 1"
        chapter1.status = "draft"

        chapter2 = MagicMock()
        chapter2.id = uuid.uuid4()
        chapter2.title = "Chapter 2"
        chapter2.content = "Content 2"
        chapter2.status = "draft"

        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = [chapter1, chapter2]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await gather_phase_context(phase_id, proj_id)

        assert result["status"] == "ok"
        assert len(result["chapters"]) == 2
        assert result["chapters"][0]["title"] == "Chapter 1"

    @pytest.mark.asyncio
    async def test_empty_project_handled_gracefully(self):
        from app.extensions.workflow.temporal.activities import gather_phase_context

        proj_id = str(uuid.uuid4())
        phase_id = "phase-1"

        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await gather_phase_context(phase_id, proj_id)

        assert result["chapters"] == []
