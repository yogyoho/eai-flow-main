"""Orchestrator for the static security scanner — placeholder stub.

ponytail: upstream #4153 added the scanner framework but orchestrator.py
was not fully ported. This stub provides the public API surface so imports
succeed; skill scanning is disabled until the full orchestrator lands.
"""

from __future__ import annotations

from deerflow.skills.skillscan.models import RuleSpec

# ── Rules registry (empty until full port) ──
RULES: list[RuleSpec] = []


def skill_scan_enabled() -> bool:
    """Return True if static scanning is enabled. Stub: always disabled."""
    return False


def enforce_static_scan() -> None:
    """Raise if scan should block but is misconfigured. Stub: no-op."""


def scan_archive_preflight() -> None:
    """Preflight scan of archive. Stub: no-op."""


def scan_skill_dir() -> None:
    """Scan a skill directory. Stub: no-op."""


def format_static_findings() -> str:
    """Format findings for display. Stub: empty."""
    return ""
