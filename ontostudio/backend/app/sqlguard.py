"""只读 SQL 守卫 + 连接 URL 构造（独立服务本地单一真源）.

EAI-CUSTOM: 自 backend/app/extensions/data_source/service.py **逐字节拷贝** assert_readonly_select /
_WRITE_VERBS / _build_db_url——ontology 包迁出独立（设计:
docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md）后不再可能与 gateway 内的
data_source 模块共享单一真源（跨服务/跨 venv）。原 D9 约定（安全规则不复制）在独立部署形态下
由"本文件即本服务唯一守卫实现"承接；两个服务各自 lint/test 覆盖同一规则文本。
上游（backend 侧）规则变更时需同步本拷贝——Task 2 起可评估改为从 ontostudio 侧反哺。
"""

from __future__ import annotations

import re

_WRITE_VERBS = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL)\b")


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
    if _WRITE_VERBS.search(upper):
        raise ValueError("禁止写操作关键字")
    # SELECT ... INTO creates a table in Postgres — block it.
    if re.search(r"\bINTO\b", upper):
        raise ValueError("禁止 SELECT INTO 写操作")
    if not re.search(r"\bLIMIT\b", upper):
        s = f"{s} LIMIT 200"
    return s


def _build_db_url(cfg: dict) -> str:
    """Build a SQLAlchemy URL from a database source's connection_config."""
    driver = cfg.get("driver") or "postgresql+asyncpg"
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    database = cfg.get("database", "")
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    return f"{driver}://{username}:{password}@{host}:{port}/{database}"
