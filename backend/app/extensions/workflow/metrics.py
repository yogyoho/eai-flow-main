"""Workflow observability — structured logging, metrics counters, trace IDs.

Lightweight in-process metrics that activities can increment.  Designed to
be replaced with a real metrics backend (Prometheus, Datadog) without
changing activity code — just swap the implementation behind the same
function signatures.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── In-process counters ─────────────────────────────────────────────────────
# Thread-safe counters for development.  Replace with real metrics in production.

_counters: dict[str, int] = defaultdict(int)
_lock = threading.Lock()


def incr(name: str, delta: int = 1) -> None:
    """Increment a named counter (thread-safe)."""
    with _lock:
        _counters[name] += delta


def read_counter(name: str) -> int:
    """Read a named counter."""
    with _lock:
        return _counters[name]


def read_all_counters() -> dict[str, int]:
    """Snapshot all counters."""
    with _lock:
        return dict(_counters)


def reset_counters() -> None:
    """Reset all counters (mainly for tests)."""
    with _lock:
        _counters.clear()


# ── Structured event logging ─────────────────────────────────────────────────


def log_workflow_event(
    event: str,
    workflow_id: str | None = None,
    project_id: str | None = None,
    node_id: str | None = None,
    **extra,
) -> None:
    """Emit a structured workflow event log line.

    All key-value pairs in ``extra`` are appended to the log message in
    ``key=value`` format so downstream log processors can parse them.
    """
    parts = [f"wf_event={event}"]
    if workflow_id:
        parts.append(f"wf_id={workflow_id}")
    if project_id:
        parts.append(f"project_id={project_id}")
    if node_id:
        parts.append(f"node_id={node_id}")
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    logger.info(" | ".join(parts))


# ── High-level metric helpers ────────────────────────────────────────────────


def record_ai_generation_success(
    project_id: str | None = None,
    chapter_id: str | None = None,
    elapsed_ms: float = 0,
) -> None:
    """Record a successful AI chapter generation."""
    incr("ai_generation_total")
    incr("ai_generation_success")
    if elapsed_ms > 0:
        # Track as integer milliseconds for simplicity
        incr("ai_generation_total_ms", int(elapsed_ms))
        incr("ai_generation_success_ms", int(elapsed_ms))
    log_workflow_event(
        "ai_generation_success",
        project_id=project_id,
        chapter_id=chapter_id,
        elapsed_ms=f"{elapsed_ms:.0f}",
    )


def record_ai_generation_failure(
    project_id: str | None = None,
    chapter_id: str | None = None,
    error_code: str = "unknown",
    elapsed_ms: float = 0,
) -> None:
    """Record a failed AI chapter generation."""
    incr("ai_generation_total")
    incr("ai_generation_failure")
    incr(f"ai_generation_error_{error_code}")
    if elapsed_ms > 0:
        incr("ai_generation_total_ms", int(elapsed_ms))
        incr("ai_generation_failure_ms", int(elapsed_ms))
    log_workflow_event(
        "ai_generation_failure",
        project_id=project_id,
        chapter_id=chapter_id,
        error_code=error_code,
        elapsed_ms=f"{elapsed_ms:.0f}",
    )


def record_review_action(
    project_id: str | None = None,
    node_id: str | None = None,
    reviewer_id: str | None = None,
    status: str = "pending",
    hours_since_assignment: float = 0,
) -> None:
    """Record a review action (approved/rejected)."""
    incr("review_actions_total")
    incr(f"review_action_{status}")
    log_workflow_event(
        "review_action",
        project_id=project_id,
        node_id=node_id,
        reviewer_id=reviewer_id,
        status=status,
        turnaround_h=f"{hours_since_assignment:.1f}",
    )


def record_workflow_phase_transition(
    workflow_id: str | None = None,
    project_id: str | None = None,
    from_node: str | None = None,
    to_node: str | None = None,
) -> None:
    """Record a workflow phase transition."""
    incr("phase_transitions_total")
    log_workflow_event(
        "phase_transition",
        workflow_id=workflow_id,
        project_id=project_id,
        from_node=from_node or "start",
        to_node=to_node or "end",
    )


# ── Export snapshot for admin/debug endpoints ────────────────────────────────


def get_metrics_snapshot() -> dict:
    """Return a snapshot of all current metrics for admin/debug display."""
    return {
        "counters": read_all_counters(),
        "ai_success_rate": (read_counter("ai_generation_success") / max(read_counter("ai_generation_total"), 1)),
        "avg_generation_ms": (read_counter("ai_generation_total_ms") // max(read_counter("ai_generation_total"), 1)),
        "review_actions": read_counter("review_actions_total"),
        "phase_transitions": read_counter("phase_transitions_total"),
    }
