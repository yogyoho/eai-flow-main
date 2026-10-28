"""Alembic owns the production schema; the initial migration must be runnable."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "flow_command",
    "flow_definition",
    "flow_form",
    "flow_his_task",
    "flow_instance",
    "flow_instance_runtime",
    "flow_node",
    "flow_outbox",
    "flow_skip",
    "flow_task",
    "flow_user",
}


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.attributes["sqlalchemy_url"] = database_url
    return config


def test_initial_migration_creates_all_tables(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    config = _config(f"sqlite+aiosqlite:///{database.as_posix()}")

    command.upgrade(config, "head")
    command.upgrade(config, "head")  # idempotent

    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("select name from sqlite_master where type = 'table'")}
    assert EXPECTED_TABLES <= tables
