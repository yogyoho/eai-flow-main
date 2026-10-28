"""bid_review engine/extract.py 基准提取单测:shape/materials_hash 稳定 + null 显式保留 + 非字典路径丢弃 + prompt 骨架转录。"""

import hashlib
import json

import pytest

from app.extensions.bid_review.engine.extract import (
    ExtractNotConfigured,
    build_baseline,
    build_extract_prompt,
    collect_field_paths,
)

FAKE_DOCS = [
    {"doc_id": "tender.pdf", "role": "tender", "text": "最高限价…"},
    {"doc_id": "bid.pdf", "role": "bid", "text": "投标总价…"},
]


def fake_extract_fn(docs, field_paths):  # 生产实现=LLM;测试=fake
    return {p: 1 if "total_price" in p else None for p in field_paths}


def test_build_baseline_shape_and_hash():
    snap = build_baseline(FAKE_DOCS, extract_fn=fake_extract_fn)
    assert set(snap["fields"]) >= {"bid.total_price", "tender.max_price"}
    h = hashlib.sha1(json.dumps(snap["fields"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert snap["materials_hash"] == h and len(h) == 40
    assert snap["fields"]["tender.max_price"] is None or isinstance(snap["fields"]["tender.max_price"], (int, float, str, bool, type(None)))


def test_missing_known_fields_become_explicit_null():
    # 提取器只回部分路径:未回的已知路径必须显式 None(缺字段显式 null,禁止静默缺失)
    def partial_fn(docs, field_paths):
        return {"bid.total_price": 100}

    snap = build_baseline(FAKE_DOCS, extract_fn=partial_fn)
    assert snap["fields"]["bid.total_price"] == 100
    assert "tender.max_price" in snap["fields"]
    assert snap["fields"]["tender.max_price"] is None


def test_unknown_paths_dropped():
    # 非 field_dictionary 路径一律丢弃(字段路径是规则↔引擎↔评测三方契约,不得擅自新增)
    def lying_fn(docs, field_paths):
        raw = {p: None for p in field_paths}
        raw["bid.made_up_path"] = "编造"
        return raw

    snap = build_baseline(FAKE_DOCS, extract_fn=lying_fn)
    assert "bid.made_up_path" not in snap["fields"]


def test_materials_hash_stable_across_calls():
    a = build_baseline(FAKE_DOCS, extract_fn=fake_extract_fn)
    b = build_baseline(FAKE_DOCS, extract_fn=fake_extract_fn)
    assert a["materials_hash"] == b["materials_hash"]


def test_extract_fn_not_configured_raises():
    with pytest.raises(ExtractNotConfigured):
        build_baseline(FAKE_DOCS)


def test_dict_list_scalar_passthrough():
    # dict/list/标量透传(不做深加工);Falsy 值(0/False)不得误判为缺失
    def rich_fn(docs, field_paths):
        return {
            "bid.boq_items": [{"code": "1.1", "amount": 5}],
            "bid.total_price_words": "壹佰元整",
            "bid.detail_rows": [{"amount": 5}],
            "bid.subtotal": 0,
            "bid.price_includes_tax": False,
        }

    snap = build_baseline(FAKE_DOCS, extract_fn=rich_fn)
    assert snap["fields"]["bid.boq_items"] == [{"code": "1.1", "amount": 5}]
    assert snap["fields"]["bid.total_price_words"] == "壹佰元整"
    assert snap["fields"]["bid.detail_rows"] == [{"amount": 5}]
    assert snap["fields"]["bid.subtotal"] == 0
    assert snap["fields"]["bid.price_includes_tax"] is False


def test_collect_paths_cover_m1_dictionary():
    # 基准提取请求的路径必须覆盖 M1 规则包 inputs(含 bid.total_price / tender.max_price);前缀只允许 tender/bid/project
    paths = collect_field_paths()
    assert {"bid.total_price", "tender.max_price", "tender.boq_items"} <= set(paths)
    assert paths == sorted(paths)
    assert all(p.split(".", 1)[0] in {"tender", "bid", "project"} for p in paths)


def test_prompt_skeleton_transcribed():
    # prompt 骨架=设计文档素材转录:四条铁律 + 只输出 field_dictionary 路径 + 缺字段=null
    prompt = build_extract_prompt(FAKE_DOCS, ["bid.total_price", "tender.max_price"])
    for needle in ("只依据", "null", "不心算", "指令", "编造", "bid.total_price", "tender.max_price", "JSON"):
        assert needle in prompt, f"prompt 骨架缺关键词: {needle}"


def test_prompt_carries_duration_type_contract():
    # fix-round 评审项:{value,unit}-or-number 契约从规则包 YAML 注释提升为提取 prompt 可见
    # 类型说明——build_extract_prompt 原只给字段路径不给类型契约,字段名又带 *_text,提取器对
    # "工期:540日历天" 大概率回流原始字符串(normalize_unit 强转失败的根源治理)。
    prompt = build_extract_prompt(FAKE_DOCS, collect_field_paths())
    targets = (
        "bid.duration_main_text",
        "bid.duration_schedule",
        "bid.duration_commitment_letter",
        "tender.max_duration",
        "bid.warranty_period",
        "tender.min_warranty_period",
    )
    for path in targets:
        line = next((ln for ln in prompt.splitlines() if ln.startswith(f"- {path}")), None)
        assert line is not None, f"{path} 不在提取 prompt 字段清单中"
        assert "{value" in line and "禁止原文文本" in line, f"{path} 缺 {{value,unit}}-or-number 类型契约: {line}"
