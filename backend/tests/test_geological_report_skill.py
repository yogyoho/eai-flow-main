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

    def test_frontmatter_description_trigger_keywords(self):
        """bug-2234：description 是 system prompt 里唯一触发匹配面，须前置场景触发词+禁自创表单指令。"""
        desc = str(_extract_frontmatter(_read_skill_content()).get("description", ""))
        for kw in ("固体矿产地质勘查报告", "储量核实", "普查/详查/勘探", "不得即兴自创问卷"):
            assert kw in desc, kw

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

    def test_knowledge_search_wiring(self):
        """knowledge_search（harness RAGFlow 检索）为范文参照主通道；红线不随工具接入放宽。"""
        assert "knowledge_search" in self.content and "ragflow-laws-standards" in self.content
        window = self.content[self.content.index("knowledge_search") : self.content.index("knowledge_search") + 600]
        assert "矿名/地名" in window, "检索红线必须随工具接入同步在场"
        assert "standards_index" in window, "规范引用仍只从 standards_index 枚举"

    def test_anomalies_must_be_surfaced(self):
        assert "anomalies" in self.content and "呈现用户" in self.content

    def test_single_clarification_per_turn(self):
        """单回合至多一次 ask_clarification：连发多张表单只有最后一张可填（线程 03e18e4a 页面实测 5/2/4/4 连发）。"""
        assert "单回合至多一次" in self.content and "一次只问一个类别" in self.content
        # 机制原因必须在场——带原因的铁律在长上下文里更不容易被模型丢弃
        assert "冻结" in self.content and "落盘" in self.content


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


class TestDataExpectationPrompt:
    """SKILL.md 步骤1 数据预告 presence（spec 2026-08-25 §6）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_data_expectation_present(self):
        assert "数据预告" in self.content
        assert "data_expectations.json" in self.content

    def test_first_turn_atomic_actions(self):
        """bug-2231 页面实测：开题三件套（KF 真实调用→兜底声明→数据预告用户可见）一轮做完、不可只说不做。"""
        assert "开题首动作" in self.content
        assert "只说不做" in self.content
        assert "口头声称" in self.content
        assert "question" in self.content and "首张表单" in self.content  # 预告载体=首张卡片，防只说不做


class TestUploadRequestChannel:
    """bug-2233 页面实测：索要文件上传用普通消息收尾，不做成 ask_clarification 卡片（无文件控件）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_upload_request_is_plain_message(self):
        assert "索要上传" in self.content and "模态错配" in self.content
        assert "绝不做成 ask_clarification 卡片" in self.content


class TestDepthParadigm:
    """SKILL.md 步骤4 深度范式升级 presence（spec 2026-08-25 §6）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill_content()

    def test_step4_depth_rules(self):
        for kw in ("逐要素成段", "五步解读", "动笔前读深度目标", "depth_targets.json", "深度目标门", "不砍段"):
            assert kw in self.content, kw

    def test_command_table(self):
        assert "calibrate.py" in self.content  # 速查表新增行
        assert "--targets" in self.content  # build_output 用法补可选参
