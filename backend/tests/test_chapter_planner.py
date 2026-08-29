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
        # 样例体例 9 节 + 合规附录（2026-08-29 对齐：ch9_equiplist/ch10_drawings 已裁撤）
        assert "ch6_calc" in ids and "ch7_pool" in ids and "ch9_filter" in ids
        assert "ch10_compliance" in ids
        assert "ch9_equiplist" not in ids and "ch10_drawings" not in ids and "ch11_compliance" not in ids
        assert len(manifest["chapters"]) == 10

    def test_formulas_assigned_by_section(self):
        """section 6.1.x → ch6_calc；7.1.x → ch7_pool；9.1.x → ch9_filter。

        样例体例下公式 section 编号即报告编号（6.1.1 → 报告 6.1.1 节）。"""
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        by_id = {c["id"]: c for c in manifest["chapters"]}
        assert "Qe" in by_id["ch6_calc"]["formula_ids"]  # 6.1.1
        assert "Qm" in by_id["ch6_calc"]["formula_ids"]  # 6.1.4
        assert "V_pool" in by_id["ch7_pool"]["formula_ids"]  # 7.1.1
        assert "Qsf" in by_id["ch9_filter"]["formula_ids"]  # 9.1.1

    def test_filter_count_routes_to_filter_section(self):
        """filter_count（section 9.1.2）唯一落在 ch9_filter（旁滤设备节）。

        回归锚（原设备一览表 dual-home 测试改写）：2026-08-29 体例对齐裁撤了
        ch9_equiplist 展示章——样例不单设设备表，设备规格叙述并入 7.2.4/8.2.1，
        由受影响计算节连带重生成；filter_count 只保留 section 前缀 "9" 单一归属。"""
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        manifest = chapter_planner.build_manifest(formulas)
        by_id = {c["id"]: c for c in manifest["chapters"]}
        assert "filter_count" in by_id["ch9_filter"]["formula_ids"]


class TestImpactedChapters:
    def _manifest(self):
        with open(_FORMULAS, encoding="utf-8") as f:
            formulas = json.load(f)["formulas"]
        return chapter_planner.build_manifest(formulas)

    def test_q_change_hits_calc_chapter(self):
        """改 Q → 影响含 Qe/Qm 的 ch6_calc。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["Qe", "Qw", "Qb", "Qm"], manifest)
        assert "ch6_calc" in chapters

    def test_no_affected_returns_empty(self):
        manifest = self._manifest()
        assert chapter_planner.impacted_chapters([], manifest) == []

    def test_dedup(self):
        """多个受影响公式落在同一节时，章节只出现一次。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["Qe", "Qb", "Qm"], manifest)
        assert chapters.count("ch6_calc") == 1

    def test_filter_count_hits_filter_and_compliance(self):
        """改 filter_count → ch9_filter（section 9 计算节）必被标记。

        bug-2199 锚点同测：合规附录 ch10_compliance 依赖全量公式，任何公式集
        都必须连带标记附录重生成。"""
        manifest = self._manifest()
        chapters = chapter_planner.impacted_chapters(["filter_count"], manifest)
        assert "ch9_filter" in chapters
        assert "ch10_compliance" in chapters
