"""bid-proposal-writing 技能脚本单测(设计文档 D4 测试计划, 任务序列 T1 测试先行)。

规格: docs/superpowers/specs/2026-08-16-bid-proposal-writing-skill-design.md

本文件覆盖两类内容:

1. fixture 自身合法性(必须真跑且绿): backend/tests/fixtures/bid_proposal/ 下的
   最小招标文件样例(docx/pdf)与样例状态 JSON, 按设计文档三 schema 字段表逐字段
   校验(字段齐全/枚举合法/Σ一致/外键一致/锚点一致)。gen_fixtures.py 可再生成。
2. 五个管线脚本的占位导入测试(ingest/extract/merge_addenda/build_output/
   score_simulate, T3-T7 落地): 模块尚不存在时 skip; 存在时必须暴露可调用的
   main()(argparse CLI 纪律, 参照 skills/public/markdown-to-docx/scripts/convert.py)。

运行: cd backend && PYTHONPATH=. uv run pytest tests/test_bid_proposal_scripts.py -v
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

# --- 路径 -------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "skills" / "public" / "bid-proposal-writing" / "scripts"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "bid_proposal"

# 五个技能脚本落地后按顶级模块导入(沙箱脚本=纯 stdlib 平铺模块, 非包)。
# 目录尚不存在时插入 sys.path 无害, importorskip 会正确 skip。
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# --- 设计文档 schema 枚举 ----------------------------------------------------
CLAUSE_CLASSES = {"mandatory", "scoring", "normal"}
CLAUSE_CATEGORIES = {"technical", "commercial", "qualification", "format", "service"}
RESPONSE_STATUSES = {"unassigned", "draft", "pending_confirm", "compliant", "deviation"}
VOLUMES = {"commercial", "technical"}
SLOT_TYPES = {"text", "table", "image", "format_check", "group"}
SCORE_TYPES = {"objective", "subjective", "price"}

# 设计文档字段表(不缺不漏不加: 精确集合比较, 多余字段同样报错)
# voided = 阶段3 落账标记(T5: 作废→标 voided; schema 可选字段, 默认 false)
CLAUSE_FIELDS = {"clause_id", "source_file", "class", "category", "source_ref", "requirement", "response_status", "response_skeleton", "from_addendum", "superseded_by", "voided"}
SOURCE_REF_FIELDS = {"page", "section", "para", "quote"}
RESPONSE_SKELETON_FIELDS = {"points", "evidence_ref", "suggestion"}
NODE_FIELDS = {"node_id", "volume", "path", "slot_type", "required_format", "linked_clause_ids"}
REQUIRED_FORMAT_FIELDS = {"desc", "table_spec"}
RUBRIC_ITEM_FIELDS = {"rubric_id", "item", "max_score", "scoring_method", "score_type", "linked_clause_ids", "source_ref"}

CLAUSE_ID_RE = re.compile(r"^[A-Z]{2}-C-\d{3}$")  # 复合 ID: <文件代号>-C-<全局序号>
NODE_ID_RE = re.compile(r"^S-\d{3}$")
RUBRIC_ID_RE = re.compile(r"^R-\d{3}$")
# chunk/table id: >=3 位序号(残留审查可选①: id 由 :03d 格式化, 超 999 自然扩位为
# CH-1000, 不设人为上限; 3 位下界保留 "CH-1"/"CH-12" 不合法的约束)
CHUNK_ID_RE = re.compile(r"^CH-\d{3,}$")
TABLE_ID_RE = re.compile(r"^T-\d{3,}$")

SCRIPT_MODULE_NAMES = ["ingest", "extract", "merge_addenda", "build_output", "score_simulate"]


def load_json(name: str):
    """加载 fixture JSON; 文件缺失直接让测试失败(fail-fast, 不静默 skip)。"""
    path = FIXTURE_DIR / name
    assert path.is_file(), f"fixture 缺失: {path}(可用 gen_fixtures.py 再生成)"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_source_ref(ref: dict, owner: str) -> None:
    assert set(ref.keys()) == SOURCE_REF_FIELDS, f"{owner} source_ref 字段集不符: {sorted(ref.keys())}"
    assert isinstance(ref["section"], str) and ref["section"].strip(), f"{owner} source_ref.section 必填"
    assert isinstance(ref["para"], int) and ref["para"] >= 1, f"{owner} source_ref.para 应为 >=1 的段落序"
    # page 按来源可空: docx 无分页概念(None), PDF/OCR 才有页码
    assert ref["page"] is None or (isinstance(ref["page"], int) and ref["page"] >= 1), f"{owner} source_ref.page 应为 None 或 >=1"
    assert isinstance(ref["quote"], str) and 0 < len(ref["quote"]) <= 50, f"{owner} source_ref.quote 应为非空且 ≤50 字"


# ===========================================================================
# 占位导入测试: 五脚本(T3-T7 落地前 skip, 落地后约束 argparse CLI 契约)
# ===========================================================================


class TestScriptPlaceholders:
    """五个确定性管线脚本的导入级占位测试。

    T3-T7 各自落地对应模块后自动转为真测试; 届时的行为用例(校验器/幂等/渲染/
    重灌契约)由各任务在本文件追加, 此处只锁定导入与 CLI 入口契约。
    """

    @pytest.mark.parametrize("module_name", SCRIPT_MODULE_NAMES)
    def test_module_importable_with_cli_main(self, module_name: str):
        mod = pytest.importorskip(module_name, reason=f"{module_name}.py 尚未落地(任务 T3-T7)")
        assert callable(getattr(mod, "main", None)), f"{module_name}.py 必须暴露可调用 main()(argparse CLI 纪律)"


# ===========================================================================
# fixture 自身合法性: 最小招标文件样例
# ===========================================================================


class TestFixtureMinimalTenderDocx:
    """minimal_tender.docx: 多级标题树/★强制句/实质性响应句/评分表/参数表。"""

    @pytest.fixture(scope="class")
    def doc(self):
        docx = pytest.importorskip("docx", reason="backend venv 缺 python-docx")
        return docx.Document(str(FIXTURE_DIR / "minimal_tender.docx"))

    def test_file_exists(self):
        assert (FIXTURE_DIR / "minimal_tender.docx").is_file()

    def test_multilevel_heading_tree(self, doc):
        levels = set()
        for p in doc.paragraphs:
            m = re.match(r"Heading (\d)$", p.style.name)
            if m and p.text.strip():
                levels.add(int(m.group(1)))
        assert {1, 2, 3} <= levels, f"章节树需覆盖三级标题, 实际: {sorted(levels)}"

    def test_star_mandatory_clause_present(self, doc):
        assert any("★" in p.text and "强制" in p.text for p in doc.paragraphs), "需含至少 1 个★强制条款句"

    def test_substantive_response_clause_present(self, doc):
        assert any("实质性响应" in p.text for p in doc.paragraphs), "需含 1 个'实质性响应'字样条款"

    def test_scoring_table_with_score_column(self, doc):
        scoring = [t for t in doc.tables if t.rows and any("分值" in c.text for c in t.rows[0].cells)]
        assert scoring, "需含 1 张评分细则表(表头含分值列)"
        assert len(scoring[0].rows) >= 3, "评分细则表需 2-3 行数据(含表头 ≥3 行)"

    def test_parameter_table_present(self, doc):
        param = [t for t in doc.tables if t.rows and any("要求值" in c.text for c in t.rows[0].cells)]
        assert param, "需含 1 张参数表(表头含要求值列)"


class TestFixtureMinimalTenderPdf:
    """minimal_tender.pdf: 单页, 2-3 个标题 + 若干正文行, pdfplumber 可解析。"""

    @pytest.fixture(scope="class")
    def pdf_text(self):
        pdfplumber = pytest.importorskip("pdfplumber", reason="backend venv 缺 pdfplumber")
        with pdfplumber.open(str(FIXTURE_DIR / "minimal_tender.pdf")) as pdf:
            assert len(pdf.pages) == 1
            return pdf.pages[0].extract_text() or ""

    def test_file_exists(self):
        assert (FIXTURE_DIR / "minimal_tender.pdf").is_file()

    def test_headings_extractable(self, pdf_text):
        for heading in ("1. Tender Notice", "2. Technical Specifications", "3. Evaluation Method"):
            assert heading in pdf_text

    def test_body_lines_extractable(self, pdf_text):
        lines = [ln for ln in pdf_text.splitlines() if ln.strip()]
        assert len(lines) >= 5, f"需若干正文行, 实际 {len(lines)}"


# ===========================================================================
# fixture 自身合法性: clauses.json(条款 schema 字段表)
# ===========================================================================


class TestFixtureClauses:
    @pytest.fixture(scope="class")
    def clauses(self):
        return load_json("clauses.json")

    def test_shape_and_required_fields(self, clauses):
        assert isinstance(clauses, list) and 3 <= len(clauses) <= 4
        for c in clauses:
            assert set(c.keys()) == CLAUSE_FIELDS, f"{c.get('clause_id')} 字段集不符: {sorted(c.keys())}"
            assert CLAUSE_ID_RE.match(c["clause_id"]), f"clause_id 应为复合 ID(<文件代号>-C-<序号>): {c['clause_id']}"
            assert isinstance(c["source_file"], str) and c["source_file"].strip()
            assert isinstance(c["requirement"], str) and c["requirement"].strip()

    def test_enums_legal(self, clauses):
        for c in clauses:
            assert c["class"] in CLAUSE_CLASSES, f"{c['clause_id']} class 非法: {c['class']}"
            assert c["category"] in CLAUSE_CATEGORIES, f"{c['clause_id']} category 非法: {c['category']}"
            assert c["response_status"] in RESPONSE_STATUSES, f"{c['clause_id']} response_status 非法: {c['response_status']}"
            assert isinstance(c["from_addendum"], bool)
            assert isinstance(c["voided"], bool), f"{c['clause_id']} voided 应为 bool(T5 落账标记)"

    def test_source_ref_shape(self, clauses):
        for c in clauses:
            _assert_source_ref(c["source_ref"], c["clause_id"])

    def test_response_skeleton_shape(self, clauses):
        for c in clauses:
            sk = c["response_skeleton"]
            assert set(sk.keys()) == RESPONSE_SKELETON_FIELDS, f"{c['clause_id']} response_skeleton 字段集不符"
            assert isinstance(sk["points"], list) and all(isinstance(x, str) for x in sk["points"])
            assert sk["evidence_ref"] is None or isinstance(sk["evidence_ref"], str)
            assert sk["suggestion"] is None or isinstance(sk["suggestion"], str)

    def test_unique_clause_ids(self, clauses):
        ids = [c["clause_id"] for c in clauses]
        assert len(ids) == len(set(ids)), "clause_id 不得重复"

    def test_class_coverage(self, clauses):
        classes = {c["class"] for c in clauses}
        assert classes == CLAUSE_CLASSES, f"mandatory/scoring/normal 各至少 1 条, 实际: {classes}"

    def test_addendum_and_supersede_chain(self, clauses):
        """1 条带 from_addendum=true + 1 条带 superseded_by 链(指向补遗新条款)。"""
        ids = {c["clause_id"] for c in clauses}
        by_id = {c["clause_id"]: c for c in clauses}
        assert any(c["from_addendum"] for c in clauses), "需至少 1 条 from_addendum=true"
        superseded = [c for c in clauses if c["superseded_by"] is not None]
        assert superseded, "需至少 1 条 superseded_by 链"
        for c in superseded:
            target = c["superseded_by"]
            assert target in ids and target != c["clause_id"], f"{c['clause_id']} superseded_by 悬挂: {target}"
            assert by_id[target]["from_addendum"] is True, f"替代条款 {target} 应来自补遗(from_addendum=true)"

    def test_docx_clause_page_is_null(self, clauses):
        """docx 无分页概念 → page 必须为 None(设计: page 按来源可空)。"""
        for c in clauses:
            if c["source_file"].endswith(".docx"):
                assert c["source_ref"]["page"] is None, f"{c['clause_id']} 来自 docx, page 应为 None"


# ===========================================================================
# fixture 自身合法性: structure.json(结构镜像节点 schema 字段表)
# ===========================================================================


class TestFixtureStructure:
    @pytest.fixture(scope="class")
    def nodes(self):
        return load_json("structure.json")

    @pytest.fixture(scope="class")
    def clause_ids(self):
        return {c["clause_id"] for c in load_json("clauses.json")}

    def test_shape_and_required_fields(self, nodes):
        assert isinstance(nodes, list) and nodes
        for n in nodes:
            assert set(n.keys()) == NODE_FIELDS, f"{n.get('node_id')} 字段集不符: {sorted(n.keys())}"
            assert NODE_ID_RE.match(n["node_id"]), f"node_id 非法: {n['node_id']}"
            assert isinstance(n["path"], str) and n["path"].strip(), f"{n['node_id']} path 应为非空标题链"
            rf = n["required_format"]
            assert set(rf.keys()) == REQUIRED_FORMAT_FIELDS, f"{n['node_id']} required_format 字段集不符"
            assert isinstance(rf["desc"], str) and rf["desc"].strip()
            assert isinstance(n["linked_clause_ids"], list)

    def test_unique_node_ids(self, nodes):
        ids = [n["node_id"] for n in nodes]
        assert len(ids) == len(set(ids)), "node_id 不得重复"

    def test_dual_volume_all_slot_types(self, nodes):
        assert {n["volume"] for n in nodes} == VOLUMES, "需覆盖 commercial|technical 双卷"
        assert {n["slot_type"] for n in nodes} == SLOT_TYPES, f"需覆盖全部 5 种槽位类型, 实际: {sorted({n['slot_type'] for n in nodes})}"

    def test_enums_legal(self, nodes):
        for n in nodes:
            assert n["volume"] in VOLUMES
            assert n["slot_type"] in SLOT_TYPES

    def test_table_slots_carry_table_spec(self, nodes):
        for n in nodes:
            if n["slot_type"] == "table":
                spec = n["required_format"]["table_spec"]
                assert isinstance(spec, dict) and spec.get("columns"), f"{n['node_id']} table 槽必须带列头规格"
                assert isinstance(spec.get("rows"), int) and spec["rows"] >= 1, f"{n['node_id']} table_spec.rows 应为 >=1"
            else:
                assert n["required_format"]["table_spec"] is None, f"{n['node_id']} 非 table 槽 table_spec 应为 null"

    def test_no_derived_fill_status_persisted(self, nodes):
        """D7 状态一致性: fill_status 为派生字段, 现算不落盘。"""
        for n in nodes:
            assert "fill_status" not in n, f"{n['node_id']} 不得持久化派生字段 fill_status(D7)"

    def test_linked_clause_fk_valid(self, nodes, clause_ids):
        """D7 外键防线: linked_clause_ids 必须存在且未被 supersede(合法 fixture 不含悬挂引用)。"""
        superseded = {c["clause_id"] for c in load_json("clauses.json") if c["superseded_by"]}
        for n in nodes:
            for cid in n["linked_clause_ids"]:
                assert cid in clause_ids, f"{n['node_id']} 悬挂外键: {cid}"
                assert cid not in superseded, f"{n['node_id']} 引用了已 supersede 条款: {cid}"


# ===========================================================================
# fixture 自身合法性: rubric.json / rubric_bad_sum.json(评分标尺 schema)
# ===========================================================================


class TestFixtureRubric:
    @pytest.fixture(scope="class")
    def data(self):
        return load_json("rubric.json")

    @pytest.fixture(scope="class")
    def clause_ids(self):
        return {c["clause_id"] for c in load_json("clauses.json")}

    def test_shape_and_required_fields(self, data):
        assert set(data.keys()) == {"total_score", "items"}
        assert isinstance(data["total_score"], int) and data["total_score"] > 0
        assert isinstance(data["items"], list) and data["items"]
        for item in data["items"]:
            assert set(item.keys()) == RUBRIC_ITEM_FIELDS, f"{item.get('rubric_id')} 字段集不符: {sorted(item.keys())}"
            assert RUBRIC_ID_RE.match(item["rubric_id"]), f"rubric_id 非法: {item['rubric_id']}"
            assert isinstance(item["item"], str) and item["item"].strip()
            assert isinstance(item["max_score"], int) and item["max_score"] > 0
            assert isinstance(item["scoring_method"], str) and item["scoring_method"].strip()
            assert isinstance(item["linked_clause_ids"], list)

    def test_unique_rubric_ids(self, data):
        ids = [i["rubric_id"] for i in data["items"]]
        assert len(ids) == len(set(ids))

    def test_score_type_coverage(self, data):
        types = {i["score_type"] for i in data["items"]}
        assert types == SCORE_TYPES, f"objective/subjective/price 各至少 1 项, 实际: {types}"

    def test_sum_matches_total(self, data):
        """Σmax_score 必须等于评分办法声称总分(设计: 双检之一, 此处为 fixture 契约)。"""
        total = sum(i["max_score"] for i in data["items"])
        assert total == data["total_score"], f"Σmax_score={total} != total_score={data['total_score']}"

    def test_linked_clause_fk_valid(self, data, clause_ids):
        for item in data["items"]:
            for cid in item["linked_clause_ids"]:
                assert cid in clause_ids, f"{item['rubric_id']} 悬挂外键: {cid}"

    def test_source_ref_shape(self, data):
        for item in data["items"]:
            _assert_source_ref(item["source_ref"], item["rubric_id"])


class TestFixtureRubricBadSum:
    """负样本: 故意 Σ 不一致, 供 T4/T7 的 Σmax_score 校验测试消费。"""

    def test_sum_mismatches_total(self):
        data = load_json("rubric_bad_sum.json")
        total = sum(i["max_score"] for i in data["items"])
        assert total != data["total_score"], f"bad 用例必须 Σ 不一致(实际 Σ={total} == total_score={data['total_score']})"

    def test_shape_matches_good_rubric(self):
        """与 rubric.json 同构(仅分值不同), 保证校验器两侧行为可比。"""
        bad, good = load_json("rubric_bad_sum.json"), load_json("rubric.json")
        assert set(bad.keys()) == set(good.keys()) == {"total_score", "items"}
        assert [i["rubric_id"] for i in bad["items"]] == [i["rubric_id"] for i in good["items"]]
        assert bad["total_score"] == good["total_score"]


# ===========================================================================
# fixture 自身合法性: sections.json(ingest 产物样例)
# ===========================================================================


class TestFixtureSections:
    @pytest.fixture(scope="class")
    def data(self):
        return load_json("sections.json")

    def test_chunks_shape(self, data):
        assert set(data.keys()) == {"chunks", "tables"}
        assert isinstance(data["chunks"], list) and data["chunks"]
        for ch in data["chunks"]:
            assert set(ch.keys()) == {"chunk_id", "source_file", "anchor", "heading_path", "n_paras"}, f"chunk 字段集不符: {sorted(ch.keys())}"
            assert CHUNK_ID_RE.match(ch["chunk_id"]), f"chunk_id 非法: {ch['chunk_id']}"
            assert isinstance(ch["heading_path"], list) and ch["heading_path"]
            # 残留审查可选②: 格式章节骨架块 n_paras==0(T3 契约: 只出章节树),
            # 常规块 >=1——下界对齐实际 ingest 行为放宽为 0
            assert isinstance(ch["n_paras"], int) and ch["n_paras"] >= 0

    def test_tables_shape_with_row_counts(self, data):
        """表必须带稳定 table_id 与行数(D5: 表行数由 ingest 端比对, 防吞表静默漏检)。"""
        assert isinstance(data["tables"], list) and data["tables"]
        for t in data["tables"]:
            assert set(t.keys()) == {"table_id", "source_file", "anchor", "n_rows", "n_cols", "caption"}, f"table 字段集不符: {sorted(t.keys())}"
            assert TABLE_ID_RE.match(t["table_id"]), f"table_id 非法: {t['table_id']}"
            assert isinstance(t["n_rows"], int) and t["n_rows"] >= 1
            assert isinstance(t["n_cols"], int) and t["n_cols"] >= 1

    def test_unique_ids(self, data):
        chunk_ids = [c["chunk_id"] for c in data["chunks"]]
        table_ids = [t["table_id"] for t in data["tables"]]
        assert len(chunk_ids) == len(set(chunk_ids)), "chunk_id 不得重复"
        assert len(table_ids) == len(set(table_ids)), "table_id 不得重复"

    def test_anchor_format_by_source_type(self, data):
        """锚点格式按来源分流: docx=section+段序(无 page), PDF/OCR=page+section。"""
        for ch in data["chunks"] + data["tables"]:
            anchor, src = ch["anchor"], ch["source_file"]
            if src.endswith(".docx"):
                assert "page" not in anchor and anchor.get("section"), f"{ch.get('chunk_id') or ch.get('table_id')} docx 锚点应为 section(+para)"
            else:
                assert isinstance(anchor.get("page"), int) and anchor["page"] >= 1 and anchor.get("section"), f"{ch.get('chunk_id') or ch.get('table_id')} PDF/OCR 锚点应为 page+section"

    def test_clause_and_rubric_anchors_covered(self, data):
        """条款/评分项的 source_ref(section 维度)必须能在 sections.json 中找到落点(extract.py 校验前提)。"""
        covered = {(c["source_file"], c["anchor"]["section"]) for c in data["chunks"]}
        for c in load_json("clauses.json"):
            assert (c["source_file"], c["source_ref"]["section"]) in covered, f"{c['clause_id']} 锚点不在 sections.json: {c['source_ref']}"
        for item in load_json("rubric.json")["items"]:
            assert ("minimal_tender.docx", item["source_ref"]["section"]) in covered, f"{item['rubric_id']} 锚点不在 sections.json"


# ===========================================================================
# fixture 自身合法性: returned_word.md(回传稿) + entities_whitelist.json
# ===========================================================================


class TestFixtureReturnedWord:
    """回传稿: 商务卷标题链镜像 structure.json 路径; 技术卷条目嵌 clause_id;
    故意留 1 个匹配失败项 + 1 个重复 clause_id 项(T7 D6 匹配器硬化测试消费)。"""

    @pytest.fixture(scope="class")
    def text(self):
        path = FIXTURE_DIR / "returned_word.md"
        assert path.is_file(), f"fixture 缺失: {path}"
        return path.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def nodes(self):
        return load_json("structure.json")

    def test_heading_chains_mirror_structure(self, text, nodes):
        headings = [ln.lstrip("#").strip() for ln in text.splitlines() if ln.startswith("#")]
        joined = "\n".join(headings)
        for n in nodes:
            for segment in n["path"].split("/"):
                assert segment in joined, f"structure 路径段未在回传稿标题链出现: {segment}(节点 {n['node_id']})"

    def test_technical_entries_embed_clause_ids(self, text):
        assert "响应[ZB-C-001]" in text, "技术卷条目标题需内嵌 clause_id(D2 锚点契约)"
        assert "响应[ZB-C-002]" in text

    def test_duplicate_clause_id_case(self, text):
        """D6: clause_id 在回传稿重复出现 → 异常区。fixture 须提供该用例。"""
        assert len(re.findall(r"响应\[ZB-C-001\]", text)) == 2, "ZB-C-001 应恰好出现 2 次(重复用例)"

    def test_match_failure_case(self, text, nodes):
        """D6: 标题链不在 structure.json 中的项 → needs_human_verify。fixture 须提供该用例。"""
        failure_segment = "售后服务承诺"
        assert failure_segment in text, "回传稿需含 1 个镜像外标题(匹配失败用例)"
        segments = {seg for n in nodes for seg in n["path"].split("/")}
        assert failure_segment not in segments, "匹配失败用例的标题不得与镜像路径段重名"


class TestFixtureEntitiesWhitelist:
    def test_shape(self):
        data = load_json("entities_whitelist.json")
        assert set(data.keys()) == {"locked_at", "source", "entities"}
        assert isinstance(data["locked_at"], str) and data["locked_at"]
        assert isinstance(data["entities"], list) and data["entities"]
        for e in data["entities"]:
            assert set(e.keys()) == {"type", "value"}, f"白名单实体字段集不符: {sorted(e.keys())}"
            assert isinstance(e["type"], str) and e["type"].strip()
            assert isinstance(e["value"], str) and e["value"].strip()

    def test_covers_project_and_company(self):
        """设计: 白名单来自封面/投标人须知抽取的公司名/项目名(+参数版本等)。"""
        types = {e["type"] for e in load_json("entities_whitelist.json")["entities"]}
        assert {"project", "company"} <= types


# ===========================================================================
# fixture 再生成入口契约
# ===========================================================================


class TestGenFixtures:
    def test_generator_exists(self):
        assert (FIXTURE_DIR / "gen_fixtures.py").is_file(), "fixture 生成器应随 fixture 一起入库"


# ===========================================================================
# T2: references/ 契约文件(三 JSON Schema + classification/extraction/scoring 文档)
# ===========================================================================
# 字段名/枚举与设计文档「详细设计」字段表逐字对齐, 复用上文 fixture 常量做精确集合比较;
# structure schema 额外声明派生字段 fill_status(值域供内存态/渲染态校验, 候选/落盘不含, D7)。

REFERENCES_DIR = REPO_ROOT / "skills" / "public" / "bid-proposal-writing" / "references"
SCHEMA_FILES = ("clauses.schema.json", "structure.schema.json", "rubric.schema.json")
DOC_FILES = ("classification.md", "extraction_prompt.md", "scoring_prompt.md")
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
STRUCTURE_SCHEMA_FIELDS = NODE_FIELDS | {"fill_status"}

# 复合 clause_id 形态: <文件代号>-C-<全局序号>(ZB=招标文件/JS=技术规范书/PB=评分办法…)。
# schema 契约比 fixture 正则宽(代号 2-4 字母/序号 1-6 位), 覆盖真实招标文件多卷量级。
CLAUSE_ID_SCHEMA_VALID = ["ZB-C-017", "JS-C-001", "PB-C-3"]
CLAUSE_ID_SCHEMA_INVALID = ["C-017", "ZB-017", "ZB-C-abc", "zb-c-017", "ZB-C-017-X"]


def _ref_json(name: str) -> dict:
    path = REFERENCES_DIR / name
    assert path.is_file(), f"references 契约文件缺失: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _ref_doc(name: str) -> str:
    path = REFERENCES_DIR / name
    assert path.is_file(), f"references 契约文件缺失: {path}"
    return path.read_text(encoding="utf-8")


def _ref_validator(name: str) -> Draft202012Validator:
    schema = _ref_json(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _sample_clause(**overrides):
    clause = {
        "clause_id": "ZB-C-017",
        "source_file": "招标文件.docx",
        "class": "mandatory",
        "category": "technical",
        "source_ref": {"page": None, "section": "3.2.1", "para": 14, "quote": "投标人应逐项响应技术参数"},
        "requirement": "逐项响应招标文件技术参数表",
        "response_status": "unassigned",
        "response_skeleton": {"points": [], "evidence_ref": None, "suggestion": None},
        "from_addendum": False,
        "superseded_by": None,
    }
    clause.update(overrides)
    return clause


def _sample_node(**overrides):
    node = {
        "node_id": "S-012",
        "volume": "commercial",
        "path": "投标文件格式/三、法定代表人身份证明",
        "slot_type": "image",
        "required_format": {"desc": "加盖公章的身份证正反面扫描件", "table_spec": None},
        "linked_clause_ids": ["ZB-C-034"],
    }
    node.update(overrides)
    return node


def _sample_rubric(**overrides):
    item = {
        "rubric_id": "R-005",
        "item": "技术方案先进性",
        "max_score": 10,
        "scoring_method": "优=8-10 良=5-7 一般=1-4 无=0",
        "score_type": "subjective",
        "linked_clause_ids": ["ZB-C-041"],
        "source_ref": {"page": 31, "section": "评分办法", "quote": "技术方案先进性优得8-10分"},
    }
    item.update(overrides)
    return item


class TestReferencesExist:
    def test_all_reference_files_exist(self):
        for name in (*SCHEMA_FILES, *DOC_FILES):
            assert (REFERENCES_DIR / name).is_file(), f"references 契约文件缺失: {name}"

    @pytest.mark.parametrize("name", SCHEMA_FILES)
    def test_schemas_declare_draft_2020_12(self, name):
        assert _ref_json(name)["$schema"] == DRAFT_2020_12


class TestClausesSchema:
    def test_field_set(self):
        assert set(_ref_json("clauses.schema.json")["properties"]) == CLAUSE_FIELDS

    def test_enums(self):
        props = _ref_json("clauses.schema.json")["properties"]
        assert set(props["class"]["enum"]) == CLAUSE_CLASSES
        assert set(props["category"]["enum"]) == CLAUSE_CATEGORIES
        assert set(props["response_status"]["enum"]) == RESPONSE_STATUSES

    def test_source_ref_shape(self):
        source_ref = _ref_json("clauses.schema.json")["properties"]["source_ref"]
        assert set(source_ref["properties"]) == SOURCE_REF_FIELDS
        # page 按来源可空: docx 无分页概念→null; PDF/OCR 扫描件才有 page。
        assert set(source_ref["properties"]["page"]["type"]) == {"integer", "null"}
        # quote(原文片段 ≤50 字)是 source_ref 内唯一必填键。
        assert source_ref["required"] == ["quote"]
        assert source_ref["properties"]["quote"]["maxLength"] == 50

    def test_required_floor(self):
        schema = _ref_json("clauses.schema.json")
        # 锚点(source_ref)/clause_id/分类(class+category)必填。
        assert {"clause_id", "source_ref", "class", "category"} <= set(schema["required"])

    def test_closes_additional_properties(self):
        schema = _ref_json("clauses.schema.json")
        assert schema["additionalProperties"] is False
        assert schema["properties"]["source_ref"]["additionalProperties"] is False
        assert set(schema["properties"]["response_skeleton"]["properties"]) == RESPONSE_SKELETON_FIELDS

    @pytest.mark.parametrize("value", CLAUSE_ID_SCHEMA_VALID)
    def test_clause_id_pattern_accepts_composite_ids(self, value):
        assert _ref_validator("clauses.schema.json").is_valid(_sample_clause(clause_id=value))

    @pytest.mark.parametrize("value", CLAUSE_ID_SCHEMA_INVALID)
    def test_clause_id_pattern_rejects_malformed_ids(self, value):
        assert not _ref_validator("clauses.schema.json").is_valid(_sample_clause(clause_id=value))


class TestStructureSchema:
    def test_field_set_and_enums(self):
        props = _ref_json("structure.schema.json")["properties"]
        assert set(props) == STRUCTURE_SCHEMA_FIELDS
        assert set(props["volume"]["enum"]) == VOLUMES
        assert set(props["slot_type"]["enum"]) == SLOT_TYPES
        # fill_status 为 D7 派生字段: 值域必须覆盖, 但不落盘(候选/落盘不含)。
        assert set(props["fill_status"]["enum"]) == {"unfilled", "filled", "needs_human_verify"}
        assert set(props["required_format"]["properties"]) == REQUIRED_FORMAT_FIELDS

    def test_required_and_strictness(self):
        schema = _ref_json("structure.schema.json")
        assert set(schema["required"]) == NODE_FIELDS  # 持久化字段全必填
        assert "fill_status" not in schema["required"]  # 派生字段不入 required(D7)
        assert schema["additionalProperties"] is False
        assert schema["properties"]["required_format"]["additionalProperties"] is False


class TestRubricSchema:
    def test_field_set_and_enums(self):
        props = _ref_json("rubric.schema.json")["properties"]
        assert set(props) == RUBRIC_ITEM_FIELDS
        assert set(props["score_type"]["enum"]) == SCORE_TYPES
        assert set(props["source_ref"]["properties"]) == SOURCE_REF_FIELDS
        assert props["source_ref"]["properties"]["quote"]["maxLength"] == 50

    def test_required_floor(self):
        schema = _ref_json("rubric.schema.json")
        # rubric 项全部 7 字段必填(评分办法原文为尺→scoring_method 必填; Σ 校验→max_score 必填)。
        assert set(schema["required"]) == RUBRIC_ITEM_FIELDS
        assert schema["additionalProperties"] is False


class TestSchemaFunctionalClauses:
    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            # PDF 来源: page+section 锚定, para 可为 null。
            {"source_file": "招标文件.pdf", "source_ref": {"page": 23, "section": "3.2.1", "para": None, "quote": "原文片段"}},
            # 补遗合并后的状态字段。
            {"from_addendum": True, "superseded_by": "ZB-C-018", "response_status": "deviation"},
            # 补遗作废落账标记(T5): voided 可选 bool。
            {"voided": True},
            {"class": "scoring", "category": "commercial", "response_status": "draft"},
            {"source_ref": {"page": None, "section": "3.2.1", "para": 14, "quote": "字" * 50}},
        ],
        ids=["design-example-docx", "pdf-page-anchor", "addendum-superseded", "addendum-voided", "scoring-class", "quote-max-50"],
    )
    def test_valid_samples_pass(self, overrides):
        assert _ref_validator("clauses.schema.json").is_valid(_sample_clause(**overrides))

    def test_minimal_required_only_passes(self):
        full = _sample_clause()
        minimal = {key: full[key] for key in ("clause_id", "source_file", "class", "category", "source_ref", "requirement")}
        assert _ref_validator("clauses.schema.json").is_valid(minimal)

    @pytest.mark.parametrize(
        "overrides,remove",
        [
            ({"class": "critical"}, None),
            ({"category": "legal"}, None),
            ({"response_status": "approved"}, None),
            ({"from_addendum": "yes"}, None),
            ({"voided": "yes"}, None),
            ({"superseded_by": "017"}, None),
            ({"requirement": ""}, None),
            ({"source_ref": {"page": "23", "section": "3.2.1", "para": 14, "quote": "原文"}}, None),
            ({"source_ref": {"page": 23, "section": "3.2.1", "para": 14}}, None),
            ({"source_ref": {"page": None, "section": "3.2.1", "para": 14, "quote": "字" * 51}}, None),
            ({"unknown_extra_field": True}, None),
            ({}, "clause_id"),
            ({}, "source_ref"),
            ({}, "requirement"),
        ],
        ids=[
            "bad-class",
            "bad-category",
            "bad-response-status",
            "bad-from-addendum-type",
            "bad-voided-type",
            "bad-superseded-by",
            "empty-requirement",
            "page-as-string",
            "source-ref-missing-quote",
            "quote-over-50",
            "unknown-extra-field",
            "missing-clause-id",
            "missing-source-ref",
            "missing-requirement",
        ],
    )
    def test_invalid_samples_rejected(self, overrides, remove):
        clause = _sample_clause(**overrides)
        if remove:
            clause.pop(remove)
        assert not _ref_validator("clauses.schema.json").is_valid(clause)


class TestSchemaFunctionalStructure:
    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            # fill_status 是声明过的派生字段: 内存态/渲染态合法取值可通过校验。
            {"fill_status": "unfilled"},
            {"fill_status": "needs_human_verify"},
            {"slot_type": "table", "required_format": {"desc": None, "table_spec": {"columns": ["名称", "数量"], "rows": 2}}},
            {"volume": "technical", "slot_type": "group", "required_format": {"desc": None, "table_spec": None}, "linked_clause_ids": []},
            {"node_id": "S-0", "slot_type": "format_check", "required_format": {"desc": "每页加盖页码", "table_spec": None}},
        ],
        ids=["design-example-image", "fill-unfilled", "fill-needs-human", "table-slot", "technical-group", "format-check"],
    )
    def test_valid_samples_pass(self, overrides):
        assert _ref_validator("structure.schema.json").is_valid(_sample_node(**overrides))

    @pytest.mark.parametrize(
        "overrides,remove",
        [
            ({"slot_type": "checkbox"}, None),
            ({"volume": "biz"}, None),
            ({"fill_status": "partial"}, None),
            ({"node_id": "12"}, None),
            ({"node_id": "S-abc"}, None),
            ({"path": ""}, None),
            ({"linked_clause_ids": ["034"]}, None),
            ({"required_format": {"desc": "x", "width": 3}}, None),
            ({"unknown_extra_field": True}, None),
            ({}, "node_id"),
            ({}, "volume"),
            ({}, "path"),
            ({}, "slot_type"),
            ({}, "required_format"),
        ],
        ids=[
            "bad-slot-type",
            "bad-volume",
            "bad-fill-status",
            "bad-node-id-no-prefix",
            "bad-node-id-non-numeric",
            "empty-path",
            "bad-linked-clause-id",
            "required-format-unknown-key",
            "unknown-extra-field",
            "missing-node-id",
            "missing-volume",
            "missing-path",
            "missing-slot-type",
            "missing-required-format",
        ],
    )
    def test_invalid_samples_rejected(self, overrides, remove):
        node = _sample_node(**overrides)
        if remove:
            node.pop(remove)
        assert not _ref_validator("structure.schema.json").is_valid(node)


class TestSchemaFunctionalRubric:
    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {"score_type": "objective"},
            {"score_type": "price"},
            {"max_score": 2.5},
            {"source_ref": {"page": None, "section": "评分办法", "quote": "原文片段"}},
            {"linked_clause_ids": []},
        ],
        ids=["design-example", "objective", "price", "fractional-max-score", "docx-null-page", "empty-links"],
    )
    def test_valid_samples_pass(self, overrides):
        assert _ref_validator("rubric.schema.json").is_valid(_sample_rubric(**overrides))

    @pytest.mark.parametrize(
        "overrides,remove",
        [
            ({"score_type": "weighted"}, None),
            ({"max_score": "10"}, None),
            ({"rubric_id": "rubric-5"}, None),
            ({"scoring_method": ""}, None),
            ({"item": ""}, None),
            ({"linked_clause_ids": ["R-005"]}, None),
            ({"source_ref": {"page": 31, "section": "评分办法"}}, None),
            ({"unknown_extra_field": True}, None),
            ({}, "rubric_id"),
            ({}, "scoring_method"),
            ({}, "source_ref"),
        ],
        ids=[
            "bad-score-type",
            "max-score-as-string",
            "bad-rubric-id",
            "empty-scoring-method",
            "empty-item",
            "bad-linked-clause-id",
            "source-ref-missing-quote",
            "unknown-extra-field",
            "missing-rubric-id",
            "missing-scoring-method",
            "missing-source-ref",
        ],
    )
    def test_invalid_samples_rejected(self, overrides, remove):
        item = _sample_rubric(**overrides)
        if remove:
            item.pop(remove)
        assert not _ref_validator("rubric.schema.json").is_valid(item)


# --- 契约文档内容 ------------------------------------------------------------

CLASSIFICATION_REQUIRED_TOKENS = (
    "★",
    "实质性响应",
    "废标",
    "评分细则表",
    "mandatory",
    "scoring",
    "normal",
    "mandatory > scoring > normal",
    "边界案例",
    "category",
    "[待确认]",
)

EXTRACTION_REQUIRED_TOKENS = (
    "①",
    "②",
    "③",
    "每次只处理一个 chunk",
    "即刻落盘",
    "chunk_id",
    "table_id",
    "0 条",
    "判空",
    "docx=section+段落序",
    "PDF/OCR=page+section",
    "绝不编造",
    "[待确认]",
    # 交叉一致性: 三个子模板的候选 JSON 骨架必须逐字使用设计文档字段名。
    '"clause_id"',
    '"source_file"',
    '"class"',
    '"category"',
    '"source_ref"',
    '"requirement"',
    '"response_status"',
    '"response_skeleton"',
    '"from_addendum"',
    '"superseded_by"',
    '"node_id"',
    '"volume"',
    '"path"',
    '"slot_type"',
    '"required_format"',
    '"linked_clause_ids"',
    '"rubric_id"',
    '"item"',
    '"max_score"',
    '"scoring_method"',
    '"score_type"',
)

SCORING_REQUIRED_TOKENS = (
    "评分办法原文为尺",
    "grep",
    "逐项独立评审",
    "防锚定",
    "模拟参考值",
    "无法模拟",
    "rubric_id",
    "失分",
    "改进建议",
    "objective",
    "subjective",
    "price",
    # 评审输出记录字段(供 score_simulate.py 汇总消费)。
    '"score"',
    '"max_score"',
    '"rationale"',
    '"evidence_quote"',
    '"missing_points"',
    '"improvement"',
)


class TestContractDocs:
    @pytest.mark.parametrize(
        "name,tokens",
        [
            pytest.param("classification.md", CLASSIFICATION_REQUIRED_TOKENS, id="classification.md"),
            pytest.param("extraction_prompt.md", EXTRACTION_REQUIRED_TOKENS, id="extraction_prompt.md"),
            pytest.param("scoring_prompt.md", SCORING_REQUIRED_TOKENS, id="scoring_prompt.md"),
        ],
    )
    def test_doc_contains_required_tokens(self, name, tokens):
        content = _ref_doc(name)
        missing = [token for token in tokens if token not in content]
        assert not missing, f"{name} missing required tokens: {missing}"

    def test_extraction_prompt_fill_status_is_derived_only(self):
        """D7: fill_status 是派生字段——extraction_prompt.md 只允许 prose 说明, 候选 JSON 骨架不得包含。"""
        content = _ref_doc("extraction_prompt.md")
        assert '"fill_status"' not in content, "候选骨架不得包含派生字段 fill_status(D7: 渲染/重灌时现算, 不落盘)"
        assert "fill_status" in content, "必须以 prose 说明 fill_status 为派生字段、候选不含"


# ===========================================================================
# T3: ingest.py — 阶段1 纯结构化解析(sections.json 产出, 无 LLM)
# ===========================================================================
# CLI: ingest.py --input <文件...> --code <代号> --out <dir> [--addendum] → <out>/sections.json
# 契约(与 T1 fixture sections.json 字段集逐字一致, 不缺不漏不加):
#   chunk  = {chunk_id, source_file, anchor, heading_path, n_paras}
#   table  = {table_id, source_file, anchor, n_rows, n_cols, caption}
#   锚点分流: docx=section+段序(无 page 键); PDF/OCR=page+section(无 para 键)
#   表行数记录 + 解析前后行数比对(D5); 格式章节只出章节树骨架; 原子写盘(D7)
# 退出码: 0=干净完成 1=用法/文件错误 2=无文本层(扫描件)需走 OCR 3=完成但有异常项

# 最小 1x1 PNG(base64), 供"扫描 docx(仅图片无文本层)"负样本使用
_TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _ingest_module():
    """硬导入 ingest(T3 已落地; 模块缺失时测试失败而非 skip——管线脚本必须存在)。"""
    import importlib

    return importlib.import_module("ingest")


def _run_ingest(tmp_path, files, code="ZB", addendum=False):
    """运行 ingest.main 并返回 (退出码, sections.json 路径)。"""
    ingest = _ingest_module()
    out_dir = tmp_path / "out"
    argv = ["--input", *[str(f) for f in files], "--code", code, "--out", str(out_dir)]
    if addendum:
        argv.append("--addendum")
    rc = ingest.main(argv)
    return rc, out_dir / "sections.json"


def _make_docx(path, blocks):
    """按块序列构造测试 docx: ("h", level, text) / ("p", text) / ("table", [[单元格...], ...])。"""
    docx = pytest.importorskip("docx", reason="backend venv 缺 python-docx")
    doc = docx.Document()
    for block in blocks:
        if block[0] == "h":
            doc.add_heading(block[2], level=block[1])
        elif block[0] == "p":
            doc.add_paragraph(block[1])
        elif block[0] == "table":
            rows = block[1]
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = "Table Grid"
            for r, cells in enumerate(rows):
                for c, value in enumerate(cells):
                    table.rows[r].cells[c].text = value
    doc.save(str(path))
    return path


def _make_raw_pdf(path, with_image: bool):
    """手写最小 PDF 字节(零外部依赖, 供扫描件/空文档负样本):

    with_image=True  → 仅含 1x1 图片 XObject、零文本行(扫描件形态, 触发 OCR 分流);
    with_image=False → 空内容流(无文本/表格/图片的空文档形态)。
    """
    if with_image:
        content = b"q 100 0 0 100 50 50 cm /Im0 Do Q\n"
        objects = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
            4: b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\x00\nendstream",
            5: b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        }
    else:
        objects = {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> /Contents 4 0 R >>",
            4: b"<< /Length 0 >>\nstream\nendstream",
        }
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_pos = len(out)
    total = max(objects) + 1
    out += f"xref\n0 {total}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, total):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    path = Path(path)
    path.write_bytes(bytes(out))
    return path


class TestIngestDocxFixture:
    """对 fixture minimal_tender.docx 跑真 ingest: 结构/锚点/行数/ID 发放全链路。"""

    @pytest.fixture(scope="class")
    def run(self, tmp_path_factory):
        rc, path = _run_ingest(tmp_path_factory.mktemp("ingest_docx"), [FIXTURE_DIR / "minimal_tender.docx"], code="ZB")
        assert rc == 0, f"fixture docx ingest 应干净退出, 实际 rc={rc}"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_shape_locked_to_t1_contract(self, run):
        assert set(run.keys()) == {"chunks", "tables"}
        for ch in run["chunks"]:
            assert set(ch.keys()) == {"chunk_id", "source_file", "anchor", "heading_path", "n_paras"}, f"chunk 字段集不符: {sorted(ch.keys())}"
        for t in run["tables"]:
            assert set(t.keys()) == {"table_id", "source_file", "anchor", "n_rows", "n_cols", "caption"}, f"table 字段集不符: {sorted(t.keys())}"

    def test_chunk_ids_sequential_unique(self, run):
        ids = [c["chunk_id"] for c in run["chunks"]]
        assert ids == [f"CH-{i:03d}" for i in range(1, len(ids) + 1)], f"chunk_id 应从 CH-001 起按文档序连续发放: {ids}"
        assert len(ids) == len(set(ids))

    def test_docx_anchor_no_page(self, run):
        """docx 锚点 = section+段序, 不得含 page 键(docx 无分页概念)。"""
        for ch in run["chunks"]:
            anchor = ch["anchor"]
            assert "page" not in anchor, f"{ch['chunk_id']} docx 锚点不得含 page: {anchor}"
            assert isinstance(anchor["section"], str) and anchor["section"].strip()
            assert isinstance(anchor["para"], int) and anchor["para"] >= 1

    def test_clause_anchor_coverage(self, run):
        """clauses.json 全部条款的 (source_file, section) 锚点必须被 ingest 产物覆盖(extract.py 校验前提)。"""
        covered = {(c["source_file"], c["anchor"]["section"]) for c in run["chunks"]} | {(t["source_file"], t["anchor"]["section"]) for t in run["tables"]}
        for c in load_json("clauses.json"):
            if c["source_file"] == "minimal_tender.docx":
                assert (c["source_file"], c["source_ref"]["section"]) in covered, f"{c['clause_id']} 锚点未被 ingest 覆盖: {c['source_ref']['section']}"

    def test_format_section_headings_present_in_tree(self, run):
        """heading_path 必须是完整标题链(供格式章节检测与结构镜像消费)。"""
        for ch in run["chunks"]:
            assert isinstance(ch["heading_path"], list) and ch["heading_path"], f"{ch['chunk_id']} heading_path 非空"
        paths = [" / ".join(c["heading_path"]) for c in run["chunks"]]
        assert any("第三章 技术规范" in p and "3.2.1 技术参数要求" in p for p in paths), f"三级标题链缺失: {paths}"

    def test_table_ids_and_real_row_counts(self, run):
        """表行数必须来自实际解析(D5): 参数表 3x3, 评分细则表 4x4, 与 fixture 文档一致。"""
        tables = sorted(run["tables"], key=lambda t: t["table_id"])
        assert [t["table_id"] for t in tables] == ["T-001", "T-002"]
        assert (tables[0]["n_rows"], tables[0]["n_cols"]) == (3, 3), f"参数表应 3x3: {tables[0]}"
        assert (tables[1]["n_rows"], tables[1]["n_cols"]) == (4, 4), f"评分细则表应 4x4: {tables[1]}"
        assert tables[0]["caption"] == "技术参数表", f"caption 应取所在章节标题(去编号): {tables[0]['caption']}"
        # 表锚点: 表在所在章节内的块序(段落序)——3.2.2 下唯一块=表→para 1;
        # 6.1 下唯一块=表(评分办法引言段属第六章直接正文, 不在 6.1 之下)→para 1
        assert (tables[0]["anchor"]["section"], tables[0]["anchor"]["para"]) == ("3.2.2", 1), f"{tables[0]['anchor']}"
        assert (tables[1]["anchor"]["section"], tables[1]["anchor"]["para"]) == ("6.1", 1), f"{tables[1]['anchor']}"

    def test_atomic_write_no_temp_leftovers(self, tmp_path):
        """D7: 写盘必须临时文件+os.replace, 结束后目录内无 *.tmp* 残留。"""
        rc, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc == 0 and path.is_file()
        leftovers = [p.name for p in path.parent.iterdir() if "tmp" in p.name.lower() or p.suffix == ".tmp"]
        assert not leftovers, f"写盘残留临时文件: {leftovers}"
        json.loads(path.read_text(encoding="utf-8"))  # 产物必须是合法 JSON(无半截文件)

    def test_rerun_replaces_not_duplicates(self, tmp_path):
        """同一文件重复 ingest → 替换该文件的旧块, 不产生重复 chunk/table。"""
        rc1, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        rc2, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc1 == 0 and rc2 == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = [c["source_file"] for c in data["chunks"]] + [t["source_file"] for t in data["tables"]]
        assert sources.count("minimal_tender.docx") == len(sources), f"重复运行不得追加重复文件块: {sources}"

    def test_summary_reports_code_allocation(self, tmp_path, capsys):
        """--code 文件代号分配必须体现在运行摘要(stdout JSON), 供阶段2 clause_id 前缀使用。"""
        rc, _ = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"], code="ZB")
        assert rc == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")]
        assert lines, "stdout 应含单行 JSON 摘要"
        summary = json.loads(lines[-1])
        assert summary["files"][0]["code"] == "ZB"
        assert summary["files"][0]["addendum"] is False


class TestIngestSummaryOutput:
    def test_summary_json_contains_code_and_counts(self, tmp_path, capsys):
        """stdout 摘要(单行 JSON)须含 files[].code/chunks/tables, 供 Agent 编排与确认门消费。"""
        rc, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"], code="ZB")
        assert rc == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
        assert lines, f"stdout 应含单行 JSON 摘要: {out!r}"
        summary = json.loads(lines[-1])
        assert summary["files"][0]["code"] == "ZB"
        assert summary["files"][0]["file"].endswith("minimal_tender.docx")
        assert isinstance(summary["files"][0]["chunks"], int) and summary["files"][0]["chunks"] >= 1
        assert isinstance(summary["files"][0]["tables"], int) and summary["files"][0]["tables"] == 2


class TestIngestPdfFixture:
    """对 fixture minimal_tender.pdf 跑真 ingest: page+section 锚点分流。"""

    @pytest.fixture(scope="class")
    def run(self, tmp_path_factory):
        rc, path = _run_ingest(tmp_path_factory.mktemp("ingest_pdf"), [FIXTURE_DIR / "minimal_tender.pdf"], code="JS")
        assert rc == 0, f"fixture pdf ingest 应干净退出, 实际 rc={rc}"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_pdf_anchor_page_plus_section(self, run):
        """PDF 锚点 = page+section(单页 fixture 全部 page=1, section=标题编号)。"""
        assert run["chunks"], "PDF 应产出 chunk"
        for ch in run["chunks"]:
            anchor = ch["anchor"]
            assert isinstance(anchor["page"], int) and anchor["page"] >= 1, f"{ch['chunk_id']} PDF 锚点缺 page: {anchor}"
            assert isinstance(anchor["section"], str) and anchor["section"].strip()
            assert "para" not in anchor, f"{ch['chunk_id']} PDF 锚点不含 para(设计: page+section): {anchor}"
        sections = {c["anchor"]["section"] for c in run["chunks"]}
        assert {"1", "2", "3"} <= sections, f"三个标题的编号段应各自成块: {sections}"

    def test_pdf_body_counted_into_chunk(self, run):
        by_section = {c["anchor"]["section"]: c for c in run["chunks"]}
        assert by_section["2"]["n_paras"] >= 1, "标题 2 下的正文行应计入 n_paras"

    def test_pdf_mixed_invocation_with_docx(self, tmp_path):
        """一次调用混合 docx+pdf: 双来源共存, chunk_id 全局唯一连续。"""
        rc, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx", FIXTURE_DIR / "minimal_tender.pdf"], code="ZB")
        assert rc == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = {c["source_file"] for c in data["chunks"]}
        assert any(s.endswith(".docx") for s in sources) and any(s.endswith(".pdf") for s in sources), sources
        ids = [c["chunk_id"] for c in data["chunks"]]
        assert len(ids) == len(set(ids)), "跨文件 chunk_id 不得重复"


class TestIngestFormatSection:
    """格式章节(投标文件格式)定位 → 只产出章节树骨架(槽位语义定型留给阶段2)。"""

    FORMAT_DOCX_BLOCKS = [
        ("h", 1, "第一章 招标公告"),
        ("p", "项目编号:EAI-T-2026-001, 欢迎符合资格条件的投标人投标。"),
        ("h", 1, "第二章 投标文件格式"),
        ("h", 2, "一、投标函"),
        ("p", "按以下格式填报投标函并加盖公章(此处为格式模板正文, 不作条款提取)。"),
        ("h", 2, "二、法定代表人身份证明"),
        ("p", "此处应插入加盖公章的身份证正反面扫描件。"),
        ("h", 1, "第三章 技术规范"),
        ("p", "设备防护等级不低于IP65。"),
    ]

    def test_detect_format_regions_unit(self):
        ingest = _ingest_module()
        headings = [(b[1], b[2]) for b in self.FORMAT_DOCX_BLOCKS if b[0] == "h"]
        regions = ingest.detect_format_regions(headings)
        assert len(regions) == 1, f"应检出 1 个格式章节: {regions}"
        start, end = regions[0]
        assert headings[start][1] == "第二章 投标文件格式"
        # 区域终点 = 下一个同级或更高级标题(第三章)之前
        assert headings[end][1] == "第三章 技术规范"

    def test_is_format_heading_heuristic(self):
        ingest = _ingest_module()
        assert ingest.is_format_heading(1, "第二章 投标文件格式")
        assert ingest.is_format_heading(2, "投标文件格式一览")
        assert not ingest.is_format_heading(1, "第六章 评标办法"), "评标办法章节不得误判为格式章节"
        assert not ingest.is_format_heading(1, "第三章 技术规范")
        assert not ingest.is_format_heading(1, "评分办法及格式说明"), "含评分/评标/办法字样的标题不按弱规则判格式"
        assert not ingest.is_format_heading(3, "3.2.2 技术参数表"), "低级标题不按弱规则判格式"

    def test_format_chapter_skeleton_only(self, tmp_path):
        """格式章节内: 每个标题都进骨架(n_paras=0, 树完整); 章外正常块 n_paras>=1。"""
        docx_path = _make_docx(tmp_path / "format_tender.docx", self.FORMAT_DOCX_BLOCKS)
        rc, path = _run_ingest(tmp_path, [docx_path])
        assert rc == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        by_path = {" / ".join(c["heading_path"]): c for c in data["chunks"]}
        # 骨架完整: 格式章节自身 + 两个二级标题全部成块, 树链可见
        for key in ("第二章 投标文件格式", "第二章 投标文件格式 / 一、投标函", "第二章 投标文件格式 / 二、法定代表人身份证明"):
            assert key in by_path, f"格式章节树缺节点: {key}; 实际: {sorted(by_path)}"
            assert by_path[key]["n_paras"] == 0, f"格式章节只出骨架, n_paras 应为 0: {key}"
        # 章外正常章节不受影响
        assert by_path["第一章 招标公告"]["n_paras"] == 1
        assert by_path["第三章 技术规范"]["n_paras"] == 1

    def test_format_sections_listed_in_summary(self, tmp_path, capsys):
        docx_path = _make_docx(tmp_path / "format_tender.docx", self.FORMAT_DOCX_BLOCKS)
        rc, _ = _run_ingest(tmp_path, [docx_path])
        assert rc == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")]
        summary = json.loads(lines[-1])
        assert any("投标文件格式" in "/".join(map(str, p)) for p in summary["format_sections"]), summary["format_sections"]


class TestIngestAddendum:
    """补遗输入(--addendum 标记, 代号前缀按文件代号分配): 增量追加 + ID 续号。"""

    def test_addendum_appends_and_continues_ids(self, tmp_path):
        addendum_docx = _make_docx(
            tmp_path / "补遗文件-01.docx",
            [
                ("h", 1, "二、补遗内容"),
                ("p", "交货期统一调整为合同签订后60天。"),
            ],
        )
        rc1, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"], code="ZB")
        assert rc1 == 0
        base = json.loads(path.read_text(encoding="utf-8"))
        base_max = max(int(c["chunk_id"].split("-")[1]) for c in base["chunks"])
        rc2, path = _run_ingest(tmp_path, [addendum_docx], code="BY", addendum=True)
        assert rc2 == 0, "补遗输入应正常增量受理"
        merged = json.loads(path.read_text(encoding="utf-8"))
        sources = {c["source_file"] for c in merged["chunks"]}
        assert any("补遗文件-01" in s for s in sources), f"补遗文件应入 sections: {sources}"
        assert any(s.endswith("minimal_tender.docx") for s in sources), "基础文件块不得被补遗运行清掉"
        new_ids = sorted(int(c["chunk_id"].split("-")[1]) for c in merged["chunks"] if "补遗" in c["source_file"])
        assert new_ids and min(new_ids) == base_max + 1, f"补遗 chunk 应从基础最大号后续发: base_max={base_max}, new={new_ids}"


class TestIngestErrorPaths:
    def test_missing_input_file_exit_1(self, tmp_path):
        rc, path = _run_ingest(tmp_path, [tmp_path / "不存在.docx"])
        assert rc == 1
        assert not path.exists(), "输入缺失时不得写出 sections.json"

    def test_unsupported_extension_exit_1(self, tmp_path):
        f = tmp_path / "tender.txt"
        f.write_text("x", encoding="utf-8")
        rc, _ = _run_ingest(tmp_path, [f])
        assert rc == 1

    def test_invalid_code_exit_1(self, tmp_path):
        rc, _ = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"], code="z1")
        assert rc == 1, "文件代号必须为 2-4 位大写字母(schema 契约)"

    def test_scanned_docx_exit_2_with_ocr_hint(self, tmp_path, capsys):
        """无文本层(仅图片)docx → 退出码 2 + 明确走 OCR 路径提示, 不写 sections.json。"""
        import base64
        import io

        docx_mod = pytest.importorskip("docx", reason="backend venv 缺 python-docx")
        doc = docx_mod.Document()
        doc.add_picture(io.BytesIO(base64.b64decode(_TINY_PNG_B64)))
        scanned = tmp_path / "扫描件.docx"
        doc.save(str(scanned))

        rc, path = _run_ingest(tmp_path, [scanned])
        assert rc == 2, f"扫描 docx 必须用独立退出码(区别于一般错误), 实际 rc={rc}"
        captured = capsys.readouterr()
        assert "OCR" in captured.out + captured.err, "必须给出走 eai-flow-ocr 路径的明确提示"
        assert not path.exists(), "OCR 分流场景不得写出 sections.json"


class TestIngestUnitHelpers:
    def test_section_id_split(self):
        """章节标识提取: 阿拉伯编号→编号; docx 中文序号标题→全文; PDF 中文序号→序号; 无编号→全文。"""
        ingest = _ingest_module()
        cases = [
            ("3.2.1 技术参数要求", "docx", "3.2.1"),
            ("6.1 评分细则", "docx", "6.1"),
            ("一、项目概况", "docx", "一、项目概况"),
            ("第一章 投标邀请", "docx", "第一章 投标邀请"),
            ("2. Technical Specifications", "pdf", "2"),
            ("二、补遗内容", "pdf", "二"),
            ("第一章 招标公告", "pdf", "第一章 招标公告"),
        ]
        for text, kind, expected in cases:
            assert ingest.section_id_for_heading(text, kind) == expected, f"{kind}: {text!r} → 期望 {expected!r}"

    def test_compare_table_rows(self):
        """D5 行数比对: 结构行数与抽取行数不一致 → 异常项; 一致 → 空。"""
        ingest = _ingest_module()
        assert ingest.compare_table_rows("T-001", 3, 3) == []
        anomalies = ingest.compare_table_rows("T-002", 5, 3)
        assert len(anomalies) == 1 and anomalies[0]["table_id"] == "T-002"
        assert anomalies[0]["structural_rows"] == 5 and anomalies[0]["extracted_rows"] == 3

    def test_xml_fallback_matches_primary(self):
        """python-docx 失效兜底(zipfile+XML 直读)须与主路径产出同构块序列(含 xml_rows)。"""
        ingest = _ingest_module()
        path = str(FIXTURE_DIR / "minimal_tender.docx")
        try:
            primary = ingest.parse_docx_blocks(path)
        except Exception:
            fallback = ingest.parse_docx_blocks_xml(path)
            assert fallback, "python-docx 不可用时兜底路径必须可独立运行"
            return
        fallback = ingest.parse_docx_blocks_xml(path)
        key = lambda b: (b["kind"], b.get("level"), b.get("text"))  # noqa: E731
        assert [key(b) for b in primary] == [key(b) for b in fallback], "兜底路径与主路径的标题/正文序列必须一致"
        # xml_rows(D5 结构行数基准)必须同口径: 曾经主路径递归数 w:tr、兜底只数直接子级,
        # 同一文件两路径给出不同行数——此处把 xml_rows 纳入逐块比对防再次分叉。
        primary_tables = [(b["n_rows"], b["n_cols"], b["xml_rows"]) for b in primary if b["kind"] == "table"]
        fallback_tables = [(b["n_rows"], b["n_cols"], b["xml_rows"]) for b in fallback if b["kind"] == "table"]
        assert primary_tables == fallback_tables == [(3, 3, 3), (4, 4, 4)]

    def test_atomic_write_json_survives_bad_dir(self, tmp_path):
        ingest = _ingest_module()
        target = tmp_path / "sub" / "sections.json"
        ingest.atomic_write_json(target, {"chunks": [], "tables": []})
        assert json.loads(target.read_text(encoding="utf-8")) == {"chunks": [], "tables": []}
        assert not [p for p in target.parent.iterdir() if "tmp" in p.name.lower()], "原子写盘不得残留临时文件"


# ===========================================================================
# T3 修复回归(审查六项): 退出码税目 / D5 嵌套表假阳性 / sections 装载校验 /
# 空文档分流 / 文首表锚点契约 / D5·OCR·损坏文件端到端补口
# ===========================================================================


class TestIngestExitCodeTaxonomy:
    """退出码分类税目: argparse 用法错误必须归 1——argparse 默认退出码 2 与
    EXIT_NEED_OCR 撞号, 会把 CLI 误用误路由进 OCR 路径(审查修复)。"""

    def test_argparse_usage_error_returns_1_not_2(self, capsys):
        ingest = _ingest_module()
        for argv in ([], ["--input", "x.docx"], ["--input", "x.docx", "--code", "ZB"], ["--unknown"]):
            rc = ingest.main(argv)
            assert rc == 1, f"用法错误 {argv!r} 应返回 1(2 保留给 OCR 分流), 实际 {rc}"
        capsys.readouterr()

    def test_help_returns_0(self, capsys):
        ingest = _ingest_module()
        assert ingest.main(["--help"]) == 0, "--help 属正常终止, 不得按错误处理"
        capsys.readouterr()

    def test_row_count_mismatch_end_to_end_rc3(self, tmp_path, capsys, monkeypatch):
        """D5 行数不一致端到端: rc=3 + 摘要 JSON anomalies 列出 row_count_mismatch + sections.json 照常落盘。"""
        ingest = _ingest_module()
        real_parse = ingest.parse_docx_blocks

        def parse_with_row_drift(path):
            blocks = real_parse(path)
            for b in blocks:
                if b["kind"] == "table":
                    b["xml_rows"] += 1  # 模拟"解析前后行数分叉"(如 pdfplumber 吞表)
            return blocks

        monkeypatch.setattr(ingest, "parse_docx_blocks", parse_with_row_drift)
        rc, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc == 3, "行数不一致必须以独立退出码 3 浮出, 绝不静默"
        assert path.is_file(), "D5 异常不阻断落盘(确认门1 需对每个 table_id 显式裁决)"
        summary = json.loads([ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")][-1])
        assert {a["kind"] for a in summary["anomalies"]} == {"row_count_mismatch"}, summary["anomalies"]
        assert {a["table_id"] for a in summary["anomalies"]} == {"T-001", "T-002"}, "两张表的不一致逐表成异常项"


class TestIngestFrontTable:
    """首个标题前的表格(封面表格形态): 锚点 section 必须非空(T1 契约),
    同时以 table_before_any_heading 异常项浮出(审查修复)。"""

    def test_table_before_heading_anchor_nonempty(self, tmp_path, capsys):
        docx_path = _make_docx(
            tmp_path / "front_table.docx",
            [
                ("table", [["项目名称", "EAI 演示项目"], ["项目编号", "EAI-T-2026-001"]]),
                ("h", 1, "第一章 招标公告"),
                ("p", "欢迎符合资格条件的投标人投标。"),
            ],
        )
        rc, path = _run_ingest(tmp_path, [docx_path])
        assert rc == 3, "文首表格应同时产出 table_before_any_heading 异常项"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["tables"]) == 1
        anchor = data["tables"][0]["anchor"]
        assert isinstance(anchor["section"], str) and anchor["section"].strip(), f"文首表格锚点 section 必须非空(T1 契约): {anchor}"
        assert isinstance(anchor["para"], int) and anchor["para"] >= 1
        summary = json.loads([ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("{")][-1])
        assert any(a["kind"] == "table_before_any_heading" for a in summary["anomalies"]), summary["anomalies"]


class TestIngestNestedTable:
    """嵌套表(投标格式模板常见): 结构行数只数直接子级 w:tr——递归口径会把内层行
    计入外层, 在与 n_rows(只数直接子级)比对时制造 row_count_mismatch 假阳性(审查修复)。"""

    def test_nested_table_no_false_mismatch(self, tmp_path):
        docx_mod = pytest.importorskip("docx", reason="backend venv 缺 python-docx")
        doc = docx_mod.Document()
        doc.add_heading("第一章 招标公告", level=1)  # 标题在前, 排除文首表异常项干扰
        doc.add_paragraph("正文。")
        outer = doc.add_table(rows=2, cols=2)
        outer.style = "Table Grid"
        for r in range(2):
            for c in range(2):
                outer.rows[r].cells[c].text = f"外{r}{c}"
        inner = outer.rows[1].cells[1].add_table(rows=2, cols=1)  # (1,1) 单元格内嵌 2x1 表
        for i in range(2):
            inner.rows[i].cells[0].text = f"内{i}"
        path = tmp_path / "nested.docx"
        doc.save(str(path))

        rc, out = _run_ingest(tmp_path, [path])
        assert rc == 0, "2x2 外层表含嵌套 2x1 表: 递归口径得 xml_rows=4 vs n_rows=2 → 假阳性 rc=3; 直接子级口径两者同为 2"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert [(t["n_rows"], t["n_cols"]) for t in data["tables"]] == [(2, 2)], "外层表行数=直接子级 2(嵌套行归嵌套表自身)"

        ingest = _ingest_module()
        blocks = ingest.parse_docx_blocks(path)
        blocks_xml = ingest.parse_docx_blocks_xml(path)
        tables = [(b["n_rows"], b["xml_rows"]) for b in blocks if b["kind"] == "table"]
        tables_xml = [(b["n_rows"], b["xml_rows"]) for b in blocks_xml if b["kind"] == "table"]
        assert tables == tables_xml == [(2, 2)], "主路径与兜底路径在嵌套表上必须同口径(直接子级)"


class TestIngestEmptyInputs:
    """空文档不是扫描件: 退出码 1 + 空文档提示——OCR 对空文档无济于事(审查修复)。"""

    def test_empty_docx_exit_1_not_ocr(self, tmp_path, capsys):
        docx_mod = pytest.importorskip("docx", reason="backend venv 缺 python-docx")
        empty = tmp_path / "空文档.docx"
        docx_mod.Document().save(str(empty))
        rc, path = _run_ingest(tmp_path, [empty])
        assert rc == 1, "空 docx(无文本/表格/图片)必须归退出码 1, 不得占用 OCR 分流的 2"
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "空" in combined and "OCR" not in combined, f"应报'空文档'而非 OCR 指引: {combined!r}"
        assert not path.exists()

    def test_image_only_pdf_exit_2_with_ocr_hint(self, tmp_path, capsys):
        """仅图片无文本层的 PDF(扫描件形态)→ 退出码 2 + 走 OCR 提示(端到端补口)。"""
        scanned = _make_raw_pdf(tmp_path / "扫描件.pdf", with_image=True)
        rc, path = _run_ingest(tmp_path, [scanned])
        assert rc == 2, "扫描 PDF 必须用独立退出码 2"
        captured = capsys.readouterr()
        assert "OCR" in captured.out + captured.err, "必须给出走 eai-flow-ocr 路径的明确提示"
        assert not path.exists(), "OCR 分流场景不得写出 sections.json"

    def test_empty_pdf_exit_1_not_ocr(self, tmp_path, capsys):
        empty = _make_raw_pdf(tmp_path / "空.pdf", with_image=False)
        rc, path = _run_ingest(tmp_path, [empty])
        assert rc == 1, "空 PDF 与空 docx 同理, 不是扫描件"
        captured = capsys.readouterr()
        assert "空" in captured.out + captured.err, f"应报'空文档'而非 OCR 指引: {captured.out!r} {captured.err!r}"
        assert not path.exists()


class TestIngestCorruptSectionsJson:
    """既有 sections.json 损坏: 干净退出 1 + 拒绝覆盖, 不得裸抛 traceback(审查修复:
    键存在但值类型错曾以未捕获 AttributeError 崩出)。"""

    def _write_existing(self, tmp_path, content: str):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        target = out_dir / "sections.json"
        target.write_text(content, encoding="utf-8")
        return target

    def test_truncated_json_exit_1(self, tmp_path):
        self._write_existing(tmp_path, '{"chunks": [')
        rc, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc == 1
        assert path.read_text(encoding="utf-8") == '{"chunks": [', "截断 JSON 必须拒绝覆盖(先人工核查)"

    def test_chunks_not_list_of_dicts_exit_1(self, tmp_path):
        existing = self._write_existing(tmp_path, json.dumps({"chunks": ["CH-001"], "tables": []}, ensure_ascii=False))
        rc, _ = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc == 1, "chunks 为字符串数组时应干净退出 1(曾裸抛 AttributeError)"
        assert existing.read_text(encoding="utf-8").startswith('{"chunks"'), "类型损坏同样拒绝覆盖"

    def test_tables_not_list_of_dicts_exit_1(self, tmp_path):
        self._write_existing(tmp_path, json.dumps({"chunks": [], "tables": [{"table_id": "T-001"}, "T-002"]}, ensure_ascii=False))
        rc, _ = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc == 1

    def test_load_sections_unit_rejects_bad_types(self, tmp_path):
        ingest = _ingest_module()
        p = tmp_path / "sections.json"
        p.write_text(json.dumps({"chunks": {}, "tables": []}), encoding="utf-8")
        with pytest.raises(ingest.IngestError):
            ingest.load_sections(p)


# ===========================================================================
# T3 残留审查修复: 无空格多级编号锚点坍缩(Critical) / 写盘 I/O 异常退出码契约
# (Important) / 同批同名文件防覆盖丢数据
# ===========================================================================


class TestIngestSpacelessNumbering:
    """Critical(残留审查): _ARABIC_PREFIX 前瞻曾允许任意位置的 ASCII 点, 回溯把
    "1.1项目概况"截成"1"、"3.2.1技术参数要求"截成"3.2"——不同章节坍缩到同一锚点
    (实测 CH-002/CH-003 同 section 且 rc=0 完全静默)。无空格编号是中文招标文件
    主流写法, 锚点又是 T4 条款溯源的全部地基。契约: 前瞻里的 ASCII 点必须后跟
    空白或行尾; 无空格多级编号回落为全文标识(与 docx "一、" 路径同构), 绝不截断。"""

    def test_spaceless_multilevel_falls_back_to_full_text(self):
        ingest = _ingest_module()
        for kind in ("docx", "pdf"):
            assert ingest.section_id_for_heading("1.1项目概况", kind) == "1.1项目概况", f"{kind}: 不得回溯截断为 '1'"
            assert ingest.section_id_for_heading("3.2.1技术参数要求", kind) == "3.2.1技术参数要求", f"{kind}: 不得截断为 '3.2'"

    def test_spaceless_headings_do_not_collapse(self):
        """坍缩复现: '1.1项目概况' 与 '1.2招标范围' 曾同坍缩为 '1'——锚点必须互异。"""
        ingest = _ingest_module()
        a = ingest.section_id_for_heading("1.1项目概况", "docx")
        b = ingest.section_id_for_heading("1.2招标范围", "docx")
        assert a != b, f"不同章节不得坍缩到同一锚点: {a!r} == {b!r}"

    def test_space_separated_numbering_still_extracted(self):
        """回归: 带空白的编号(含 '2. Title' 点+空格、行尾点号)提取行为不变。"""
        ingest = _ingest_module()
        assert ingest.section_id_for_heading("3.2.1 技术参数要求", "docx") == "3.2.1"
        assert ingest.section_id_for_heading("6.1 评分细则", "docx") == "6.1"
        assert ingest.section_id_for_heading("2. Technical Specifications", "pdf") == "2"
        assert ingest.section_id_for_heading("3.2.1. 技术参数要求", "docx") == "3.2.1", "点+空格收尾的多级编号仍取完整编号"
        assert ingest.section_id_for_heading("2.", "docx") == "2", "行尾点号仍视为编号分隔"

    def test_pdf_numbering_depth_spaceless_is_zero(self):
        """PDF 标题层级: 无空格编号不再误判深度(曾 '1.1项目概况' 拍平为 1)。"""
        ingest = _ingest_module()
        assert ingest._pdf_numbering_depth("2.") == 1
        assert ingest._pdf_numbering_depth("2.1") == 2
        assert ingest._pdf_numbering_depth("3.2.1 技术参数要求") == 3
        assert ingest._pdf_numbering_depth("1.1项目概况") == 0, "无空格编号回落为无编号(调用方回退为 1), 不得截断计数"

    def test_strip_heading_number_spaceless_unchanged(self):
        """caption 不被啃位: '1.1项目概况' 曾被剥成 '1项目概况'。"""
        ingest = _ingest_module()
        assert ingest.strip_heading_number("1.1项目概况") == "1.1项目概况"
        assert ingest.strip_heading_number("3.2.2 技术参数表") == "技术参数表"
        assert ingest.strip_heading_number("2. Technical Specifications") == "Technical Specifications"

    def test_spaceless_end_to_end_distinct_sections(self, tmp_path):
        """端到端(审查复现路径): 无空格编号标题各自成块、锚点互异且 rc=0, 不得静默坍缩。"""
        docx_path = _make_docx(
            tmp_path / "spaceless.docx",
            [
                ("h", 1, "1 招标公告"),
                ("p", "项目编号:EAI-T-2026-001。"),
                ("h", 2, "1.1项目概况"),
                ("p", "本项目为EAI演示项目。"),
                ("h", 2, "1.2招标范围"),
                ("p", "招标范围包括设备供货。"),
            ],
        )
        rc, path = _run_ingest(tmp_path, [docx_path])
        assert rc == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        sections = [c["anchor"]["section"] for c in data["chunks"]]
        assert sections == ["1", "1.1项目概况", "1.2招标范围"], f"无空格编号必须各自成块且锚点互异: {sections}"


class TestIngestWritePathErrors:
    """Important(残留审查): 写盘路径 I/O 异常曾以裸 traceback 逃出 main()——模块
    docstring 承诺 '1 = 用法/文件错误' 且 'main 统一转退出码', 解析路径包了但
    atomic_write_json(含其 mkdir)没包; 编排方应拿到干净的 [ingest] 错误行而非裸栈。"""

    def test_out_points_to_existing_file_exit_1(self, tmp_path, capsys):
        """--out 指向已存在普通文件 → mkdir FileExistsError 曾裸抛(审查复现 a)。"""
        ingest = _ingest_module()
        out_as_file = tmp_path / "out"
        out_as_file.write_text("我是一个普通文件, 不是目录", encoding="utf-8")
        argv = ["--input", str(FIXTURE_DIR / "minimal_tender.docx"), "--code", "ZB", "--out", str(out_as_file)]
        rc = ingest.main(argv)
        assert rc == 1, "--out 为普通文件时必须干净退出 1(不得 FileExistsError 裸栈)"
        err = capsys.readouterr().err
        assert "[ingest] 错误" in err, f"必须给出干净的 [ingest] 错误行: {err!r}"

    def test_sections_json_locked_on_replace_exit_1(self, tmp_path, capsys, monkeypatch):
        """sections.json 被其他程序占用(Windows 上 os.replace 拒绝访问) → 干净退出 1,
        原文件完好、无 tmp 残留(审查复现 b; 原子性实测无恙, 缺的只是退出码契约)。"""
        ingest = _ingest_module()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        target = out_dir / "sections.json"
        target.write_text('{"chunks": [], "tables": []}', encoding="utf-8")

        real_replace = os.replace

        def locked_replace(src, dst, *args, **kwargs):
            if str(dst).endswith("sections.json"):
                raise PermissionError(13, "拒绝访问(模拟目标文件被其他程序占用)")
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr(ingest.os, "replace", locked_replace)
        rc, path = _run_ingest(tmp_path, [FIXTURE_DIR / "minimal_tender.docx"])
        assert rc == 1, "目标被占用必须干净退出 1(不得 PermissionError 裸栈)"
        err = capsys.readouterr().err
        assert "[ingest] 错误" in err, f"必须给出干净的 [ingest] 错误行: {err!r}"
        assert path.read_text(encoding="utf-8") == '{"chunks": [], "tables": []}', "失败时目标文件必须完好(原子性)"
        leftovers = [p.name for p in path.parent.iterdir() if "tmp" in p.name.lower()]
        assert not leftovers, f"失败路径不得残留临时文件: {leftovers}"


class TestIngestSameBasenameInputs:
    """同批同名不同目录输入曾静默覆盖丢数据(残留审查可选③): sections.json 以
    basename 为同名替换键, 同名两文件的块混入同一 source_file 身份且重跑互相顶替。"""

    def test_duplicate_basename_exit_1(self, tmp_path, capsys):
        dir_a, dir_b = tmp_path / "a", tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        _make_docx(dir_a / "招标文件.docx", [("h", 1, "第一章 招标公告"), ("p", "甲目录版本正文。")])
        _make_docx(dir_b / "招标文件.docx", [("h", 1, "第二章 技术规范"), ("p", "乙目录版本正文。")])
        rc, path = _run_ingest(tmp_path, [dir_a / "招标文件.docx", dir_b / "招标文件.docx"])
        assert rc == 1, "同批同名文件必须显式拒绝(rc=1), 不得静默混身份"
        err = capsys.readouterr().err
        assert "招标文件.docx" in err, f"错误行须点名冲突文件名: {err!r}"
        assert not path.exists(), "拒绝受理时不得写出 sections.json"


# ===========================================================================
# T4: extract.py — 阶段2 候选 JSON 的确定性校验 + 合并(无 LLM)
# ===========================================================================
# CLI: extract.py validate --candidates <候选JSON...> --sections sections.json [--declared-total N]
#      extract.py merge    --candidates <候选JSON...> --sections sections.json --state-dir <dir> [--declared-total N]
# 候选记录契约(一次裁决 = 一个文件, 对齐 extraction_prompt.md 循环纪律):
#   {"chunk_id"|"table_id"(二选一), "kind": clauses|structure|rubric, "items": [...], "note": 判空理由(可选)}
# 校验规则(设计文档阶段2节 + D5/D7):
#   锚点必须存在于 sections.json / 枚举合法(对 references/*.schema.json, stdlib mini 校验器) /
#   跨块 clause_id(及 node_id/rubric_id)去重 / rubric Σmax_score=declared-total 不一致→异常并中止 /
#   chunk_id·table_id 全量有裁决(未裁决→异常清单"待门1显式判空", D5) /
#   linked_clause_ids 存在于 clauses 且未被 superseded(D7 外键装载校验);
#   merge: 派生字段(fill_status)不落盘 + 全部状态文件临时文件+os.replace 原子写
# 退出码: 0=干净 1=用法/文件错误 3=完成但有异常项(Σ 不一致时 merge 整体中止、不落盘)


def _extract_module():
    """硬导入 extract(T4 已落地; 模块缺失时测试失败而非 skip——管线脚本必须存在)。"""
    import importlib

    return importlib.import_module("extract")


def _write_candidate(dir_path, name, *, chunk_id=None, table_id=None, kind="clauses", items=None, **extra):
    """写一个候选裁决记录文件(一次裁决=一个文件契约)。"""
    record = {"kind": kind, "items": items if items is not None else []}
    if chunk_id is not None:
        record["chunk_id"] = chunk_id
    if table_id is not None:
        record["table_id"] = table_id
    record.update(extra)
    path = Path(dir_path) / name
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return path


def _happy_candidate_files(tmp_path, *, bad_sum=False):
    """全量裁决候选集: 5 chunk + 2 table 全覆盖, 条款/结构/评分全部合法。

    fixture sections.json 的 id 分配: CH-001/002/005/004→条款, CH-003→结构(占位,
    fixture 无格式章节块), T-001→判空, T-002→评分细则(Σ=declared=100)。
    """
    clauses_by_id = {c["clause_id"]: c for c in load_json("clauses.json")}
    rubric = load_json("rubric_bad_sum.json" if bad_sum else "rubric.json")
    return [
        _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[clauses_by_id["ZB-C-001"]]),
        _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[clauses_by_id["ZB-C-002"]]),
        _write_candidate(tmp_path, "c3.json", chunk_id="CH-005", kind="clauses", items=[clauses_by_id["ZB-C-003"]]),
        _write_candidate(tmp_path, "c4.json", chunk_id="CH-004", kind="clauses", items=[clauses_by_id["BY-C-004"]]),
        _write_candidate(tmp_path, "c5.json", chunk_id="CH-003", kind="structure", items=load_json("structure.json")),
        _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[], note="参数表无评分行, 显式判空"),
        _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=rubric["items"]),
    ]


def _run_extract(command, candidates, *, sections=None, declared_total=None, state_dir=None, references=None):
    extract = _extract_module()
    argv = [command, "--candidates", *[str(c) for c in candidates], "--sections", str(sections if sections is not None else FIXTURE_DIR / "sections.json")]
    if declared_total is not None:
        argv += ["--declared-total", str(declared_total)]
    if state_dir is not None:
        argv += ["--state-dir", str(state_dir)]
    if references is not None:
        argv += ["--references", str(references)]
    return extract.main(argv)


def _last_summary_json(capsys):
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip().startswith("{")]
    assert lines, f"stdout 应含单行 JSON 摘要: {out!r}"
    return json.loads(lines[-1])


def _anomaly_kinds(summary):
    return {a["kind"] for a in summary["anomalies"]}


class TestExtractValidateHappyPath:
    def test_full_adjudication_clean_exit_0(self, tmp_path, capsys):
        rc = _run_extract("validate", _happy_candidate_files(tmp_path), declared_total=100)
        assert rc == 0, f"全量裁决+合法候选应干净退出, 实际 rc={rc}"
        summary = _last_summary_json(capsys)
        assert summary["anomalies"] == []
        assert summary["unadjudicated"] == []
        assert summary["adjudicated"] == {"chunks": 5, "tables": 2}
        assert summary["counts"] == {"clauses": 4, "structure": 8, "rubric": 3}
        assert summary["rubric_sum"] == {"computed": 100, "declared": 100}

    def test_no_declared_total_skips_sum_check(self, tmp_path, capsys):
        rc = _run_extract("validate", _happy_candidate_files(tmp_path))
        assert rc == 0, "未给 --declared-total 时跳过 Σ 校验(无基准不误报)"
        summary = _last_summary_json(capsys)
        assert "rubric_sum" not in summary or summary["rubric_sum"].get("declared") is None

    def test_empty_adjudication_counts_as_coverage(self, tmp_path, capsys):
        """0 条显式判空(带 note)也是合法裁决——D5 要求的是'有裁决', 不是'有条目'。"""
        rc = _run_extract("validate", [_happy_candidate_files(tmp_path)[5]], declared_total=None)
        assert rc == 3  # 其余 id 未裁决 → 异常, 但 T-001 本身不算未裁决
        summary = _last_summary_json(capsys)
        assert "T-001" not in summary["unadjudicated"]
        assert set(summary["unadjudicated"]) == {"CH-001", "CH-002", "CH-003", "CH-004", "CH-005", "T-002"}


class TestExtractValidateNegative:
    """负例五类: Σ 不一致 / 未裁决 / 悬挂外键 / 跨块重复 / 枚举非法(+锚点/未知id/坏记录)。"""

    def test_rubric_sum_mismatch(self, tmp_path, capsys):
        rc = _run_extract("validate", _happy_candidate_files(tmp_path, bad_sum=True), declared_total=100)
        assert rc == 3, "Σmax_score(60+12+25=97) != declared-total(100) → 异常"
        summary = _last_summary_json(capsys)
        assert "rubric_sum_mismatch" in _anomaly_kinds(summary)
        assert summary["rubric_sum"]["computed"] == 97
        assert any("不一致" in a.get("message", "") for a in summary["anomalies"] if a["kind"] == "rubric_sum_mismatch")

    def test_declared_total_without_rubric_items_mismatches(self, tmp_path, capsys):
        files = [f for f in _happy_candidate_files(tmp_path) if f.name != "t2.json"]
        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "rubric_sum_mismatch" in _anomaly_kinds(summary), "声称总分 100 而评分项 Σ=0, 同样是 Σ 不一致"

    def test_unadjudicated_ids_pending_gate1(self, tmp_path, capsys):
        rc = _run_extract("validate", _happy_candidate_files(tmp_path)[:1])  # 只裁决 CH-001
        assert rc == 3
        summary = _last_summary_json(capsys)
        unadjudicated = [a for a in summary["anomalies"] if a["kind"] == "unadjudicated_id"]
        assert {a["id"] for a in unadjudicated} == {"CH-002", "CH-003", "CH-004", "CH-005", "T-001", "T-002"}
        assert all("判空" in a["message"] for a in unadjudicated), "未裁决 id 一律[待确认]进确认门1 显式判空"

    def test_dangling_fk_missing_clause(self, tmp_path, capsys):
        clauses_by_id = {c["clause_id"]: c for c in load_json("clauses.json")}
        node = dict(load_json("structure.json")[0])
        node["linked_clause_ids"] = ["ZB-C-999"]
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=list(clauses_by_id.values())),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-003", kind="structure", items=[node]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        fk = [a for a in summary["anomalies"] if a["kind"] == "clause_fk_invalid"]
        assert fk and fk[0]["clause_id"] == "ZB-C-999" and fk[0]["reason"] == "missing"

    def test_fk_to_superseded_clause_rejected(self, tmp_path, capsys):
        """D7: 引用已 supersede 条款(ZB-C-003 被 BY-C-004 替代)同样算外键不合法。"""
        clauses_by_id = {c["clause_id"]: c for c in load_json("clauses.json")}
        node = dict(load_json("structure.json")[0])
        node["linked_clause_ids"] = ["ZB-C-003"]
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=list(clauses_by_id.values())),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-003", kind="structure", items=[node]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        fk = [a for a in summary["anomalies"] if a["kind"] == "clause_fk_invalid"]
        assert fk and fk[0]["clause_id"] == "ZB-C-003" and fk[0]["reason"] == "superseded"

    def test_duplicate_clause_id_across_chunks(self, tmp_path, capsys):
        clauses_by_id = {c["clause_id"]: c for c in load_json("clauses.json")}
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[clauses_by_id["ZB-C-001"]]),
            _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[clauses_by_id["ZB-C-001"]]),  # 跨块撞号
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-003", kind="structure", items=[]),
            _write_candidate(tmp_path, "c6.json", chunk_id="CH-004", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c7.json", chunk_id="CH-005", kind="clauses", items=[]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3, "跨块 clause_id 重复必须拦截(去重防线)"
        summary = _last_summary_json(capsys)
        dup = [a for a in summary["anomalies"] if a["kind"] == "duplicate_id"]
        assert dup and dup[0]["id"] == "ZB-C-001" and len(dup[0]["files"]) == 2

    def test_duplicate_adjudication_of_same_chunk(self, tmp_path, capsys):
        """同一 chunk_id 两条裁决记录 = 检查点分叉, 双双隔离不强取首个。"""
        files = _happy_candidate_files(tmp_path)
        files.append(_write_candidate(tmp_path, "c1b.json", chunk_id="CH-001", kind="clauses", items=[]))
        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "duplicate_adjudication" in _anomaly_kinds(summary)

    def test_illegal_enum_schema_violation(self, tmp_path, capsys):
        clause = dict(load_json("clauses.json")[0])
        clause["class"] = "critical"  # 枚举外
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[clause]),
            _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c3.json", chunk_id="CH-003", kind="structure", items=[]),
            _write_candidate(tmp_path, "c4.json", chunk_id="CH-004", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-005", kind="clauses", items=[]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        violations = [a for a in summary["anomalies"] if a["kind"] == "schema_violation"]
        assert violations and violations[0]["item_id"] == "ZB-C-001"
        assert any("class" in err for a in violations for err in a["errors"])

    def test_anchor_not_in_sections(self, tmp_path, capsys):
        clause = dict(load_json("clauses.json")[0])
        clause["source_ref"] = dict(clause["source_ref"], section="9.9")
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[clause]),
            _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c3.json", chunk_id="CH-003", kind="structure", items=[]),
            _write_candidate(tmp_path, "c4.json", chunk_id="CH-004", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-005", kind="clauses", items=[]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        anchor = [a for a in summary["anomalies"] if a["kind"] == "anchor_not_in_sections"]
        assert anchor and anchor[0]["item_id"] == "ZB-C-001" and anchor[0]["section"] == "9.9"

    def test_unknown_adjudication_id(self, tmp_path, capsys):
        files = _happy_candidate_files(tmp_path)
        files.append(_write_candidate(tmp_path, "c9.json", chunk_id="CH-999", kind="clauses", items=[]))
        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        unknown = [a for a in summary["anomalies"] if a["kind"] == "unknown_adjudication_id"]
        assert unknown and unknown[0]["id"] == "CH-999"

    def test_malformed_record(self, tmp_path, capsys):
        files = _happy_candidate_files(tmp_path)
        files.append(_write_candidate(tmp_path, "cx.json", kind="clauses", items="not-a-list"))  # 无 id + items 非数组
        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "malformed_record" in _anomaly_kinds(summary)


class TestExtractValidateFileErrors:
    def test_missing_candidate_file_exit_1(self, tmp_path):
        files = _happy_candidate_files(tmp_path)
        rc = _run_extract("validate", files + [tmp_path / "不存在.json"])
        assert rc == 1

    def test_invalid_json_candidate_exit_1(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        rc = _run_extract("validate", _happy_candidate_files(tmp_path) + [bad])
        assert rc == 1

    def test_missing_sections_file_exit_1(self, tmp_path):
        rc = _run_extract("validate", _happy_candidate_files(tmp_path), sections=tmp_path / "无.sections.json")
        assert rc == 1

    def test_argparse_usage_error_exit_1(self, capsys):
        extract = _extract_module()
        for argv in ([], ["validate"], ["validate", "--sections", "s.json"], ["merge", "--candidates", "c.json", "--sections", "s.json"], ["--unknown"]):
            rc = extract.main(argv)
            assert rc == 1, f"用法错误 {argv!r} 应返回 1, 实际 {rc}"
        capsys.readouterr()

    def test_help_returns_0(self, capsys):
        extract = _extract_module()
        assert extract.main(["--help"]) == 0
        assert extract.main(["validate", "--help"]) == 0
        capsys.readouterr()


class TestExtractMergeHappyPath:
    def test_merge_writes_three_state_files(self, tmp_path, capsys):
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 0
        clauses = json.loads((state_dir / "clauses.json").read_text(encoding="utf-8"))
        structure = json.loads((state_dir / "structure.json").read_text(encoding="utf-8"))
        rubric = json.loads((state_dir / "rubric.json").read_text(encoding="utf-8"))
        assert [c["clause_id"] for c in clauses] == ["ZB-C-001", "ZB-C-002", "ZB-C-003", "BY-C-004"]
        assert [n["node_id"] for n in structure] == [f"S-{i:03d}" for i in range(1, 9)]
        assert rubric["total_score"] == 100 and [i["rubric_id"] for i in rubric["items"]] == ["R-001", "R-002", "R-003"]
        summary = _last_summary_json(capsys)
        assert sorted(summary["written"]) == ["clauses.json", "rubric.json", "structure.json"]
        assert summary["aborted"] is False

    def test_merge_strips_derived_fill_status(self, tmp_path):
        """D7: 派生字段 fill_status 候选可带(schema 值域内), 落盘必须剥离——现算不落盘。"""
        nodes = [dict(n) for n in load_json("structure.json")]
        for n in nodes:
            n["fill_status"] = "filled"
        files = _happy_candidate_files(tmp_path)
        files[4] = _write_candidate(tmp_path, "c5.json", chunk_id="CH-003", kind="structure", items=nodes)
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", files, declared_total=100, state_dir=state_dir)
        assert rc == 0
        structure = json.loads((state_dir / "structure.json").read_text(encoding="utf-8"))
        assert structure and all("fill_status" not in n for n in structure), "落盘不得含派生字段 fill_status(D7)"

    def test_merge_atomic_no_tmp_leftovers(self, tmp_path):
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 0
        leftovers = [p.name for p in state_dir.iterdir() if "tmp" in p.name.lower()]
        assert not leftovers, f"原子写盘不得残留临时文件: {leftovers}"

    def test_merge_rerun_idempotent(self, tmp_path):
        state_dir = tmp_path / "state"
        files = _happy_candidate_files(tmp_path)
        assert _run_extract("merge", files, declared_total=100, state_dir=state_dir) == 0
        before = {p.name: p.read_text(encoding="utf-8") for p in state_dir.iterdir()}
        assert _run_extract("merge", files, declared_total=100, state_dir=state_dir) == 0
        after = {p.name: p.read_text(encoding="utf-8") for p in state_dir.iterdir()}
        assert before == after, "同一候选集重复合并必须幂等(按 id upsert, 不产生重复条目)"

    def test_merge_upsert_replaces_and_preserves(self, tmp_path):
        """既有状态: 候选按 id 替换旧条目, 未覆盖条目原样保留。"""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        old = dict(load_json("clauses.json")[0])
        old["requirement"] = "旧版要求(将被候选替换)"
        extra = dict(load_json("clauses.json")[1])
        extra.update({"clause_id": "JS-C-001", "source_file": "技术规范书.docx"})
        (state_dir / "clauses.json").write_text(json.dumps([old, extra], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 0
        clauses = json.loads((state_dir / "clauses.json").read_text(encoding="utf-8"))
        by_id = {c["clause_id"]: c for c in clauses}
        assert by_id["ZB-C-001"]["requirement"] == load_json("clauses.json")[0]["requirement"], "同 id 候选应替换旧条目"
        assert by_id["JS-C-001"]["requirement"] == extra["requirement"], "未被候选覆盖的既有条目必须保留"
        assert [c["clause_id"] for c in clauses] == ["ZB-C-001", "JS-C-001", "ZB-C-002", "ZB-C-003", "BY-C-004"]


class TestExtractMergeAbortsAndQuarantines:
    def test_sum_mismatch_aborts_merge_nothing_written(self, tmp_path, capsys):
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", _happy_candidate_files(tmp_path, bad_sum=True), declared_total=100, state_dir=state_dir)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert summary["aborted"] is True, "Σ 不一致 → 异常并中止"
        assert "rubric_sum_mismatch" in _anomaly_kinds(summary)
        assert not state_dir.exists() or not any(state_dir.iterdir()), "中止时一个状态文件都不得写(防止带病状态入库)"

    def test_bad_item_quarantined_clean_merged_with_fk_cascade(self, tmp_path, capsys):
        """枚举非法条目所在裁决块整体[待确认]不合并; 引用该条款的结构/评分项级联隔离(D7 外键)。

        不传 --declared-total: 评分块被级联隔离后 Σ 无干净基准——隔离/级联/干净块合并
        语义与 Σ 校验正交, 在此单独锁定; Σ 无条件中止语义由下一条测试锁定。
        """
        files = _happy_candidate_files(tmp_path)
        bad = dict(load_json("clauses.json")[1])  # ZB-C-002
        bad["class"] = "critical"
        files[1] = _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[bad])
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", files, state_dir=state_dir)
        assert rc == 3
        summary = _last_summary_json(capsys)
        kinds = _anomaly_kinds(summary)
        assert "schema_violation" in kinds
        assert "clause_fk_invalid" in kinds, "S-007/R-002 引用被隔离的 ZB-C-002 → 悬挂外键级联浮出"
        clauses = json.loads((state_dir / "clauses.json").read_text(encoding="utf-8"))
        assert [c["clause_id"] for c in clauses] == ["ZB-C-001", "ZB-C-003", "BY-C-004"], "干净裁决块照常合并, 异常块保持[待确认]不落盘"
        assert not (state_dir / "structure.json").exists(), "结构裁决块因悬挂外键被隔离, 不写 structure.json"
        assert not (state_dir / "rubric.json").exists(), "评分裁决块因悬挂外键被隔离, 不写 rubric.json"

    def test_sum_gap_attributable_to_quarantined_block_still_aborts(self, tmp_path, capsys):
        """Σ 校验无条件(任务T4/设计文档: 不一致→异常并中止, 不设归因例外): 评分块被级联隔离 →
        合并终态 Σ=0≠100, 即使差额恰等于被隔离块分值合计(0+100=100)也必须异常并整体中止。"""
        files = _happy_candidate_files(tmp_path)
        bad = dict(load_json("clauses.json")[1])  # ZB-C-002 非法 → S-007/R-002 级联隔离 c5/t2 两块
        bad["class"] = "critical"
        files[1] = _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[bad])

        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "rubric_sum_mismatch" in _anomaly_kinds(summary), "validate 同样必须报出该 Σ 不一致, 不得静默吞掉"
        assert summary["rubric_sum"]["computed"] == 0

        state_dir = tmp_path / "state"
        rc = _run_extract("merge", files, declared_total=100, state_dir=state_dir)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert summary["aborted"] is True, "Σ 不一致必须无条件中止——不得因差额可归因隔离块而放行干净块落盘"
        assert "rubric_sum_mismatch" in _anomaly_kinds(summary)
        assert not state_dir.exists() or not any(state_dir.iterdir()), "中止时一个状态文件都不得写(防带病状态入库)"

    def test_merge_without_declared_total_and_state(self, tmp_path, capsys):
        """首合并未给 --declared-total: rubric 照常合并但 total_score=null + 异常项提示(Σ 无基准未检)。"""
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), state_dir=state_dir)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "rubric_declared_total_missing" in _anomaly_kinds(summary)
        rubric = json.loads((state_dir / "rubric.json").read_text(encoding="utf-8"))
        assert rubric["total_score"] is None and len(rubric["items"]) == 3

    def test_merge_preserves_existing_declared_total(self, tmp_path, capsys):
        """既有 rubric.json 已有 total_score: 未传 --declared-total 时保留, 且不再报缺基准。"""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "rubric.json").write_text(json.dumps({"total_score": 100, "items": []}, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), state_dir=state_dir)
        assert rc == 0
        rubric = json.loads((state_dir / "rubric.json").read_text(encoding="utf-8"))
        assert rubric["total_score"] == 100 and len(rubric["items"]) == 3

    def test_corrupt_existing_state_exit_1_refuses_overwrite(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        target = state_dir / "clauses.json"
        target.write_text('{"truncated": [', encoding="utf-8")
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 1
        assert target.read_text(encoding="utf-8") == '{"truncated": [', "损坏状态文件必须拒绝覆盖(先人工核查)"


class TestExtractUnitHelpers:
    def test_load_schemas_default_references_dir(self):
        extract = _extract_module()
        schemas = extract.load_schemas()
        assert set(schemas) == {"clauses", "structure", "rubric"}

    def test_mini_validator_accepts_fixture_items(self):
        extract = _extract_module()
        schemas = extract.load_schemas()
        for c in load_json("clauses.json"):
            assert extract.validate_against_schema(schemas["clauses"], c) == [], f"{c['clause_id']} 应通过 schema 校验"
        for n in load_json("structure.json"):
            assert extract.validate_against_schema(schemas["structure"], n) == [], f"{n['node_id']} 应通过 schema 校验"
        for i in load_json("rubric.json")["items"]:
            assert extract.validate_against_schema(schemas["rubric"], i) == [], f"{i['rubric_id']} 应通过 schema 校验"

    def test_mini_validator_rejects_enum_and_extra_field(self):
        extract = _extract_module()
        schema = extract.load_schemas()["clauses"]
        bad_enum = dict(load_json("clauses.json")[0], **{"class": "critical"})
        assert extract.validate_against_schema(schema, bad_enum)
        extra_field = dict(load_json("clauses.json")[0], unknown_extra=True)
        assert extract.validate_against_schema(schema, extra_field)

    def test_strip_derived_fields(self):
        extract = _extract_module()
        node = {"node_id": "S-001", "fill_status": "filled", "path": "x"}
        assert extract.strip_derived_fields(node) == {"node_id": "S-001", "path": "x"}
        assert "fill_status" not in node or node["fill_status"]  # 原对象不被原地修改(防御式拷贝)


# ===========================================================================
# T4 审查修复回归(七项): Σ基准回用既有 total_score / 编码边界 / sections id 装载校验 /
# rubric 挂 chunk 归因 / 隔离汇总口径 / evaluate 纯函数 / 既有状态 max_score 纵深+原子写清理
# ===========================================================================


class TestExtractMergeBaselineReusesExistingTotal:
    """Σ 校验基准: merge 未给 --declared-total 时回用既有 rubric.json total_score——
    防"声称总分"与"实际 Σ"在同一状态里无告警分叉(重合并可静默落盘带病 rubric)。"""

    def test_remerge_without_flag_checks_against_existing_total(self, tmp_path, capsys):
        state_dir = tmp_path / "state"
        rc1 = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc1 == 0
        # 重合并不带 flag, 候选 Σ=97(bad_sum) → 以既有 total_score=100 为基准参与比较与展示
        rc2 = _run_extract("merge", _happy_candidate_files(tmp_path, bad_sum=True), state_dir=state_dir)
        assert rc2 == 3, "既有 total_score=100 而 items 实际 Σ=97 → 必须异常并整体中止, 不得静默落盘"
        summary = _last_summary_json(capsys)
        assert summary["aborted"] is True
        mismatch = [a for a in summary["anomalies"] if a["kind"] == "rubric_sum_mismatch"]
        assert mismatch and mismatch[0]["declared"] == 100 and mismatch[0]["computed"] == 97
        assert summary["rubric_sum"] == {"computed": 97, "declared": 100}
        rubric = json.loads((state_dir / "rubric.json").read_text(encoding="utf-8"))
        assert sum(i["max_score"] for i in rubric["items"]) == 100, "带病 rubric(Σ=97)不得覆盖既有干净状态(中止时不写任何文件)"

    def test_remerge_without_flag_matching_sum_stays_clean(self, tmp_path, capsys):
        """既有 total 与候选 Σ 一致时, 缺省基准不制造误报。"""
        state_dir = tmp_path / "state"
        assert _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir) == 0
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), state_dir=state_dir)
        assert rc == 0, "回用既有 total_score=100 且 Σ=100 → 无异常"
        summary = _last_summary_json(capsys)
        assert summary["rubric_sum"] == {"computed": 100, "declared": 100}
        assert "rubric_declared_total_missing" not in _anomaly_kinds(summary), "已有基准时不得再报缺基准"

    def test_validate_mode_never_uses_state_baseline(self, tmp_path, capsys):
        """validate 无状态目录概念: 未给 flag 即无基准, 不做 Σ 比较(既有契约不回归)。"""
        rc = _run_extract("validate", _happy_candidate_files(tmp_path, bad_sum=True))
        assert rc == 0
        summary = _last_summary_json(capsys)
        assert summary["rubric_sum"]["declared"] is None
        assert "rubric_sum_mismatch" not in _anomaly_kinds(summary)


class TestExtractEncodingBoundaries:
    """编码边界: 非 UTF-8 字节(GBK 候选/sections/schema/状态文件)必须归入 ExtractError
    (退出码 1 的文件错误契约), 进程内调用 main() 不得裸抛 UnicodeDecodeError。"""

    def test_gbk_candidate_exit_1(self, tmp_path):
        files = _happy_candidate_files(tmp_path)
        bad = tmp_path / "gbk候选.json"
        bad.write_bytes('{"chunk_id": "CH-001", "kind": "clauses", "items": [], "note": "中文备注"}'.encode("gbk"))
        assert _run_extract("validate", files + [bad]) == 1

    def test_gbk_sections_exit_1(self, tmp_path):
        sections = tmp_path / "sections.json"
        sections.write_bytes('{"chunks": [], "tables": [], "note": "中文"}'.encode("gbk"))
        assert _run_extract("validate", _happy_candidate_files(tmp_path), sections=sections) == 1

    def test_gbk_references_schema_exit_1(self, tmp_path):
        refs = tmp_path / "refs"
        refs.mkdir()
        for name in ("clauses.schema.json", "structure.schema.json", "rubric.schema.json"):
            (refs / name).write_text('{"type": "object"}', encoding="utf-8")
        (refs / "clauses.schema.json").write_bytes('{"$schema": "中文"}'.encode("gbk"))
        assert _run_extract("validate", _happy_candidate_files(tmp_path), references=refs) == 1

    def test_gbk_existing_state_exit_1(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "clauses.json").write_bytes('{"备注": "中文"}'.encode("gbk"))
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 1


class TestExtractSectionsIdValidation:
    """sections 装载校验补口: chunks/tables 条目的 chunk_id/table_id 必须是非空 str——
    此前缺 id 的条目会在 evaluate 的 sorted(None+str) 处裸崩 TypeError, 或产出 id:null 的
    无意义 unadjudicated 异常。"""

    def test_chunk_entry_missing_id_exit_1(self, tmp_path):
        sections = json.loads((FIXTURE_DIR / "sections.json").read_text(encoding="utf-8"))
        sections["chunks"][0].pop("chunk_id")  # CH-001
        path = tmp_path / "sections.json"
        path.write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("validate", _happy_candidate_files(tmp_path), sections=path)
        assert rc == 1, "缺 chunk_id 的 sections.json 属文件损坏(退出码 1), 不得进校验管线"

    def test_table_entry_id_wrong_type_exit_1(self, tmp_path):
        sections = json.loads((FIXTURE_DIR / "sections.json").read_text(encoding="utf-8"))
        sections["tables"][0]["table_id"] = 123
        path = tmp_path / "sections.json"
        path.write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("validate", _happy_candidate_files(tmp_path), sections=path)
        assert rc == 1, "table_id 类型错(非 str)同样属装载层损坏"

    def test_load_sections_unit_rejects_missing_id(self, tmp_path):
        extract = _extract_module()
        path = tmp_path / "sections.json"
        path.write_text(json.dumps({"chunks": [{"source_file": "x.docx"}], "tables": []}), encoding="utf-8")
        with pytest.raises(extract.ExtractError):
            extract.load_sections(path)


class TestExtractRubricChunkAnchor:
    """rubric 裁决挂 chunk_id: 锚点解析按表源走, 挂 chunk 恒 source_file=None →
    误诊为 anchor_not_in_sections; 必须显式拒绝并给出准确归因(应挂表裁决)。"""

    def test_rubric_on_chunk_id_specific_reason(self, tmp_path, capsys):
        files = [f for f in _happy_candidate_files(tmp_path) if f.name not in ("c1.json", "t2.json")]
        files.append(_write_candidate(tmp_path, "t2.json", chunk_id="CH-001", kind="rubric", items=load_json("rubric.json")["items"]))
        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        kinds = _anomaly_kinds(summary)
        assert "rubric_chunk_anchor" in kinds, "挂 chunk 的评分细则裁决必须有独立异常 kind"
        assert "anchor_not_in_sections" not in kinds, "不得误诊为'锚点不在 sections'(真实原因是应挂表裁决)"
        message = [a for a in summary["anomalies"] if a["kind"] == "rubric_chunk_anchor"][0]["message"]
        assert "table_id" in message, f"归因必须指向表裁决: {message}"
        assert any("rubric_chunk_anchor" in q["kinds"] for q in summary["quarantined"]), "该裁决块必须被隔离"


class TestExtractQuarantineAttribution:
    """隔离/重复归因三处口径: (a)同块撞 id 不得报'跨块'文案; (b)同块多种异常 kinds 不得漏报;
    (c)quarantined 按完整路径为键, 不同目录同名候选不得合并成一条。"""

    def test_intra_block_dup_not_labeled_cross_block(self, tmp_path, capsys):
        clause = load_json("clauses.json")[0]
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[clause, dict(clause)]),  # 同块撞 clause_id
            _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c3.json", chunk_id="CH-003", kind="structure", items=[]),
            _write_candidate(tmp_path, "c4.json", chunk_id="CH-004", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-005", kind="clauses", items=[]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        dup = [a for a in summary["anomalies"] if a["kind"] == "duplicate_id"]
        assert dup and dup[0]["id"] == "ZB-C-001"
        assert "跨块" not in dup[0]["message"], f"同一裁决块内撞 id 不得报'跨块'文案: {dup[0]['message']}"
        assert "同一裁决块" in dup[0]["message"]

    def test_cross_block_dup_still_labeled_cross_block(self, tmp_path, capsys):
        """真跨块重复的既有文案语义不回归。"""
        clauses_by_id = {c["clause_id"]: c for c in load_json("clauses.json")}
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[clauses_by_id["ZB-C-001"]]),
            _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[clauses_by_id["ZB-C-001"]]),
            _write_candidate(tmp_path, "c3.json", chunk_id="CH-003", kind="structure", items=[]),
            _write_candidate(tmp_path, "c4.json", chunk_id="CH-004", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-005", kind="clauses", items=[]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        dup = [a for a in summary["anomalies"] if a["kind"] == "duplicate_id"]
        assert dup and "跨块" in dup[0]["message"]

    def test_quarantine_kinds_lists_all_problem_kinds(self, tmp_path, capsys):
        """同块多种异常: quarantined[].kinds 必须收全(此前只取 problems[0])。"""
        good, bad_anchor = load_json("clauses.json")[0], load_json("clauses.json")[1]
        bad_enum = dict(good, **{"class": "critical"})
        bad_anchor = dict(bad_anchor, source_ref=dict(bad_anchor["source_ref"], section="9.9"))
        files = [
            _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[bad_enum, bad_anchor]),
            _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c3.json", chunk_id="CH-003", kind="structure", items=[]),
            _write_candidate(tmp_path, "c4.json", chunk_id="CH-004", kind="clauses", items=[]),
            _write_candidate(tmp_path, "c5.json", chunk_id="CH-005", kind="clauses", items=[]),
            _write_candidate(tmp_path, "t1.json", table_id="T-001", kind="rubric", items=[]),
            _write_candidate(tmp_path, "t2.json", table_id="T-002", kind="rubric", items=[]),
        ]
        rc = _run_extract("validate", files)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert {"schema_violation", "anchor_not_in_sections"} <= _anomaly_kinds(summary)
        entry = [q for q in summary["quarantined"] if q["file"].endswith("c1.json")]
        assert entry, summary["quarantined"]
        assert sorted(entry[0]["kinds"]) == ["anchor_not_in_sections", "schema_violation"], f"同块多种异常必须全部入 kinds: {entry[0]}"

    def test_same_name_candidates_in_different_dirs_not_merged(self, tmp_path, capsys):
        """不同目录同名候选文件: quarantined 按完整路径为键, 不得合并成一条。"""
        dir_a, dir_b = tmp_path / "a", tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        files = _happy_candidate_files(tmp_path)
        files.append(_write_candidate(dir_a, "bad.json", kind="clauses", items="not-a-list"))
        files.append(_write_candidate(dir_b, "bad.json", kind="clauses", items="not-a-list"))
        rc = _run_extract("validate", files, declared_total=100)
        assert rc == 3
        summary = _last_summary_json(capsys)
        bad_entries = [q for q in summary["quarantined"] if q["file"].endswith("bad.json")]
        assert len(bad_entries) == 2, f"不同目录同名文件必须各占一条(按完整路径为键): {summary['quarantined']}"
        assert len({q["file"] for q in bad_entries}) == 2, "两条记录的 file 必须可区分(完整路径)"


class TestExtractEvaluatePurity:
    """evaluate 声称纯函数: 不得原地改写传入的候选记录(派生字段剥离改走新列表)。"""

    def test_evaluate_does_not_mutate_input_records(self, tmp_path):
        extract = _extract_module()
        node = dict(load_json("structure.json")[0])
        node["fill_status"] = "filled"  # D7 派生字段: 校验时剥离, 但不得写回候选原对象
        record = {"chunk_id": "CH-003", "kind": "structure", "items": [node]}
        original = json.loads(json.dumps(record, ensure_ascii=False))
        sections = json.loads((FIXTURE_DIR / "sections.json").read_text(encoding="utf-8"))
        report = extract.evaluate(sections, extract.load_schemas(), [(tmp_path / "c.json", record)], None)
        assert record == original, f"evaluate 不得原地改写候选记录(纯函数契约): {record}"
        assert report["clean"]["structure"] and "fill_status" not in report["clean"]["structure"][0], "剥离结果仍须进入 clean 输出"


class TestExtractExistingStateHardening:
    """既有 rubric 状态装载纵深: items[].max_score 必须为整数(非 bool)——缺失误按 0 计、
    bool True 误按 1 计会让 Σ 摘要失真或制造假 fatal。"""

    def test_existing_rubric_item_missing_max_score_exit_1(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        target = state_dir / "rubric.json"
        target.write_text(json.dumps({"total_score": 100, "items": [{"rubric_id": "R-001"}]}, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 1, "既有 rubric 项缺 max_score 属状态损坏, 必须拒绝覆盖(先人工核查)"
        assert json.loads(target.read_text(encoding="utf-8"))["items"] == [{"rubric_id": "R-001"}]

    def test_existing_rubric_item_boolean_max_score_exit_1(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "rubric.json").write_text(json.dumps({"total_score": 100, "items": [{"rubric_id": "R-001", "max_score": True}]}, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 1, "bool 不是合法分值(True 会被 sum 误按 1 计)"

    def test_atomic_write_cleanup_failure_does_not_mask_original(self, tmp_path, monkeypatch):
        """Windows 文件占用场景: finally 里 tmp.unlink() 失败不得掩盖 os.replace 的原始异常。"""
        extract = _extract_module()
        monkeypatch.setattr(extract.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("replace-boom")))
        monkeypatch.setattr("os.unlink", lambda p, *a, **k: (_ for _ in ()).throw(PermissionError("unlink-busy")))
        with pytest.raises(extract.ExtractError) as excinfo:  # 修复轮2 起 OSError 包成 ExtractError(原始异常挂 __cause__)
            extract.atomic_write_json(tmp_path / "out.json", {"a": 1})
        cause = excinfo.value.__cause__
        assert cause is not None and "replace-boom" in str(cause), f"必须保留原始 OSError 而非清理失败的 PermissionError: {excinfo.value!r} cause={cause!r}"


# ===========================================================================
# T4 审查修复轮2(残留发现): sections anchor 值类型装载校验(T4-1) / mini 校验器 pattern
# 尾随换行按 ECMA 拒绝 / atomic_write_json IO 失败归入 ExtractError / utf-8-sig 兼容 BOM /
# 顶层 JSON 数组候选拒绝分支补用例
# ===========================================================================


class TestExtractSectionsAnchorValidation:
    """T4-1: sections.json 条目 anchor 为真值非 dict(str/list)时, evaluate 的
    (e.get("anchor") or {}).get("section") 裸抛 AttributeError 逃出 main()——chunk_id/
    table_id 有装载防线而 anchor 没有, 违反 load_sections 自身契约(值类型错 → ExtractError)。"""

    def test_chunk_anchor_string_value_exit_1(self, tmp_path):
        sections = json.loads((FIXTURE_DIR / "sections.json").read_text(encoding="utf-8"))
        sections["chunks"][0]["anchor"] = "3.2.1"  # 审查实测复现形态: 真值非 dict
        path = tmp_path / "sections.json"
        path.write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("validate", _happy_candidate_files(tmp_path), sections=path)
        assert rc == 1, "anchor 值类型错(str)属文件损坏(退出码 1), 不得在 evaluate 裸抛 AttributeError"

    def test_table_anchor_list_value_exit_1(self, tmp_path):
        sections = json.loads((FIXTURE_DIR / "sections.json").read_text(encoding="utf-8"))
        sections["tables"][0]["anchor"] = ["6.1"]
        path = tmp_path / "sections.json"
        path.write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")
        rc = _run_extract("validate", _happy_candidate_files(tmp_path), sections=path)
        assert rc == 1, "anchor 值类型错(list)同样属装载层损坏"

    def test_anchor_falsy_non_dict_rejected_unit(self, tmp_path):
        """falsy 非 dict(空串/0/[]/False)虽不裸崩, 但同样产出无意义锚点(section=None)——值类型错一律拒绝。"""
        extract = _extract_module()
        for bad in ("", [], 0, False):
            path = tmp_path / "sections.json"
            path.write_text(json.dumps({"chunks": [{"chunk_id": "CH-001", "source_file": "a.docx", "anchor": bad}], "tables": []}), encoding="utf-8")
            with pytest.raises(extract.ExtractError):
                extract.load_sections(path)

    def test_anchor_missing_or_null_accepted_unit(self, tmp_path):
        """契约允许形态: anchor 缺失或显式 null 不属于值类型错(evaluate 以 (None or {}) 兜底)。"""
        extract = _extract_module()
        path = tmp_path / "sections.json"
        path.write_text(json.dumps({"chunks": [{"chunk_id": "CH-001", "source_file": "a.docx"}, {"chunk_id": "CH-002", "source_file": "a.docx", "anchor": None}], "tables": []}), encoding="utf-8")
        data = extract.load_sections(path)
        assert len(data["chunks"]) == 2


class TestExtractPatternTrailingNewline:
    """mini 校验器: Python `$` 额外匹配"末尾换行之前"(ECMA-262 不允许)——id 类字段的
    锚定 pattern 不得放行 "ZB-C-001\\n" 这类含尾随换行的值(此前蒙混过关并可入库)。"""

    def test_id_with_trailing_newline_rejected_unit(self):
        extract = _extract_module()
        schema = extract.load_schemas()["clauses"]
        sneaky = dict(load_json("clauses.json")[0], clause_id="ZB-C-001\n")
        errors = extract.validate_against_schema(schema, sneaky)
        assert any("clause_id" in e for e in errors), f"尾部换行的 clause_id 必须被 pattern 拒绝: {errors}"

    def test_normal_id_still_passes_unit(self):
        """收紧不得误伤: 无换行的合法 id 照常通过(既有 fixture 全量绿)。"""
        extract = _extract_module()
        schemas = extract.load_schemas()
        assert extract.validate_against_schema(schemas["clauses"], load_json("clauses.json")[0]) == []

    def test_merge_rejects_trailing_newline_id(self, tmp_path, capsys):
        """端到端: 此前 "ZB-C-001\\n" 蒙混过 pattern 并入库; 现在裁决块 schema_violation 隔离,
        S-008/R-003 引用它级联悬挂外键 → Σ 无干净基准 → merge 整体中止(既有无条件中止语义)。"""
        clauses_by_id = {c["clause_id"]: c for c in load_json("clauses.json")}
        sneaky = dict(clauses_by_id["ZB-C-001"], clause_id="ZB-C-001\n")
        files = _happy_candidate_files(tmp_path)
        files[0] = _write_candidate(tmp_path, "c1.json", chunk_id="CH-001", kind="clauses", items=[sneaky])
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", files, declared_total=100, state_dir=state_dir)
        assert rc == 3, "含尾随换行的 clause_id 属 schema_violation, 裁决块[待确认]"
        summary = _last_summary_json(capsys)
        assert "schema_violation" in _anomaly_kinds(summary)
        entry = [q for q in summary["quarantined"] if q["file"].endswith("c1.json")]
        assert entry and "schema_violation" in entry[0]["kinds"]
        assert not state_dir.exists() or not any(state_dir.iterdir()), "级联隔离后 Σ=0≠100 → 整体中止, 含尾随换行的 id 不可能入库"


class TestExtractAtomicWriteIOErrorWrapped:
    """atomic_write_json 的 IO 失败(OSError)包成 ExtractError——CLI 契约"文件错误→rc=1
    干净消息", 裸 OSError 逃出 main() 只会留 traceback; 原始异常保留为 __cause__。"""

    def test_write_oserror_wrapped_as_extract_error(self, tmp_path, monkeypatch):
        extract = _extract_module()
        monkeypatch.setattr(extract.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("replace-boom")))
        with pytest.raises(extract.ExtractError) as excinfo:
            extract.atomic_write_json(tmp_path / "out.json", {"a": 1})
        assert excinfo.value.__cause__ is not None and "replace-boom" in str(excinfo.value.__cause__)

    def test_merge_write_failure_exit_1_not_raw(self, tmp_path, monkeypatch):
        extract = _extract_module()
        state_dir = tmp_path / "state"
        monkeypatch.setattr(extract.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("disk-full")))
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), declared_total=100, state_dir=state_dir)
        assert rc == 1, "写盘 IO 失败必须归入 ExtractError(rc=1), 不得让裸 OSError 逃出 main()"


class TestExtractBomTolerantLoading:
    """Windows 记事本"带 BOM 的 UTF-8"产物兼容: JSON 装载用 utf-8-sig(无 BOM 行为不变,
    GBK 等非 UTF-8 编码仍拒绝——见 TestExtractEncodingBoundaries 既有锁定)。"""

    def test_bom_sections_accepted(self, tmp_path):
        raw = (FIXTURE_DIR / "sections.json").read_text(encoding="utf-8")
        path = tmp_path / "sections.json"
        path.write_bytes(b"\xef\xbb\xbf" + raw.encode("utf-8"))
        assert _run_extract("validate", _happy_candidate_files(tmp_path), sections=path) == 0

    def test_bom_candidate_accepted(self, tmp_path):
        files = _happy_candidate_files(tmp_path)
        files[0].write_bytes(b"\xef\xbb\xbf" + files[0].read_bytes())
        assert _run_extract("validate", files) == 0

    def test_bom_existing_state_accepted(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        content = json.dumps({"total_score": 100, "items": []}, ensure_ascii=False)
        (state_dir / "rubric.json").write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        rc = _run_extract("merge", _happy_candidate_files(tmp_path), state_dir=state_dir)
        assert rc == 0, "带 BOM 的既有 rubric.json 是合法 UTF-8, 不得拒绝覆盖路径"


class TestExtractTopLevelArrayCandidate:
    """顶层 JSON 数组候选(非对象)拒绝分支: load_candidate 已有 isinstance(data, dict)
    检查, 补直接用例锁定该分支(覆盖补口, 非缺陷)。"""

    def test_top_level_array_candidate_exit_1(self, tmp_path):
        bad = tmp_path / "array.json"
        bad.write_text('["chunk_id", "CH-001"]', encoding="utf-8")
        rc = _run_extract("validate", _happy_candidate_files(tmp_path) + [bad])
        assert rc == 1, "顶层 JSON 数组不是合法候选记录(应为对象), 归入文件错误"


# ===========================================================================
# T5: merge_addenda.py — 阶段3 补遗/答疑确定性落账(幂等台账 + 新实体 D3 + 悬挂外键 D7)
# ===========================================================================
# CLI: merge_addenda.py --addendum-candidates <候选JSON> --state-dir <dir> [--decisions <人工裁决JSON>]
# 候选契约(一份补遗 = 一次调用 = 一个文件):
#   {"addendum_file": "补遗文件-01.pdf",
#    "entities": [{"type", "value"}],   # 可选: Agent 从补遗文本观察到的实体(D3 diff 基准)
#    "items": [{"mapping_id", "action": "new|modify|void",
#               "anchor": {"section"}|null, "target": <clause_id>|null, "clause": {...}|null}]}
# 三级合并: ①章节锚点在活条款(未 superseded/未 voided)中唯一命中→自动落账
#           ②相似度候选(仅 target 无 anchor)→脚本不合并, pending 产出新旧并排 diff
#           ③平手(锚点多命中)/同目标冲突→必须 --decisions 人工裁决
# 落账: new/modify 新条款强制 from_addendum=true; modify→旧项标 superseded_by; void→标 voided。
# 台账 merge_ledger.json 按 sha256(候选内容规范化哈希) 幂等: 同 hash 重跑整体跳过零写入。
# D7: 落账后扫描 structure/rubric 的 linked_clause_ids, 指向缺失/superseded/voided → 异常不静默。
# 退出码: 0=干净完成(含台账跳过) 1=用法/文件错误 3=完成但有异常项


def _merge_module():
    """硬导入 merge_addenda(T5 已落地; 模块缺失时测试失败而非 skip——管线脚本必须存在)。"""
    import importlib

    return importlib.import_module("merge_addenda")


def _copy_prestate(tmp_path, *, merged: bool = True) -> Path:
    """构建状态目录基线: 拷贝 fixture 四件套。

    merged=True  → fixture 原样(补遗已合并形态: ZB-C-003 已被 BY-C-004 supersede, 全外键合法);
    merged=False → 还原'补遗未合并'形态(移除 BY-C-004 + 清 ZB-C-003.superseded_by +
                   清 S-002/S-004 对 BY-C-004 的链接), 使干净合并后 FK 扫描全绿。
    """
    state = tmp_path / "state"
    state.mkdir(parents=True)
    clauses = json.loads((FIXTURE_DIR / "clauses.json").read_text(encoding="utf-8"))
    structure = json.loads((FIXTURE_DIR / "structure.json").read_text(encoding="utf-8"))
    if not merged:
        clauses = [c for c in clauses if c["clause_id"] != "BY-C-004"]
        for c in clauses:
            if c["clause_id"] == "ZB-C-003":
                c["superseded_by"] = None
        for n in structure:
            n["linked_clause_ids"] = [cid for cid in n["linked_clause_ids"] if cid != "BY-C-004"]
    # write_bytes: write_text 在 Windows 会把 \n 翻成 \r\n, 与 fixture 字节比对/脚本 LF 原子写不一致
    (state / "clauses.json").write_bytes((json.dumps(clauses, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    (state / "structure.json").write_bytes((json.dumps(structure, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    (state / "rubric.json").write_bytes((FIXTURE_DIR / "rubric.json").read_bytes())
    (state / "entities_whitelist.json").write_bytes((FIXTURE_DIR / "entities_whitelist.json").read_bytes())
    return state


def _addendum_clause(clause_id="BY-C-004", *, section="二", requirement="交货期:合同签订后60天内交货(补遗文件-01修订版)", quote="交货期统一调整为合同签订后60天"):
    """补遗新条款载荷: from_addendum 故意 False——脚本落账时必须强制置 True。"""
    return {
        "clause_id": clause_id,
        "source_file": "补遗文件-01.pdf",
        "class": "normal",
        "category": "commercial",
        "source_ref": {"page": 1, "section": section, "para": 1, "quote": quote},
        "requirement": requirement,
        "response_status": "pending_confirm",
        "response_skeleton": {"points": [], "evidence_ref": None, "suggestion": None},
        "from_addendum": False,
        "superseded_by": None,
    }


def _write_addendum(tmp_path, name="cands.json", *, items=None, entities=None, addendum_file="补遗文件-01.pdf", raw=None):
    record = raw if raw is not None else {"addendum_file": addendum_file, "items": items}
    if entities is not None:
        record["entities"] = entities
    path = Path(tmp_path) / name
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_decisions(tmp_path, decisions, name="decisions.json"):
    path = Path(tmp_path) / name
    path.write_text(json.dumps({"decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_merge(state_dir, candidates, *, decisions=None):
    mod = _merge_module()
    argv = ["--addendum-candidates", str(candidates), "--state-dir", str(state_dir)]
    if decisions is not None:
        argv += ["--decisions", str(decisions)]
    return mod.main(argv)


def _state_json(state_dir, name):
    return json.loads((Path(state_dir) / name).read_text(encoding="utf-8"))


def _snapshot(state_dir):
    return {p.name: p.read_bytes() for p in Path(state_dir).iterdir()}


def _clauses_by_id(state_dir):
    return {c["clause_id"]: c for c in _state_json(state_dir, "clauses.json")}


_MODIFY_ANCHOR_ITEMS = [{"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-004")}]


class TestMergeAddendaTier1Auto:
    """①章节锚点精确匹配 → 自动落账。"""

    def test_exact_anchor_modify_supersedes(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        rc = _run_merge(state, _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS))
        assert rc == 0, f"锚点唯一命中应自动落账干净退出, 实际 rc={rc}"
        by_id = _clauses_by_id(state)
        assert by_id["ZB-C-003"]["superseded_by"] == "BY-C-004", "修改条款: 旧项必须标 superseded_by 指向新 id"
        assert by_id["BY-C-004"]["from_addendum"] is True, "新条款必须强制 from_addendum=true(载荷为 False 也要覆盖)"
        assert by_id["BY-C-004"]["voided"] is False, "落账时 voided 缺省补 false"
        summary = _last_summary_json(capsys)
        assert summary["applied"]["added"] == ["BY-C-004"]
        assert summary["applied"]["superseded"] == [{"from": "ZB-C-003", "to": "BY-C-004"}]
        assert summary["pending"] == [] and summary["anomalies"] == []
        assert "clauses.json" in summary["written"] and summary["ledger_recorded"] is True

    def test_new_clause_action_enters_with_from_addendum(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "new", "clause": _addendum_clause("BY-C-005", requirement="质保期延长至36个月")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 0
        by_id = _clauses_by_id(state)
        assert by_id["BY-C-005"]["from_addendum"] is True
        summary = _last_summary_json(capsys)
        assert summary["applied"]["added"] == ["BY-C-005"] and summary["applied"]["superseded"] == []

    def test_void_marks_voided(self, tmp_path, capsys):
        """作废→标 voided; 引用该条款的 structure/rubric 外键以 voided 理由浮出(D7)。"""
        state = _copy_prestate(tmp_path, merged=True)
        items = [{"mapping_id": "M-003", "action": "void", "anchor": {"section": "3.2.1"}}]  # → ZB-C-001(S-008/R-003 引用)
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3, "落账后出现悬挂外键 → 完成但有异常(退出码 3)"
        assert _clauses_by_id(state)["ZB-C-001"]["voided"] is True, "作废落盘不因外键异常回滚"
        summary = _last_summary_json(capsys)
        assert summary["applied"]["voided"] == ["ZB-C-001"]
        fk = [(a["source"], a["item_id"], a["reason"]) for a in summary["anomalies"] if a["kind"] == "clause_fk_invalid"]
        assert sorted(fk) == [("rubric", "R-003", "voided"), ("structure", "S-008", "voided")]
        assert "clauses.json" in summary["written"], "外键异常是扫描型发现, 不阻断落账"

    def test_anchor_target_agreement_checked(self, tmp_path, capsys):
        """锚点命中与显式 target 不一致 → 异常, 不合并(绝不静默取其一)。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-004", "action": "modify", "anchor": {"section": "一、项目概况"}, "target": "ZB-C-001", "clause": _addendum_clause("BY-C-004")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "anchor_target_mismatch" in _anomaly_kinds(summary)
        assert "clauses.json" not in summary["written"]
        assert not (state / "merge_ledger.json").exists()


class TestMergeAddendaIdempotency:
    """内容哈希台账: 同补遗重跑直接跳过, 状态字节级不变。"""

    def test_same_candidates_rerun_byte_identical_and_skipped(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands) == 0
        snapshot = _snapshot(state)
        assert "merge_ledger.json" in snapshot, "完整落账必须记台账"
        assert not [n for n in snapshot if "tmp" in n.lower()], "原子写盘不得残留临时文件"
        rc = _run_merge(state, cands)
        assert rc == 0, "台账命中跳过属正常完成"
        summary = _last_summary_json(capsys)
        assert summary["skipped"] is True and summary["written"] == [], "跳过时零写入"
        assert _snapshot(state) == snapshot, "同补遗跑两遍, 状态目录必须字节级不变"
        ledger = _state_json(state, "merge_ledger.json")
        assert len(ledger) == 1, "同 hash 重跑不得追加台账条目"

    def test_hash_format_independent_of_key_order(self, tmp_path, capsys):
        """候选 JSON 键序/缩进不同但内容相同 → 同 hash → 跳过(规范化哈希)。"""
        state = _copy_prestate(tmp_path, merged=False)
        cands1 = _write_addendum(tmp_path, "a.json", items=_MODIFY_ANCHOR_ITEMS)
        reordered = {"items": _MODIFY_ANCHOR_ITEMS, "addendum_file": "补遗文件-01.pdf"}
        cands2 = _write_addendum(tmp_path, "b.json", raw=reordered)
        assert _run_merge(state, cands1) == 0
        assert _run_merge(state, cands2) == 0
        summary = _last_summary_json(capsys)
        assert summary["skipped"] is True, "内容等价的候选(键序不同)必须命中同一台账 hash"
        assert len(_state_json(state, "merge_ledger.json")) == 1

    def test_partial_run_rerun_byte_identical(self, tmp_path, capsys):
        """有 pending(需裁决)时不记台账; 相同候选重跑: 已落账项幂等重放, 状态字节级不变。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            *_MODIFY_ANCHOR_ITEMS,  # 锚点自动落账
            {"mapping_id": "M-009", "action": "modify", "target": "ZB-C-002", "clause": _addendum_clause("BY-C-006")},  # 相似度候选→pending
        ]
        cands = _write_addendum(tmp_path, items=items)
        assert _run_merge(state, cands) == 3
        assert not (state / "merge_ledger.json").exists(), "存在 pending 时不得记台账(重跑须能重新浮出)"
        snapshot = _snapshot(state)
        assert _run_merge(state, cands) == 3
        assert _snapshot(state) == snapshot, "部分落账状态重跑: 幂等重放不得产生字节漂移"
        assert _clauses_by_id(state)["ZB-C-003"]["superseded_by"] == "BY-C-004", "已落账链保留"


class TestMergeAddendaLedger:
    def test_ledger_entry_shape(self, tmp_path):
        from datetime import datetime

        state = _copy_prestate(tmp_path, merged=False)
        assert _run_merge(state, _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)) == 0
        ledger = _state_json(state, "merge_ledger.json")
        assert isinstance(ledger, list) and len(ledger) == 1
        entry = ledger[0]
        assert entry["hash"].startswith("sha256:") and len(entry["hash"]) == len("sha256:") + 64
        assert entry["addendum_file"] == "补遗文件-01.pdf"
        assert datetime.fromisoformat(entry["applied_at"]) is not None, "applied_at 必须是可解析的 ISO 时间戳(非法字符串会以 ValueError 失败)"
        assert entry["applied"] == {"added": ["BY-C-004"], "superseded": [{"from": "ZB-C-003", "to": "BY-C-004"}], "voided": [], "rejected": []}

    def test_pending_run_does_not_record_ledger(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        assert not (state / "merge_ledger.json").exists()
        summary = _last_summary_json(capsys)
        assert summary["ledger_recorded"] is False


class TestMergeAddendaSimilar:
    """②相似度候选: 脚本只产出新旧并排 diff, 不自行合并。"""

    def test_similar_candidate_pending_with_side_by_side_diff(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "pending_decision" in _anomaly_kinds(summary)
        assert len(summary["pending"]) == 1
        pending = summary["pending"][0]
        assert pending["mapping_id"] == "M-002" and pending["tier"] == "similar"
        assert pending["old"]["clause_id"] == "ZB-C-003" and "90天" in pending["old"]["requirement"], "旧条款并排"
        assert pending["new"]["clause_id"] == "BY-C-004" and "60天" in pending["new"]["requirement"], "新条款并排"
        assert "clauses.json" not in summary["written"], "相似度候选绝不自动合并"
        by_id = _clauses_by_id(state)
        assert by_id["ZB-C-003"]["superseded_by"] is None and "BY-C-004" not in by_id

    def test_decisions_apply_resolves_similar(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "apply"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 0, "人工裁决 apply 后应干净落账(ZB-C-003 无外键引用)"
        summary = _last_summary_json(capsys)
        assert summary["pending"] == [] and summary["ledger_recorded"] is True
        assert _clauses_by_id(state)["ZB-C-003"]["superseded_by"] == "BY-C-004"

    def test_decisions_reject_drops_item(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "reject"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 0, "reject 也是 resolved: 全部条目有裁决即干净完成"
        summary = _last_summary_json(capsys)
        assert summary["applied"]["rejected"] == ["M-002"] and summary["pending"] == []
        assert "clauses.json" not in summary["written"], "否决项不产生任何条款变更"
        assert summary["ledger_recorded"] is True, "全 resolved(含否决)记台账"

    def test_apply_decision_target_mismatch_keeps_pending(self, tmp_path, capsys):
        """similar 层裁决携带 target 且与条目不一致 → 异常浮出保持待裁决, 不得无声背离人工指示落账别处。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "apply", "target": "ZB-C-002"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "malformed_decision" in _anomaly_kinds(summary)
        assert len(summary["pending"]) == 1, "target 不一致的裁决不得执行, 条目保持待裁决"
        assert "clauses.json" not in summary["written"]
        assert _clauses_by_id(state)["ZB-C-003"]["superseded_by"] is None

    def test_apply_decision_target_consistent_applies(self, tmp_path, capsys):
        """similar 层裁决 target 与条目一致 → 照常落账(裁决 target 允许省略或与条目一致)。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "apply", "target": "ZB-C-003"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 0
        assert _clauses_by_id(state)["ZB-C-003"]["superseded_by"] == "BY-C-004"


class TestMergeAddendaTie:
    """③平手: 锚点多命中 → 必须 decisions 裁决。"""

    def _tie_state(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        clauses = _state_json(state, "clauses.json")
        clone = json.loads(json.dumps(clauses[0]))  # ZB-C-001(3.2.1) 克隆
        clone["clause_id"] = "ZB-C-005"
        clauses.append(clone)
        (state / "clauses.json").write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state

    def test_tie_pending_lists_candidates(self, tmp_path, capsys):
        state = self._tie_state(tmp_path)
        items = [{"mapping_id": "M-005", "action": "void", "anchor": {"section": "3.2.1"}}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert len(summary["pending"]) == 1
        pending = summary["pending"][0]
        assert pending["tier"] == "tie"
        assert sorted(pending["candidates"]) == ["ZB-C-001", "ZB-C-005"], "平手必须列全候选目标"
        assert all(not _clauses_by_id(state)[cid]["voided"] for cid in ("ZB-C-001", "ZB-C-005")), "平手绝不自动落账"

    def test_tie_decision_with_target_applies(self, tmp_path, capsys):
        state = self._tie_state(tmp_path)
        items = [{"mapping_id": "M-005", "action": "void", "anchor": {"section": "3.2.1"}}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-005", "decision": "apply", "target": "ZB-C-005"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 0, "人工选定目标后落账(ZB-C-005 无外键引用)"
        by_id = _clauses_by_id(state)
        assert by_id["ZB-C-005"]["voided"] is True and by_id["ZB-C-001"]["voided"] is False
        summary = _last_summary_json(capsys)
        assert summary["applied"]["voided"] == ["ZB-C-005"]

    def test_tie_decision_without_target_anomaly(self, tmp_path, capsys):
        state = self._tie_state(tmp_path)
        items = [{"mapping_id": "M-005", "action": "void", "anchor": {"section": "3.2.1"}}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-005", "decision": "apply"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "malformed_decision" in _anomaly_kinds(summary)
        assert len(summary["pending"]) == 1, "缺 target 的平手裁决不得落账, 条目保持待裁决"


class TestMergeAddendaConflicts:
    def test_two_items_same_target_conflict(self, tmp_path, capsys):
        """同目标两条修改映射 → 双双 pending + target_conflict, 绝不静默取首个。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            {"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-004")},
            {"mapping_id": "M-002", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-005", requirement="交货期45天")},
        ]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "target_conflict" in _anomaly_kinds(summary)
        assert {p["mapping_id"] for p in summary["pending"]} == {"M-001", "M-002"}
        assert "clauses.json" not in summary["written"]

    def test_conflict_resolved_by_reject_decision(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            {"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-004")},
            {"mapping_id": "M-002", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-005", requirement="交货期45天")},
        ]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "reject"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 0, "裁决否决其一后冲突解除, 另一条自动落账"
        by_id = _clauses_by_id(state)
        assert by_id["ZB-C-003"]["superseded_by"] == "BY-C-004" and "BY-C-005" not in by_id
        summary = _last_summary_json(capsys)
        assert summary["applied"]["rejected"] == ["M-002"] and summary["pending"] == []


class TestMergeAddendaNewCollision:
    """new 动作撞号防线: 重放判定必须校验载荷内容一致, 否则 duplicate_clause_id 异常——
    同候选撞号/跨补遗同号不同内容绝不静默吞第二份载荷(审查修复: 原 from_addendum 即静默幂等)。"""

    def test_two_new_items_same_clause_id_different_content(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            {"mapping_id": "M-001", "action": "new", "clause": _addendum_clause("BY-C-009", requirement="质保期延长至36个月")},
            {"mapping_id": "M-002", "action": "new", "clause": _addendum_clause("BY-C-009", requirement="质保期延长至60个月")},
        ]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3, "同候选文件内两条 new 映射撞 clause_id → 异常, 绝不静默丢弃第二份载荷"
        summary = _last_summary_json(capsys)
        assert "duplicate_clause_id" in _anomaly_kinds(summary)
        assert summary["applied"]["added"] == ["BY-C-009"], "applied.added 不得出现同 id 两次的自相矛盾"
        assert _clauses_by_id(state)["BY-C-009"]["requirement"].startswith("质保期延长至36"), "首条落账, 第二条撞号浮出待人工"
        assert not (state / "merge_ledger.json").exists(), "有异常不得记台账"

    def test_new_replay_with_identical_payload_stays_idempotent(self, tmp_path, capsys):
        """部分落账后重跑同候选(无台账可跳): 载荷内容一致 → 幂等重放零字节漂移, 不误报撞号。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            {"mapping_id": "M-001", "action": "new", "clause": _addendum_clause("BY-C-005", requirement="质保期延长至36个月")},
            {"mapping_id": "M-009", "action": "modify", "target": "ZB-C-002", "clause": _addendum_clause("BY-C-006")},  # 相似度候选→pending
        ]
        cands = _write_addendum(tmp_path, items=items)
        assert _run_merge(state, cands) == 3
        snapshot = _snapshot(state)
        assert _run_merge(state, cands) == 3
        summary = _last_summary_json(capsys)
        assert "duplicate_clause_id" not in _anomaly_kinds(summary), "内容一致的重放不是撞号"
        assert summary["applied"]["added"] == ["BY-C-005"], "重放照常记 applied, 状态零变更"
        assert _snapshot(state) == snapshot, "幂等重放不得产生字节漂移"

    def test_cross_addendum_same_id_different_content_anomaly(self, tmp_path, capsys):
        """补遗-02 复用补遗-01 已入库 id 且内容不同 → 异常浮出, 不得静默吞掉第二份补遗条款。"""
        state = _copy_prestate(tmp_path, merged=True)  # BY-C-004 已入库(from_addendum=True)
        before = (state / "clauses.json").read_bytes()
        items = [{"mapping_id": "M-001", "action": "new", "clause": _addendum_clause("BY-C-004", requirement="交货期:合同签订后45天内交货(补遗文件-02修订版)")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items, addendum_file="补遗文件-02.pdf"))
        assert rc == 3, "跨补遗同号不同内容必须浮出, 不得静默按已应用记台账"
        summary = _last_summary_json(capsys)
        assert "duplicate_clause_id" in _anomaly_kinds(summary)
        assert summary["applied"]["added"] == []
        assert (state / "clauses.json").read_bytes() == before, "库内条款内容不得被静默改写"
        assert not (state / "merge_ledger.json").exists(), "静默吞条款后还记台账 = 双重假象"

    def test_new_id_collides_with_non_addendum_clause(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-001", "action": "new", "clause": _addendum_clause("ZB-C-001", requirement="与既有招标条款同号的新增条款")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "duplicate_clause_id" in _anomaly_kinds(summary)
        assert summary["applied"]["added"] == []
        assert _clauses_by_id(state)["ZB-C-001"]["from_addendum"] is False, "既有非补遗条款不得被覆盖"


class TestMergeAddendaModifyReplayContent:
    """T5-1 审查修复: modify 幂等重放(锚点层/相似度层)必须与 new 撞号防线同口径走
    _authored_content 比较——部分落账后操作者编辑载荷重跑, 同 id 不同内容 → 异常浮出
    而非重放, 绝不静默吞掉编辑后的候选(否则陈旧内容永久封存且零信号)。"""

    def test_anchor_replay_with_edited_payload_surfaces_anomaly(self, tmp_path, capsys):
        """锚点层: 运行1落账 BY-C-004(60天)且因 pending 不记台账; 修正为45天后重跑 →
        重放链命中但载荷内容不一致 → 异常浮出, applied.added 不得照报(原实现零信号)。"""
        state = _copy_prestate(tmp_path, merged=False)
        run1_items = [
            *_MODIFY_ANCHOR_ITEMS,  # 锚点自动落账 BY-C-004(60天)
            {"mapping_id": "M-009", "action": "modify", "target": "ZB-C-002", "clause": _addendum_clause("BY-C-006")},  # 相似度候选→pending, 台账不记
        ]
        assert _run_merge(state, _write_addendum(tmp_path, "run1.json", items=run1_items)) == 3
        assert _clauses_by_id(state)["BY-C-004"]["requirement"].startswith("交货期:合同签订后60"), "运行1已落账60天版本"
        before = (state / "clauses.json").read_bytes()
        # 操作者修正载荷为45天后重跑(同链同 id 不同内容)
        run2_items = [
            {"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-004", requirement="交货期:合同签订后45天内交货(补遗文件-01修订版)")},
            {"mapping_id": "M-009", "action": "modify", "target": "ZB-C-002", "clause": _addendum_clause("BY-C-006")},
        ]
        rc = _run_merge(state, _write_addendum(tmp_path, "run2.json", items=run2_items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        mismatch = [a for a in summary["anomalies"] if a["kind"] == "replay_content_mismatch"]
        assert mismatch and mismatch[0]["mapping_id"] == "M-001" and mismatch[0]["clause_id"] == "BY-C-004", "编辑后的候选被静默按重放吞掉 = 零信号"
        assert summary["applied"]["added"] == [], "内容分歧时 applied.added 照报 = 落账假象"
        assert (state / "clauses.json").read_bytes() == before, "库内60天陈旧内容不得被静默改写"
        assert not (state / "merge_ledger.json").exists(), "有异常不得记台账(陈旧内容不得被台账封存)"

    def test_similar_replay_with_edited_payload_surfaces_anomaly(self, tmp_path, capsys):
        """相似度层: 目标已被同 id 条款 supersede 且本次候选载荷与库内不一致 → 异常浮出
        (原实现只查 superseded_by==clause_id 即重放, rc=0 零信号)。"""
        state = _copy_prestate(tmp_path, merged=True)  # ZB-C-003 已被 BY-C-004(60天) supersede
        before = (state / "clauses.json").read_bytes()
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004", requirement="交货期:合同签订后45天内交货(补遗文件-01修订版)")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3, "重放内容分歧必须浮出(原实现 rc=0 干净完成 = 编辑内容永不落盘)"
        summary = _last_summary_json(capsys)
        assert "replay_content_mismatch" in _anomaly_kinds(summary)
        assert summary["applied"]["added"] == [], "内容分歧不得照报 applied"
        assert (state / "clauses.json").read_bytes() == before, "库内条款不得被静默改写"
        assert not (state / "merge_ledger.json").exists()

    def test_partial_run_similar_replay_identical_payload_stays_idempotent(self, tmp_path, capsys):
        """绿路径守卫: 相似度裁决已 apply、另一项 pending(台账不记)后重跑同候选同裁决——
        载荷内容一致 → 幂等重放照常, 不误报 replay_content_mismatch。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            {"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")},
            {"mapping_id": "M-009", "action": "modify", "target": "ZB-C-002", "clause": _addendum_clause("BY-C-006")},  # 不给裁决→pending, 台账不记
        ]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "apply"}])
        assert _run_merge(state, cands, decisions=decisions) == 3
        snapshot = _snapshot(state)
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "replay_content_mismatch" not in _anomaly_kinds(summary), "内容一致的重放不是异常"
        assert summary["applied"]["added"] == ["BY-C-004"], "重放照常记 applied, 状态零变更"
        assert _snapshot(state) == snapshot, "幂等重放不得产生字节漂移"


class TestMergeAddendaEntities:
    """D3 新实体提取: 补遗实体 diff 白名单 → 增量清单文件(确认门2 消费)。"""

    def test_new_entities_diff_file_written_whitelist_untouched(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        entities = [
            {"type": "company", "value": "东智装备制造有限公司"},  # 已在白名单
            {"type": "spec_version", "value": "S7-1500 V2.4"},  # 新版本号 → 增量
        ]
        whitelist_before = (state / "entities_whitelist.json").read_bytes()
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS, entities=entities)
        rc = _run_merge(state, cands)
        assert rc == 0
        pending_file = state / "addendum_entities_pending.json"
        assert pending_file.is_file(), "有新实体时必须产出增量实体清单文件"
        assert json.loads(pending_file.read_text(encoding="utf-8")) == {"entities": [{"type": "spec_version", "value": "S7-1500 V2.4"}]}
        assert (state / "entities_whitelist.json").read_bytes() == whitelist_before, "白名单不经本脚本修改(确认门2 才写入)"
        summary = _last_summary_json(capsys)
        assert summary["new_entities"] == [{"type": "spec_version", "value": "S7-1500 V2.4"}]

    def test_no_new_entities_no_file(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        entities = [{"type": "company", "value": "东智装备制造有限公司"}]  # 全部已白
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS, entities=entities)
        rc = _run_merge(state, cands)
        assert rc == 0
        assert not (state / "addendum_entities_pending.json").exists(), "无增量不产出空文件"

    def test_pending_entities_accumulate_and_clear_on_whitelist(self, tmp_path):
        """增量清单累积式: 既有 pending ∪ 本次新增 − 当前白名单(白名单确认后自动出列)。"""
        state = _copy_prestate(tmp_path, merged=False)
        run1 = _write_addendum(tmp_path, "c1.json", items=[], entities=[{"type": "spec_version", "value": "S7-1500 V2.4"}])
        assert _run_merge(state, run1) == 0
        pending = json.loads((state / "addendum_entities_pending.json").read_text(encoding="utf-8"))
        assert pending["entities"] == [{"type": "spec_version", "value": "S7-1500 V2.4"}]
        # 确认门2 之后: V2.4 勾入白名单; 第二份补遗带来新实体 李四
        whitelist = json.loads((state / "entities_whitelist.json").read_text(encoding="utf-8"))
        whitelist["entities"].append({"type": "spec_version", "value": "S7-1500 V2.4"})
        (state / "entities_whitelist.json").write_text(json.dumps(whitelist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run2 = _write_addendum(tmp_path, "c2.json", items=[], addendum_file="补遗文件-02.pdf", entities=[{"type": "person", "value": "李四"}])
        assert _run_merge(state, run2) == 0
        pending = json.loads((state / "addendum_entities_pending.json").read_text(encoding="utf-8"))
        assert pending["entities"] == [{"type": "person", "value": "李四"}], "已确认入白名单的实体自动出列, 新实体保留"

    def test_entities_without_whitelist_anomaly(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        (state / "entities_whitelist.json").unlink()
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS, entities=[{"type": "company", "value": "新公司"}])
        rc = _run_merge(state, cands)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "whitelist_missing" in _anomaly_kinds(summary), "白名单缺失必须浮出, 不静默"
        pending = json.loads((state / "addendum_entities_pending.json").read_text(encoding="utf-8"))
        assert pending["entities"] == [{"type": "company", "value": "新公司"}], "无白名单时按空集 diff, 全部进增量清单"
        assert not (state / "merge_ledger.json").exists(), "该异常阻断台账(修复白名单后重跑需重新 diff)"


class TestMergeAddendaHygiene:
    """审查修复: addendum_file 回退口径统一 / 增量清单删除在摘要可见。"""

    def test_blank_addendum_file_falls_back_uniformly(self, tmp_path, capsys):
        """纯空白 addendum_file: 落账路径与台账跳过路径统一回退候选文件名(原两处判空口径不一致)。"""
        state = _copy_prestate(tmp_path, merged=False)
        cands = _write_addendum(tmp_path, "cands.json", items=_MODIFY_ANCHOR_ITEMS, addendum_file="   ")
        assert _run_merge(state, cands) == 0
        summary = _last_summary_json(capsys)
        assert summary["addendum_file"] == "cands.json", "落账路径: 空白串回退候选文件名"
        assert _state_json(state, "merge_ledger.json")[0]["addendum_file"] == "cands.json"
        assert _run_merge(state, cands) == 0  # 台账命中跳过路径
        assert _last_summary_json(capsys)["addendum_file"] == "cands.json", "跳过路径与落账路径口径必须一致"

    def test_pending_entities_clear_reflected_in_written(self, tmp_path, capsys):
        """白名单确认后增量清单出清: 删除必须以 del: 前缀反映在 summary.written, 摘要不可见即不透明。"""
        state = _copy_prestate(tmp_path, merged=False)
        run1 = _write_addendum(tmp_path, "c1.json", items=[], entities=[{"type": "spec_version", "value": "S7-1500 V2.4"}])
        assert _run_merge(state, run1) == 0
        assert (state / "addendum_entities_pending.json").is_file()
        whitelist = _state_json(state, "entities_whitelist.json")
        whitelist["entities"].append({"type": "spec_version", "value": "S7-1500 V2.4"})
        (state / "entities_whitelist.json").write_text(json.dumps(whitelist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run2 = _write_addendum(tmp_path, "c2.json", items=[], addendum_file="补遗文件-02.pdf", entities=[{"type": "company", "value": "东智装备制造有限公司"}])
        assert _run_merge(state, run2) == 0
        assert not (state / "addendum_entities_pending.json").exists(), "已确认入白名单的实体增量自动出清"
        summary = _last_summary_json(capsys)
        assert "del:addendum_entities_pending.json" in summary["written"], "删除不入摘要 = 摘要撒谎"


class TestMergeAddendaFkScan:
    """D7 悬挂外键拦截: 落账后扫描 structure/rubric 的 linked_clause_ids。"""

    def test_supersede_dangles_rubric_link(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        items = [{"mapping_id": "M-006", "action": "modify", "anchor": {"section": "6.1"}, "clause": _addendum_clause("BY-C-005", section="三", requirement="技术方案先进性评分调整为20分", quote="技术方案先进性满分调整为20分")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        by_id = _clauses_by_id(state)
        assert by_id["ZB-C-002"]["superseded_by"] == "BY-C-005", "落账照常"
        summary = _last_summary_json(capsys)
        fk = [(a["source"], a["item_id"], a["clause_id"], a["reason"]) for a in summary["anomalies"] if a["kind"] == "clause_fk_invalid"]
        assert sorted(fk) == [("rubric", "R-002", "ZB-C-002", "superseded"), ("structure", "S-007", "ZB-C-002", "superseded")]

    def test_preexisting_missing_fk_surfaces_on_unrelated_merge(self, tmp_path, capsys):
        """合并前已存在的悬挂外键同样浮出(扫描以落账后全量状态为口径)。"""
        state = _copy_prestate(tmp_path, merged=False)
        structure = _state_json(state, "structure.json")
        structure[0]["linked_clause_ids"] = ["ZB-C-999"]
        (state / "structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        items = [{"mapping_id": "M-007", "action": "new", "clause": _addendum_clause("BY-C-005", requirement="质保期36个月")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        fk = [a for a in summary["anomalies"] if a["kind"] == "clause_fk_invalid"]
        assert fk and fk[0]["clause_id"] == "ZB-C-999" and fk[0]["reason"] == "missing"
        assert summary["applied"]["added"] == ["BY-C-005"], "外键发现不阻断本次落账"


class TestMergeAddendaValidation:
    """候选/裁决形态与落账时校验负例。"""

    def test_schema_invalid_clause_quarantined(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        bad = _addendum_clause("BY-C-004")
        bad["class"] = "critical"  # 枚举外
        items = [{"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": bad}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "schema_violation" in _anomaly_kinds(summary)
        assert "clauses.json" not in summary["written"], "载荷不合法不落账"

    def test_unknown_action_anomaly(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-001", "action": "delete", "target": "ZB-C-003"}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        assert "malformed_item" in _anomaly_kinds(_last_summary_json(capsys))

    def test_duplicate_mapping_id_second_skipped(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [
            {"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("BY-C-004")},
            {"mapping_id": "M-001", "action": "new", "clause": _addendum_clause("BY-C-005", requirement="重复映射的第二个条目")},
        ]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "duplicate_mapping_id" in _anomaly_kinds(summary)
        by_id = _clauses_by_id(state)
        assert by_id["ZB-C-003"]["superseded_by"] == "BY-C-004" and "BY-C-005" not in by_id, "首个映射落账, 重复映射跳过"

    def test_modify_without_anchor_or_target_anomaly(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-001", "action": "modify", "clause": _addendum_clause("BY-C-004")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        assert "malformed_item" in _anomaly_kinds(_last_summary_json(capsys))

    def test_self_supersede_anomaly(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "clause": _addendum_clause("ZB-C-003")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "self_supersede" in _anomaly_kinds(summary)
        assert _clauses_by_id(state)["ZB-C-003"]["superseded_by"] is None

    def test_target_already_superseded_anomaly(self, tmp_path, capsys):
        """raw 状态 ZB-C-003 已被 supersede: 人工裁决 apply 指向死条款 → target_inactive。"""
        state = _copy_prestate(tmp_path, merged=True)
        items = [{"mapping_id": "M-002", "action": "modify", "target": "ZB-C-003", "clause": _addendum_clause("BY-C-005", requirement="交货期45天")}]
        cands = _write_addendum(tmp_path, items=items)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-002", "decision": "apply"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 3
        summary = _last_summary_json(capsys)
        inactive = [a for a in summary["anomalies"] if a["kind"] == "target_inactive"]
        assert inactive and inactive[0]["reason"] == "superseded"
        assert len(summary["pending"]) == 1

    def test_decision_on_auto_item_unnecessary(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-001", "decision": "apply"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 3, "对自动落账项的冗余裁决 → 异常浮出"
        summary = _last_summary_json(capsys)
        assert "unnecessary_decision" in _anomaly_kinds(summary)
        assert _clauses_by_id(state)["ZB-C-003"]["superseded_by"] == "BY-C-004", "自动项照常落账"

    def test_unknown_and_duplicate_decisions(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        decisions = _write_decisions(tmp_path, [{"mapping_id": "M-999", "decision": "apply"}, {"mapping_id": "M-001", "decision": "reject"}, {"mapping_id": "M-001", "decision": "apply"}])
        rc = _run_merge(state, cands, decisions=decisions)
        assert rc == 3
        kinds = _anomaly_kinds(_last_summary_json(capsys))
        assert {"unknown_decision", "duplicate_decision"} <= kinds

    def test_malformed_record_no_items_key(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        rc = _run_merge(state, _write_addendum(tmp_path, raw={"addendum_file": "补遗文件-01.pdf"}))
        assert rc == 3
        assert "malformed_record" in _anomaly_kinds(_last_summary_json(capsys))

    def test_malformed_anchor_shape_anomaly_not_silent_downgrade(self, tmp_path, capsys):
        """anchor 存在但形态非法(section 非字符串, 即使 target 合法) → malformed_item, 不得静默降级为相似度候选。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-001", "action": "modify", "anchor": {"section": 3.2}, "target": "ZB-C-003", "clause": _addendum_clause("BY-C-004")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "malformed_item" in _anomaly_kinds(summary)
        assert summary["pending"] == [], "畸形锚点不得降级为相似度候选进 pending(锚点安全网对它将完全失效)"
        assert "clauses.json" not in summary["written"]

    def test_malformed_target_shape_anomaly(self, tmp_path, capsys):
        """target 存在但形态非法(非字符串, 即使 anchor 合法) → malformed_item, 不得静默置 None 后仅按锚点落账。"""
        state = _copy_prestate(tmp_path, merged=False)
        items = [{"mapping_id": "M-001", "action": "modify", "anchor": {"section": "一、项目概况"}, "target": 123, "clause": _addendum_clause("BY-C-004")}]
        rc = _run_merge(state, _write_addendum(tmp_path, items=items))
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert "malformed_item" in _anomaly_kinds(summary)
        assert summary["pending"] == [] and "clauses.json" not in summary["written"]


class TestMergeAddendaFileErrors:
    def test_missing_candidate_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        assert _run_merge(state, tmp_path / "不存在.json") == 1

    def test_invalid_candidate_json_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert _run_merge(state, bad) == 1

    def test_missing_state_clauses_exit_1(self, tmp_path):
        state = tmp_path / "empty-state"
        state.mkdir()
        cands = _write_addendum(tmp_path, items=[])
        assert _run_merge(state, cands) == 1, "阶段3 前提: 阶段2 已产出 clauses.json"

    def test_corrupt_state_refuses_overwrite(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        target = state / "clauses.json"
        target.write_text('{"truncated": [', encoding="utf-8")
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands) == 1
        assert target.read_text(encoding="utf-8") == '{"truncated": [', "损坏状态必须拒绝覆盖(先人工核查)"

    def test_clauses_source_ref_bad_shape_exit_1(self, tmp_path):
        """clauses.json 某条款 source_ref 为字符串 → 装载即拒绝覆盖, 不得在锚点匹配处裸 AttributeError。"""
        state = _copy_prestate(tmp_path, merged=False)
        clauses = _state_json(state, "clauses.json")
        clauses[0]["source_ref"] = "3.2.1"  # ZB-C-001: source_ref 非对象
        target = state / "clauses.json"
        target.write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands) == 1, "状态形态异常必须以 MergeAddendaError 拒绝(退出码 1), 不是未捕获崩溃"
        assert "3.2.1" in target.read_text(encoding="utf-8"), "拒绝覆盖: 原样保留待人工核查"

    def test_missing_decisions_file_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands, decisions=tmp_path / "无.json") == 1

    def test_invalid_decisions_json_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        bad = tmp_path / "decisions.json"
        bad.write_text("{not json", encoding="utf-8")
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands, decisions=bad) == 1

    def test_argparse_usage_error_exit_1(self, capsys):
        mod = _merge_module()
        for argv in ([], ["--state-dir", "x"], ["--addendum-candidates", "c.json"], ["--unknown"]):
            rc = mod.main(argv)
            assert rc == 1, f"用法错误 {argv!r} 应返回 1(2 保留给 ingest OCR 分流), 实际 {rc}"
        capsys.readouterr()

    def test_help_returns_0(self, capsys):
        assert _merge_module().main(["--help"]) == 0
        capsys.readouterr()


class TestMergeAddendaLinkedIdsShape:
    """T5-2 审查修复: structure/rubric 的 linked_clause_ids 畸形 → 装载时按状态契约干净拒绝
    (退出码 1, 拒绝覆盖先人工核查)——原实现字符串按字符迭代产出垃圾 clause_fk_invalid,
    dict 元素致 by_id.get(unhashable) 裸 TypeError 逃出 main() 的 MergeAddendaError 处理。"""

    def test_structure_linked_ids_string_rejected_exit_1(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=False)
        structure = _state_json(state, "structure.json")
        structure[0]["linked_clause_ids"] = "ZB-C-001"  # 字符串: 原实现按字符迭代产出 8 条假 clause_fk_invalid
        target = state / "structure.json"
        target.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands) == 1, "畸形状态必须装载时干净拒绝(退出码 1), 不是垃圾异常清单"
        err = capsys.readouterr().err
        assert "linked_clause_ids" in err and "拒绝覆盖" in err, "错误信息须定位到字段并声明拒绝覆盖"
        assert '"ZB-C-001"' in target.read_text(encoding="utf-8"), "拒绝覆盖: 原样保留待人工核查"

    def test_structure_linked_ids_dict_element_rejected_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        structure = _state_json(state, "structure.json")
        structure[0]["linked_clause_ids"] = [{"clause_id": "ZB-C-001"}]  # 元素为 dict: 原实现 by_id.get(unhashable) 裸 TypeError
        (state / "structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands) == 1, "未捕获 TypeError 不得逃出 main() 的 MergeAddendaError 处理(进程退出码不得靠巧合)"

    def test_rubric_linked_ids_non_list_rejected_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=False)
        rubric = _state_json(state, "rubric.json")
        rubric["items"][0]["linked_clause_ids"] = 42  # 非列表: 原实现 for 迭代 int 裸 TypeError
        target = state / "rubric.json"
        target.write_text(json.dumps(rubric, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cands = _write_addendum(tmp_path, items=_MODIFY_ANCHOR_ITEMS)
        assert _run_merge(state, cands) == 1
        assert '"linked_clause_ids": 42' in target.read_text(encoding="utf-8"), "拒绝覆盖: 原样保留待人工核查"


class TestMergeAddendaUnitHelpers:
    def test_content_hash_canonical(self):
        mod = _merge_module()
        assert mod.content_hash({"a": 1, "b": "x"}) == mod.content_hash({"b": "x", "a": 1}), "哈希必须规范化(键序无关)"
        assert mod.content_hash({"a": 1}) != mod.content_hash({"a": 2})
        assert mod.content_hash({"a": 1}).startswith("sha256:")


# ===========================================================================
# T6 build_output: 阶段4 双卷骨架渲染 + D2 clause_id 埋锚 + 偏离表/覆盖率 +
#    实体 lint + 人核清单(无 LLM; 不做 Word 转换——Agent 另调 markdown-to-docx)
# CLI: --state-dir <dir> --out <dir> → 六个 md: 商务卷/技术卷/偏离表/覆盖率报表/
#    人核清单/实体lint报告
# ① 商务卷=structure.json 镜像(只镜像不自创); ② 技术卷=镜像+逐条款条目,
#    条目标题嵌 clause_id(D2 锚点载体, 保留不删); ③ 偏离表=仅 mandatory+偏离项;
# ④ 覆盖率报表=清单总数/已响应/待确认/未分配; ⑤ 实体 lint=白名单 diff 全部
#    evidence_ref 与引用片段, 白名单外→[待核对](报告标"LLM辅助抽取白名单，非确定性");
# ⑥ format_check 项与[待人工复刻]表格槽全部进人核清单, 不进确定性判定。
# 纪律: 状态目录只读(D7 派生字段现算不落盘); 输出原子写盘; 重跑字节级幂等。
# 退出码: 0=干净完成(--help 亦 0) 1=用法/文件错误 3=完成但有异常项
# ===========================================================================


def _build_module():
    """硬导入 build_output(T6 已落地; 模块缺失时测试失败而非 skip)。"""
    import importlib

    return importlib.import_module("build_output")


BUILD_OUTPUT_FILES = ["商务卷.md", "技术卷.md", "偏离表.md", "覆盖率报表.md", "人核清单.md", "实体lint报告.md"]


def _run_build(state_dir, out_dir):
    return _build_module().main(["--state-dir", str(state_dir), "--out", str(out_dir)])


def _out_text(out_dir, name):
    return (Path(out_dir) / name).read_text(encoding="utf-8")


def _set_clause(state_dir, clause_id, **fields):
    """就地改写状态目录中某条款(测试构造偏离/未分配/证据引用/引用片段用例)。"""
    path = Path(state_dir) / "clauses.json"
    clauses = json.loads(path.read_text(encoding="utf-8"))
    for c in clauses:
        if c["clause_id"] == clause_id:
            for key, value in fields.items():
                if key == "evidence_ref":
                    c["response_skeleton"]["evidence_ref"] = value
                elif key == "quote":
                    c["source_ref"]["quote"] = value
                else:
                    c[key] = value
    path.write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _add_clause(state_dir, clause):
    """向状态目录追加一条条款(编号/孤儿节用例构造)。"""
    path = Path(state_dir) / "clauses.json"
    clauses = json.loads(path.read_text(encoding="utf-8"))
    clauses.append(clause)
    path.write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _set_structure_node(state_dir, node_id, **fields):
    """就地改写状态目录 structure.json 中某节点(表格形状/编号用例构造)。"""
    path = Path(state_dir) / "structure.json"
    structure = json.loads(path.read_text(encoding="utf-8"))
    for node in structure:
        if node["node_id"] == node_id:
            node.update(fields)
    path.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _lint_flagged_values(lint_text):
    """解析实体lint报告[待核对]表的提取值列(第 4 列)——钉住提取值本身。"""
    section = lint_text.split("## [待核对] 白名单外实体(疑似上一项目残留)", 1)[1]
    rows = [ln for ln in section.splitlines() if ln.startswith("|") and "---" not in ln and not ln.startswith("| 条款")]
    return [ln.split("|")[4].strip() for ln in rows]


class TestBuildOutputCliContract:
    def test_help_returns_0(self, capsys):
        assert _build_module().main(["--help"]) == 0
        capsys.readouterr()

    def test_usage_errors_exit_1(self, capsys):
        mod = _build_module()
        for argv in ([], ["--state-dir", "x"], ["--out", "y"], ["--unknown"]):
            rc = mod.main(argv)
            assert rc == 1, f"用法错误 {argv!r} 应返回 1(2 保留给 ingest OCR 分流), 实际 {rc}"
        capsys.readouterr()

    def test_missing_state_files_exit_1(self, tmp_path):
        state = tmp_path / "empty-state"
        state.mkdir()
        assert _run_build(state, tmp_path / "out") == 1, "阶段4 前提: clauses.json/structure.json 必须存在"

    def test_corrupt_state_json_exit_1(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        (state / "clauses.json").write_text("{not json", encoding="utf-8")
        assert _run_build(state, tmp_path / "out") == 1

    def test_state_dir_readonly_d7(self, tmp_path, capsys):
        """状态目录只读: build 不回写任何状态文件(fill_status 等派生字段现算不落盘)。"""
        state = _copy_prestate(tmp_path, merged=True)
        before = _snapshot(state)
        assert _run_build(state, tmp_path / "out") == 0
        assert _snapshot(state) == before, "状态目录字节级不变(D7)"
        summary = _last_summary_json(capsys)
        assert sorted(summary["written"]) == sorted(BUILD_OUTPUT_FILES)

    def test_six_outputs_no_tmp_residue(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        assert _run_build(state, out) == 0
        assert sorted(p.name for p in out.iterdir()) == sorted(BUILD_OUTPUT_FILES), "恰好六个输出, 无 .tmp 残留"

    def test_rerun_byte_identical(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        out = tmp_path / "out"
        assert _run_build(state, out) == 0
        first = _snapshot(out)
        assert _run_build(state, out) == 0
        assert _snapshot(out) == first, "渲染不含时间戳, 重跑字节级幂等"

    def test_summary_json_shape(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        assert _run_build(state, tmp_path / "out") == 0
        summary = _last_summary_json(capsys)
        assert summary["coverage"] == {"total": 3, "responded": 1, "pending": 2, "unassigned": 0, "superseded": 1, "voided": 0}
        assert summary["lint"]["flagged"] == 0 and summary["anomalies"] == []
        assert summary["deviation_rows"] == 1, "仅 ZB-C-001(mandatory)入偏离表"


class TestBuildOutputMirrorVolumes:
    """①镜像层级完整/槽位标注 ②条目标题嵌 clause_id(D2)/条目体五字段。"""

    def test_commercial_heading_tree_complete(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        lines = _out_text(tmp_path / "out", "商务卷.md").splitlines()
        for heading in ("# 投标文件格式", "## 一、投标函", "## 二、法定代表人身份证明", "## 三、开标一览表", "## 四、投标文件签章与份数"):
            assert heading in lines, f"商务卷镜像章节树缺 {heading!r}(path 标题链→# 层级, 只镜像不自创)"

    def test_technical_heading_tree_complete(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        lines = _out_text(tmp_path / "out", "技术卷.md").splitlines()
        for heading in ("# 技术部分", "## 1 技术方案", "## 2 技术参数响应表"):
            assert heading in lines, f"技术卷镜像缺 {heading!r}"

    def test_slot_annotations_present(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "商务卷.md")
        for label in ("槽位类型", "格式要求", "待填提示", "填写状态"):
            assert label in text, f"槽位标注缺 {label}"
        for label in ("文字槽", "表格槽", "图片槽", "格式核验槽"):
            assert label in text
        assert "按给定格式填报投标函并加盖投标人公章" in text, "格式要求=required_format.desc 原文"

    def test_technical_entry_titles_embed_clause_id(self, tmp_path):
        """D2 锚点契约: 条目标题嵌 clause_id(交付物保留不删); superseded 条款不出条目。"""
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        lines = _out_text(tmp_path / "out", "技术卷.md").splitlines()
        assert "### 2.1 响应[ZB-C-001]" in lines or "### **2.1 响应[ZB-C-001]**" in lines, "条目标题必须形如 'N.M 响应[<clause_id>]'"
        assert "### 1.1 响应[ZB-C-002]" in lines, "ZB-C-002 挂接 S-007('1 技术方案')→编号 1.1"
        joined = "\n".join(lines)
        assert "响应[ZB-C-003]" not in joined, "superseded 条款不产生条目(活条款才逐项响应)"

    def test_mandatory_entry_title_bold(self, tmp_path):
        """强制条款条目标题**加粗**(convert.py 不支持高亮, 加粗是唯一强调载体)。"""
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        lines = _out_text(tmp_path / "out", "技术卷.md").splitlines()
        assert any(ln.startswith("### **") and "响应[ZB-C-001]" in ln for ln in lines), "mandatory 条款 ZB-C-001 条目标题须加粗"
        assert "### 1.1 响应[ZB-C-002]" in lines, "非强制条款不加粗"

    def test_entry_body_five_fields(self, tmp_path):
        """条目体 = 要求原文锚点→响应要点→证据引用→满足状态→suggestion(不缺不漏)。"""
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "技术卷.md")
        for field in ("要求原文锚点", "响应要点", "证据引用", "满足状态", "suggestion"):
            assert field in text, f"条目体缺字段 {field}"
        assert "设备防护等级不低于IP65,控制器采用S7-1500系列" in text, "原文锚点=source_ref.quote 原文"
        assert "3.2.1" in text and "防护等级IP65" in text, "锚点定位(§section)与响应要点(points)入文"
        assert "compliant" in text, "满足状态用枚举原值(机器可核)"

    def test_image_slot_scan_list(self, tmp_path):
        """image 槽汇总扫描件清单(图片不经 md 链路插入, 终稿人工替换占位)。"""
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "商务卷.md")
        assert "扫描件清单" in text
        assert "S-003" in text and "加盖公章的身份证正反面扫描件" in text

    def test_table_slots_marked_replica(self, tmp_path):
        """管道表格无法表达合并单元格/列宽 → 表格槽标[待人工复刻]; 列头骨架仍渲染。"""
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        commercial = _out_text(tmp_path / "out", "商务卷.md")
        technical = _out_text(tmp_path / "out", "技术卷.md")
        assert "[待人工复刻]" in commercial and "[待人工复刻]" in technical
        assert "| 序号 | 货物名称 | 数量 | 总价(元) |" in commercial, "列头骨架照渲染"
        assert "| 序号 | 招标要求 | 响应情况 | 满足状态 |" in technical

    def test_dangling_linked_clause_anomaly(self, tmp_path, capsys):
        """linked_clause_ids 指向缺失条款 → 异常不静默(渲染标注 + 摘要 anomalies)。"""
        state = _copy_prestate(tmp_path, merged=True)
        structure = _state_json(state, "structure.json")
        structure[1]["linked_clause_ids"] = ["ZB-C-999"]  # S-002
        (state / "structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        assert _run_build(state, tmp_path / "out") == 3
        summary = _last_summary_json(capsys)
        assert "clause_fk_invalid" in _anomaly_kinds(summary)
        assert "ZB-C-999" in _out_text(tmp_path / "out", "商务卷.md"), "渲染处标注缺失, 不静默"


class TestBuildOutputDeviationTable:
    """③ 偏离表 = 仅 class=mandatory 或 response_status=deviation 的活条款。"""

    def test_baseline_only_mandatory_included(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "偏离表.md")
        assert "ZB-C-001" in text, "mandatory 条款必须入表(即使 compliant, 须声明零偏离)"
        assert "ZB-C-002" not in text, "scoring+draft 不入表"
        assert "BY-C-004" not in text, "normal+pending_confirm 不入表"
        assert "ZB-C-003" not in text, "superseded 历史条款不入表"

    def test_deviation_status_rows_included(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-002", response_status="deviation")
        _set_clause(state, "BY-C-004", response_status="deviation")
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "偏离表.md")
        for cid in ("ZB-C-001", "ZB-C-002", "BY-C-004"):
            assert cid in text, f"偏离项 {cid} 必须入表"


class TestBuildOutputCoverage:
    """④ 覆盖率报表: 清单总数/已响应/待确认/未分配(superseded/voided 除外)。"""

    def test_coverage_counts_baseline(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "覆盖率报表.md")
        assert "| 清单总数(活条款) | 3 |" in text, "活条款 3 条(ZB-C-003 superseded 除外)"
        assert "| 已响应(compliant+deviation) | 1 |" in text
        assert "| 待确认(draft+pending_confirm) | 2 |" in text
        assert "| 未分配(unassigned) | 0 |" in text

    def test_unassigned_bucket(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "BY-C-004", response_status="unassigned")
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "覆盖率报表.md")
        assert "| 未分配(unassigned) | 1 |" in text
        assert "| 待确认(draft+pending_confirm) | 1 |" in text


class TestBuildOutputEntityLint:
    """⑤ 实体 lint: 白名单 diff 全部 evidence_ref 与引用片段; 白名单外→[待核对]。"""

    def test_baseline_clean_with_disclaimer(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        assert _run_build(state, tmp_path / "out") == 0
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "LLM辅助" in text and "非确定性" in text, "报告必须标注白名单为 LLM 辅助抽取、非确定性"
        assert "未发现白名单外实体" in text

    def test_whitelisted_entity_passes(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", evidence_ref="东智装备制造有限公司出具的IP65防护检测报告")
        assert _run_build(state, tmp_path / "out") == 0
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "东智装备制造有限公司" in text, "白名单实体进命中统计"
        assert "未发现白名单外实体" in text

    def test_unknown_company_in_evidence_flagged(self, tmp_path, capsys):
        """负例: evidence_ref 引用白名单外公司(上一项目残留)→[待核对]+摘要异常。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", evidence_ref="恒力泵业股份有限公司样册(上项目遗留)")
        assert _run_build(state, tmp_path / "out") == 3
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "[待核对]" in text and "恒力泵业股份有限公司" in text
        summary = _last_summary_json(capsys)
        assert "entity_unverified" in _anomaly_kinds(summary) and summary["lint"]["flagged"] >= 1

    def test_quote_fragment_scanned(self, tmp_path, capsys):
        """引用片段(source_ref.quote)同样在 lint 范围内; 钉住提取值本身(审查修复:
        原断言只查子串, 候选值被前导散文污染时照样通过, 掩盖提取缺陷)。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-002", quote="技术方案先进性,参照华新重工股份有限公司业绩 15 优=12-15")
        assert _run_build(state, tmp_path / "out") == 3
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "[待核对]" in text
        # 白名单外残留嵌在中文散文中: 前导引介词"参照"从候选显示值中修剪
        assert _lint_flagged_values(text) == ["华新重工股份有限公司"]

    def test_whitelist_missing_anomaly(self, tmp_path, capsys):
        """白名单缺失 → 异常不静默, 按空集 diff(沿用 merge_addenda 语义)。"""
        state = _copy_prestate(tmp_path, merged=True)
        (state / "entities_whitelist.json").unlink()
        assert _run_build(state, tmp_path / "out") == 3
        summary = _last_summary_json(capsys)
        assert "whitelist_missing" in _anomaly_kinds(summary)
        assert "白名单缺失" in _out_text(tmp_path / "out", "实体lint报告.md")


class TestBuildOutputHumanChecklist:
    """⑥ format_check 项与[待人工复刻]表格槽全部进人核清单, 不进确定性判定。"""

    def test_format_check_items_all_listed(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "人核清单.md")
        assert "S-005" in text and "正本壹份副本肆份" in text, "签字/盖章/份数项必须人人可见"
        assert "投标文件格式/四、投标文件签章与份数" in text

    def test_replica_tables_listed(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _run_build(state, tmp_path / "out")
        text = _out_text(tmp_path / "out", "人核清单.md")
        assert "[待人工复刻]" in text
        for node_id in ("S-004", "S-008"):
            assert node_id in text, f"表格槽 {node_id} 必须入人核清单"


# ===========================================================================
# T6 审查修复回归(四项): F1 实体lint候选提取(贪婪前缀污染/相邻合并/归一化缺口)
#    + F2 table_spec 装载校验 + F3 技术卷条目编号去撞 + F4 口径统一(行数/单次计算/
#    渲染纯函数化/命中按出现次数)
# ===========================================================================


class TestBuildOutputLintExtraction:
    """F1(Important): 原 company 正则 r"\\w{2,30}(后缀)" 最左贪婪——中文无空格分隔,
    白名单公司嵌在连续语句中("见东智装备制造有限公司检测报告")必被吸成污染候选
    → 白名单内公司误判"疑似上一项目残留"+虚假退出码 3; 相邻两公司合并为单一候选;
    spec_version 无空格写法("S7-1500V2.3" vs 白名单"S7-1500 V2.3")同族归一化缺口。"""

    def test_whitelisted_company_embedded_in_prose_not_flagged(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", evidence_ref="见东智装备制造有限公司检测报告")
        assert _run_build(state, tmp_path / "out") == 0, "白名单公司嵌在中文语句中不得误报[待核对](曾因贪婪前缀吸'见'字成污染候选)"
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "未发现白名单外实体" in text
        assert "东智装备制造有限公司" in text, "白名单公司照常进命中统计"
        summary = _last_summary_json(capsys)
        assert summary["lint"]["flagged"] == 0 and summary["anomalies"] == []

    def test_adjacent_companies_flag_residue_value_not_merged(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", evidence_ref="由东智装备制造有限公司与恒力泵业股份有限公司联合出具")
        assert _run_build(state, tmp_path / "out") == 3
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "[待核对]" in text
        assert _lint_flagged_values(text) == ["恒力泵业股份有限公司"], "残留公司按自身取值入表(连接字'与'修剪), 不得与相邻白名单公司合并为单一候选"
        assert "| 东智装备制造有限公司 | company | 1 |" in text, "白名单公司照常进命中统计"

    def test_spec_version_no_space_form_not_flagged(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", evidence_ref="控制器固件S7-1500V2.3出厂检测")
        assert _run_build(state, tmp_path / "out") == 0, "无空格写法与白名单'S7-1500 V2.3'应归一化同值, 不得误报"
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "未发现白名单外实体" in text
        assert "| S7-1500 V2.3 | spec_version | 1 |" in text, "归一化命中计入出现次数"
        summary = _last_summary_json(capsys)
        assert summary["lint"]["flagged"] == 0

    def test_hit_counts_occurrences_not_fields(self, tmp_path):
        """F4④: 命中统计按出现次数(同一字段出现两次计 2), 非按含该值的字段数计 1。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", evidence_ref="东智装备制造有限公司与东智装备制造有限公司组成的联合体")
        assert _run_build(state, tmp_path / "out") == 0
        text = _out_text(tmp_path / "out", "实体lint报告.md")
        assert "| 东智装备制造有限公司 | company | 2 |" in text


class TestBuildOutputTableSpecValidation:
    """F2(Minor): table_spec 形状不进装载校验时——rows 为非数字字符串在渲染处以
    未捕获 ValueError 裸崩(退出码 1 契约失守, 非 BuildOutputError); columns 为字符串
    时按字符迭代静默渲染逐字列头。装载期校验: columns=非空标量数组, rows=缺省或
    int>=1(渲染双卷/人核清单统一按缺省 1)。"""

    def _with_s004_spec(self, tmp_path, spec):
        state = _copy_prestate(tmp_path, merged=True)
        _set_structure_node(state, "S-004", required_format={"desc": "按下列列头复刻开标一览表格式", "table_spec": spec})
        return state

    def test_rows_string_exit_1(self, tmp_path):
        state = self._with_s004_spec(tmp_path, {"columns": ["序号", "数量"], "rows": "3"})
        assert _run_build(state, tmp_path / "out") == 1, "rows 字符串必须以 BuildOutputError 干净退出(曾未捕获 ValueError 裸 traceback)"
        assert not (tmp_path / "out" / "商务卷.md").exists(), "失败路径不产出文件"

    def test_rows_null_exit_1(self, tmp_path):
        state = self._with_s004_spec(tmp_path, {"columns": ["序号"], "rows": None})
        assert _run_build(state, tmp_path / "out") == 1, "rows 显式 null 违反 int>=1 契约(曾渲染字面 None 单元格)"

    def test_columns_string_exit_1(self, tmp_path):
        state = self._with_s004_spec(tmp_path, {"columns": "序号数量", "rows": 3})
        assert _run_build(state, tmp_path / "out") == 1, "columns 字符串须拒绝(曾按字符迭代静默渲染逐字列头)"

    def test_columns_empty_exit_1(self, tmp_path):
        state = self._with_s004_spec(tmp_path, {"columns": [], "rows": 3})
        assert _run_build(state, tmp_path / "out") == 1

    def test_rows_missing_renders_default_1_consistently(self, tmp_path):
        """F4①: rows 缺省 → 商务卷骨架 1 行 + 人核清单行数列 1(两处口径一致, 不再渲染空/None)。"""
        state = self._with_s004_spec(tmp_path, {"columns": ["序号", "数量"]})
        assert _run_build(state, tmp_path / "out") == 0
        commercial = _out_text(tmp_path / "out", "商务卷.md")
        assert commercial.count("| (待填) | (待填) |") == 1, "缺省 rows=1, 骨架恰一行"
        checklist = _out_text(tmp_path / "out", "人核清单.md")
        assert "| 序号/数量 | 1 |" in checklist, "人核清单行数列与商务卷口径一致(1)"
        assert "None" not in checklist


class TestBuildOutputEntryNumbering:
    """F3(Minor): 条目编号 N.M 取槽位标题前导数字——两技术卷槽同前导数字(或均无数字
    走 node 计数回退)时产出重复"N.1 响应[...]"标题; 卷末孤儿节 max(nums)+1 也可能撞既有
    编号节。clause_id 锚点(D2)不受编号影响, 纯观感去重。"""

    def test_duplicate_leading_digits_get_disambiguated(self, tmp_path):
        state = _copy_prestate(tmp_path, merged=True)
        _set_structure_node(state, "S-007", path="技术部分/2 技术方案")  # 与 S-008 同前导数字 2
        _run_build(state, tmp_path / "out")
        lines = _out_text(tmp_path / "out", "技术卷.md").splitlines()
        assert "### 2.1 响应[ZB-C-002]" in lines, "首个认领前导数字 2 的槽保留 2"
        assert "### **3.1 响应[ZB-C-001]**" in lines, "撞号槽顺延取下一个未占用号 3"
        nums = [re.match(r"^### (?:\*\*)?(\d+\.\d+)", ln).group(1) for ln in lines if re.match(r"^### (?:\*\*)?\d+\.\d+ 响应\[", ln)]
        assert len(nums) == len(set(nums)) == 2, f"全卷条目编号不得重复: {nums}"

    def test_orphan_section_number_never_collides(self, tmp_path):
        """无数字槽走顺延号时, 卷末孤儿节号必须再顺延(旧算法 max(titled)+1 会与顺延号撞号)。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_structure_node(state, "S-008", path="技术部分/附表")  # 去前导数字 → 顺延取 2
        orphan_clause = {
            "clause_id": "JS-C-001",
            "source_file": "技术规范书.docx",
            "class": "normal",
            "category": "technical",
            "source_ref": {"page": None, "section": "3.2.2", "para": 1, "quote": "控制器冗余配置"},
            "requirement": "控制器冗余配置",
            "response_status": "unassigned",
            "response_skeleton": {"points": [], "evidence_ref": None, "suggestion": None},
            "from_addendum": False,
            "superseded_by": None,
            "voided": False,
        }
        _add_clause(state, orphan_clause)
        _run_build(state, tmp_path / "out")
        lines = _out_text(tmp_path / "out", "技术卷.md").splitlines()
        assert "### 1.1 响应[ZB-C-002]" in lines, "带号槽'1 技术方案'保留 1"
        assert "### **2.1 响应[ZB-C-001]**" in lines, "无数字槽顺延取 2(旧算法回退计数同为 2——孤儿节撞号根源)"
        assert "## 3 未挂接格式槽的技术条款(清单驱动)" in lines, "孤儿节继续顺延取 3(旧算法 max+1=2 与上面撞号)"
        assert "### 3.1 响应[JS-C-001]" in lines
        nums = [re.match(r"^### (?:\*\*)?(\d+\.\d+)", ln).group(1) for ln in lines if re.match(r"^### (?:\*\*)?\d+\.\d+ 响应\[", ln)]
        assert len(nums) == len(set(nums)) == 3, f"含孤儿节条目在内全卷编号不得重复: {nums}"


class TestBuildOutputRenderHygiene:
    """F4②③: render_volume_md 不再以出参方式变异共享 anomalies 列表(纯函数化);
    deviation_rows 同一数据只计算一次(渲染+摘要共用)。"""

    def test_render_volume_md_returns_anomalies_no_outparam(self):
        build = _build_module()
        import inspect

        params = inspect.signature(build.render_volume_md).parameters
        assert "anomalies" not in params, "渲染函数不得以出参方式变异共享列表(隐藏副作用)"
        fixtures = Path(__file__).parent / "fixtures" / "bid_proposal"
        structure = json.loads((fixtures / "structure.json").read_text(encoding="utf-8"))
        clauses = json.loads((fixtures / "clauses.json").read_text(encoding="utf-8"))
        md, anomalies = build.render_volume_md("commercial", structure, clauses)
        assert md.startswith("# 投标文件格式") and anomalies == [], "返回 (md, 本卷异常) 元组, 由调用方合并"

    def test_deviation_rows_computed_once_per_run(self, tmp_path, monkeypatch):
        build = _build_module()
        calls = []
        real = build.deviation_rows

        def counting(clauses):
            calls.append(1)
            return real(clauses)

        monkeypatch.setattr(build, "deviation_rows", counting)
        state = _copy_prestate(tmp_path, merged=True)
        assert build.main(["--state-dir", str(state), "--out", str(tmp_path / "out")]) == 0
        assert len(calls) == 1, "渲染与摘要共用同一份偏离行(曾对同一数据计算两次)"


# ===========================================================================
# T7 score_simulate: 阶段5 模拟评分闭环(重灌契约 D2/D6 + 客观汇总 + 报告 version++)
# 四子命令: reingest(--source 显式指定 D2) / assemble-evidence / aggregate / report。
# 重灌锚点契约(D2): 商务卷=structure.json 树路径标题链, 技术卷=条目标题 clause_id;
# 匹配器硬化(D6): ①多命中→异常区不取首个 ②归一化(去编号/空白/全半角)
# ③clause_id 重复出现→异常区 ④命中率低于阈值(默认 0.6)→整体降级人核覆盖率清单,
# 不做部分计分; 匹配失败→needs_human_verify 不计 0 不静默。
# 纪律: 无 LLM(主观项由 Agent 在上下文评, 脚本只组装证据包/消费评分);
# 重灌只更新权威态(clauses.json response_status), fill_status 现算不落盘(D7);
# 全部写盘临时文件+os.replace 原子化(D7); 报告 version++ 留痕不覆盖历史。
# 退出码: 0=干净完成(--help 亦 0) 1=用法/文件错误/Σ 不一致中止/降级拒绝计分 3=完成但有异常项
# ===========================================================================


def _score_module():
    """硬导入 score_simulate(T7 已落地; 模块缺失时测试失败而非 skip)。"""
    import importlib

    return importlib.import_module("score_simulate")


def _fixture_source_text() -> str:
    return (FIXTURE_DIR / "returned_word.md").read_text(encoding="utf-8")


def _drop_section(text: str, heading_prefix: str) -> str:
    """删除以 heading_prefix 开头的标题节(标题+正文, 到下一任意级标题为止)。"""
    out, skip = [], False
    for ln in text.splitlines():
        if ln.startswith("#"):
            skip = ln.startswith(heading_prefix)
        if not skip:
            out.append(ln)
    return "\n".join(out) + "\n"


def _clean_source_text() -> str:
    """全净源: 去掉重复 clause_id 节(2.3)与镜像外标题(售后服务承诺)——重灌零异常。"""
    text = _fixture_source_text()
    text = _drop_section(text, "### 2.3 响应[ZB-C-001]")
    return _drop_section(text, "## 3 售后服务承诺")


def _write_source(tmp_path, text: str, name: str = "returned.md"):
    path = Path(tmp_path) / name
    path.write_text(text, encoding="utf-8")
    return path


def _score_records(score=11, max_score=15, rubric_id="R-002", **over) -> dict:
    """Agent 主观评分 JSON(scoring_prompt.md 评审输出记录契约)。"""
    rec = {
        "rubric_id": rubric_id,
        "score": score,
        "max_score": max_score,
        "rationale": "对照评分办法分档, 架构先进性与工艺契合证据充分, 评良好偏上",
        "evidence_quote": "围绕总体架构先进性与工艺场景契合度展开",
        "missing_points": ["缺控制器冗余配置联动说明"],
        "improvement": "补一节控制器冗余与工艺联动的方案说明",
    }
    rec.update(over)
    return {"records": [rec]}


def _write_scores(tmp_path, payload, name: str = "scores.json"):
    path = Path(tmp_path) / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_reingest(state_dir, source, *, threshold=None):
    argv = ["reingest", "--source", str(source), "--state-dir", str(state_dir)]
    if threshold is not None:
        argv += ["--threshold", str(threshold)]
    return _score_module().main(argv)


def _reingest_result(state_dir):
    return _state_json(state_dir, "reingest_result.json")


def _aggregate_items(result):
    return {i["rubric_id"]: i for i in result["items"]}


SCORE_SUBCOMMANDS = ["reingest", "assemble-evidence", "aggregate", "report"]


class TestScoreSimulateCliContract:
    def test_help_each_subcommand_returns_0(self, capsys):
        mod = _score_module()
        for sub in SCORE_SUBCOMMANDS:
            assert mod.main([sub, "--help"]) == 0, f"{sub} --help 应返回 0"
        capsys.readouterr()

    def test_no_subcommand_exit_1(self, capsys):
        assert _score_module().main([]) == 1, "缺子命令=用法错误, 归退出码 1"
        capsys.readouterr()

    def test_reingest_source_required_d2(self, tmp_path, capsys):
        """D2: 重灌输入必须显式指定——防团队多版回传并存时'灌了旧版'状态漂移。"""
        state = _copy_prestate(tmp_path, merged=True)
        assert _score_module().main(["reingest", "--state-dir", str(state)]) == 1
        capsys.readouterr()

    def test_missing_source_file_exit_1(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        assert _run_reingest(state, tmp_path / "nope.md") == 1
        capsys.readouterr()

    def test_missing_state_files_exit_1(self, tmp_path, capsys):
        mod = _score_module()
        empty = tmp_path / "empty"
        empty.mkdir()
        source = _write_source(tmp_path, _fixture_source_text())
        scores = _write_scores(tmp_path, _score_records())
        assert mod.main(["reingest", "--source", str(source), "--state-dir", str(empty)]) == 1
        assert mod.main(["assemble-evidence", "--state-dir", str(empty)]) == 1
        assert mod.main(["aggregate", "--scores", str(scores), "--state-dir", str(empty)]) == 1
        assert mod.main(["report", "--state-dir", str(empty)]) == 1
        capsys.readouterr()

    def test_threshold_bounds_validated(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, _fixture_source_text())
        assert _run_reingest(state, source, threshold=0) == 1
        assert _run_reingest(state, source, threshold=1.5) == 1
        capsys.readouterr()


class TestReingestHeadingChain:
    """商务卷锚点=structure.json 树路径标题链(D2); 归一化匹配(D6②);
    fill 事实记录(group/text/image/table/format_check 分型)。"""

    def _run(self, tmp_path, capsys, text=None):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, text if text is not None else _fixture_source_text())
        rc = _run_reingest(state, source)
        return state, rc, _last_summary_json(capsys)

    def test_commercial_nodes_matched_by_chain(self, tmp_path, capsys):
        state, rc, summary = self._run(tmp_path, capsys)
        assert rc == 3, "fixture 含重复 clause_id+镜像外标题 → 有异常项归 3"
        nodes = {n["node_id"]: n for n in _reingest_result(state)["nodes"]}
        for node_id in ["S-001", "S-002", "S-003", "S-004", "S-005"]:
            assert nodes[node_id]["match"] == "matched", f"{node_id} 标题链应命中"
        assert nodes["S-001"]["fill"] == "not_applicable", "group=纯章节容器, 无填写语义"
        assert nodes["S-002"]["fill"] == "filled", "投标函槽有正文"
        assert nodes["S-003"]["fill"] == "needs_human_verify", "image 槽=扫描件人核, 不做确定性判定"
        assert nodes["S-004"]["fill"] == "needs_human_verify", "table 槽=合并单元格/列宽人工复刻核验"
        assert "表格" in nodes["S-004"]["fill_reason"], "表格槽 reason 应携带检测到的表格事实"
        assert nodes["S-005"]["fill"] == "needs_human_verify", "format_check 槽=签字/盖章/份数人核"

    def test_hit_rate_and_no_partial_state_leak(self, tmp_path, capsys):
        """锚点口径: 商务卷 5 槽 + 活技术条款 2 = 7; 命中 5+1(ZB-C-002)=6。"""
        state, rc, summary = self._run(tmp_path, capsys)
        assert summary["anchors"] == {"total": 7, "matched": 6, "needs_human_verify": 0, "multi_hit": 0, "duplicate_id": 1}
        assert abs(summary["hit_rate"] - 6 / 7) < 1e-6
        assert summary["degraded"] is False
        assert not any(p.name.startswith(".") for p in state.iterdir()), "无 .tmp 残留(原子写盘)"

    def test_state_authority_only_d7(self, tmp_path, capsys):
        """重灌只更新权威态: clauses.json 按 fill 事实改 response_status;
        structure.json/rubric.json 字节级不变(fill_status 现算不落盘, D7)。"""
        state, rc, summary = self._run(tmp_path, capsys)
        structure_before = (FIXTURE_DIR / "structure.json").read_bytes()
        assert (state / "structure.json").read_bytes() == structure_before, "structure.json 不可被重灌改写"
        assert (state / "rubric.json").read_bytes() == (FIXTURE_DIR / "rubric.json").read_bytes()
        clauses = _clauses_by_id(state)
        assert clauses["ZB-C-002"]["response_status"] == "compliant", "2.2 条目有正文 → 已响应"
        assert clauses["ZB-C-001"]["response_status"] == "compliant", "重复 id 条款不重灌, 权威态保持"
        assert summary["updated_clauses"] == 1

    def test_unmatched_doc_heading_to_anomaly(self, tmp_path, capsys):
        """镜像外标题(售后服务承诺)→ 异常区, 不静默(结构=只镜像不自创)。"""
        state, rc, summary = self._run(tmp_path, capsys)
        kinds = _anomaly_kinds(summary)
        assert "unmatched_heading" in kinds
        unmatched = [a for a in summary["anomalies"] if a["kind"] == "unmatched_heading"]
        assert any("售后服务承诺" in json.dumps(a, ensure_ascii=False) for a in unmatched)

    def test_node_anchor_missing_needs_human(self, tmp_path, capsys):
        """结构槽在回传稿缺失 → needs_human_verify(锚点侧失败, 不计 0 不静默)。"""
        text = _drop_section(_fixture_source_text(), "## 二、法定代表人身份证明")
        state, rc, summary = self._run(tmp_path, capsys, text)
        nodes = {n["node_id"]: n for n in _reingest_result(state)["nodes"]}
        assert nodes["S-003"]["match"] == "needs_human_verify"
        assert "node_anchor_unmatched" in _anomaly_kinds(summary)


class TestReingestClauseId:
    """技术卷锚点=条目标题内嵌 clause_id(D2; build_output 渲染时埋定)。"""

    def _run(self, tmp_path, capsys, text):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, text)
        rc = _run_reingest(state, source)
        return state, rc, _last_summary_json(capsys)

    def test_clause_entry_hit_and_status_update(self, tmp_path, capsys):
        state, rc, summary = self._run(tmp_path, capsys, _fixture_source_text())
        clauses = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert clauses["ZB-C-002"]["match"] == "matched"
        assert clauses["ZB-C-002"]["filled"] is True
        assert clauses["ZB-C-002"]["response_status_before"] == "draft"
        assert clauses["ZB-C-002"]["response_status_after"] == "compliant"
        assert _clauses_by_id(state)["ZB-C-002"]["response_status"] == "compliant"

    def test_empty_entry_reverts_to_unassigned(self, tmp_path, capsys):
        text = _fixture_source_text().replace('技术方案先进性:详见"1 技术方案"章节的架构说明与工艺契合分析。', "")
        state, rc, summary = self._run(tmp_path, capsys, text)
        clauses = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert clauses["ZB-C-002"]["filled"] is False
        assert clauses["ZB-C-002"]["response_status_after"] == "unassigned", "空条目=未填写"
        assert _clauses_by_id(state)["ZB-C-002"]["response_status"] == "unassigned"

    def test_match_failure_needs_human_not_zero(self, tmp_path, capsys):
        """条目缺失 → needs_human_verify: 权威态不动, 不计 0 分不静默(D6)。"""
        text = _drop_section(_fixture_source_text(), "### 2.2 响应[ZB-C-002]")
        state, rc, summary = self._run(tmp_path, capsys, text)
        clauses = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert clauses["ZB-C-002"]["match"] == "needs_human_verify"
        assert clauses["ZB-C-002"]["updated"] is False
        assert _clauses_by_id(state)["ZB-C-002"]["response_status"] == "draft", "权威态保持, 绝不静默灌 0"
        assert "clause_anchor_unmatched" in _anomaly_kinds(summary)

    def test_duplicate_clause_id_to_anomaly(self, tmp_path, capsys):
        """D6③: clause_id 重复出现(Word 修订模式重复文本)→ 异常区, 不重灌。"""
        state, rc, summary = self._run(tmp_path, capsys, _fixture_source_text())
        clauses = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert clauses["ZB-C-001"]["match"] == "duplicate_id"
        assert clauses["ZB-C-001"]["occurrences"] == 2
        assert clauses["ZB-C-001"]["updated"] is False
        dup = [a for a in summary["anomalies"] if a["kind"] == "duplicate_clause_id"]
        assert dup and dup[0]["clause_id"] == "ZB-C-001"

    def test_body_cross_reference_not_duplicate(self, tmp_path, capsys):
        """D6③ 计数口径=含 cid 的条目标题数(D2 锚点载体=条目标题内嵌 clause_id):
        条目正文合法交叉引用自身条款 id(如"满足ZB-C-001要求")不算重复, 不拦命中。"""
        text = _clean_source_text().replace(
            '技术方案先进性:详见"1 技术方案"章节的架构说明与工艺契合分析。',
            '技术方案先进性:详见"1 技术方案"章节的架构说明与工艺契合分析; 设备防护要求满足ZB-C-001条款。',
        )
        state, rc, summary = self._run(tmp_path, capsys, text)
        assert rc == 0, "正文交叉引用不产生异常"
        assert "duplicate_clause_id" not in _anomaly_kinds(summary)
        clauses = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert clauses["ZB-C-001"]["match"] == "matched", "标题唯一即命中, 正文出现走自洽路径"

    def test_registered_deviation_filled_entry_self_consistent(self, tmp_path, capsys):
        """已登记 deviation 且条目带偏离声明正文=自洽: 保留人裁不覆盖, 不制造异常噪音。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", response_status="deviation")
        source = _write_source(tmp_path, _clean_source_text())
        assert _run_reingest(state, source) == 0, "自洽偏离不应产生异常项"
        summary = _last_summary_json(capsys)
        assert "deviation_conflict" not in _anomaly_kinds(summary)
        assert _clauses_by_id(state)["ZB-C-001"]["response_status"] == "deviation", "人裁不被确定性重灌静默覆盖"
        records = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert records["ZB-C-001"]["response_status_after"] == "deviation" and records["ZB-C-001"]["updated"] is False

    def test_registered_deviation_empty_entry_conflict(self, tmp_path, capsys):
        """登记 deviation 但回传条目为空=偏离声明无处对账 → deviation_conflict 待人核。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_clause(state, "ZB-C-001", response_status="deviation")
        text = _clean_source_text().replace("设备防护等级 IP65,控制器采用西门子 S7-1500 系列(参数版本 V2.3),完全响应★强制条款。", "")
        source = _write_source(tmp_path, text)
        assert _run_reingest(state, source) == 3
        summary = _last_summary_json(capsys)
        assert "deviation_conflict" in _anomaly_kinds(summary)
        assert _clauses_by_id(state)["ZB-C-001"]["response_status"] == "deviation"


class TestReingestMatcherHardening:
    """D6 四类失败全显式: ①多命中 ②归一化 ③重复 id(上组) ④低命中率降级(下组)。"""

    def test_multi_hit_not_first_match(self, tmp_path, capsys):
        """D6①: 同一标题链多命中(目录与正文同名)→ 不取首个, 整项进异常区。"""
        text = _fixture_source_text()
        dup_section = "\n## 一、投标函\n\n(目录外的重复投标函节——多命中用例)\n"
        text = text.replace("## 二、法定代表人身份证明", dup_section.lstrip("\n") + "\n## 二、法定代表人身份证明")
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, text)
        assert _run_reingest(state, source) == 3
        summary = _last_summary_json(capsys)
        nodes = {n["node_id"]: n for n in _reingest_result(state)["nodes"]}
        assert nodes["S-002"]["match"] == "multi_hit", "不取首个——比匹配失败更危险的静默灌错必须拦截"
        assert summary["anchors"]["multi_hit"] == 1
        assert summary["anchors"]["matched"] == 5, "S-002 不计入命中"
        hit = [a for a in summary["anomalies"] if a["kind"] == "heading_multi_hit"]
        assert hit and hit[0]["node_id"] == "S-002"

    def test_normalization_d6_rule2(self):
        """D6②: 去编号/空白/全半角后等价——防 Word 自动编号/样式差异导致精确匹配雪崩。"""
        norm = _score_module().normalize_title
        assert norm("一、投标函") == norm("投标函")
        assert norm("1 技术方案") == norm("技术方案")
        assert norm("１技术方案") == norm("1 技术方案"), "全角数字归一"
        assert norm("２．１响应[ZB-C-001]") == norm("2.1 响应[ZB-C-001]"), "全角点号+空白归一"
        assert norm("第三章 技术规范") == norm("技术规范"), "章号前缀剥离"
        assert norm("投标文件格式") != norm("技术部分")

    def test_normalized_chain_match_survives_renumbering(self, tmp_path, capsys):
        """回传稿编号被 Word 重排(一、→ 1、)仍命中——归一化匹配的意义。"""
        text = _fixture_source_text().replace("## 一、投标函", "## 1、投标函").replace("## 二、法定代表人身份证明", "## 2、法定代表人身份证明")
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, text)
        assert _run_reingest(state, source) == 3
        nodes = {n["node_id"]: n for n in _reingest_result(state)["nodes"]}
        assert nodes["S-002"]["match"] == "matched"
        assert nodes["S-003"]["match"] == "matched"

    def test_low_hit_rate_degrades_whole_reingest(self, tmp_path, capsys):
        """D6④: 命中率低于阈值 → 整体降级人核覆盖率清单, 不灌半套状态。"""
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, "# 投标文件格式\n\n## 一、投标函\n\n仅两锚点命中, 其余全缺失。\n")
        rc = _run_reingest(state, source)
        assert rc == 3
        summary = _last_summary_json(capsys)
        assert summary["degraded"] is True
        assert summary["anchors"]["matched"] == 2 and summary["anchors"]["total"] == 7
        assert summary["hit_rate"] < 0.6
        assert "reingest_degraded" in _anomaly_kinds(summary)
        assert (state / "clauses.json").read_bytes() == (FIXTURE_DIR / "clauses.json").read_bytes(), "降级=不灌半套状态, clauses.json 原样"

    def test_threshold_flag_configurable(self, tmp_path, capsys):
        """--threshold 可调: 6/7≈0.857 在默认 0.6 不降级, 提到 0.9 即降级。"""
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, _fixture_source_text())
        assert _run_reingest(state, source, threshold=0.9) == 3
        assert _last_summary_json(capsys)["degraded"] is True

    def test_fk_validation_d7(self, tmp_path, capsys):
        """D7 第一防线: 重灌装载三件套时校验 linked_clause_ids 存在且未 superseded。"""
        state = _copy_prestate(tmp_path, merged=True)
        _set_structure_node(state, "S-002", linked_clause_ids=["ZB-C-999"])
        source = _write_source(tmp_path, _clean_source_text())
        assert _run_reingest(state, source) == 3
        summary = _last_summary_json(capsys)
        dangling = [a for a in summary["anomalies"] if a["kind"] == "dangling_fk"]
        assert dangling and "ZB-C-999" in json.dumps(dangling[0], ensure_ascii=False)

    def test_bom_source_first_heading_matches(self, tmp_path, capsys):
        """回传 md 带 UTF-8 BOM 时首标题仍应匹配(回传稿读取用 utf-8-sig 免疫)。"""
        state = _copy_prestate(tmp_path, merged=True)
        path = tmp_path / "returned.md"
        path.write_bytes(b"\xef\xbb\xbf" + _clean_source_text().encode("utf-8"))
        assert _run_reingest(state, path) == 0, "BOM 不应导致首标题失配"
        summary = _last_summary_json(capsys)
        assert "node_anchor_unmatched" not in _anomaly_kinds(summary)

    def test_wide_clause_id_heading_exempt_from_mirror_check(self, tmp_path, capsys):
        """CLAUSE_ID_RE 与 schema/merge_addenda 对齐(^[A-Z]{2,4}-C-\\d{1,6}$): 3-4 位文件
        代号/非 3 位序号的合法 id 条目标题归技术卷锚点管辖, 不误报 unmatched_heading。"""
        state = _copy_prestate(tmp_path, merged=True)
        _add_clause(state, {"clause_id": "ABCD-C-12", "source_file": "技术规范书.docx", "class": "normal", "category": "technical", "requirement": "宽口径 id 用例", "response_status": "draft", "superseded_by": None, "voided": False})
        text = _clean_source_text() + "\n## 4 响应[ABCD-C-12]\n\n防护与联动要求已逐项响应。\n"
        source = _write_source(tmp_path, text)
        assert _run_reingest(state, source) == 0, "宽口径合法 id 不产生镜像外噪音"
        summary = _last_summary_json(capsys)
        assert "unmatched_heading" not in _anomaly_kinds(summary)
        records = {c["clause_id"]: c for c in _reingest_result(state)["clauses"]}
        assert records["ABCD-C-12"]["match"] == "matched"
        assert _clauses_by_id(state)["ABCD-C-12"]["response_status"] == "compliant"

    def test_reingest_idempotent(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, _clean_source_text())
        assert _run_reingest(state, source) == 0, "全净源零异常"
        snap = {name: (state / name).read_bytes() for name in ("clauses.json", "structure.json", "rubric.json")}
        assert _run_reingest(state, source) == 0
        assert {name: (state / name).read_bytes() for name in snap} == snap, "同源重灌权威态幂等(字节级不变; reingest_result.json 记录本趟事实, 不属权威态)"


class TestAssembleEvidence:
    """assemble-evidence: 逐 rubric 项组装确定性证据包(grep 证据行), 供 Agent 主观评审。"""

    def test_pack_shape_and_evidence_lines(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, _fixture_source_text())
        _run_reingest(state, source)
        capsys.readouterr()
        assert _score_module().main(["assemble-evidence", "--state-dir", str(state)]) == 0
        summary = _last_summary_json(capsys)
        assert summary["written"] == "evidence_pack.json"
        pack = _state_json(state, "evidence_pack.json")
        bundles = {b["rubric_id"]: b for b in pack["items"]}
        assert set(bundles) == {"R-001", "R-002", "R-003"}, "全量 rubric 项, 不缺不漏"
        r2 = bundles["R-002"]
        assert r2["score_type"] == "subjective" and r2["scoring_method"].startswith("优=")
        assert r2["linked_clauses"][0]["clause_id"] == "ZB-C-002"
        assert any("ZB-C-002" in ln["text"] for ln in r2["evidence_lines"]), "证据行应含 clause_id 检索命中"
        assert r2["evidence_lines"], "技术方案正文行(总体架构先进性)应被 grep 命中"

    def test_price_item_marked_not_scorable(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, _clean_source_text())
        _run_reingest(state, source)
        capsys.readouterr()
        assert _score_module().main(["assemble-evidence", "--state-dir", str(state)]) == 0
        capsys.readouterr()
        pack = _state_json(state, "evidence_pack.json")
        r1 = {b["rubric_id"]: b for b in pack["items"]}["R-001"]
        assert "无法模拟" in r1["note"]

    def test_session_state_without_reingest(self, tmp_path, capsys):
        """会话内填写态(未重灌)也能组装: 证据行为空, 如实标注。"""
        state = _copy_prestate(tmp_path, merged=True)
        assert _score_module().main(["assemble-evidence", "--state-dir", str(state)]) == 0
        pack = _state_json(state, "evidence_pack.json")
        assert all(b["evidence_lines"] == [] for b in pack["items"])

    def test_degraded_refuses(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, "# 投标文件格式\n\n## 一、投标函\n\n仅两锚点。\n")
        _run_reingest(state, source)
        capsys.readouterr()
        assert _score_module().main(["assemble-evidence", "--state-dir", str(state)]) == 1, "降级模式不做评审循环"
        capsys.readouterr()


class TestAggregateSumCheck:
    """aggregate 第一步: rubric Σmax_score 纵深复检——不一致异常中止(extract 已前置拦截)。"""

    def test_bad_sum_aborts_no_output(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        (state / "rubric.json").write_text((FIXTURE_DIR / "rubric_bad_sum.json").read_text(encoding="utf-8"), encoding="utf-8")
        scores = _write_scores(tmp_path, _score_records())
        rc = _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)])
        assert rc == 1, "Σ 不一致=异常中止, 非完成带异常"
        err = capsys.readouterr().err
        assert "Σ" in err and "97" in err and "100" in err
        assert not (state / "aggregate_result.json").exists(), "中止=不落任何汇总产物"

    def test_non_int_max_score_rejected(self, tmp_path, capsys):
        """max_score 非 number(bool/str)会让 Σ 失真——装载即拒绝(bool 误按 0/1 计)。"""
        state = _copy_prestate(tmp_path, merged=True)
        rubric = _state_json(state, "rubric.json")
        rubric["items"][1]["max_score"] = True
        (state / "rubric.json").write_text(json.dumps(rubric, ensure_ascii=False), encoding="utf-8")
        scores = _write_scores(tmp_path, _score_records())
        assert _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)]) == 1
        capsys.readouterr()

    def test_decimal_max_score_accepted(self, tmp_path, capsys):
        """max_score 契约=rubric.schema.json 的 number: 合法小数满分不应让 aggregate 退出 1。"""
        state = _copy_prestate(tmp_path, merged=True)
        rubric = _state_json(state, "rubric.json")
        rubric["total_score"] = 100.5
        rubric["items"][1]["max_score"] = 15.5
        (state / "rubric.json").write_text(json.dumps(rubric, ensure_ascii=False), encoding="utf-8")
        scores = _write_scores(tmp_path, _score_records(score=11, max_score=15.5))
        assert _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)]) == 0
        result = _state_json(state, "aggregate_result.json")
        assert result["totals"] == {"full": 100.5, "simulatable_max": 40.5, "simulated": 36.0}
        capsys.readouterr()


class TestAggregateObjectiveMath:
    """objective 项确定性汇总: 按重灌后条款状态, 已响应占比折算(不解析分档算术)。"""

    def _aggregate(self, tmp_path, capsys, *, source_text=None, records=None, rubric_edit=None, clause_edit=None):
        state = _copy_prestate(tmp_path, merged=True)
        if rubric_edit:
            rubric_edit(state)
        if clause_edit:
            clause_edit(state)
        if source_text is not None:
            source = _write_source(tmp_path, source_text)
            _run_reingest(state, source)
            capsys.readouterr()
        payload = records if records is not None else _score_records()
        scores = _write_scores(tmp_path, payload)
        rc = _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)])
        result = _state_json(state, "aggregate_result.json")
        return state, rc, result, _last_summary_json(capsys)

    def test_full_satisfaction_after_clean_reingest(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, source_text=_clean_source_text())
        assert rc == 0
        items = _aggregate_items(result)
        assert items["R-003"]["score"] == 25 and items["R-003"]["status"] == "scored"
        assert items["R-003"]["clause_states"][0]["clause_id"] == "ZB-C-001"
        assert result["totals"] == {"full": 100, "simulatable_max": 40, "simulated": 36.0}, "15+25=36, price 60 不入可模拟口径"

    def test_session_state_mode_without_reingest(self, tmp_path, capsys):
        """会话内填写态: 无重灌产物时直接按 clauses.json 现状汇总。"""
        state, rc, result, summary = self._aggregate(tmp_path, capsys)
        assert _aggregate_items(result)["R-003"]["score"] == 25, "ZB-C-001=compliant → 1/1"

    def test_proportional_math_partial(self, tmp_path, capsys):
        def rubric_edit(state):
            rubric = _state_json(state, "rubric.json")
            rubric["items"][2]["linked_clause_ids"] = ["ZB-C-001", "ZB-C-002"]
            (state / "rubric.json").write_text(json.dumps(rubric, ensure_ascii=False), encoding="utf-8")

        state, rc, result, summary = self._aggregate(tmp_path, capsys, rubric_edit=rubric_edit)
        item = _aggregate_items(result)["R-003"]
        assert item["score"] == 12.5, "compliant 1 / total 2 → 25×0.5"
        assert {c["clause_id"]: c["state"] for c in item["clause_states"]}["ZB-C-002"] == "draft"

    def test_deviation_scores_zero(self, tmp_path, capsys):
        def clause_edit(state):
            _set_clause(state, "ZB-C-001", response_status="deviation")

        state, rc, result, summary = self._aggregate(tmp_path, capsys, clause_edit=clause_edit)
        assert _aggregate_items(result)["R-003"]["score"] == 0.0

    def test_unverified_clause_needs_human_not_zero(self, tmp_path, capsys):
        """fixture 重灌(ZB-C-001 重复 id)→ R-003 needs_human: score=None 不计 0(D6)。"""
        state, rc, result, summary = self._aggregate(tmp_path, capsys, source_text=_fixture_source_text())
        assert rc == 3, "存在未核条款 → 异常项"
        item = _aggregate_items(result)["R-003"]
        assert item["score"] is None and item["status"] == "needs_human"
        kinds = _anomaly_kinds(summary)
        assert "objective_unverified_clause" in kinds
        assert result["totals"]["simulated"] == 11.0, "仅 R-002 入账, needs_human 不按 0 计"

    def test_objective_without_linkage_anomaly(self, tmp_path, capsys):
        def rubric_edit(state):
            rubric = _state_json(state, "rubric.json")
            rubric["items"][2]["linked_clause_ids"] = []
            (state / "rubric.json").write_text(json.dumps(rubric, ensure_ascii=False), encoding="utf-8")

        state, rc, result, summary = self._aggregate(tmp_path, capsys, rubric_edit=rubric_edit)
        assert rc == 3
        item = _aggregate_items(result)["R-003"]
        assert item["score"] is None
        assert "objective_no_linkage" in _anomaly_kinds(summary)

    def test_fk_check_symmetric_without_reingest_d7(self, tmp_path, capsys):
        """D7 防线对称: 会话内填写态(无 reingest 产物)下 rubric 链接 superseded 条款同样
        dangling_fk 异常, 不再只以'历史(不计)'披露剔出分母(reingest 路径同款拦截)。"""

        def rubric_edit(state):
            rubric = _state_json(state, "rubric.json")
            rubric["items"][2]["linked_clause_ids"] = ["ZB-C-003"]  # ZB-C-003 已被 BY-C-004 supersede
            (state / "rubric.json").write_text(json.dumps(rubric, ensure_ascii=False), encoding="utf-8")

        state, rc, result, summary = self._aggregate(tmp_path, capsys, rubric_edit=rubric_edit)
        assert rc == 3
        dangling = [a for a in summary["anomalies"] if a["kind"] == "dangling_fk"]
        assert dangling and any("ZB-C-003" in json.dumps(a, ensure_ascii=False) for a in dangling)
        item = _aggregate_items(result)["R-003"]
        assert item["score"] is None and item["status"] == "needs_human"

    def test_degraded_reingest_refuses_aggregation(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        source = _write_source(tmp_path, "# 投标文件格式\n\n## 一、投标函\n\n仅两锚点。\n")
        _run_reingest(state, source)
        capsys.readouterr()
        scores = _write_scores(tmp_path, _score_records())
        rc = _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)])
        assert rc == 1, "降级模式拒绝计分(不做部分计分, D6④)"
        assert not (state / "aggregate_result.json").exists()
        capsys.readouterr()


class TestAggregateSubjectiveRecords:
    """subjective 项消费 Agent 评分 JSON(scoring_prompt.md 契约); 违规记录逐类拦截。"""

    def _aggregate(self, tmp_path, capsys, payload, *, source_text=None):
        state = _copy_prestate(tmp_path, merged=True)
        if source_text is not None:
            _run_reingest(state, _write_source(tmp_path, source_text))
            capsys.readouterr()
        scores = _write_scores(tmp_path, payload)
        rc = _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)])
        return state, rc, _state_json(state, "aggregate_result.json"), _last_summary_json(capsys)

    def test_happy_subjective_consumed(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, _score_records(), source_text=_clean_source_text())
        assert rc == 0
        item = _aggregate_items(result)["R-002"]
        assert item["score"] == 11 and item["status"] == "scored"
        assert item["score_type"] == "subjective" and item["rationale"].startswith("对照评分办法分档")
        assert item["missing_points"] == ["缺控制器冗余配置联动说明"]

    def test_price_marked_unsimulatable(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, _score_records())
        item = _aggregate_items(result)["R-001"]
        assert item["score"] is None and item["status"] == "price_unsimulatable"
        assert "无法模拟" in item["rationale"]
        assert result["totals"]["simulatable_max"] == 40, "price 60 分不入可模拟口径"

    def test_over_max_score_excluded(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, _score_records(score=20))
        assert rc == 3
        item = _aggregate_items(result)["R-002"]
        assert item["score"] is None and item["status"] == "review_invalid"
        assert "score_out_of_range" in _anomaly_kinds(summary)

    def test_nan_score_excluded(self, tmp_path, capsys):
        """NaN 对一切比较为 False 会逃过越界检查, 污染 totals 并落非法 JSON(NaN 非严格
        JSON 值)——isfinite 拦截: 排除待人核, 不计 0 不带病计入。"""
        state, rc, result, summary = self._aggregate(tmp_path, capsys, _score_records(score=float("nan")))
        assert rc == 3
        assert "score_out_of_range" in _anomaly_kinds(summary)
        item = _aggregate_items(result)["R-002"]
        assert item["score"] is None and item["status"] == "review_invalid"
        assert math.isfinite(result["totals"]["simulated"]), "totals 不得被 NaN 污染"

    def test_unknown_rubric_id_flagged(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, _score_records(rubric_id="R-999"))
        assert rc == 3
        assert "unknown_rubric_id" in _anomaly_kinds(summary)

    def test_record_for_non_subjective_rejected(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, _score_records(rubric_id="R-003", max_score=25, score=10))
        assert "record_not_subjective" in _anomaly_kinds(summary)
        assert _aggregate_items(result)["R-003"]["status"] == "scored", "objective 由确定性汇总出分, 不吃 Agent 记录"

    def test_missing_subjective_review_anomaly(self, tmp_path, capsys):
        state, rc, result, summary = self._aggregate(tmp_path, capsys, {"records": []})
        assert rc == 3
        item = _aggregate_items(result)["R-002"]
        assert item["score"] is None and item["status"] == "missing_review"
        assert "subjective_missing_review" in _anomaly_kinds(summary)

    def test_duplicate_records_excluded(self, tmp_path, capsys):
        rec = _score_records()
        payload = {"records": [rec["records"][0], dict(rec["records"][0])]}
        state, rc, result, summary = self._aggregate(tmp_path, capsys, payload)
        assert "duplicate_record" in _anomaly_kinds(summary)
        assert _aggregate_items(result)["R-002"]["score"] is None, "重复记录不可信, 排除待人核"

    def test_malformed_scores_file_exit_1(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        scores = tmp_path / "bad.json"
        scores.write_text("{not json", encoding="utf-8")
        assert _score_module().main(["aggregate", "--scores", str(scores), "--state-dir", str(state)]) == 1
        capsys.readouterr()

    def test_missing_scores_file_exit_1(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        assert _score_module().main(["aggregate", "--scores", str(tmp_path / "nope.json"), "--state-dir", str(state)]) == 1
        capsys.readouterr()


class TestReport:
    """report: 逐项得分/满分/理由/失分原因 + 改进建议(失分值×可改性排序) +
    主观分标'模拟参考值' + 异常区 + version++ 留痕不覆盖历史。"""

    def _full_flow(self, tmp_path, capsys, *, source_text=None, records=None):
        state = _copy_prestate(tmp_path, merged=True)
        if source_text is not None:
            _run_reingest(state, _write_source(tmp_path, source_text))
            capsys.readouterr()
        payload = records if records is not None else _score_records()
        _score_module().main(["aggregate", "--scores", str(_write_scores(tmp_path, payload)), "--state-dir", str(state)])
        capsys.readouterr()
        rc = _score_module().main(["report", "--state-dir", str(state)])
        return state, rc, _last_summary_json(capsys)

    def test_version_increments_no_overwrite(self, tmp_path, capsys):
        state, rc, summary = self._full_flow(tmp_path, capsys)
        report_dir = state / "评分报告"
        assert summary["version"] == 1
        assert (report_dir / "version_1.md").is_file()
        capsys.readouterr()
        assert _score_module().main(["report", "--state-dir", str(state)]) == 0
        summary2 = _last_summary_json(capsys)
        assert summary2["version"] == 2, "version++ 留痕"
        assert (report_dir / "version_1.md").is_file() and (report_dir / "version_2.md").is_file(), "历史不覆盖(二期校准闭环消费)"

    def test_report_content_sections(self, tmp_path, capsys):
        """fixture 流(重复 id+镜像外标题): 全要素渲染。"""
        state, rc, summary = self._full_flow(tmp_path, capsys, source_text=_fixture_source_text())
        text = (state / "评分报告" / "version_1.md").read_text(encoding="utf-8")
        assert "模拟参考值" in text, "主观分一律标注"
        assert "无法模拟" in text, "price 项如实标注"
        assert "11 / 15" in text and "R-002" in text
        assert "缺控制器冗余配置联动说明" in text, "失分原因(主观记录 missing_points)"
        assert "补一节控制器冗余" in text, "改进建议(主观记录 improvement)"
        assert "异常区" in text
        assert "ZB-C-001" in text and "2 个条目标题" in text, "重复 clause_id(按含 cid 的条目标题数计, D2 锚点载体)入异常区"
        assert "售后服务承诺" in text, "镜像外标题入异常区"
        assert "needs_human" in text or "人核" in text, "R-003 未核条款进异常区"

    def test_improvement_list_sorted_by_loss_times_modifiability(self, tmp_path, capsys):
        """排序: R-003(失分25×可改性0.5=12.5) 先于 R-002(失分4×1.0=4.0)。"""
        state, rc, summary = self._full_flow(tmp_path, capsys, source_text=_fixture_source_text())
        text = (state / "评分报告" / "version_1.md").read_text(encoding="utf-8")
        section = text.split("改进建议", 1)[1]
        rows = [ln for ln in section.splitlines() if ln.startswith("|") and "---" not in ln and "rubric_id" not in ln]
        order = [ln.split("|")[2].strip() for ln in rows]
        assert order == ["R-003", "R-002"], f"按 失分值×可改性 降序: {order}"

    def test_clean_flow_full_marks_no_improvement(self, tmp_path, capsys):
        state, rc, summary = self._full_flow(tmp_path, capsys, source_text=_clean_source_text())
        text = (state / "评分报告" / "version_1.md").read_text(encoding="utf-8")
        assert "36.0" in text or "36" in text, "可模拟口径 36/40"
        section = text.split("改进建议", 1)[1].split("异常区", 1)[0] if "改进建议" in text else ""
        rows = [ln for ln in section.splitlines() if ln.startswith("|") and "---" not in ln and "rubric_id" not in ln]
        assert len(rows) == 1, "仅 R-002 失 4 分一条建议(R-003 满分, R-001 price 不入建议)"

    def test_degraded_report_is_coverage_checklist(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        _run_reingest(state, _write_source(tmp_path, "# 投标文件格式\n\n## 一、投标函\n\n仅两锚点。\n"))
        capsys.readouterr()
        rc = _score_module().main(["report", "--state-dir", str(state)])
        assert rc == 0, "降级模式 report 产出覆盖率清单(非计分报告)"
        _last_summary_json(capsys)
        text = (state / "评分报告" / "version_1.md").read_text(encoding="utf-8")
        assert "人核覆盖率清单" in text and "降级" in text
        assert "S-003" in text and "ZB-C-001" in text, "清单逐锚点列出待人核项"

    def test_report_requires_aggregate_unless_degraded(self, tmp_path, capsys):
        state = _copy_prestate(tmp_path, merged=True)
        assert _score_module().main(["report", "--state-dir", str(state)]) == 1, "未汇总先 report=文件错误"
        capsys.readouterr()


# ===========================================================================
# T8: SKILL.md — Agent 编排总纲(frontmatter 对齐先例 + 内容要件 + 命令-CLI 一致性)
# ===========================================================================

SKILL_MD_PATH = REPO_ROOT / "skills" / "public" / "bid-proposal-writing" / "SKILL.md"

# SKILL.md 里允许调用的本技能脚本(五管线脚本; markdown-to-docx 的 convert.py 属其他技能不校验)
_SKILL_SCRIPT_RE = re.compile(r"bid-proposal-writing/scripts/([a-z_]+)\.py")

# 内容要件: 铁律1-7 / 六阶段+两门 / 门1 计数与异常项 / 门2 补遗diff+终稿复核 /
# 阶段5 双形态+重灌硬化 / 上下文纪律 / 沙箱路径(任务 T8 内容①-⑥逐条落)
SKILL_MD_REQUIRED_TOKENS = (
    # ① 铁律 1-7(原文照录, 每条取一个不可省略的标识短语)
    "唯一来源",  # 铁律1: 条款数据唯一来源=clauses.json
    "改分类必须改文件",  # 铁律1
    "先跑通 ingest/extract 才允许谈清单",  # 铁律2
    "整篇方案生成器",  # 铁律3
    "只镜像不自创",  # 铁律3
    "每卷单次成文",  # 铁律4
    "偏轨停下",  # 铁律5 耗时自检
    "project_snapshot.json",  # 铁律6 多轮承接锚点
    "评分纪律",  # 铁律7
    "不为留印象给分",  # 铁律7
    # ② 六阶段编排 + 两道确认门
    "阶段0",
    "阶段1",
    "阶段2",
    "阶段3",
    "阶段4",
    "阶段5",
    "确认门1",
    "确认门2",
    # ③ 门1: 计数(N1/N2/N3) + 异常项 + 完整清单落盘 + clause_id 改分类回写 + 实体白名单锁定
    "N1",
    "N2",
    "N3",
    "判空",  # 未裁决 chunk/table 显式判空
    "总分不符",  # rubric Σmax_score 与评分办法总分不符
    "clause_id 改分类",
    "实体白名单",
    # ③ 门2: 补遗 diff 表(新增/被替代/作废) + 新实体确认 + 终稿复核清单 + format_check 人工签字
    "新增/被替代/作废",
    "新实体确认",
    "终稿复核",
    "人工签字",
    # ④ 阶段5 双形态: 会话内填写态 / 回传 Word 先转换再 reingest --source
    "会话内填写态",
    "回传",
    "--source",
    "needs_human_verify",
    "多命中",  # D6 匹配器硬化
    "归一化",  # D6
    "version",  # 报告 version++ 留痕
    # ⑤ 上下文纪律
    "行区间",
    "task()",
    "3 并发",
    # ⑥ 沙箱路径 + 编排配套(references/转换链路/OCR 受限支持)
    "/mnt/skills/public/bid-proposal-writing/scripts/",
    "/mnt/skills/public/bid-proposal-writing/references/",
    "extraction_prompt.md",
    "scoring_prompt.md",
    "classification.md",
    "markdown-to-docx",  # 阶段4 双卷 Word 走 convert.py 链路
    "eai-flow-ocr",  # 阶段0 扫描件分流(V1 受限支持)
)


def _skill_md_text() -> str:
    """读取 SKILL.md; 文件缺失直接失败(T8 交付物必须存在, 不 skip)。"""
    assert SKILL_MD_PATH.is_file(), f"SKILL.md 缺失: {SKILL_MD_PATH}(任务 T8 交付物)"
    return SKILL_MD_PATH.read_text(encoding="utf-8")


def _skill_md_script_invocations(text: str) -> list[tuple[str, list[str]]]:
    """提取 ```bash 代码块中五脚本调用 → [(模块名, argv), ...]。

    处理反斜杠续行; 只认 bid-proposal-writing/scripts/<name>.py 形态的调用
    (grep/read_file 等编排指令、markdown-to-docx 的 convert.py 不在提取范围)。
    """
    invocations: list[tuple[str, list[str]]] = []
    for block in re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.DOTALL):
        joined = block.replace("\\\n", " ")  # 反斜杠续行合并为单行(\<LF> → 空格)
        for line in joined.splitlines():
            line = line.strip()
            match = _SKILL_SCRIPT_RE.search(line)
            if not match or not line.startswith("python"):
                continue
            tokens = line.split()
            script_index = next(i for i, tok in enumerate(tokens) if tok.endswith(f"{match.group(1)}.py"))
            invocations.append((match.group(1), tokens[script_index + 1 :]))
    return invocations


class TestSkillMd:
    """T8: SKILL.md 编排总纲——frontmatter/内容要件/命令与实际 CLI 逐个对照。"""

    def test_frontmatter_aligns_with_precedent(self):
        """frontmatter(name/description)对齐 markdown-to-docx 先例格式。"""
        text = _skill_md_text()
        assert text.startswith("---\n"), "SKILL.md 必须以 YAML frontmatter 开头(先例: markdown-to-docx/SKILL.md)"
        end = text.index("\n---", 3)
        frontmatter = text[3:end]
        assert re.search(r"^name:\s*bid-proposal-writing\s*$", frontmatter, re.MULTILINE), "frontmatter 必须声明 name: bid-proposal-writing"
        description = re.search(r"^description:\s*(\S.*)$", frontmatter, re.MULTILINE)
        assert description, "frontmatter 必须声明非空 description(触发词说明)"
        assert len(description.group(1)) >= 30, "description 应为完整触发说明(先例风格), 不是短语"

    def test_required_content_tokens(self):
        """内容要件逐条在册(任务 T8 ①-⑥ 对应设计文档详细设计节)。"""
        content = _skill_md_text()
        missing = [token for token in SKILL_MD_REQUIRED_TOKENS if token not in content]
        assert not missing, f"SKILL.md 缺少内容要件: {missing}"

    def test_script_invocations_use_sandbox_path(self):
        """所有五脚本调用必须走沙箱路径 /mnt/skills/public/...(同 markdown-to-docx 先例)。"""
        content = _skill_md_text()
        assert _skill_md_script_invocations(content), "SKILL.md 必须包含五脚本的实际调用命令(不能只描述不示例)"
        for line in re.findall(r"^.*bid-proposal-writing/scripts/[a-z_]+\.py.*$", content, re.MULTILINE):
            assert line.lstrip().startswith("python /mnt/skills/public/bid-proposal-writing/scripts/"), f"脚本调用必须用沙箱绝对路径: {line.strip()}"

    def _capture_documented_namespaces(self, monkeypatch):
        """对 SKILL.md 全部脚本命令跑 main(), 完整 argparse 解析后哨兵截停, 返回 [(module_name, argv, namespace)]。

        机制: monkeypatch argparse.ArgumentParser.parse_args——结构校验(子命令/必填/
        枚举/type 转换)在原 parse_args 内完成后抛哨兵异常, 证明 argparse 原样接受文档命令;
        参数不合法时脚本 main() 捕获 SystemExit 返回 1, 下方 pytest.raises 不命中即失败。
        注意: 值域校验(如 ingest --code 的 _CODE_RE)发生在 parse_args 之后, 不被此机制
        拦截——由 test_documented_argument_values_pass_script_value_domain_checks 复检。
        """
        import argparse
        import importlib

        class _ParseCaptured(Exception):
            def __init__(self, namespace):
                super().__init__("argparse accepted")
                self.namespace = namespace

        original = argparse.ArgumentParser.parse_args

        def capture(self, args=None, namespace=None):
            ns = original(self, args, namespace)
            raise _ParseCaptured(ns)

        monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture)
        captured = []
        for module_name, argv in _skill_md_script_invocations(_skill_md_text()):
            mod = importlib.import_module(module_name)
            with pytest.raises(_ParseCaptured, match="argparse accepted") as excinfo:
                mod.main(argv)
            captured.append((module_name, argv, excinfo.value.namespace))
        return captured

    def test_every_documented_command_is_accepted_by_actual_cli(self, monkeypatch):
        """T8 自检: SKILL.md 里每个脚本调用命令与实际脚本 CLI 参数一致(逐个对照 scripts/, argparse 结构层)。"""
        invocations = _skill_md_script_invocations(_skill_md_text())
        assert {name for name, _ in invocations} == set(SCRIPT_MODULE_NAMES), f"SKILL.md 应覆盖五脚本调用, 实际: {sorted({n for n, _ in invocations})}"
        assert len(self._capture_documented_namespaces(monkeypatch)) == len(invocations), "每条文档命令都应被实际 CLI 的 argparse 完整接受(子命令/必填/枚举/type 转换)"

    def test_documented_argument_values_pass_script_value_domain_checks(self, monkeypatch):
        """T8 自检(值域层): 文档命令的参数值必须通过脚本 main() 在 parse_args 之后的值域校验。

        哨兵捕获只证明 argparse 结构接受; 值域校验在 argparse 之后(五脚本中唯一的 CLI
        值域校验 = ingest.py 的 _CODE_RE: 2-4 位大写字母, 违规实测 main() 退出码 1
        '--code 非法')——结构合法≠值合法, 曾放行示例 --code BY01(含数字, 与 SKILL.md
        阶段0 '文件代号=2-4 位大写字母' 定义自相矛盾)。用脚本自身的模块级值域校验器
        复检文档示例值: 脚本契约变更时测试同步跟进, 不在测试里复刻第二份正则。
        """
        import importlib

        # module → (argparse dest, 脚本内模块级值域校验器名); 其余脚本的"非法"校验
        # 均针对文件内容(状态文件/候选), 不针对 CLI 参数值, 无需在此登记
        value_domain_validators = {"ingest": ("code", "_CODE_RE")}
        checked = 0
        for module_name, argv, ns in self._capture_documented_namespaces(monkeypatch):
            if module_name not in value_domain_validators:
                continue
            dest, validator_name = value_domain_validators[module_name]
            validator = getattr(importlib.import_module(module_name), validator_name)
            value = getattr(ns, dest)
            assert validator.match(value), f"SKILL.md 示例 {module_name} --{dest.replace('_', '-')} {value!r} 不满足脚本值域校验 {validator.pattern}(实测 main() 退出码 1; argv={argv})"
            checked += 1
        assert checked > 0, "SKILL.md 应包含 ingest 的 --code 示例(值域校验对象), 实际未捕获到"
