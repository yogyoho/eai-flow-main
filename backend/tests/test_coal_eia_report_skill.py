"""coal-eia-report SKILL.md v2 结构 + stages/planning_eia.json 接口测试（T7 文件②）。

对齐 geo 先例 test_geological_report_skill.py：本文件只锁 SKILL.md 文档结构与
references 结构真源（stage/contracts/depth_targets/sample_entities）的接口契约；
脚本层行为（CLI/退出码/门语义）由 test_coal_eia_report_v2_scripts.py 覆盖。

设计依据: docs/designs/coal-eia-report-v2.md（D8 结构去污染 / D9 粒度分层 /
D11 节级依赖 / D12 章树供给；allowed-tools 禁令=bug-186）。
运行: cd backend && PYTHONPATH=. uv run pytest tests/test_coal_eia_report_skill.py -v
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "skills" / "public" / "coal-eia-report"
SKILL_FILE = SKILL / "SKILL.md"
SCRIPTS = SKILL / "scripts"  # conftest._SkillScriptsFinder 依赖此模块级常量做同名脚本隔离
STAGE = SKILL / "references" / "stages" / "planning_eia.json"
CONTRACTS = SKILL / "references" / "consistency_contracts.json"
DEPTH = SKILL / "references" / "depth_targets" / "planning_eia.json"


def _read_skill() -> str:
    if not SKILL_FILE.exists():
        pytest.skip("SKILL.md not yet created")
    return SKILL_FILE.read_text(encoding="utf-8")


def _frontmatter(content: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    return yaml.safe_load(m.group(1)) or {} if m else {}


def _stage() -> dict:
    return json.loads(STAGE.read_text(encoding="utf-8"))


class TestFrontmatter:
    def test_skill_file_exists(self):
        assert SKILL_FILE.exists()

    def test_frontmatter_name(self):
        assert _frontmatter(_read_skill()).get("name") == "coal-eia-report"

    def test_frontmatter_license(self):
        assert _frontmatter(_read_skill()).get("license") is not None

    def test_no_allowed_tools(self):
        """bug-186：allowed-tools 是全局 agent 白名单（跨技能并集），声明即饿死整个 agent。"""
        assert _frontmatter(_read_skill()).get("allowed-tools") is None, "allowed-tools 不得回归（bug-186）"

    def test_description_trigger_keywords(self):
        """bug-2234 同构：description 是 system prompt 唯一触发匹配面，须前置场景触发词+禁自创指令。"""
        desc = str(_frontmatter(_read_skill()).get("description", ""))
        for kw in ("环境影响报告书", "环境影响评价报告", "矿区总体规划", "井", "不得即兴自创问卷", "{{SLOT:key}}"):
            assert kw in desc, kw

    def test_description_stage_matrix(self):
        """stage 选择面：planning_eia / project_eia_underground 一期两 stage；openpit/post 二期标注。"""
        desc = str(_frontmatter(_read_skill()).get("description", ""))
        assert "planning_eia" in desc and "project_eia_underground" in desc
        assert "二期" in desc


class TestRedlines:
    """红线 P1–P6 全套在场（geo P1–P5 移植 + 环评特例：类比来源/口径标签/数字零过 LLM）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill()

    def test_redline_header_and_basics(self):
        for kw in ("红线", "禁联网搜索", "绝不编造", "[待确认]"):
            assert kw in self.content, kw

    def test_no_llm_numbers(self):
        """P6/SL1 根基：数字永不经过 LLM，正文只写 {{SLOT:key}}/{{TABLE:族}}。"""
        assert "数字永不经过 LLM" in self.content
        assert "{{SLOT:key}}" in self.content and "{{TABLE:族}}" in self.content

    def test_analog_source_enum(self):
        """D4/月儿湾 §5-A：监测/岩移参数来源必须枚举，沉陷参数 param_source 三值枚举强制。"""
        assert "user_monitoring" in self.content and "analog_mine" in self.content
        assert "param_source" in self.content and "规范推荐" in self.content

    def test_sample_entity_ban(self):
        """P3：范文只学范式禁抄——实体清单 + 范文数值禁入。"""
        assert "sample_entities" in self.content and "禁入" in self.content

    def test_caliber_labels(self):
        """P4 环评扩展：修编双口径 *_before/*_after 成对字段 + 口径标签绑定。"""
        assert "*_before" in self.content and "*_after" in self.content and "口径标签" in self.content

    def test_standards_index_only(self):
        assert "standards_index.json" in self.content and "禁凭记忆" in self.content

    def test_software_transcription_boundary(self):
        """能力边界（月儿湾 §5-B）：开采沉陷软件成果走表单转录，禁公式硬凑。"""
        assert "开采沉陷软件" in self.content and "禁" in self.content


class TestPipelineSections:
    """v2 管线骨架：步骤 0–7 标题 + 两道门 + 两层状态模型 + 派发/停车/修改回路。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill()

    def test_step_headings_0_to_7(self):
        for head in ("步骤 0", "步骤 1", "步骤 2–3", "步骤 4", "步骤 5–7"):
            assert f"### {head}" in self.content, head

    def test_two_gates(self):
        assert "门 1" in self.content and "GATE1_COMPLETE" in self.content
        assert "门 2" in self.content and "anomalies" in self.content

    def test_two_layer_state_model(self):
        """两层模型：派发/交付=节级、门禁=章级、节无独立门。"""
        assert "节级" in self.content and "章级" in self.content
        assert "节 VERIFIED" in self.content and "唯一通道" in self.content

    def test_two_layer_workspace_tree(self):
        for kw in ("state/", "sections/", "chapters/", "mapping.json", "formula_state.json", "progress.json"):
            assert kw in self.content, kw

    def test_single_chapter_gate_and_batch(self):
        assert "--chapter" in self.content and "progress.py gate" in self.content

    def test_controller_protocol(self):
        """步骤4 控制器模式：薄上下文协调、batch_task 分波、批量记账（bug-3048）、VERIFIED 禁手动（bug-3049）。"""
        for kw in ("控制器", "batch_task", "mark --sections", "bug-3048", "bug-3049"):
            assert kw in self.content, kw

    def test_dispatch_contract_fields(self):
        """派发契约注入 stage 要素链 + 范文禁入清单 + 节级深度目标。"""
        for kw in ("派发契约", "depth_targets", "sample_entities/_index.json", "直写", "### "):
            assert kw in self.content, kw

    def test_stop_contract(self):
        """停车契约：700 页多 run 推进是默认生存方式；发卡即停。"""
        assert "停车" in self.content and "发卡即停" in self.content and "batch_task" in self.content

    def test_iron_law_and_excuse_reality(self):
        assert "Iron Law" in self.content and "Excuse" in self.content and "Reality" in self.content
        assert "approve-downgrade" in self.content

    def test_key_points_projection_chapter(self):
        """波间要点包 = 投影章唯一事实源（EO3 反向断言锚）。"""
        assert "要点包" in self.content and "key_points.json" in self.content and "confirm-key-points" in self.content

    def test_modification_loop_ironlaw(self):
        """顺序铁律（bug-2199）+ D11 节级反查。"""
        assert "顺序铁律" in self.content and "--impacted-file" in self.content
        assert "--deps" in self.content and "owners ∪ consumers" in self.content

    def test_granularity_ironlaw(self):
        """D9 粒度铁律：编辑器叶子=节、组装回章级过门。"""
        assert "粒度铁律" in self.content and "节" in self.content and "1.5 万字" in self.content

    def test_delivery_dual_channel(self):
        """D6 交付双通道：项目路径逐节 write_chapter（mapping.json 取 UUID）+ 独立路径单文件。"""
        assert "project_write_chapter" in self.content and "mapping.json" in self.content
        assert "present_files" in self.content
        assert "delivered --sections" in self.content

    def test_delivery_iron_laws(self):
        """交付铁律（bug-2225 同构）：build 收尾/BUILD_READY 粘贴/契约标记勿删。"""
        assert "交付铁律" in self.content and "绝不手工拼装" in self.content
        assert "BUILD_READY" in self.content and "MANIFEST_READY" in self.content
        assert ".delivery-contract" in self.content and "勿删" in self.content

    def test_order_free_toc_gate(self):
        """序无关目录覆盖门（章级必备/可选集匹配，序不校验；ABSENT 豁免）。"""
        for kw in ("序无关目录覆盖门", "必备", "可选", "ABSENT", "超集"):
            assert kw in self.content, kw

    def test_conditional_contract_activation(self):
        """合约条件激活：缺席记 skip 非 fail。"""
        assert "skip 非 fail" in self.content and "applicable_stages" in self.content

    def test_kf_contract_and_domain_keywords(self):
        """KF resolve 优先 + references 兜底；domain_keywords 必带（bug-3066）。"""
        assert "kf_resolve_template" in self.content and "domain_keywords" in self.content
        assert "seed_gen.py" in self.content  # D12：stage→KF 模板 seed 单向生成

    def test_capability_boundaries_section(self):
        """能力边界（走查 §5-B/C 回写）：沉陷软件黑箱/生态土壤方法学/air_screen 点源/公式 OLE 化。"""
        for kw in ("能力边界", "air_screen", "面源", "OLE", "生态"):
            assert kw in self.content, kw


class TestCommandTable:
    """命令速查表：每条命令引用的脚本必须在 scripts/ 实有；核心 9 脚本全覆盖。"""

    CORE_SCRIPTS = (
        "ingest.py",
        "formula_runner.py",
        "chapter_planner.py",
        "consistency.py",
        "build_output.py",
        "snapshot.py",
        "progress.py",
        "mapping.py",
        "seed_gen.py",
    )

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read_skill()

    def test_referenced_scripts_all_exist(self):
        """速查表每行行首脚本名 ↔ scripts/ 实有文件（命令速查与磁盘不许两张皮）。"""
        rows = set(re.findall(r"^\| `([A-Za-z_]+\.py)", self.content, re.M))
        assert rows, "未解析到命令速查表行——表结构变了？"
        missing = sorted(r for r in rows if not (SCRIPTS / r).is_file())
        assert not missing, f"速查表引用了不存在的脚本: {missing}"

    def test_core_nine_scripts_covered(self):
        for script in self.CORE_SCRIPTS:
            assert script in self.content, script

    def test_maintenance_scripts_annotation(self):
        """calibrate/bank_compile 二期维护工具不入管线命令面——须有显式注记。"""
        assert "calibrate.py" in self.content and "bank_compile.py" in self.content and "二期" in self.content

    def test_rc_semantics_columns(self):
        assert "关键退出码" in self.content and "rc" in self.content

    def test_script_prefix_convention(self):
        assert "python -X utf8" in self.content


class TestStageInterface:
    """references/stages/planning_eia.json 接口断言（唯一结构真源，13 章/77 节定稿）。"""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.stage = _stage()

    def test_identity_and_version(self):
        assert self.stage.get("stage_id") == "planning_eia"
        assert self.stage.get("stage") == "规划环评"
        assert str(self.stage.get("version", "")).startswith("2.")

    def test_13_chapters_77_sections(self):
        chs = self.stage["chapters"]
        assert len(chs) == 13, len(chs)
        n_secs = sum(len(c.get("sections", [])) for c in chs.values())
        assert n_secs == 77, n_secs
        assert "ch13" in chs and chs["ch13"]["title"] == "结论与建议"

    def test_chapter_order_policy_order_free(self):
        """序无关门的结构源：章序不锁死（回填对账：13/13 骨架收敛、章号级一致仅 7/13）。"""
        assert self.stage.get("chapter_order_policy") == "order_free_with_semantic_match"
        assert "互换" in self.stage.get("order_policy_note", "")

    def test_section_id_contract(self):
        """节 id 契约 = progress.init 解析前提：chNN_SNN、章前缀一致、章内唯一。"""
        for cid, ch in self.stage["chapters"].items():
            seen = set()
            for s in ch.get("sections", []):
                sid = s["id"]
                assert re.fullmatch(r"ch\d+_S\d+", sid), sid
                assert sid.startswith(cid + "_S"), (cid, sid)
                assert sid not in seen, sid
                seen.add(sid)
                assert s.get("title"), sid

    def test_variant_swap_layout_policy(self):
        """第 4/5 章回顾/识别互换双模式（layout_policy.variant_swap）。"""
        vs = (self.stage.get("layout_policy") or {}).get("variant_swap")
        assert vs and "ch4" in str(vs) and "ch5" in str(vs)

    def test_forms_33_families_with_runner_families(self):
        forms = self.stage.get("forms", {})
        assert len(forms) == 33, len(forms)
        for fam in ("project", "mine_plan", "subsidence_params", "water", "air", "noise", "solid_waste", "sensitive_targets", "standards_confirm"):
            assert fam in forms, fam

    def test_subsidence_param_source_enum_required(self):
        """D4/月儿湾 §5-A 回写：param_source 三值枚举必填。"""
        fd = {f["name"]: f for f in self.stage["forms"]["subsidence_params"]["fields"]}
        ps = fd.get("param_source", {})
        assert ps.get("required", True) is True
        for v in ("规范推荐值", "实测岩移回归", "类比矿实测"):
            assert v in ps.get("type", ""), (v, ps.get("type"))

    def test_mine_plan_before_after_pairs(self):
        """修编双口径（D4）：*_before/*_after 成对字段在场。"""
        names = {f["name"] for f in self.stage["forms"]["mine_plan"]["fields"]}
        assert "total_scale_mt_a_before" in names and "total_scale_mt_a_after" in names
        assert "minefield_area_km2_after" in names

    def test_capability_boundaries_recorded(self):
        """能力边界两条进 stage（走查 §5-B/C 回写）。"""
        cb = " ".join(self.stage.get("capability_boundaries", []))
        assert "不入 formula freeze" in cb and "air_screen" in cb

    def test_std_ref_no_llm_memory(self):
        assert "禁 LLM 记忆" in self.stage.get("std_ref", "")


class TestReferencesIntegrity:
    """SKILL.md「参考文件（v2 新体系）」指向的注册表实有且自洽。"""

    def test_referenced_files_exist(self):
        for rel in (
            "references/stages/planning_eia.json",
            "references/standards_index.json",
            "references/consistency_contracts.json",
            "references/data_expectations.json",
            "references/depth_targets/planning_eia.json",
            "references/formulas.json",
            "references/sample_entities/_index.json",
        ):
            assert (SKILL / rel).is_file(), rel

    def test_contracts_registry_shape(self):
        doc = json.loads(CONTRACTS.read_text(encoding="utf-8"))
        cs = doc.get("contracts", [])
        ids = {c.get("id") for c in cs}
        # 设计基线族 XS1–XS12 + EO1–EO3 全在册（注册表可扩容——月儿湾走查回写新增规则族，
        # 故不锁死总数，只锁基线覆盖与结构自洽）
        assert {f"XS{i}" for i in range(1, 13)} | {f"EO{i}" for i in range(1, 4)} <= ids, sorted(ids)
        assert len(ids) == len(cs), "合约 id 重复"
        types = {c["type"] for c in cs}
        assert types <= {"cross_section", "code_constraint", "echo_obligation"}
        for c in cs:
            assert c.get("stages"), c["id"]  # 条件激活：每条带 applicable stages（可为子集——
            # 要素/场景专属合约合法收窄，如沉陷族仅 underground；条件激活按语义标题命中）
            assert set(c["stages"]) & {"planning_eia", "project_eia_underground"}, c["id"]
        assert doc.get("caliber_labels"), "口径标签注册缺失（D4）"
        assert "echo_obligation" in doc.get("contract_types", {})

    def test_depth_targets_cover_all_chapters(self):
        doc = json.loads(DEPTH.read_text(encoding="utf-8"))
        floors = doc.get("chapters", {})
        stage = _stage()
        assert set(floors) == set(stage["chapters"])
        assert all(isinstance(v.get("floor_chars"), int) and v["floor_chars"] > 0 for v in floors.values())

    def test_sample_entities_registry(self):
        idx = json.loads((SKILL / "references" / "sample_entities" / "_index.json").read_text(encoding="utf-8"))
        slugs = {s["slug"] for s in idx.get("samples", [])}
        assert len(slugs) >= 20, len(slugs)
        assert {"hengcheng", "yueerwan"} <= slugs  # SC#3 反测双方注册表在册
        for s in idx["samples"]:
            assert (SKILL / "references" / s["file"]).is_file(), s["file"]

    def test_data_expectations_13_chapters(self):
        doc = json.loads((SKILL / "references" / "data_expectations.json").read_text(encoding="utf-8"))
        assert len(doc.get("per_chapter", {})) == 13

    def test_v1_references_marked_deprecated_not_pipeline(self):
        """v1 旧参考暂留待二期替代、不作管线输入（D8：report_structure.md 废止=从 v2 参考面除名）。"""
        content = _read_skill()
        assert "不再作为管线输入" in content
        assert "report_structure.md" not in content, "D8：横城污染模板不得再入 v2 参考面"
