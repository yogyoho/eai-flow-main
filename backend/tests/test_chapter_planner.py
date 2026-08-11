"""chapter_planner 测试：章节 manifest 生成 + 受影响章节反查（反馈6）。"""

import json
import sys
from pathlib import Path

# 把 skills/.../scripts 加入 sys.path 以 import chapter_planner
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "skills" / "public" / "water-drainage-report" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import chapter_planner  # noqa: E402

# 用 formulas.json 的真实 section 结构做 fixture
_FORMULAS = _REPO_ROOT / "skills" / "public" / "water-drainage-report" / "references" / "formulas.json"


class TestBuildManifest:
    def test_manifest_has_all_chapters(self):
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        ids = [c["id"] for c in manifest["chapters"]]
        # fallback 10 章
        assert "ch5_calc" in ids and "ch6_pool" in ids and "ch9_equiplist" in ids
        assert len(manifest["chapters"]) == 10

    def test_formulas_assigned_by_section(self):
        """section 6.1.x → ch5_calc；7.1.x → ch6_pool；9.1.x → ch8_filter。"""
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        by_id = {c["id"]: c for c in manifest["chapters"]}
        assert "Qe" in by_id["ch5_calc"]["formula_ids"]  # 6.1.1
        assert "Qm" in by_id["ch5_calc"]["formula_ids"]  # 6.1.4
        assert "V_pool" in by_id["ch6_pool"]["formula_ids"]  # 7.1.1
        assert "Qsf" in by_id["ch8_filter"]["formula_ids"]  # 9.1.1

    def test_equiplist_has_explicit_filter_count(self):
        """ch9_equiplist 无 section_prefixes，靠显式 formula_ids 收 filter_count（展示章）。

        回归锚：设备一览表展示 filter_count 台数；若丢失，改 filter_count 不会标记
        设备一览表重生成（反馈6 漏更新，见评审 I1）。"""
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        by_id = {c["id"]: c for c in manifest["chapters"]}
        assert "filter_count" in by_id["ch9_equiplist"]["formula_ids"]


class TestImpactedChapters:
    def _manifest(self):
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        return chapter_planner.build_manifest(formulas)

    def test_q_change_hits_calc_chapter(self):
        """改 Q → 影响含 Qe/Qm 的 ch5_calc。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["Qe", "Qw", "Qb", "Qm"], manifest)
        assert "ch5_calc" in chapters

    def test_no_affected_returns_empty(self):
        manifest = self._manifest()
        assert chapter_planner.impacted_chapters([], manifest) == []

    def test_dedup(self):
        """多个受影响公式落在同一章时，章节只出现一次。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["Qe", "Qb", "Qm"], manifest)
        assert chapters.count("ch5_calc") == 1

    def test_filter_count_hits_both_filter_and_equiplist(self):
        """filter_count 同属 ch8_filter（计算章,section 9）和 ch9_equiplist（展示章,显式）。

        回归锚：一个公式可落在多章——计算结果既驱动其计算章，也驱动展示该值的设备一览表。
        改 filter_count 必须同时标记两章重生成（反馈6 设备一览表不再漏更新,评审 I1）。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["filter_count"], manifest)
        assert "ch8_filter" in chapters
        assert "ch9_equiplist" in chapters
