"""DataSource service: connection testing, sync, read-only query guard, CRUD.

NOTE on the DB connection: every function that talks to the extensions DB
receives an injected ``AsyncSession`` (router path) or builds a short-lived
engine from ``get_extensions_config().database.url`` (MCP path). NEVER use
PROJECT_DB_URL here — that points at a different database (project-db)."""

from __future__ import annotations

import re


def assert_readonly_select(sql: str) -> str:
    """Validate that ``sql`` is a single read-only SELECT/WITH query.

    Returns a sanitized SQL string with a guaranteed LIMIT (appended if absent).
    Raises ValueError for anything that is not a single read-only statement.
    Fail-closed: ambiguous input is rejected rather than executed.
    """
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].strip()
    if not s:
        raise ValueError("SQL 不能为空")
    if ";" in s:
        raise ValueError("禁止多语句查询")
    upper = s.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("仅允许 SELECT / WITH 查询")
    # SELECT ... INTO creates a table in Postgres — block it.
    if re.search(r"\bINTO\b", upper):
        raise ValueError("禁止 SELECT INTO 写操作")
    if not re.search(r"\bLIMIT\b", upper):
        s = f"{s} LIMIT 200"
    return s
