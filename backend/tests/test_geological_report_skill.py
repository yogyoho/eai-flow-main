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
