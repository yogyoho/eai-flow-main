"""Translation workbench settings store (pure)."""

from pathlib import Path

from app.extensions.translation.settings import (
    read_translation_settings,
    resolve_effective_model_name,
    write_translation_settings,
)


def test_settings_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    write_translation_settings({"translation_model": "gemma-4"}, p)
    assert read_translation_settings(p) == {"translation_model": "gemma-4"}


def test_bad_json_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text("{oops", encoding="utf-8")
    assert read_translation_settings(p) == {}


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_translation_settings(tmp_path / "missing.json") == {}


def test_setting_wins(monkeypatch) -> None:
    monkeypatch.setenv("EAI_TRANSLATION_MODEL", "env-model")
    assert resolve_effective_model_name("gemma-4", ["agnes", "gemma-4", "env-model"]) == "gemma-4"


def test_env_fallback(monkeypatch) -> None:
    monkeypatch.setenv("EAI_TRANSLATION_MODEL", "env-model")
    assert resolve_effective_model_name(None, ["agnes", "env-model"]) == "env-model"


def test_first_model_fallback(monkeypatch) -> None:
    monkeypatch.delenv("EAI_TRANSLATION_MODEL", raising=False)
    assert resolve_effective_model_name(None, ["agnes", "gemma-4"]) == "agnes"


def test_invalid_setting_falls_back(monkeypatch) -> None:
    monkeypatch.delenv("EAI_TRANSLATION_MODEL", raising=False)
    assert resolve_effective_model_name("missing", ["agnes"]) == "agnes"
