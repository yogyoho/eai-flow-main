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
CLAUSE_FIELDS = {"clause_id", "source_file", "class", "category", "source_ref", "requirement", "response_status", "response_skeleton", "from_addendum", "superseded_by"}
SOURCE_REF_FIELDS = {"page", "section", "para", "quote"}
RESPONSE_SKELETON_FIELDS = {"points", "evidence_ref", "suggestion"}
NODE_FIELDS = {"node_id", "volume", "path", "slot_type", "required_format", "linked_clause_ids"}
REQUIRED_FORMAT_FIELDS = {"desc", "table_spec"}
RUBRIC_ITEM_FIELDS = {"rubric_id", "item", "max_score", "scoring_method", "score_type", "linked_clause_ids", "source_ref"}

CLAUSE_ID_RE = re.compile(r"^[A-Z]{2}-C-\d{3}$")  # 复合 ID: <文件代号>-C-<全局序号>
NODE_ID_RE = re.compile(r"^S-\d{3}$")
RUBRIC_ID_RE = re.compile(r"^R-\d{3}$")
CHUNK_ID_RE = re.compile(r"^CH-\d{3}$")
TABLE_ID_RE = re.compile(r"^T-\d{3}$")

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
            assert isinstance(ch["n_paras"], int) and ch["n_paras"] >= 1

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
            {"class": "scoring", "category": "commercial", "response_status": "draft"},
            {"source_ref": {"page": None, "section": "3.2.1", "para": 14, "quote": "字" * 50}},
        ],
        ids=["design-example-docx", "pdf-page-anchor", "addendum-superseded", "scoring-class", "quote-max-50"],
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
