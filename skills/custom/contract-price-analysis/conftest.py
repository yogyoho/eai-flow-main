"""Pytest config: ensure required env vars exist before module import.

``scripts.db`` builds its engine at import time via ``get_config()``, which reads
``RAGFLOW_API_KEY``. Set sensible test defaults here so collection never fails;
individual tests override via ``monkeypatch.setenv``.
"""

import os

os.environ.setdefault("RAGFLOW_API_KEY", "test-key")
os.environ.setdefault("CPA_DATABASE_URL", "postgresql+asyncpg://nobody:nobody@localhost:1/none")
