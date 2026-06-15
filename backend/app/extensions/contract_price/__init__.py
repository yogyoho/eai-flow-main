"""Contract price analysis extension.

Provides the management API (mounted into the Gateway) for the contract
line-item price extraction + clustering pipeline. Reuses the shared
``app.extensions.database`` engine + cookie-JWT auth; stays physically isolated
from procurement-service via the ``cpa_`` table prefix.

The pipeline itself (RAGFlow client, parsers, clustering, Excel) lives in the
agent skill ``skills/custom/contract-price-analysis/scripts/`` and is triggered
by ``service.run_pipeline_subprocess``.
"""

from app.extensions.contract_price.models import (  # noqa: F401
    CpaCluster,
    CpaDocument,
    CpaItem,
    CpaRunHistory,
)
from app.extensions.contract_price.routers import router

__all__ = ["router", "CpaCluster", "CpaDocument", "CpaItem", "CpaRunHistory"]
