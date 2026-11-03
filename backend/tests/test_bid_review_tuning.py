"""tuning loader 单测(L2 调参外置 spec 2026-11-03 §4)。seam=monkeypatch _FILE+_cache。"""

from pathlib import Path

import pytest

from app.extensions.bid_review.engine import tuning as tun


@pytest.fixture()
def isolated_tuning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """指向不存在路径 + 清缓存 → 每测全默认起点。"""
    monkeypatch.setattr(tun, "_FILE", tmp_path / "tuning.yaml")
    monkeypatch.setattr(tun, "_cache", None)
    return tmp_path / "tuning.yaml"


def test_defaults_when_file_missing(isolated_tuning: Path) -> None:
    assert tun.get("near_miss_gate") == 0.75
    assert tun.get("evidence_min_sim") == 0.30
    assert tun.get("evidence_top_k") == 3


def test_override_applied(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        "near_miss_gate: 0.9\nevidence_min_sim: 0.5\nevidence_top_k: 5\n",
        encoding="utf-8",
    )
    assert tun.get("near_miss_gate") == 0.9
    assert tun.get("evidence_min_sim") == 0.5
    assert tun.get("evidence_top_k") == 5  # int 键收 int


def test_invalid_values_fall_back_per_key(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        'near_miss_gate: "high"\nevidence_min_sim: 7.0\nevidence_top_k: 0\n',
        encoding="utf-8",
    )
    assert tun.get("near_miss_gate") == 0.75  # 类型错
    assert tun.get("evidence_min_sim") == 0.30  # 超上界
    assert tun.get("evidence_top_k") == 3  # 超下界


def test_bad_yaml_falls_back(isolated_tuning: Path) -> None:
    isolated_tuning.write_text("{oops", encoding="utf-8")
    assert tun.get("near_miss_gate") == 0.75
    assert tun.get("evidence_top_k") == 3


def test_bool_rejected(isolated_tuning: Path) -> None:
    isolated_tuning.write_text("evidence_top_k: true\n", encoding="utf-8")
    assert tun.get("evidence_top_k") == 3  # bool 是 int 子类,显式拒


def test_synonym_defaults_when_file_missing(isolated_tuning: Path) -> None:
    assert tun.synonym_groups() == (
        ("营业执照", "企业法人营业执照"),
        ("审计报告", "年度审计报告"),
    )


def test_synonym_override_replaces_section(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        "evidence_top_k: 5\nsynonyms:\n  - [中标通知书, 招标中标通知书]\n  - [资质证书, 资质证明文件, 资质文件]\n",
        encoding="utf-8",
    )
    assert tun.synonym_groups() == (
        ("中标通知书", "招标中标通知书"),
        ("资质证书", "资质证明文件", "资质文件"),
    )
    assert tun.get("evidence_top_k") == 5  # 数字键与 synonyms 节互不干扰


def test_synonym_bad_groups_dropped(isolated_tuning: Path) -> None:
    isolated_tuning.write_text(
        "synonyms:\n  - [营业执照, 企业法人营业执照]\n  - [只有一项]\n  - [混合, 123, true]\n  - 不是列表\n",
        encoding="utf-8",
    )
    assert tun.synonym_groups() == (("营业执照", "企业法人营业执照"),)


def test_synonym_section_not_a_list_falls_back(isolated_tuning: Path) -> None:
    isolated_tuning.write_text('synonyms: "oops"\n', encoding="utf-8")
    assert tun.synonym_groups() == (
        ("营业执照", "企业法人营业执照"),
        ("审计报告", "年度审计报告"),
    )
