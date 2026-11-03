"""指纹字典 loader 单测(L2 指纹通道 spec 2026-11-04 §2.2)。seam=monkeypatch _FILE+_cache。"""

from pathlib import Path

import pytest

from app.extensions.bid_review.engine import fingerprints as fp


@pytest.fixture()
def isolated_fp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fp, "_FILE", tmp_path / "fingerprints.yaml")
    monkeypatch.setattr(fp, "_cache", None)
    return tmp_path / "fingerprints.yaml"


def test_default_empty_when_missing(isolated_fp: Path) -> None:
    assert fp.load() == {}


def test_valid_yaml_loaded(isolated_fp: Path) -> None:
    isolated_fp.write_text("营业执照: [统一社会信用代码, 注册资本]\n安全生产许可证: [许可证编号]\n", encoding="utf-8")
    assert fp.load() == {"营业执照": ["统一社会信用代码", "注册资本"], "安全生产许可证": ["许可证编号"]}


def test_bad_entries_dropped(isolated_fp: Path) -> None:
    isolated_fp.write_text("营业执照: [统一社会信用代码, 123]\n坏组: 不是列表\n空组: []\n合规: [许可证编号]\n", encoding="utf-8")
    assert fp.load() == {"合规": ["许可证编号"]}
