"""Writer assignment with workload-aware load balancing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WriterCandidate:
    user_id: str
    workload: int = 0


def select_writer(candidates: list[WriterCandidate]) -> str | None:
    """Select the writer with the lowest current workload."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.workload).user_id
