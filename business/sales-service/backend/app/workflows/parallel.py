"""Pure helpers shared by the parallel approval workflow and activities.

Kept free of Temporal and SQLAlchemy imports so the rules can be unit-tested
without a workflow environment.
"""

from __future__ import annotations

PARALLEL_MODES = {"parallel_all", "parallel_any"}
STEP_MODES = {"sequential", *PARALLEL_MODES}

TERMINAL_STEP_STATUSES = {"approved", "rejected", "returned"}


def assignment_key_for(*, role: str | None = None, user_id: str | None = None) -> str:
    """Return a deterministic slot key used by signals, todos and projections."""
    if user_id:
        return f"user:{user_id}"
    if role:
        return f"role:{role}"
    raise ValueError("并行审批席位必须指定角色或用户")


def parallel_step_outcome(mode: str, statuses: list[str]) -> str:
    """Aggregate participant statuses into a step outcome.

    ``parallel_all`` passes only when every slot approves; any rejection or
    return closes the step immediately. ``parallel_any`` passes on the first
    approval, rejects only after every slot rejects, and treats a return as an
    immediate termination. ``active`` means the workflow must keep waiting.
    """
    if mode not in PARALLEL_MODES:
        raise ValueError(f"未知并行审批模式: {mode}")
    if any(status == "returned" for status in statuses):
        return "returned"
    if mode == "parallel_all":
        if any(status == "rejected" for status in statuses):
            return "rejected"
        if statuses and all(status == "approved" for status in statuses):
            return "approved"
        return "active"
    if any(status == "approved" for status in statuses):
        return "approved"
    if statuses and all(status == "rejected" for status in statuses):
        return "rejected"
    return "active"
