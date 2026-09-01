# EAI-CUSTOM: forked from app.extensions.contract_price (geo-sample-bank Phase 1), spec 2026-09-01.
"""Geo sample bank extension (gsb_ tables). Phase 1 skeleton: models only.

Importing this package registers the gsb_ models on the shared
``app.extensions.database`` Base so the tables auto-create at gateway startup
(same mechanism as contract_price), and exports the management router
(routers.py, mounted by the Gateway at /api/extensions/geo-samples — Task 8).
"""

from app.extensions.geo_samples.models import (  # noqa: F401
    GsbDocument,
    GsbRedaction,
    GsbRunHistory,
)
from app.extensions.geo_samples.routers import router  # noqa: F401

__all__ = ["router", "GsbDocument", "GsbRedaction", "GsbRunHistory"]
