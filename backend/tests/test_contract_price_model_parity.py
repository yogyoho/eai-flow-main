"""Parity test: the agent skill's mirror ``cpa_`` models must stay in sync with
the canonical Gateway extension models.

Why this exists
---------------
The agent skill ``skills/custom/contract-price-analysis/scripts/models.py``
defines its OWN ``DeclarativeBase`` and a parallel set of ``cpa_*`` ORM classes
so its standalone CLI can persist to the shared ``postgres-ext`` database
WITHOUT importing ``app.*`` (the harness/app boundary forbids it). Both model
sets describe the SAME physical tables. If they drift, the skill writes a
column the extension doesn't expect (or vice-versa) and reads silently corrupt.

This test loads the skill models BY PATH (``importlib``) -- no package import,
no ``app`` -> skill coupling -- and compares every ``cpa_*`` table's
``(column_name, sql_type)`` set against the canonical extension models. It
skips entirely when the skill file is absent (``skills/custom/`` is gitignored,
so CI never sees it); the invariant only matters where both copies exist.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.extensions.contract_price import models as ext_models

# backend/tests/<file> -> repo root (host: repo root; container: /app)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MODELS = (
    _REPO_ROOT / "skills" / "custom" / "contract-price-analysis" / "scripts" / "models.py"
)

# tablename -> class attribute name on BOTH model modules
_TABLES: dict[str, str] = {
    "cpa_documents": "CpaDocument",
    "cpa_items": "CpaItem",
    "cpa_clusters": "CpaCluster",
    "cpa_run_history": "CpaRunHistory",
}

pytestmark = pytest.mark.skipif(
    not _SKILL_MODELS.exists(),
    reason=f"skill models not present (gitignored custom skill): {_SKILL_MODELS}",
)


def _load_skill_models() -> object:
    spec = importlib.util.spec_from_file_location("cpa_skill_models", _SKILL_MODELS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(module: object, class_name: str) -> list[tuple[str, str]]:
    table = getattr(module, class_name).__table__
    return sorted((col.name, str(col.type)) for col in table.columns)


def test_cpa_models_in_sync_with_skill_mirror() -> None:
    """Extension (canonical) and skill (mirror) cpa_ tables must agree column-for-column."""
    skill_models = _load_skill_models()

    drift: list[str] = []
    for table_name, class_name in _TABLES.items():
        ext_cols = _columns(ext_models, class_name)
        skill_cols = _columns(skill_models, class_name)
        if ext_cols != skill_cols:
            ext_only = sorted(set(ext_cols) - set(skill_cols))
            skill_only = sorted(set(skill_cols) - set(ext_cols))
            drift.append(
                f"\n  [{table_name}]\n"
                f"    extension-only: {ext_only}\n"
                f"    skill-only:     {skill_only}"
            )

    assert not drift, (
        "cpa_ model drift between the Gateway extension "
        "(backend/app/extensions/contract_price/models.py) and the skill mirror "
        "(skills/custom/contract-price-analysis/scripts/models.py). "
        "They describe the same physical tables -- reconcile them:" + "".join(drift)
    )
