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


class TestM1SixTypes:
    """M1 补 6 类(spec 2026-11-04 §4 裁决④,2026-11-05):真实字典 ≥14 键,内容自证词 ≥2 字。"""

    _NEW = ["保证金回单", "授权委托书", "法定代表人身份证明", "竣工验收报告", "检测报告", "制造商授权"]

    def test_real_dictionary_has_six_new_types(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fp, "_cache", None)
        table = fp.load()
        assert len(table) >= 14
        for name in self._NEW:
            assert table.get(name), f"缺指纹类型 {name}"

    def test_no_single_char_generic_words(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fp, "_cache", None)
        for words in fp.load().values():
            for w in words:
                assert len(w) >= 2, f"泛词风险: {w}"


class TestEntityFingerprintChannel:
    """M1 实体级指纹通道(spec 2026-11-04 §4 消费面,2026-11-05):实体 type_fingerprint
    直连规则卡(check._entities 注入);缺席/空 → 卡不带该节,行为=现状(裁决⑤ join key 通道序不动)。"""

    def test_summary_projection(self):
        from app.extensions.bid_review.engine.llm_runner import _entity_fingerprint_summary

        fields = {
            "bid.attachments": [
                {"name": "营业执照副本", "type_fingerprint": "营业执照", "is_empty_text": False, "pages": [1, 2]},
                {"name": "x", "type_fingerprint": None, "is_empty_text": True},
                "junk",
                {"pages": [1]},
            ]
        }
        assert _entity_fingerprint_summary(fields) == [
            {"name": "营业执照副本", "type_fingerprint": "营业执照", "is_empty_text": False},
            {"name": "x", "type_fingerprint": None, "is_empty_text": True},
        ]
        assert _entity_fingerprint_summary({}) == []
        assert _entity_fingerprint_summary(None) == []
        assert _entity_fingerprint_summary({"bid.attachments": "junk"}) == []

    @pytest.mark.asyncio
    async def test_card_injects_entities(self):
        from app.extensions.bid_review.engine.llm_runner import run_sem_rule

        rule = {
            "id": "L2-999",
            "name": "指纹测试",
            "layer": "L2",
            "type": "semantic",
            "inputs": ["bid.attachment_index"],
            "check": {"fingerprints": "external", "verdict_set": ["full", "partial", "none", "unclear"]},
            "severity": "major",
            "message_tpl": "x",
            "fix_tpl": "y",
        }
        fields = {"bid.attachments": [{"name": "营业执照副本", "type_fingerprint": "营业执照", "is_empty_text": False}]}
        captured: dict = {}

        async def _fake_model(messages):
            captured["card"] = messages[0]["content"]
            raise ValueError("stop")

        with pytest.raises(ValueError):
            await run_sem_rule(rule, fields, "MATERIALS", _fake_model, {})
        assert "营业执照副本" in captured["card"]
        assert '"_entities"' in captured["card"]

    @pytest.mark.asyncio
    async def test_card_without_entities_has_no_section(self):
        from app.extensions.bid_review.engine.llm_runner import run_sem_rule

        rule = {
            "id": "L2-999",
            "name": "指纹测试",
            "layer": "L2",
            "type": "semantic",
            "inputs": ["bid.attachment_index"],
            "check": {"fingerprints": "external", "verdict_set": ["full", "partial", "none", "unclear"]},
            "severity": "major",
            "message_tpl": "x",
            "fix_tpl": "y",
        }
        captured: dict = {}

        async def _fake_model(messages):
            captured["card"] = messages[0]["content"]
            raise ValueError("stop")

        with pytest.raises(ValueError):
            await run_sem_rule(rule, {}, "MATERIALS", _fake_model, {})
        assert '"_entities"' not in captured["card"]
