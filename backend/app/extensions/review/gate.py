"""Review gate — waits for all assigned reviewers before deciding outcome."""
from __future__ import annotations

from enum import StrEnum


class GateMode(StrEnum):
    ALL_MUST_APPROVE = "all_must_approve"
    ANY_CAN_APPROVE = "any_can_approve"
    MAJORITY = "majority"
    WEIGHTED = "weighted"


class GateResult(StrEnum):
    PASS = "pass"
    REJECT = "reject"
    WAITING = "waiting"


def evaluate_gate(
    mode: GateMode,
    total_reviewers: int,
    judgments: list[dict],
    weights: dict[str, float] | None = None,
) -> GateResult:
    """Evaluate the review gate based on current judgments.

    Args:
        mode: The gating strategy
        total_reviewers: Total number of assigned reviewers
        judgments: List of {reviewer_id, status} dicts for submitted judgments
        weights: Per-reviewer weight for WEIGHTED mode (defaults to 1.0 each)
    """
    if len(judgments) < total_reviewers and mode != GateMode.ANY_CAN_APPROVE:
        return GateResult.WAITING

    approved = sum(1 for j in judgments if j["status"] == "approved")
    rejected = sum(1 for j in judgments if j["status"] == "rejected")

    if mode == GateMode.ALL_MUST_APPROVE:
        if len(judgments) < total_reviewers:
            return GateResult.WAITING
        if rejected > 0:
            return GateResult.REJECT
        return GateResult.PASS

    if mode == GateMode.ANY_CAN_APPROVE:
        if approved > 0:
            return GateResult.PASS
        if rejected == total_reviewers:
            return GateResult.REJECT
        return GateResult.WAITING

    if mode == GateMode.MAJORITY:
        threshold = total_reviewers / 2
        if approved > threshold:
            return GateResult.PASS
        if rejected > threshold or len(judgments) == total_reviewers:
            return GateResult.REJECT
        return GateResult.WAITING

    if mode == GateMode.WEIGHTED:
        w = weights or {}
        weighted_approved = sum(w.get(j["reviewer_id"], 1.0) for j in judgments if j["status"] == "approved")
        weighted_rejected = sum(w.get(j["reviewer_id"], 1.0) for j in judgments if j["status"] == "rejected")
        total_weight = sum(w.values()) if w else total_reviewers
        if weighted_approved > total_weight / 2:
            return GateResult.PASS
        if weighted_rejected >= total_weight / 2:
            return GateResult.REJECT
        return GateResult.WAITING

    return GateResult.WAITING
