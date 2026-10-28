"""Glossary loader/store tests (language dimension + per-block prompt filtering)."""

from pathlib import Path

import yaml

from app.extensions.translation.glossary import (
    GlossaryEntry,
    file_version,
    load_glossary,
    read_entries,
    write_entries,
)


def _write_yaml(path: Path, terms: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"terms": terms}, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_missing_lang_defaults_to_any(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    _write_yaml(path, [{"source": "ArcelorMittal", "action": "forbid"}])

    glossary = load_glossary(str(path))

    for lang in ("en", "fr", "mixed"):
        _, dont = glossary.for_language(lang)
        assert "ArcelorMittal" in dont


def test_language_scoping_and_specific_over_any(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    _write_yaml(
        path,
        [
            {"source": "tonne", "lang": "any", "action": "force", "target": "吨"},
            {"source": "tonne", "lang": "en", "action": "force", "target": "公吨"},
            {"source": "contrat", "lang": "fr", "action": "force", "target": "合同"},
            {"source": "bordereau", "lang": "fr", "action": "forbid"},
        ],
    )

    glossary = load_glossary(str(path))

    en_force, en_dont = glossary.for_language("en")
    fr_force, fr_dont = glossary.for_language("fr")
    mixed_force, mixed_dont = glossary.for_language("mixed")

    assert en_force["tonne"] == "公吨"  # 具体语言覆盖 ANY
    assert fr_force["tonne"] == "吨"
    assert "contrat" not in en_force
    assert fr_force["contrat"] == "合同"
    assert "bordereau" in fr_dont and "bordereau" not in en_dont
    assert mixed_force["contrat"] == "合同"
    assert "bordereau" in mixed_dont


def test_prompt_fragment_only_injects_matching_terms(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    _write_yaml(
        path,
        [
            {"source": "iron ore", "lang": "en", "action": "force", "target": "铁矿石"},
            {"source": "contract", "lang": "en", "action": "force", "target": "合同"},
            {"source": "ArcelorMittal", "lang": "any", "action": "forbid"},
        ],
    )
    glossary = load_glossary(str(path))

    fragment = glossary.prompt_fragment("Iron Ore price from ArcelorMittal", "en")

    assert "iron ore→铁矿石" in fragment
    assert "contract" not in fragment
    assert "ArcelorMittal" in fragment
    assert glossary.prompt_fragment("unrelated text", "en") == ""
    # 法文任务不会注入英文 force 词条
    assert "iron ore" not in glossary.prompt_fragment("iron ore", "fr")


def test_invalid_action_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    _write_yaml(path, [{"source": "bad", "action": "explode", "target": "坏"}])

    assert read_entries(path) == []


def test_write_read_roundtrip_and_version(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    before = file_version(path)

    entries = [
        GlossaryEntry(
            source="iron ore concentrate",
            lang="en",
            action="force",
            target="铁精矿",
            domains=["铁矿开采", "货物运输"],
            notes="首批术语",
        ),
        GlossaryEntry(source="ArcelorMittal", lang="any", action="forbid"),
    ]
    write_entries(path, entries)

    loaded = read_entries(path)
    assert loaded == entries
    assert file_version(path) != before


def test_legacy_single_domain_is_read_as_list(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    _write_yaml(path, [{"source": "freight rate", "action": "forbid", "domain": "货物运输"}])

    entries = read_entries(path)

    assert entries[0].domains == ["货物运输"]
    assert entries[0].notes is None
