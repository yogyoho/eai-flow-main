"""EIA pattern_mine 归并挖掘 + pattern_ingest 变体连边/精炼加载 单测——纯函数层, 不碰真库（test_eia_scope_tag.py 同法）.

覆盖: 词表装载与别名大小写不敏感 / 无命中保原名 / 复合名全分解与部分命中不分解 /
模式位置作用域（治理宾语不吃处置表、处置宾语吃 disposal∪measure）/ 同名跨表（矸石井下充填）无冲突 /
pattern_id 稳定 / _aggregate 变体合并（support=报告集并集、变体清单记录）/ ingest _load_refined
（_meta 跳过、缺字段报错）/ _variant_endpoints 新旧格式 / _clip 截断。
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# scripts/ 不是包——importlib 直接按文件路径加载脚本模块（test_eia_scope_tag.py 同法）
_BACKEND = Path(__file__).resolve().parents[1]


def _load(name: str):
    _spec = importlib.util.spec_from_file_location(name, _BACKEND / "scripts" / f"{name}.py")
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[name] = _mod
    _spec.loader.exec_module(_mod)
    return _mod


mine = _load("eia_pattern_mine")
ingest = _load("eia_pattern_ingest")


@pytest.fixture(scope="module")
def normalizer():
    return mine.load_normalizer(mine.VOCAB_PATH)


# ---------------------------------------------------------------- 词表装载


def test_load_real_vocab_tables(normalizer):
    """真词表可装载：4 表、无表内冲突。"""
    assert normalizer.conflicts == []
    assert set(normalizer._tables) == {
        "pollutant_concept",
        "measure_process_concept",
        "pollution_process_concept",
        "disposal_target_concept",
    }


def test_alias_case_insensitive(normalizer):
    """latin 别名大小写不敏感：ss/COD/NOx 命中污染物表。"""
    assert normalizer.expand("ss", ("pollutant_concept",)) == ["悬浮物"]
    assert normalizer.expand("cod", ("pollutant_concept",)) == ["化学需氧量"]
    assert normalizer.expand("codcr", ("pollutant_concept",)) == ["化学需氧量"]
    assert normalizer.expand("NOx", ("pollutant_concept",)) == ["氮氧化物"]


def test_alias_chinese_and_no_hit_passthrough(normalizer):
    """中文别名命中；无命中（或空词表位）保原名。"""
    assert normalizer.expand("悬浮", ("pollutant_concept",)) == ["悬浮物"]
    assert normalizer.expand("悬浮性固体", ("pollutant_concept",)) == ["悬浮物"]
    assert normalizer.expand("烟气", ("pollutant_concept",)) == ["烟气"]
    assert normalizer.expand("任家庄煤矿矸石", ()) == ["任家庄煤矿矸石"]


def test_compound_full_split_and_partial_kept(normalizer):
    """复合名：每段都命中→全分解去重；任一段词表外→整体保留。三批词表后 bod/bod5 入表，
    「cod、bod5、ss、石油类」等含 BOD 复合名已可全分解；部分命中仍保原名。"""
    assert normalizer.expand("悬浮物、cod、石油类、氟化物、溶解性总固体", ("pollutant_concept",)) == [
        "悬浮物",
        "化学需氧量",
        "石油类",
        "氟化物",
        "矿化度",
    ]
    assert normalizer.expand("cod、bod5、ss、石油类", ("pollutant_concept",)) == [
        "化学需氧量",
        "生化需氧量",
        "悬浮物",
        "石油类",
    ]
    assert normalizer.expand("cod、烟气、ss", ("pollutant_concept",)) == ["cod、烟气、ss"]
    # bod/bod5 平行条目经 生化需氧量 规范名归并
    assert normalizer.expand("bod", ("pollutant_concept",)) == ["生化需氧量"]
    assert normalizer.expand("bod5", ("pollutant_concept",)) == ["生化需氧量"]
    # 伊敏设施同名异写归并（治理宾语=measure 表作用域）
    assert normalizer.expand("伊敏污水处理厂", ("measure_process_concept",)) == ["伊敏河镇污水处理厂"]


def test_position_scope_disposal_table_not_on_treat_object(normalizer):
    """位置作用域：治理宾语（measure 表）不吃 disposal 表别名；处置宾语（disposal∪measure）吃。"""
    assert normalizer.expand("有资质的危废处置公司", ("measure_process_concept",)) == ["有资质的危废处置公司"]
    assert normalizer.expand("有资质的危废处置公司", ("disposal_target_concept", "measure_process_concept")) == ["有资质单位"]
    assert normalizer.expand("垃圾场", ("disposal_target_concept", "measure_process_concept")) == ["市政垃圾处理厂"]


def test_same_name_across_tables_no_conflict(normalizer):
    """同名跨表（矸石井下充填=measure 概念名 & 井下充填别名）：治理宾语保原名，处置宾语归并。"""
    assert normalizer.expand("矸石井下充填", ("measure_process_concept",)) == ["矸石井下充填"]
    assert normalizer.expand("矸石井下充填", ("disposal_target_concept", "measure_process_concept")) == ["井下充填"]


# ---------------------------------------------------------------- pattern_id 与聚合


def test_pattern_id_stable():
    """pattern_id 只由 (type, s, o, pred) 决定且稳定。"""
    a = mine._pattern_id("治理", "悬浮物", "矿井水处理站", "emitted_as+treated_by")
    b = mine._pattern_id("治理", "悬浮物", "矿井水处理站", "emitted_as+treated_by")
    c = mine._pattern_id("处置", "悬浮物", "矿井水处理站", "emitted_as+treated_by")
    assert a == b and a != c and a.startswith("dp-")


def _agg_env():
    name_of = {"s1": "ss", "o1": "矿井水处理站", "s2": "悬浮物", "b1": "采煤环节"}
    etype_of = {"s1": "pollutant", "o1": "treatment_measure", "s2": "pollutant", "b1": "pollution_process"}
    docs_of: dict = {}
    sr_of: dict = {}
    return name_of, etype_of, docs_of, sr_of


def test_aggregate_merges_variants_union_reports():
    """同规范名的变体路径合并为一条：support=报告集并集，变体（名+etype）入清单。"""
    name_of, etype_of, docs_of, sr_of = _agg_env()
    paths = [
        ("s1", "o1", "emitted_as+treated_by", ["b1"], {"r1", "r2"}, "悬浮物", "矿井水处理站"),
        ("s2", "o1", "emitted_as+treated_by", ["b1"], {"r2", "r3"}, "悬浮物", "矿井水处理站"),
    ]
    entries = mine._aggregate("治理", paths, name_of, etype_of, docs_of, sr_of)
    assert len(entries) == 1
    e = entries[0]
    assert e["support_count"] == 3  # 并集 {r1,r2,r3}，非算术和 4
    assert e["occurrence_count"] == 2
    assert e["subject_name"] == "悬浮物" and e["object_name"] == "矿井水处理站"
    assert {v["name"] for v in e["subject_variants"]} == {"ss", "悬浮物"}
    assert e["subject_variants"][0]["etype"] == "pollutant"


def test_aggregate_disposal_pred_disambiguated():
    """处置规律同名不同谓词：pattern_name 带谓词消歧，id 亦不同。"""
    name_of, etype_of, docs_of, sr_of = _agg_env()
    name_of["w1"] = "矸石"
    etype_of["w1"] = "waste_stream"
    paths = [
        ("w1", "o1", "disposed_by", [], {"r1"}, "矸石", "井下充填"),
        ("w1", "o1", "utilized_by", [], {"r1"}, "矸石", "井下充填"),
    ]
    entries = mine._aggregate("处置", paths, name_of, etype_of, docs_of, sr_of)
    assert len(entries) == 2
    assert {e["pattern_id"] for e in entries} == {
        mine._pattern_id("处置", "矸石", "井下充填", "disposed_by"),
        mine._pattern_id("处置", "矸石", "井下充填", "utilized_by"),
    }
    assert all("（" in e["pattern_name"] for e in entries)


def test_aggregate_ghost_iri_not_in_variants():
    """重构后 name 缺失检查在 expand_paths 层；_aggregate 对 name_of 缺失的 IRI 只跳过变体登记，不崩、不产生 None 项。"""
    name_of, etype_of, docs_of, sr_of = _agg_env()
    paths = [("ghost", "o1", "emitted_as+treated_by", [], {"r1"}, "x", "y")]
    entries = mine._aggregate("治理", paths, name_of, etype_of, docs_of, sr_of)
    assert len(entries) == 1
    e = entries[0]
    assert e["subject_name"] == "x" and e["support_count"] == 1
    assert e["subject_variants"] == []  # ghost IRI 无 name_of 登记被跳过
    assert {v["name"] for v in e["object_variants"]} == {"矿井水处理站"}


# ---------------------------------------------------------------- ingest 侧


def test_load_refined_skips_meta_and_requires_desc(tmp_path):
    """_meta 下划线键跳过；缺 refined_desc 的条目 SystemExit。"""
    f = tmp_path / "refined.json"
    f.write_text(
        json.dumps(
            {
                "_meta": {"note": "provenance"},
                "dp-1": {"refined_desc": "ok"},
                "dp-2": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        ingest._load_refined(f)
    f.write_text(json.dumps({"_meta": {"note": "x"}, "dp-1": {"refined_desc": "ok"}}, ensure_ascii=False), encoding="utf-8")
    out = ingest._load_refined(f)
    assert out == {"dp-1": {"refined_desc": "ok"}}
    assert ingest._load_refined(None) == {}


def test_variant_endpoints_new_and_legacy():
    """归并版 variants（名+etype）优先；旧格式回退单端点。"""
    merged = {
        "subject_name": "悬浮物",
        "subject_etype": "pollutant",
        "subject_variants": [{"name": "ss", "etype": "pollutant"}, {"name": "悬浮物", "etype": "pollutant"}],
        "object_name": "矿井水处理站",
        "object_etype": "treatment_measure",
    }
    assert ingest._variant_endpoints(merged, "subject") == [("ss", "pollutant"), ("悬浮物", "pollutant")]
    legacy = {"subject_name": "悬浮物", "subject_etype": "pollutant"}
    assert ingest._variant_endpoints(legacy, "subject") == [("悬浮物", "pollutant")]


def test_clip_appends_pattern_id_on_overflow():
    """超 norm_name 列宽截断并拼 pattern_id 保唯一；未超原样返回。"""
    long_name = "治" * 400
    out = ingest._clip(long_name, "dp-abcdef1234")
    assert len(out) <= ingest.NAME_MAX and out.endswith("dp-abcdef1234")
    assert ingest._clip("短名", "dp-abcdef1234") == "短名"
