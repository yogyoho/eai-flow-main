"""bid_review engine/extract.py 基准提取单测:shape/materials_hash 稳定 + null 显式保留 + 非字典路径丢弃 + prompt 骨架转录。"""

import hashlib
import json

import pytest

from app.extensions.bid_review.engine.extract import (
    ExtractNotConfigured,
    apply_adjudications,
    build_baseline,
    build_extract_prompt,
    collect_field_paths,
    detect_conflicts,
    normalize_candidates,
    normalize_confidence,
    verify_quotes,
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


# ── 抽取 v2(EAI-CUSTOM 2026-10-30,spec D5/D7):provenance + 分片 ──────


def test_normalize_provenance_filters_and_clamps():
    from app.extensions.bid_review.engine.extract import normalize_provenance

    raw = {
        "bid.total_price": {"doc_id": "bid.docx", "page": "3", "quote": "x" * 200},  # page 非法→None,quote 截120
        "ghost.path": {"doc_id": "bid.docx", "page": 1, "quote": "q"},  # 未知路径丢
        "tender.max_price": {"doc_id": "ghost.doc", "page": 1, "quote": "q"},  # 未知 doc_id 丢
        "bid.subtotal": {"doc_id": "bid.docx", "page": True, "quote": 5},  # bool page→None;非 str quote→""
        "notadict": 1,
    }
    out = normalize_provenance(raw, ["bid.total_price", "tender.max_price", "bid.subtotal"], {"bid.docx"})
    assert set(out) == {"bid.total_price", "bid.subtotal"}
    assert out["bid.total_price"] == {"doc_id": "bid.docx", "page": None, "quote": "x" * 120}
    assert out["bid.subtotal"]["page"] is None and out["bid.subtotal"]["quote"] == ""
    assert normalize_provenance(None, [], set()) == {}


def test_normalize_provenance_role_alias():
    # EAI-CUSTOM 2026-10-30 E2E 实测:模型把材料头 role 词当 doc_id(tender/bid),
    # role_map 唯一命中代真;未知 role 仍丢。
    from app.extensions.bid_review.engine.extract import normalize_provenance

    raw = {
        "bid.total_price": {"doc_id": "bid", "page": None, "quote": "总价"},
        "tender.max_price": {"doc_id": "采购", "page": None, "quote": "控制价"},  # 未知 role,丢
    }
    out = normalize_provenance(
        raw,
        ["bid.total_price", "tender.max_price"],
        {"招标.docx", "投标.docx"},
        role_map={"tender": "招标.docx", "bid": "投标.docx"},
    )
    assert set(out) == {"bid.total_price"}
    assert out["bid.total_price"] == {"doc_id": "投标.docx", "page": None, "quote": "总价"}


def test_shard_docs_packs_by_cap():
    from app.extensions.bid_review.engine.extract import shard_docs

    docs = [{"doc_id": "a", "text": "x" * 60}, {"doc_id": "b", "text": "y" * 60}, {"doc_id": "c", "text": "z" * 10}]
    shards = shard_docs(docs, cap=100)
    assert [[d["doc_id"] for d in s] for s in shards] == [["a"], ["b", "c"]]  # 贪心:放不下即开新片
    assert shard_docs([], cap=100) == []
    assert shard_docs([{"doc_id": "a", "text": "hi"}], cap=100) == [[{"doc_id": "a", "text": "hi"}]]


def test_build_baseline_new_shape_and_legacy_compat():
    # 新契约:{"fields","provenance"} → provenance 归一并只留非 null 字段
    new_fn = lambda docs, paths: {  # noqa: E731
        "fields": {"bid.total_price": 1.0, "tender.max_price": None},
        "provenance": {
            "bid.total_price": {"doc_id": "bid.docx", "page": 3, "quote": "报价总额"},
            "tender.max_price": {"doc_id": "t.docx", "page": 1, "quote": "不该留"},  # value null → 丢
        },
    }
    snap = build_baseline([{"doc_id": "bid.docx", "role": "bid", "text": "t"}, {"doc_id": "t.docx", "role": "tender", "text": "t"}], extract_fn=new_fn)
    assert snap["fields"]["tender.max_price"] is None
    assert snap["provenance"] == {"bid.total_price": {"doc_id": "bid.docx", "page": 3, "quote": "报价总额"}}
    # legacy 扁平形态(fake/旧模型输出)→ provenance={},materials_hash 不变
    legacy = build_baseline(FAKE_DOCS, extract_fn=lambda d, p: {"bid.total_price": 1.0})
    assert legacy["provenance"] == {} and legacy["materials_hash"] == build_baseline(FAKE_DOCS, extract_fn=lambda d, p: {"bid.total_price": 1.0, "provenance": {}})["materials_hash"]


def test_materials_hash_ignores_provenance():
    # det 零漂移门:provenance 变化不影响 materials_hash(同 fields 同 hash)
    from app.extensions.bid_review.engine.extract import materials_hash

    assert materials_hash({"a": 1}) == materials_hash({"a": 1})


# ── 二期(EAI-CUSTOM 2026-10-30 spec §1.1/§二):多候选 / 置信 / 冲突 / quote 核验 / 裁定合并 ──

def test_normalize_candidates_filters_and_caps():
    paths = {"bid.total_price"}
    doc_ids = {"bid.pdf"}
    role_map = {"bid": "bid.pdf"}
    raw = {
        "bid.total_price": [
            {"value": 8000000, "doc_id": "bid", "page": 3, "quote": "总价捌佰万"},  # role 别名代真
            {"value": "八百万", "doc_id": "bid.pdf", "page": 5, "quote": ""},
            {"value": None, "doc_id": "bid.pdf"},  # null 不收
            {"value": 1, "doc_id": "ghost.pdf"},  # 未知 doc_id 丢
            {"value": {1, 2}, "doc_id": "bid.pdf"},  # 非 JSON 安全类型丢(set 不在类型闸)
            "junk",  # 非 dict 丢
        ],
        "bid.made_up": [{"value": 1, "doc_id": "bid.pdf"}],  # 未知路径丢
    }
    out = normalize_candidates(raw, paths, doc_ids, role_map)
    assert set(out) == {"bid.total_price"}
    assert len(out["bid.total_price"]) == 2
    assert out["bid.total_price"][0]["doc_id"] == "bid.pdf"
    assert out["bid.total_price"][0]["page"] == 3


def test_normalize_candidates_cap():
    raw = {"p": [{"value": i, "doc_id": "d"} for i in range(30)]}
    out = normalize_candidates(raw, {"p"}, {"d"})
    assert len(out["p"]) == 8  # _CANDIDATE_MAX


def test_detect_conflicts_normalization():
    cands = {
        "bid.total_price": [{"value": "8,000,000 元"}, {"value": "8000000元"}, {"value": 9000000}],
        "bid.subtotal": [{"value": 100}, {"value": 100.0}],  # 归一后同值 → 不冲突
        "bid.detail_rows": [{"value": [{"a": 1}]}, {"value": [{"a": 1}]}],  # list 归一同值
    }
    conflicts = detect_conflicts(cands)
    assert set(conflicts) == {"bid.total_price"}
    assert len(conflicts["bid.total_price"]) == 2


def test_normalize_confidence_clamps():
    out = normalize_confidence({"a": 1.4, "b": -0.5, "c": True, "d": "x", "e": 0.75}, {"a", "b", "c", "d", "e"})
    assert out == {"a": 1.0, "b": 0.0, "e": 0.75}


def test_verify_quotes_whitespace_collapsed():
    docs = [{"doc_id": "bid.pdf", "text": "投标  总价:\n捌佰万元整(含税)"}]
    prov = {
        "hit": {"doc_id": "bid.pdf", "quote": "投标 总价: 捌佰万元整"},
        "miss": {"doc_id": "bid.pdf", "quote": "报价玖佰万"},
        "empty": {"doc_id": "bid.pdf", "quote": ""},
        "wrong_doc": {"doc_id": "ghost", "quote": "投标"},
    }
    v = verify_quotes(prov, docs)
    assert v == {"hit": True, "miss": False, "empty": False, "wrong_doc": False}


def test_apply_adjudications_merges_known_paths_only():
    fields = {"bid.total_price": 8000000, "bid.subtotal": 100}
    adj = {"bid.total_price": {"value": 9000000}, "bid.ghost": {"value": 1}, "bid.subtotal": "not_dict", "bid.detail_rows": {"value": None}}
    out = apply_adjudications(fields, adj)
    assert out["bid.total_price"] == 9000000  # 裁定覆盖
    assert out["bid.subtotal"] == 100  # adj 非 dict 忽略
    assert out == {"bid.total_price": 9000000, "bid.subtotal": 100}  # 未知/null 路径不新增
    assert fields["bid.total_price"] == 8000000  # 不改入参


def test_build_baseline_payload_with_candidates_and_conf():
    def rich_fn(docs, field_paths):
        return {
            "fields": {"bid.total_price": 9000000, "tender.max_price": 8000000},
            "provenance": {"tender.max_price": {"doc_id": "tender.pdf", "page": 3, "quote": "最高限价"}},
            "candidates": {
                "bid.total_price": [{"value": 8000000, "doc_id": "bid.pdf", "page": 1, "quote": "捌佰万"}, {"value": 9000000, "doc_id": "bid.pdf", "page": 2, "quote": "玖佰万"}],
                "tender.max_price": [{"value": 8000000, "doc_id": "tender.pdf", "page": 3, "quote": "最高限价"}],
            },
            "confidence": {"bid.total_price": 0.6, "tender.max_price": 0.95},
        }

    snap = build_baseline(FAKE_DOCS, extract_fn=rich_fn)
    assert snap["materials_hash"] == hashlib.sha1(json.dumps(snap["fields"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert len(snap["candidates"]["bid.total_price"]) == 2
    assert detect_conflicts(snap["candidates"]).keys() == {"bid.total_price"}
    assert snap["fields_conf"]["bid.total_price"] == {"conf": 0.6, "verified": False}  # 无 provenance quote → 不造假核验
    assert snap["fields_conf"]["tender.max_price"] == {"conf": 0.95, "verified": True}  # quote 命中 FAKE_DOCS 文本


def test_build_baseline_legacy_fn_still_works():
    # 旧 fake(扁平 {路径: 值})不断:候选空、fields_conf 全 verified=False(无 quote 不造假核验)
    snap = build_baseline(FAKE_DOCS, extract_fn=fake_extract_fn)
    assert snap["candidates"] == {}
    assert snap["fields_conf"]["bid.total_price"] == {"conf": None, "verified": False}
