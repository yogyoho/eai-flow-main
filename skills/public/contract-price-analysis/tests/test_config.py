import os

from scripts.config import get_config


def test_get_config_reads_env(monkeypatch):
    monkeypatch.setenv("RAGFLOW_API_KEY", "test-key-123")
    monkeypatch.setenv("RAGFLOW_BASE_URL", "http://example:9999/api/v1")
    monkeypatch.setenv("RAGFLOW_KB_ID", "kb-abc")
    cfg = get_config()
    assert cfg.ragflow_api_key == "test-key-123"
    assert cfg.ragflow_base_url == "http://example:9999/api/v1"
    assert cfg.ragflow_kb_id == "kb-abc"


def test_get_config_defaults(monkeypatch):
    monkeypatch.setenv("RAGFLOW_API_KEY", "k")
    monkeypatch.delenv("RAGFLOW_BASE_URL", raising=False)
    monkeypatch.delenv("RAGFLOW_KB_ID", raising=False)
    cfg = get_config()
    assert cfg.ragflow_base_url == "http://localhost:9380/api/v1"
    assert cfg.ragflow_kb_id == "a8e8f3dc660d11f1ad61e1631bd6f152"
