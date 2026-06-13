"""AI generation strategy selector — batch vs per-chapter."""
from __future__ import annotations

from enum import StrEnum


class GenerationStrategy(StrEnum):
    BATCH = "batch"
    SEQUENTIAL = "sequential"


COMPLEX_THRESHOLD = 100_000  # Total word_count_target threshold


def select_strategy(
    sections: list[dict],
    report_type: str,
    manual_override: str | None = None,
) -> GenerationStrategy:
    """Select generation strategy based on report complexity."""
    if manual_override:
        return GenerationStrategy(manual_override)

    total_words = _sum_word_counts(sections)
    if total_words >= COMPLEX_THRESHOLD:
        return GenerationStrategy.SEQUENTIAL
    return GenerationStrategy.BATCH


def _sum_word_counts(sections: list[dict]) -> int:
    total = 0
    for s in sections:
        total += s.get("word_count_target", 0)
        total += _sum_word_counts(s.get("children", []))
    return total
