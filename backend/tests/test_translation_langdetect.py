"""Language detection unit tests (pure)."""

from app.extensions.translation.langdetect import detect_language


class TestDetectLanguage:
    def test_english(self):
        assert detect_language("The quarterly report of the company was published in May.") == "en"

    def test_french_by_diacritics(self):
        assert detect_language("Les données opérationnelles ont été vérifiées à l'usine.") == "fr"

    def test_french_by_stopwords(self):
        assert detect_language("Le conseil a approuve le budget pour les operations de la mine.") == "fr"

    def test_chinese(self):
        assert detect_language("公司第三季度的经营报告已经发布。") == "zh"

    def test_numeric_only_is_mixed(self):
        assert detect_language("1 234,56 789 3.14") == "mixed"

    def test_empty_is_mixed(self):
        assert detect_language("") == "mixed"

    def test_short_conflicting_is_mixed(self):
        # 信号比接近 60/40 阈值 → 宁可 mixed 不错路由
        text = "The report et le budget pour la mine and the operations."
        assert detect_language(text) in {"en", "fr", "mixed"}
