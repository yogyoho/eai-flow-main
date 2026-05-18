"""TDD tests for the geological-report SKILL.md.

Validates that the skill file:
1. Parses correctly through the existing skills parser
2. Has valid frontmatter (name, description, license, allowed-tools)
3. Contains all required content sections per the design spec
4. Includes the three report stage templates
5. Contains mineral-type adaptation guides
6. Contains resource classification and quality checklists
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"
SKILL_DIR = SKILLS_ROOT / "custom" / "geological-report"
SKILL_FILE = SKILL_DIR / "SKILL.md"


def _read_skill_content() -> str:
    """Read the SKILL.md file content; skip if not yet created."""
    if not SKILL_FILE.exists():
        pytest.skip("SKILL.md not yet created")
    return SKILL_FILE.read_text(encoding="utf-8")


def _extract_frontmatter(content: str) -> dict:
    """Extract and parse YAML frontmatter from SKILL.md content."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


# ---------------------------------------------------------------------------
# Group 1: Frontmatter validation
# ---------------------------------------------------------------------------


class TestFrontmatter:
    """Verify SKILL.md frontmatter is valid and parseable."""

    def test_skill_file_exists(self):
        """SKILL.md file must exist at the expected path."""
        assert SKILL_FILE.exists(), f"SKILL.md not found at {SKILL_FILE}"

    def test_skill_file_not_empty(self):
        """SKILL.md must not be empty."""
        content = _read_skill_content()
        assert len(content.strip()) > 0

    def test_has_yaml_frontmatter(self):
        """SKILL.md must start with YAML frontmatter block."""
        content = _read_skill_content()
        assert content.startswith("---\n"), "SKILL.md must start with --- frontmatter delimiter"
        # Must have closing --- on its own line
        match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
        assert match, "SKILL.md must have properly closed YAML frontmatter"

    def test_frontmatter_name(self):
        """Frontmatter must have name='geological-report'."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        assert fm.get("name") == "geological-report"

    def test_frontmatter_description_not_empty(self):
        """Frontmatter description must be non-empty."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        desc = fm.get("description", "")
        assert isinstance(desc, str) and len(desc.strip()) > 0

    def test_frontmatter_description_mentions_standards(self):
        """Description must mention key standards."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        desc = fm.get("description", "")
        assert "DZ/T 0033" in desc
        assert "GB/T 13908" in desc

    def test_frontmatter_license(self):
        """Frontmatter must specify license."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        assert fm.get("license") is not None

    def test_frontmatter_allowed_tools(self):
        """Frontmatter allowed-tools must be a list of valid tool names."""
        content = _read_skill_content()
        fm = _extract_frontmatter(content)
        tools = fm.get("allowed-tools")
        assert isinstance(tools, list)
        assert len(tools) > 0
        expected_tools = {"bash", "read_file", "write_file", "str_replace", "ls", "ask_clarification"}
        assert set(tools) == expected_tools

    def test_parses_via_skill_parser(self):
        """SKILL.md must parse successfully through the DeerFlow skills parser."""
        skill = parse_skill_file(SKILL_FILE, category=SkillCategory.CUSTOM)
        assert skill is not None, "parse_skill_file returned None — check frontmatter format"
        assert skill.name == "geological-report"
        assert skill.category == SkillCategory.CUSTOM
        assert skill.license is not None
        assert skill.allowed_tools is not None
        assert len(skill.allowed_tools) > 0


# ---------------------------------------------------------------------------
# Group 2: Structural sections
# ---------------------------------------------------------------------------


class TestStructuralSections:
    """Verify SKILL.md contains all required content sections (design spec §2.3)."""

    @pytest.fixture(autouse=True)
    def _load_content(self):
        self.content = _read_skill_content()

    def test_has_workflow_protocol_section(self):
        """Must contain workflow protocol section."""
        assert "工作流协议" in self.content or "## 工作流" in self.content

    def test_has_stage_templates_section(self):
        """Must contain report stage templates section."""
        assert "附录A" in self.content or "普查" in self.content
        assert "附录B" in self.content or "详查" in self.content
        assert "附录C" in self.content or "勘探" in self.content

    def test_has_technical_requirements_section(self):
        """Must contain technical requirements section (GB/T 13908-2020)."""
        assert "勘查类型" in self.content
        assert "工程间距" in self.content

    def test_has_resource_classification_section(self):
        """Must contain resource classification section (TD/KZ/TM/KX/ZS)."""
        for code in ["TD", "KZ", "TM", "KX", "ZS"]:
            assert code in self.content, f"Resource classification code {code} not found"

    def test_has_quality_checklist_section(self):
        """Must contain quality checklist section."""
        assert "质量校验" in self.content or "质量自检" in self.content or "质量检查" in self.content

    def test_has_mineral_adaptation_section(self):
        """Must contain mineral-type adaptation section."""
        assert "矿种适配" in self.content or "矿种" in self.content
        assert "煤" in self.content
        assert "铜" in self.content

    def test_has_output_specification_section(self):
        """Must contain output specification section."""
        assert "输出规范" in self.content or "输出格式" in self.content
        assert "/mnt/user-data/outputs" in self.content

    def test_has_dual_mode_workflow(self):
        """Must describe both auto-parse and conversational guidance modes."""
        assert "自动解析" in self.content or "解析模式" in self.content
        assert "对话引导" in self.content or "引导模式" in self.content

    def test_has_conversational_question_sequence(self):
        """Must define the information collection question sequence."""
        assert "矿种" in self.content
        assert "勘查阶段" in self.content
        assert "资源量估算" in self.content


# ---------------------------------------------------------------------------
# Group 3: Content depth validation
# ---------------------------------------------------------------------------


class TestContentDepth:
    """Verify specific content details from the design spec are present."""

    @pytest.fixture(autouse=True)
    def _load_content(self):
        self.content = _read_skill_content()

    # --- Census template completeness ---

    def test_census_template_has_six_chapters(self):
        """Census (附录A) template must have chapters 绪论 through 结论."""
        assert "第一章 绪论" in self.content
        assert "结论与建议" in self.content

    def test_census_template_has_resource_estimation(self):
        """Census template must include resource estimation chapter."""
        assert "资源量估算" in self.content
        assert "工业指标" in self.content
        assert "估算方法" in self.content

    # --- Detailed template completeness ---

    def test_detailed_template_has_mining_conditions(self):
        """Detailed (附录B) template must include mining conditions."""
        assert "水文地质" in self.content
        assert "工程地质" in self.content
        assert "环境地质" in self.content

    def test_detailed_template_has_quality_assessment(self):
        """Detailed template must include exploration quality assessment."""
        assert "勘查工作" in self.content
        assert "质量评述" in self.content

    # --- Exploration template completeness ---

    def test_exploration_template_has_economic_evaluation(self):
        """Exploration (附录C) template must include economic evaluation."""
        assert "经济评价" in self.content

    # --- Resource classification completeness ---

    def test_resource_classification_has_all_codes_defined(self):
        """Each resource classification code must have its full name defined."""
        assert "TM" in self.content
        assert "探明" in self.content or "探明的" in self.content
        assert "KZ" in self.content
        assert "控制" in self.content or "控制的" in self.content
        assert "TD" in self.content
        assert "推断" in self.content or "推定的" in self.content

    # --- Mineral adaptation completeness ---

    def test_coal_adaptation_has_industrial_indicators(self):
        """Coal adaptation must list key industrial indicators."""
        assert "最低可采厚度" in self.content
        assert "灰分" in self.content
        assert "发热量" in self.content

    def test_copper_adaptation_has_analysis_items(self):
        """Copper adaptation must list analysis items."""
        assert "Cu" in self.content
        assert "Ag" in self.content or "Au" in self.content

    # --- Standards references ---

    def test_references_dz0033(self):
        """Must reference DZ/T 0033-2020."""
        assert "DZ/T 0033" in self.content
        assert "2020" in self.content

    def test_references_gb13908(self):
        """Must reference GB/T 13908-2020."""
        assert "GB/T 13908" in self.content

    def test_references_gb33444(self):
        """Must reference GB/T 33444-2016."""
        assert "GB/T 33444" in self.content or "33444" in self.content

    # --- Quality checklist items ---

    def test_quality_checklist_has_completeness_items(self):
        """Quality checklist must cover completeness checks."""
        assert "完整性" in self.content

    def test_quality_checklist_has_consistency_items(self):
        """Quality checklist must cover data consistency checks."""
        assert "一致性" in self.content

    # --- Output specification ---

    def test_output_spec_has_markdown_format(self):
        """Output spec must specify Markdown format."""
        assert "Markdown" in self.content

    def test_output_spec_has_chapter_numbering(self):
        """Output spec must define chapter numbering scheme."""
        assert "第一章" in self.content
        assert "1.1" in self.content


# ---------------------------------------------------------------------------
# Group 4: Skill loading integration
# ---------------------------------------------------------------------------


class TestSkillLoadingIntegration:
    """Verify the skill integrates with the DeerFlow skills system."""

    def test_skill_loads_into_storage(self, tmp_path: Path):
        """Skill should be discoverable by LocalSkillStorage when placed in custom/."""
        skill_dir = tmp_path / "custom" / "geological-report"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            SKILL_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )

        from deerflow.skills.storage import get_or_new_skill_storage

        storage = get_or_new_skill_storage(skills_path=tmp_path)
        skills = storage.load_skills(enabled_only=False)
        geo_skill = next((s for s in skills if s.name == "geological-report"), None)
        assert geo_skill is not None
        assert geo_skill.category == SkillCategory.CUSTOM

    def test_skill_container_path_correct(self, tmp_path: Path):
        """Skill container path must point to the correct custom location."""
        skill_dir = tmp_path / "custom" / "geological-report"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            SKILL_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )

        from deerflow.skills.storage import get_or_new_skill_storage

        storage = get_or_new_skill_storage(skills_path=tmp_path)
        skills = storage.load_skills(enabled_only=False)
        geo_skill = next(s for s in skills if s.name == "geological-report")
        assert geo_skill.get_container_file_path() == "/mnt/skills/custom/geological-report/SKILL.md"

    def test_skill_content_not_truncated(self):
        """Skill body content must not be empty (real content exists beyond frontmatter)."""
        content = _read_skill_content()
        # Remove frontmatter
        body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
        assert len(body.strip()) > 500, "SKILL.md body seems too short — content may be missing"
