"""import_eia_samples 转换纯逻辑测试——隐私排除/桶映射/大纲头部解析."""

import importlib.util
import sys
from pathlib import Path

# scripts/ 不是包——importlib 直接按文件路径加载脚本模块
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_eia_samples.py"
_spec = importlib.util.spec_from_file_location("import_eia_samples", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["import_eia_samples"] = _mod
_spec.loader.exec_module(_mod)

import pytest  # noqa: E402

_build_payload = _mod._build_payload
_parse_outline_header = _mod._parse_outline_header


def _sample(slug="s1", extra=None):
    d = {
        "sample_slug": slug,
        "entities": {"projects": ["项目A"], "mines": ["矿B"], "orgs": ["机构C"], "places": ["地名D"], "sensitive": ["水源地E"]},
    }
    if extra:
        d.update(extra)
    return d


def test_bucket_to_etype_mapping():
    payload = _build_payload(_sample(), "s1", None)
    etypes = sorted(e["etype"] for e in payload["entities"])
    assert etypes == ["mine", "org", "place", "project", "sensitive_point"]
    assert all(e["mention"]["document_id"] == "eia-sample:s1" for e in payload["entities"])
    assert all(e["mention"]["quote"] == "" for e in payload["entities"])
    assert payload["domain"] == "eia"


def test_people_and_generic_terms_excluded():
    """隐私红线: generic_terms / aux.people / aux.doc_numbers 永不产出实体."""
    payload = _build_payload(
        _sample(extra={"generic_terms": ["公路"], "aux": {"people": ["张三"], "doc_numbers": ["环审〔2021〕1号"], "privacy_notes": None}}),
        "s1",
        None,
    )
    names = [e["name"] for e in payload["entities"]]
    assert "张三" not in names and "公路" not in names and "环审〔2021〕1号" not in names


def test_privacy_buckets_structurally_excluded():
    """结构性钉: 实体只来自 entities 下 5 桶——即使整个 payload 除隐私桶外为空也零实体产出."""
    payload = _build_payload({"sample_slug": "s1", "generic_terms": ["公路", "铁路"], "aux": {"people": ["张三"], "doc_numbers": ["环审〔2021〕1号"]}}, "s1", None)
    assert payload["entities"] == []
    assert payload["relations"] == []


def test_outline_header_parse_relations():
    text = "- **编制单位**: 中煤科工集团北京华宇工程有限公司（工程编号 H7367Z）；**委托单位**: 宁夏回族自治区发展和改革委员会\n- **开发主体**: 宁夏宝丰能源集团有限公司、国家能源集团宁夏煤业有限责任公司\n"
    parsed = _parse_outline_header(text)
    assert parsed["compiles"] == ["中煤科工集团北京华宇工程有限公司"]
    assert parsed["commissions"] == ["宁夏回族自治区发展和改革委员会"]
    assert parsed["develops"] == ["宁夏宝丰能源集团有限公司", "国家能源集团宁夏煤业有限责任公司"]


def test_outline_relations_shape():
    parsed = {"compiles": ["机构甲"], "commissions": ["机构乙"], "develops": ["机构丙", "机构丁"]}
    orgs, relations = _mod._outline_relations(parsed, "项目A")
    preds = sorted(r["predicate"] for r in relations)
    # 计划样例期望列表误排（commissions < compiles 按字典序）; 此处以真实 sorted 序为准
    assert preds == ["org_commissions_project", "org_compiles_project", "org_develops_project", "org_develops_project"]
    assert all(r["object"] == "项目A" for r in relations)
    assert {o["name"] for o in orgs} == {"机构甲", "机构乙", "机构丙", "机构丁"}


def test_outline_org_deduped_across_roles():
    """同一 org 挂多角色 → 一实体多边."""
    orgs, relations = _mod._outline_relations({"compiles": ["机构甲"], "commissions": ["机构甲"], "develops": []}, "项目A")
    assert len(orgs) == 1 and len(relations) == 2


def test_project_name_must_be_declared():
    """fail-closed: project_name 未在实体清单声明即拒绝（防关系边悬空引用）."""
    with pytest.raises(ValueError, match="未在实体清单"):
        _build_payload(_sample(), "s1", "不存在的项目")


def test_payload_passes_eia_schema():
    from app.extensions.ontology.doc_graph.schemas import EiaExtraction

    payload = _build_payload(_sample(), "s1", "项目A")
    orgs, relations = _mod._outline_relations({"compiles": ["机构甲"], "commissions": [], "develops": []}, "项目A")
    payload["entities"] += orgs
    payload["relations"] += relations
    p = EiaExtraction.model_validate(payload)  # 全管线 fail-closed 过
    assert p.domain == "eia"
