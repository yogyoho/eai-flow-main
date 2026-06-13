"""Derive chapter dependency graph from a template section tree.

Rules:
1. Parent → child: parent must be generated before children
2. Sibling (same parent): by sort_order — chapter[N] depends on chapter[N-1]
3. Sibling (different parent): independent, can be parallel
"""
from __future__ import annotations


def derive_chapter_dependencies(
    sections: list[dict],
    parent_title: str | None = None,
) -> dict[str, set[str]]:
    """Return {chapter_title: {depends_on_title, ...}} from a section tree."""
    deps: dict[str, set[str]] = {}

    sorted_sections = sorted(sections, key=lambda s: s.get("sort_order", 0))

    for i, section in enumerate(sorted_sections):
        title = section["title"]
        section_deps: set[str] = set()

        # Rule 1: parent → child
        if parent_title:
            section_deps.add(parent_title)

        # Rule 2: sibling[i] depends on sibling[i-1]
        if i > 0:
            prev_title = sorted_sections[i - 1]["title"]
            section_deps.add(prev_title)

        deps[title] = section_deps

        # Recurse into children
        children = section.get("children", [])
        if children:
            child_deps = derive_chapter_dependencies(children, parent_title=title)
            deps.update(child_deps)

    return deps


def topological_order(
    sections: list[dict],
) -> list[list[str]]:
    """Return chapters grouped into parallel-executable batches.

    Batch 0 = no dependencies (can all start in parallel).
    Batch N = depends only on chapters in batches 0..N-1.
    """
    deps = derive_chapter_dependencies(sections)
    all_titles = set(deps.keys())
    batches: list[list[str]] = []
    completed: set[str] = set()

    remaining = all_titles - completed
    while remaining:
        batch = [
            title
            for title in remaining
            if deps.get(title, set()).issubset(completed)
        ]
        if not batch:
            # Cycle or orphan — break to avoid infinite loop
            break
        batches.append(batch)
        completed.update(batch)
        remaining = all_titles - completed

    return batches
