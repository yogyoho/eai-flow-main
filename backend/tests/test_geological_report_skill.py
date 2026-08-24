"""geological-report SKILL.md v2 结构测试。

v1 版测试断言 LLM 手写时代的章节（质量校验清单/附录A-C 全目录），v2 重写为
管线驱动（表单→冻结→槽位注入→合约→快照）后全部换新。指向 public/ 路径
（v1 误指 custom/，预存 4 failed）。

脚本层行为（六脚本 CLI/退出码/锚点）由 test_geological_report_v2_scripts.py 覆盖；
本文件只锁 SKILL.md 文档结构本身。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"
SKILL_DIR = SKILLS_ROOT / "public" / "geological-report"
SKILL_FILE = SKILL_DIR / "SKILL.md"


def _read_skill_content() -> str:
    if not SKILL_FILE.exists():
        pytest.skip("SKILL.md not yet created")
    return SKILL_FILE.read_text(encoding="utf-8")


def _extract_frontmatter(content: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


class TestFrontmatter:
    def test_skill_file_exists(self):
        assert SKILL_FILE.exists(), f"SKILL.md not found at {SKILL_FILE}"

    def test_skill_file_not_empty(self):
        assert len(_read_skill_content().strip()) > 0

    def test_has_yaml_frontmatter(self):
        content = _read_skill_content()
        assert content.startswith("---\n")
        assert re.match(r"^---\n.*?\n---\n", content, re.DOTALL)

    def test_frontmatter_name(self):
        fm = _extract_frontmatter(_read_skill_content())
        assert fm.get("name") == "geological-report"

    def test_frontmatter_description_mentions_standards(self):
        desc = str(_extract_frontmatter(_read_skill_content()).get("description", ""))
        assert "DZ/T 0033" in desc and "GB/T 13908" in desc

    def test_frontmatter_license(self):
        assert _extract_frontmatter(_read_skill_content()).get("license") is not None

    def test_no_allowed_tools(
        self,
    ):
        """bug-186：allowed-tools 是全局 agent 白名单（跨技能并集），声明即饿死整个 agent。"""
        fm = _extract_frontmatter(_read_skill_content())
        assert fm.get("allowed-tools") is None, "allowed-tools 不得回归（bug-186）"

    def test_parses_via_skill_parser(self):
        skill = parse_skill_file(SKILL_FILE, category=SkillCategory.PUBLIC)
        assert skill is not None
        assert skill.name == "geological-report"
        assert skill.category == SkillCategory.PUBLIC


class TestV2PipelineSections:
    """v2 管线骨架：红线 → 门1 → 冻结门2 → 两波生成 → 组装校验快照 → 修改回路。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_redlines_present(self):
        for kw in ("红线", "禁联网搜索", "绝不编造", "****", "禁现代化改写"):
            assert kw in self.content, kw

    def test_standards_index_only(self):
        """CC3：规范编号仅 standards_index 枚举，禁 LLM 记忆。"""
        assert "standards_index" in self.content
        assert "禁凭记忆" in self.content or "禁 LLM 记忆" in self.content or "禁凭记忆生成" in self.content

    def test_slot_protocol(self):
        """数字永不经过 LLM：{{SLOT:key}} / {{TABLE:fam}}。"""
        assert "{{SLOT:key}}" in self.content and "{{TABLE:fam}}" in self.content

    def test_two_gates(self):
        assert "门 1" in self.content and "门 2" in self.content
        assert "GATE1_COMPLETE" in self.content

    def test_two_wave_generation(self):
        assert "wave1" in self.content and "wave2" in self.content
        assert "要点包" in self.content

    def test_update_sequence_ironlaw(self):
        """bug-2199 顺序铁律：impacted 先行，update 必带 --impacted-file。"""
        assert "顺序铁律" in self.content and "--impacted-file" in self.content

    def test_command_table_covers_six_scripts(self):
        for script in ("ingest.py", "chapter_planner.py", "formula_runner.py", "build_output.py", "consistency.py", "snapshot.py"):
            assert script in self.content, script

    def test_exit_code_semantics(self):
        assert "rc=2" in self.content or "0 干净" in self.content or "/ 2 缺项" in self.content

    def test_kf_mcp_fallback_declaration(self):
        """KF resolve 优先；found=false 须向用户声明 references/ 兜底。"""
        assert "kf_resolve_template" in self.content and "found=false" in self.content

    def test_anomalies_must_be_surfaced(self):
        assert "anomalies" in self.content and "呈现用户" in self.content


class TestDeliveryIronLaw:
    """bug-2225 SKILL.md 交付铁律：build 收尾 + BUILD_READY 粘贴 + manifest 在场。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_delivery_iron_laws_present(self):
        """律1–律4：build 收尾 / BUILD_READY+退出码粘贴 / manifest 在场 / 契约标记勿删。"""
        text = self.content
        assert "交付铁律" in text and "bug-2225" in text
        assert "绝不手工拼装" in text  # 律1
        assert "BUILD_READY" in text and "退出码" in text  # 律2
        assert "delivery_manifest.json" in text  # 律3
        assert ".delivery-contract" in text and "勿删" in text  # 律4

    def test_toc_gate_script_enforced(self):
        """toc 全覆盖由 build_output 目录覆盖门 exit 1 脚本化拦截。"""
        assert "目录覆盖门" in self.content

    def test_workspace_tree_and_command_table(self):
        """outputs/ 是线程级 /mnt/user-data/outputs/（非 workspace 子目录）；步骤0 补标记；速查表退出码。"""
        assert "/mnt/user-data/outputs" in self.content
        assert "skipped_existing" in self.content  # 步骤0 恢复补 .delivery-contract
        assert "MANIFEST_READY" in self.content  # 命令速查 build_output 行


class TestDomainNotes:
    """v2 保留的领域速记（写叙述时的事实基准）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_resource_classification_codes(self):
        for code in ("TM", "KZ", "TD"):
            assert code in self.content, code

    def test_exploration_types(self):
        for t in ("Ⅰ", "Ⅱ", "Ⅲ"):
            assert t in self.content, t

    def test_mineral_adaptation(self):
        assert "矿种适配" in self.content and "煤" in self.content and "铜" in self.content

    def test_standards_references(self):
        assert "DZ/T 0033-2020" in self.content and "GB/T 13908" in self.content

    def test_historical_codes_preserved(self):
        assert "332" in self.content and "111b" in self.content


class TestSkillLoadingIntegration:
    def test_skill_loads_into_storage(self, tmp_path: Path):
        skill_dir = tmp_path / "public" / "geological-report"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL_FILE.read_text(encoding="utf-8"), encoding="utf-8")

        from deerflow.skills.storage import get_or_new_skill_storage

        storage = get_or_new_skill_storage(skills_path=tmp_path)
        skills = storage.load_skills(enabled_only=False)
        geo = next((s for s in skills if s.name == "geological-report"), None)
        assert geo is not None
        assert geo.category == SkillCategory.PUBLIC

    def test_skill_container_path_correct(self, tmp_path: Path):
        skill_dir = tmp_path / "public" / "geological-report"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL_FILE.read_text(encoding="utf-8"), encoding="utf-8")

        from deerflow.skills.storage import get_or_new_skill_storage

        storage = get_or_new_skill_storage(skills_path=tmp_path)
        skills = storage.load_skills(enabled_only=False)
        geo = next(s for s in skills if s.name == "geological-report")
        assert geo.get_container_file_path() == "/mnt/skills/public/geological-report/SKILL.md"

    def test_skill_content_not_truncated(self):
        body = re.sub(r"^---\n.*?\n---\n", "", _read_skill_content(), flags=re.DOTALL)
        assert len(body.strip()) > 500
