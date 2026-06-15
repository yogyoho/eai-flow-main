"""Tests for schemas + config CRUD (JSON-backed, no DB needed).

The DB-backed CRUD functions are exercised through router tests with a mocked
session; here we cover the pure-logic pieces: schema validation and the
JSON-file config round-trip.
"""

import json
import os

from scripts.server import crud
from scripts.server.schemas import (
    ClusterMerge,
    ConfigOut,
    ConfigUpdate,
    DashboardOut,
    ItemUpdate,
    Page,
    PipelineRunRequest,
)


def test_schemas_validate_minimal():
    cfg = ConfigOut()
    assert cfg.parse_mode == "table"
    assert cfg.cluster_eps == 0.6
    assert cfg.scheduled_enabled is False

    upd = ItemUpdate(unit_price=123.45)
    assert upd.unit_price == 123.45

    merge = ClusterMerge(cluster_ids=["00000000-0000-0000-0000-000000000000"] * 2, representative_name="开关柜")
    assert merge.representative_name == "开关柜"

    run_req = PipelineRunRequest()
    assert run_req.mode == "table"


def test_page_generic():
    p = Page[ConfigOut](items=[ConfigOut()], total=1, skip=0, limit=10)
    assert p.total == 1 and len(p.items) == 1


def test_dashboard_out_defaults():
    d = DashboardOut(contract_count=0, item_count=0, cluster_count=0,
                     pending_cluster_count=0, confirmed_cluster_count=0)
    assert d.recent_runs == []
    assert d.price_range is None


def test_config_roundtrip(tmp_path, monkeypatch):
    # Point the config file at a tmp path.
    monkeypatch.setattr(crud, "_CONFIG_PATH", str(tmp_path / "config.json"))

    cfg = ConfigUpdate(parse_mode="list", cluster_eps=0.5, scheduled_enabled=True, schedule_cron="0 2 * * *")
    saved = crud.save_config(cfg)
    assert os.path.exists(os.path.abspath(crud._CONFIG_PATH))

    loaded = crud.load_config()
    assert loaded.parse_mode == "list"
    assert loaded.cluster_eps == 0.5
    assert loaded.scheduled_enabled is True
    assert loaded.schedule_cron == "0 2 * * *"


def test_load_config_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(crud, "_CONFIG_PATH", str(tmp_path / "nope.json"))
    cfg = crud.load_config()
    assert cfg.parse_mode == "table"
    assert cfg.cluster_eps == 0.6
