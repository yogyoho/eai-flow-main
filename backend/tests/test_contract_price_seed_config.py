"""ConfigOut.table_seeds 往返 + load_config 默认注入。"""

import json

from app.extensions.contract_price.crud import load_config, save_config


def test_config_roundtrip_keeps_table_seeds(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"table_seeds": [{"id": "t1", "display_name": "T", "columns": {"name": ["品名"], "price_unit": ["单价"]}}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    import app.extensions.contract_price.crud as crud

    monkeypatch.setattr(crud, "_config_path", lambda: str(cfg_path))
    got = load_config()
    assert got.table_seeds[0]["id"] == "t1"
    saved = save_config(got)
    assert saved.table_seeds[0]["id"] == "t1"


def test_load_config_injects_default_seeds_when_empty(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    import app.extensions.contract_price.crud as crud

    monkeypatch.setattr(crud, "_config_path", lambda: str(cfg_path))
    got = load_config()
    assert len(got.table_seeds) == 6
