# EAI-CUSTOM: forked from app.extensions.contract_price (geo-sample-bank Phase 1), spec 2026-09-01.
"""Geo sample bank extension (gsb_ tables). Phase 1 skeleton: models only.

Importing this package registers the gsb_ models on the shared
``app.extensions.database`` Base so the tables auto-create at gateway startup
(same mechanism as contract_price). The management router is wired in Phase 1
Task 8 (routers.py + Gateway mount).
"""

from app.extensions.geo_samples.models import (  # noqa: F401
    GsbDocument,
    GsbRedaction,
    GsbRunHistory,
)

__all__ = ["GsbDocument", "GsbRedaction", "GsbRunHistory"]
