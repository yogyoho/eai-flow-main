"""laws-standards/legal 种子配置与 RAGFlow 文档名组装器单测。"""

from app.extensions.law.service import (
    RAGFLOW_DATASET_GROUPS,
    LawService,
    build_ragflow_doc_name,
    merge_industries,
    seed_config_diff,
)


class TestBuildRagflowDocName:
    def test_full(self):
        assert build_ragflow_doc_name("环境评价", "HJ 130-2019", "规划环评总纲", "pdf") == "【环境评价】HJ 130-2019 规划环评总纲.pdf"

    def test_no_industry(self):
        assert build_ragflow_doc_name(None, "GB 3095-2012", "环境空气质量标准", "docx") == "GB 3095-2012 环境空气质量标准.docx"

    def test_no_law_number(self):
        assert build_ragflow_doc_name("地质勘查", None, "勘查规范", "txt") == "【地质勘查】勘查规范.txt"

    def test_neither(self):
        assert build_ragflow_doc_name(None, None, "水法", "docx") == "水法.docx"

    def test_long_title_not_truncated(self):
        title = "超" * 300
        assert build_ragflow_doc_name("地质勘查", "DZ 1", title, "pdf").endswith(title + ".pdf")

    def test_dotted_ext_normalized(self):
        assert build_ragflow_doc_name("环境评价", "HJ 130-2019", "规划环评总纲", ".pdf") == "【环境评价】HJ 130-2019 规划环评总纲.pdf"

    def test_empty_ext(self):
        assert build_ragflow_doc_name(None, "GB 1", "标准", "") == "GB 1 标准"


class TestKbSeedConfig:
    def test_both_kbs_present(self):
        assert set(LawService.KB_SEED_CONFIG) == {"ragflow-laws-legal", "ragflow-laws-standards"}

    def test_legal_uses_laws(self):
        seed = LawService.KB_SEED_CONFIG["ragflow-laws-legal"]
        assert seed["chunk_method"] == "laws"
        assert seed["parser_config"]["layout_recognize"] == "DeepDOC"
        assert seed["parser_config"]["auto_keywords"] == 0

    def test_standards_uses_naive384(self):
        seed = LawService.KB_SEED_CONFIG["ragflow-laws-standards"]
        assert seed["chunk_method"] == "naive"
        pc = seed["parser_config"]
        assert pc["chunk_token_num"] == 384
        assert pc["delimiter"] == "\n。！？；"
        assert pc["delimiter"].startswith("\n")  # 真实换行符,不是字面反斜杠
        assert pc["layout_recognize"] == "DeepDOC"
        assert pc["html4excel"] is True
        assert pc["auto_keywords"] == 0 and pc["auto_questions"] == 0
        assert pc["enable_children"] is False
        assert "use_parent_child" not in pc  # 非 REST 合法键

    def test_legacy_groups_derived_from_seed(self):
        assert RAGFLOW_DATASET_GROUPS["ragflow-laws-standards"] == "naive"
        assert RAGFLOW_DATASET_GROUPS["ragflow-laws-legal"] == "laws"


class TestSeedConfigDiff:
    SEED = {"chunk_method": "naive", "parser_config": {"chunk_token_num": 384, "layout_recognize": "DeepDOC"}}

    def test_identical(self):
        cur = {"chunk_method": "naive", "parser_config": {"chunk_token_num": 384, "layout_recognize": "DeepDOC", "auto_keywords": 0}}
        assert seed_config_diff(cur, self.SEED) == {}

    def test_method_drift(self):
        diff = seed_config_diff({"chunk_method": "manual", "parser_config": {}}, self.SEED)
        assert diff["chunk_method"] == ("manual", "naive")

    def test_value_drift(self):
        diff = seed_config_diff({"chunk_method": "naive", "parser_config": {"chunk_token_num": 512}}, self.SEED)
        assert diff["parser_config.chunk_token_num"] == (512, 384)

    def test_missing_seed_key(self):
        diff = seed_config_diff({"chunk_method": "naive", "parser_config": {}}, self.SEED)
        assert diff["parser_config.layout_recognize"] == (None, "DeepDOC")

    def test_extra_current_keys_ignored(self):
        cur = {"chunk_method": "naive", "parser_config": {"chunk_token_num": 384, "layout_recognize": "DeepDOC", "some_upstream_default": 1}}
        assert seed_config_diff(cur, self.SEED) == {}


class TestChunkMethodConsistency:
    def test_law_chunk_method_matches_seed(self):
        # _LAW_CHUNK_METHOD 改为派生后,此测试钉住两映射不再漂移
        from app.extensions.law import service
        for law_type, kb in service.RAGFLOW_KB_MAPPING.items():
            expected = service._KB_SEED_CONFIG[kb]["chunk_method"]
            assert service._LAW_CHUNK_METHOD[law_type] == expected, law_type


class TestMergeIndustries:
    def test_union_dedup(self):
        assert merge_industries(["环境评价", "地质勘查"]) == ["环境评价", "地质勘查", "煤炭工业"]

    def test_empty_falls_back(self):
        assert merge_industries([]) == ["地质勘查", "环境评价", "煤炭工业"]
