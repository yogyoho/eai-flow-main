"""Service layer for phase review operations.

Extracts review business logic from routers.py for testability
and separation of concerns.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PhaseReview
from .schemas import PhaseReviewOut, ReviewStatusResponse


async def assign_reviews(
    db: AsyncSession,
    project_id: uuid.UUID,
    phase_node: str,
    assignments: list[dict],
) -> list[PhaseReviewOut]:
    """Create review assignments, replacing existing pending ones for the phase node."""
    # Delete existing pending assignments
    await db.execute(
        PhaseReview.__table__.delete()
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.phase_node == phase_node)
        .where(PhaseReview.status == "pending")
    )

    reviews = []
    for item in assignments:
        review = PhaseReview(
            project_id=project_id,
            phase_node=phase_node,
            chapter_id=item.get("chapter_id"),
            reviewer_id=item["reviewer_id"],
            review_type=item["review_type"],
            dimension=item.get("dimension"),
            status="pending",
        )
        db.add(review)
        reviews.append(review)

    await db.commit()
    for r in reviews:
        await db.refresh(r)

    return [PhaseReviewOut.model_validate(r) for r in reviews]


async def submit_action(
    db: AsyncSession,
    project_id: uuid.UUID,
    review_id: uuid.UUID,
    action: str,
    comment: str | None,
) -> tuple[PhaseReviewOut, bool]:
    """Submit a review action. Returns (updated_review, all_reviews_complete)."""
    review = await db.get(PhaseReview, review_id)
    if not review or review.project_id != project_id:
        return None, False

    review.status = action
    review.comment = comment
    review.updated_at = func.now()
    await db.commit()
    await db.refresh(review)

    # Check if all reviews for this phase node are done
    result = await db.execute(
        select(PhaseReview)
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.phase_node == review.phase_node)
    )
    all_reviews = result.scalars().all()
    all_done = all(r.status in ("approved", "rejected") for r in all_reviews)

    return PhaseReviewOut.model_validate(review), all_done


async def get_review_status(
    db: AsyncSession,
    project_id: uuid.UUID,
    phase_node: str,
) -> ReviewStatusResponse:
    """Get aggregated review status for a phase node."""
    result = await db.execute(
        select(PhaseReview)
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.phase_node == phase_node)
        .order_by(PhaseReview.created_at)
    )
    reviews = result.scalars().all()

    approved = sum(1 for r in reviews if r.status == "approved")
    rejected = sum(1 for r in reviews if r.status == "rejected")
    pending = sum(1 for r in reviews if r.status == "pending")

    return ReviewStatusResponse(
        phase_node=phase_node,
        total=len(reviews),
        approved=approved,
        rejected=rejected,
        pending=pending,
        all_approved=len(reviews) > 0 and approved == len(reviews),
        reviews=[PhaseReviewOut.model_validate(r) for r in reviews],
    )


async def get_my_pending_reviews(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[PhaseReviewOut]:
    """Get current user's pending reviews for a project."""
    result = await db.execute(
        select(PhaseReview)
        .where(PhaseReview.project_id == project_id)
        .where(PhaseReview.reviewer_id == user_id)
        .where(PhaseReview.status == "pending")
        .order_by(PhaseReview.created_at.desc())
    )
    return [PhaseReviewOut.model_validate(r) for r in result.scalars().all()]
