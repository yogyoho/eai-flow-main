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


def _run_extract(command, candidates, *, sections=None, declared_total=None, state_dir=None):
    extract = _extract_module()
    argv = [command, "--candidates", *[str(c) for c in candidates], "--sections", str(sections if sections is not None else FIXTURE_DIR / "sections.json")]
    if declared_total is not None:
        argv += ["--declared-total", str(declared_total)]
    if state_dir is not None:
        argv += ["--state-dir", str(state_dir)]
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
        """枚举非法条目所在裁决块整体[待确认]不合并; 引用该条款的结构/评分项级联隔离(D7 外键)。"""
        files = _happy_candidate_files(tmp_path)
        bad = dict(load_json("clauses.json")[1])  # ZB-C-002
        bad["class"] = "critical"
        files[1] = _write_candidate(tmp_path, "c2.json", chunk_id="CH-002", kind="clauses", items=[bad])
        state_dir = tmp_path / "state"
        rc = _run_extract("merge", files, declared_total=100, state_dir=state_dir)
        assert rc == 3
        summary = _last_summary_json(capsys)
        kinds = _anomaly_kinds(summary)
        assert "schema_violation" in kinds
        assert "clause_fk_invalid" in kinds, "S-007/R-002 引用被隔离的 ZB-C-002 → 悬挂外键级联浮出"
        clauses = json.loads((state_dir / "clauses.json").read_text(encoding="utf-8"))
        assert [c["clause_id"] for c in clauses] == ["ZB-C-001", "ZB-C-003", "BY-C-004"], "干净裁决块照常合并, 异常块保持[待确认]不落盘"
        assert not (state_dir / "structure.json").exists(), "结构裁决块因悬挂外键被隔离, 不写 structure.json"
        assert not (state_dir / "rubric.json").exists(), "评分裁决块因悬挂外键被隔离, 不写 rubric.json"

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
