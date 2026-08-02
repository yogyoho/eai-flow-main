"""Integration tests for the full writing-project workflow chain.

Covers the four-module flow end-to-end with mocked DB:
1. E2E: create → AI draft → complete → review → approve → finalize
2. Review gate strategies (all/any/majority)
3. Rejection rollback restores chapter + review state
4. Finalize precondition checks
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_db(get_return=None, execute_return=None):
    """Build a minimal AsyncMock DB session."""
    db = AsyncMock()
    if get_return is not None:
        db.get = AsyncMock(return_value=get_return)
    if execute_return is not None:
        db.execute = AsyncMock(return_value=execute_return)
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _mock_get_db_context(db):
    """Patch get_db_context to return *db*."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return patch("app.extensions.database.get_db_context", return_value=ctx)


def _review_mock(status: str, reviewer_id: str = "u1") -> MagicMock:
    m = MagicMock()
    m.status = status
    m.reviewer_id = uuid.UUID(reviewer_id) if len(reviewer_id) == 36 else reviewer_id
    return m


def _chapter_mock(
    ch_id: str,
    title: str = "Chapter 1",
    status: str = "pending",
    content: str = "Some content",
    phase_node: str = "writing-1",
    project_id: str = "00000000-0000-0000-0000-000000000001",
    sort_order: int = 0,
) -> MagicMock:
    m = MagicMock()
    m.id = uuid.UUID(ch_id)
    m.title = title
    m.status = status
    m.content = content
    m.phase_node = phase_node
    m.project_id = uuid.UUID(project_id)
    m.sort_order = sort_order
    m.level = 1
    m.parent_id = None
    m.word_count_current = len(content) if content else 0
    return m


# ── Review Gate Tests ────────────────────────────────────────────────────────


class TestReviewGateIntegration:
    """Gate strategies work correctly with realistic judgment data."""

    def test_all_must_approve_passes(self):
        from app.extensions.review.gate import evaluate_gate, GateMode, GateResult

        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "approved"},
        ]
        result = evaluate_gate(GateMode.ALL_MUST_APPROVE, 2, judgments)
        assert result == GateResult.PASS

    def test_all_must_approve_rejects_on_single_rejection(self):
        from app.extensions.review.gate import evaluate_gate, GateMode, GateResult

        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "rejected"},
        ]
        result = evaluate_gate(GateMode.ALL_MUST_APPROVE, 2, judgments)
        assert result == GateResult.REJECT

    def test_any_can_approve_passes_first(self):
        from app.extensions.review.gate import evaluate_gate, GateMode, GateResult

        judgments = [{"reviewer_id": "u1", "status": "approved"}]
        result = evaluate_gate(GateMode.ANY_CAN_APPROVE, 3, judgments)
        assert result == GateResult.PASS

    def test_majority_with_tie_waits(self):
        from app.extensions.review.gate import evaluate_gate, GateMode, GateResult

        # 2 submitted, 1 approved, 1 rejected — not yet majority
        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "rejected"},
        ]
        result = evaluate_gate(GateMode.MAJORITY, 3, judgments)
        assert result == GateResult.WAITING

    def test_weighted_with_custom_weights(self):
        from app.extensions.review.gate import evaluate_gate, GateMode, GateResult

        judgments = [
            {"reviewer_id": "u1", "status": "approved"},
            {"reviewer_id": "u2", "status": "rejected"},
        ]
        weights = {"u1": 3.0, "u2": 1.0}
        result = evaluate_gate(GateMode.WEIGHTED, 2, judgments, weights=weights)
        assert result == GateResult.PASS  # 3.0 > 2.0


# ── Check Reviews Complete Tests ─────────────────────────────────────────────


class TestCheckReviewsCompleteIntegration:
    @pytest.mark.asyncio
    async def test_all_approved_returns_pass(self):
        from app.extensions.workflow.temporal.review_activities import check_reviews_complete

        reviews = [_review_mock("approved", str(uuid.uuid4())) for _ in range(3)]
        scalars = MagicMock()
        scalars.all.return_value = reviews
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        db = _mock_db(execute_return=exec_result)

        with _mock_get_db_context(db):
            result = await check_reviews_complete("review-1", str(uuid.uuid4()))

        assert result["status"] == "ok"
        assert result["all_done"] is True
        assert result["all_approved"] is True
        assert result["gate_result"] == "pass"

    @pytest.mark.asyncio
    async def test_one_rejected_returns_reject(self):
        from app.extensions.workflow.temporal.review_activities import check_reviews_complete

        reviews = [
            _review_mock("approved", str(uuid.uuid4())),
            _review_mock("rejected", str(uuid.uuid4())),
        ]
        scalars = MagicMock()
        scalars.all.return_value = reviews
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        db = _mock_db(execute_return=exec_result)

        with _mock_get_db_context(db):
            result = await check_reviews_complete("review-1", str(uuid.uuid4()))

        assert result["gate_result"] == "reject"
        assert result["all_approved"] is False

    @pytest.mark.asyncio
    async def test_pending_returns_waiting(self):
        from app.extensions.workflow.temporal.review_activities import check_reviews_complete

        reviews = [
            _review_mock("approved", str(uuid.uuid4())),
            _review_mock("pending", str(uuid.uuid4())),
        ]
        scalars = MagicMock()
        scalars.all.return_value = reviews
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        db = _mock_db(execute_return=exec_result)

        with _mock_get_db_context(db):
            result = await check_reviews_complete("review-1", str(uuid.uuid4()))

        assert result["gate_result"] == "waiting"
        assert result["pending"] == 1


# ── Rejection Rollback Tests ─────────────────────────────────────────────────


class TestRejectionRollbackIntegration:
    @pytest.mark.asyncio
    async def test_rollback_resets_reviews_and_chapters(self):
        """handle_rejection should reset rejected reviews and rollback chapters."""
        from app.extensions.workflow.temporal.review_activities import handle_rejection

        proj_id = str(uuid.uuid4())
        rollback_target = "writing-phase-1"

        db = _mock_db()

        with _mock_get_db_context(db):
            result = await handle_rejection("review-1", proj_id, rollback_target)

        assert result["status"] == "ok"
        assert result["rollback_to"] == rollback_target
        # DB execute should have been called 3 times:
        # 1. update ReviewAssignment (reset rejected → pending)
        # 2. update ReportProject (move current_phase_node)
        # 3. update ProjectChapter (reset status → pending)
        assert db.execute.call_count >= 3


# ── Chapter State Machine Integration ────────────────────────────────────────


class TestChapterLifecycle:
    """Canonical chapter lifecycle (ADR 2026-08-02): pending → draft → reviewing → approved, with reviewing → draft (reject) and approved → draft (rework)."""

    def test_full_happy_path_transitions(self):
        from app.extensions.writing.state_machine import validate_chapter_transition

        assert validate_chapter_transition("pending", "draft") is None
        assert validate_chapter_transition("draft", "reviewing") is None
        assert validate_chapter_transition("reviewing", "approved") is None

    def test_tier1_direct_approval(self):
        from app.extensions.writing.state_machine import validate_chapter_transition

        # Tier-1 (no review gate): draft may go straight to approved.
        assert validate_chapter_transition("draft", "approved") is None

    def test_rejection_rollback_path(self):
        from app.extensions.writing.state_machine import validate_chapter_transition

        # Rejection = event that returns the chapter to 'draft' with feedback.
        assert validate_chapter_transition("reviewing", "draft") is None
        # Post-approval rework mirrors the project-level re-open.
        assert validate_chapter_transition("approved", "draft") is None

    def test_error_state_removed(self):
        # EAI-CUSTOM: 'error'/'completed' removed (ADR 2026-08-02). AI-failure
        # retry is re-derived from an empty draft (word_count_current == 0);
        # failed chapters stay 'pending' so generation can rerun.
        from app.extensions.writing.state_machine import ChapterStatus

        values = {c.value for c in ChapterStatus}
        assert "error" not in values
        assert "completed" not in values
        assert {"pending", "draft", "reviewing", "approved"} <= values


# ── Finalize Integration Tests ───────────────────────────────────────────────


class TestFinalizeIntegration:
    def test_preconditions_blocked_when_reviews_not_approved(self):
        from app.extensions.docmgr.finalize import check_preconditions, FinalizeStatus

        chapters = [{"id": "c1", "title": "Ch1", "status": "reviewing"}]  # EAI-CUSTOM: canonical (ADR 2026-08-02)
        result = check_preconditions(chapters, reviews_approved=False)
        assert result.status == FinalizeStatus.BLOCKED

    def test_preconditions_blocked_when_chapters_incomplete(self):
        from app.extensions.docmgr.finalize import check_preconditions, FinalizeStatus

        chapters = [
            {"id": "c1", "title": "Ch1", "status": "reviewing"},  # EAI-CUSTOM: canonical (ADR 2026-08-02)
            {"id": "c2", "title": "Ch2", "status": "pending"},
        ]
        result = check_preconditions(chapters, reviews_approved=True)
        assert result.status == FinalizeStatus.BLOCKED

    def test_preconditions_ready_when_all_ok(self):
        from app.extensions.docmgr.finalize import check_preconditions, FinalizeStatus

        chapters = [
            {"id": "c1", "title": "Ch1", "status": "reviewing"},  # EAI-CUSTOM: canonical (ADR 2026-08-02)
            {"id": "c2", "title": "Ch2", "status": "approved"},
        ]
        result = check_preconditions(chapters, reviews_approved=True)
        assert result.status == FinalizeStatus.READY

    def test_preconditions_warnings_for_unresolved_comments(self):
        from app.extensions.docmgr.finalize import check_preconditions, FinalizeStatus

        chapters = [{"id": "c1", "title": "Ch1", "status": "reviewing"}]  # EAI-CUSTOM: canonical (ADR 2026-08-02)
        result = check_preconditions(chapters, reviews_approved=True, unresolved_comments=3)
        assert result.status == FinalizeStatus.WARNINGS
        assert any("评论" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_execute_finalize_creates_document(self):
        """execute_finalize should create a document entry (content merge verified at integration level)."""
        from app.extensions.docmgr.finalize import execute_finalize

        proj_id = uuid.uuid4()

        mock_project = MagicMock()
        mock_project.name = "测试项目"
        mock_project.report_type = "safety_assessment"

        mock_chapter = _chapter_mock(
            "00000000-0000-0000-0000-000000000001",
            "第一章", "completed", "这是第一章内容",
        )

        db = AsyncMock()
        db.get = AsyncMock(return_value=mock_project)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        # execute call order: 1) chapters, 2) folder, 3) owner
        ch_scalars = MagicMock()
        ch_scalars.all.return_value = [mock_chapter]
        ch_result = MagicMock()
        ch_result.scalars.return_value = ch_scalars

        folder_result = MagicMock()
        folder_result.first.return_value = None

        owner_result = MagicMock()
        owner_result.first.return_value = None

        # 4 execute calls: chapters, folder, owner, update chapters to approved
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[ch_result, folder_result, owner_result, update_result])

        result = await execute_finalize(db, proj_id)

        assert result["status"] == "ok"
        assert "document_id" in result
        assert result["chapter_count"] == 1
        assert db.add.call_count >= 1  # Document was added


# ── Full E2E Activity Chain (Mocked DB) ──────────────────────────────────────


class TestE2EWorkflowChain:
    """Simulate the full workflow chain: create → draft → complete → review → finalize."""

    @pytest.mark.asyncio
    async def test_full_chain_writing_to_review(self):
        """Chapters move through the writing pipeline and trigger review assignments."""
        from app.extensions.workflow.temporal.review_activities import (
            create_review_assignments,
            check_reviews_complete,
        )

        proj_id = str(uuid.uuid4())
        node_id = "writing-1"

        # Mock project members — two with "reviewer" duty for this node
        mock_members = []
        for i in range(2):
            m = MagicMock()
            m.user_id = uuid.uuid4()
            m.phase_duties = {node_id: {"role": "reviewer"}}
            m.role = "reviewer"
            mock_members.append(m)

        # Build a DB mock that handles execute calls in sequence
        db = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        # First execute: members query
        member_scalars = MagicMock()
        member_scalars.all.return_value = mock_members
        member_result = MagicMock()
        member_result.scalars.return_value = member_scalars

        # Second/third execute: existing review check → None (no duplicates)
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[member_result, review_result, review_result])

        with _mock_get_db_context(db):
            result = await create_review_assignments(node_id, proj_id)

        assert result["status"] == "ok"
        assert result["assignment_count"] == 2  # Both reviewers assigned

        # Step 2: Check reviews — mock approved judgments
        reviews_approved = [
            _review_mock("approved", str(uuid.uuid4())),
            _review_mock("approved", str(uuid.uuid4())),
        ]
        rev_scalars = MagicMock()
        rev_scalars.all.return_value = reviews_approved
        rev_result = MagicMock()
        rev_result.scalars.return_value = rev_scalars

        db2 = _mock_db(execute_return=rev_result)
        with _mock_get_db_context(db2):
            result2 = await check_reviews_complete(node_id, proj_id)

        assert result2["all_approved"] is True
        assert result2["gate_result"] == "pass"

    @pytest.mark.asyncio
    async def test_chain_with_rejection_and_rollback(self):
        """Full cycle: review rejected → rollback → chapters reset."""
        from app.extensions.workflow.temporal.review_activities import (
            check_reviews_complete,
            handle_rejection,
        )

        proj_id = str(uuid.uuid4())
        node_id = "review-1"

        # Step 1: One reviewer rejects
        reviews = [
            _review_mock("approved", str(uuid.uuid4())),
            _review_mock("rejected", str(uuid.uuid4())),
        ]
        scalars = MagicMock()
        scalars.all.return_value = reviews
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars

        db1 = _mock_db(execute_return=exec_result)
        with _mock_get_db_context(db1):
            result1 = await check_reviews_complete(node_id, proj_id)

        assert result1["gate_result"] == "reject"

        # Step 2: Handle rejection — rollback to writing phase
        db2 = _mock_db()
        with _mock_get_db_context(db2):
            result2 = await handle_rejection(node_id, proj_id, "writing-1")

        assert result2["status"] == "ok"
        assert result2["rollback_to"] == "writing-1"


# ── Dependency Graph Integration ─────────────────────────────────────────────


class TestDependencyGraphIntegration:
    """Template section tree → chapter dependency derivation → topological order."""

    def test_linear_chapters_topological_order(self):
        from app.extensions.writing.dependency_graph import (
            derive_chapter_dependencies,
            topological_order,
        )

        sections = [
            {"title": "Ch1", "sort_order": 0, "children": []},
            {"title": "Ch2", "sort_order": 1, "children": []},
            {"title": "Ch3", "sort_order": 2, "children": []},
        ]
        deps = derive_chapter_dependencies(sections)
        assert deps["Ch2"] == {"Ch1"}
        assert deps["Ch3"] == {"Ch2"}

        batches = topological_order(sections)
        assert batches == [["Ch1"], ["Ch2"], ["Ch3"]]

    def test_nested_chapters_create_parent_dependency(self):
        from app.extensions.writing.dependency_graph import derive_chapter_dependencies

        sections = [
            {"title": "Ch1", "sort_order": 0, "children": [
                {"title": "1.1", "sort_order": 0, "children": []},
                {"title": "1.2", "sort_order": 1, "children": []},
            ]},
        ]
        deps = derive_chapter_dependencies(sections)
        # Children depend on parent
        assert "Ch1" in deps.get("1.1", set())
        assert "Ch1" in deps.get("1.2", set())
        # Siblings depend on each other
        assert "1.1" in deps.get("1.2", set())

    def test_siblings_in_different_parents_are_independent(self):
        from app.extensions.writing.dependency_graph import (
            derive_chapter_dependencies,
            topological_order,
        )

        sections = [
            {"title": "Ch1", "sort_order": 0, "children": [
                {"title": "1.1", "sort_order": 0, "children": []},
            ]},
            {"title": "Ch2", "sort_order": 1, "children": [
                {"title": "2.1", "sort_order": 0, "children": []},
            ]},
        ]
        deps = derive_chapter_dependencies(sections)
        # Cross-parent siblings are independent
        assert "2.1" not in deps.get("1.1", set())
        assert "1.1" not in deps.get("2.1", set())

        batches = topological_order(sections)
        # Ch1 has no deps → batch 0
        # Ch2 depends on Ch1 (sibling rule) → batch 1
        # 1.1 depends on Ch1 (parent rule) → batch 1
        # 2.1 depends on Ch2 (parent rule) → batch 2
        assert set(batches[0]) == {"Ch1"}
        assert set(batches[1]) == {"Ch2", "1.1"}
        assert set(batches[2]) == {"2.1"}


# ── Review Deadline Escalation Tests ────────────────────────────────────────


class TestReviewDeadlineEscalation:
    """T9: Deadline-based escalation in notify_review_pending."""

    def test_resolve_phase_lead_from_duties(self):
        """Phase lead resolved from phase_duties role key."""
        from app.extensions.workflow.temporal.notification_activities import (
            _resolve_phase_lead_ids,
        )

        member = MagicMock()
        member.user_id = uuid.uuid4()
        member.phase_duties = {"review-1": {"role": "phase_lead"}}
        member.role = "writer"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [member]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        # We need to run the coroutine
        import asyncio
        loop = asyncio.new_event_loop()
        ids = loop.run_until_complete(
            _resolve_phase_lead_ids(db, str(uuid.uuid4()), "review-1")
        )
        loop.close()
        assert len(ids) == 1
        assert ids[0] == member.user_id

    def test_resolve_owner_ids(self):
        """Project owners resolved by ProjectMember.role."""
        from app.extensions.workflow.temporal.notification_activities import (
            _resolve_owner_ids,
        )

        owner = MagicMock()
        owner.user_id = uuid.uuid4()
        owner.role = "owner"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [owner]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        import asyncio
        loop = asyncio.new_event_loop()
        ids = loop.run_until_complete(
            _resolve_owner_ids(db, str(uuid.uuid4()))
        )
        loop.close()
        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_notify_review_pending_with_deadlines(self):
        """notify_review_pending sends notifications and escalates overdue reviews."""
        from app.extensions.workflow.temporal.notification_activities import (
            notify_review_pending,
        )
        from datetime import datetime, timedelta, timezone

        proj_id = str(uuid.uuid4())
        node_id = "review-1"

        # Create a pending assignment with a deadline 50h ago (overdue > 48h)
        ra = MagicMock()
        ra.reviewer_id = uuid.uuid4()
        ra.phase_node = node_id
        ra.status = "pending"
        ra.deadline_at = datetime.now(timezone.utc) - timedelta(hours=50)

        ra_scalars = MagicMock()
        ra_scalars.all.return_value = [ra]
        ra_result = MagicMock()
        ra_result.scalars.return_value = ra_scalars

        # Phase lead query — returns one lead
        lead = MagicMock()
        lead.user_id = uuid.uuid4()
        lead.phase_duties = {node_id: {"role": "phase_lead"}}
        lead.role = "writer"
        lead_scalars = MagicMock()
        lead_scalars.all.return_value = [lead]
        lead_result = MagicMock()
        lead_result.scalars.return_value = lead_scalars

        # Owner query — returns one owner
        owner = MagicMock()
        owner.user_id = uuid.uuid4()
        owner.role = "owner"
        owner_scalars = MagicMock()
        owner_scalars.all.return_value = [owner]
        owner_result = MagicMock()
        owner_result.scalars.return_value = owner_scalars

        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(side_effect=[ra_result, lead_result, owner_result])

        with patch("app.extensions.database.get_db_context") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await notify_review_pending(node_id, proj_id)

        assert result["status"] == "ok"
        # notified=1 (reviewer) + escalated>=2 (lead + owner)
        assert result["notified"] >= 1
        assert result["escalated"] >= 2  # overdue 50h → lead + owner notified
