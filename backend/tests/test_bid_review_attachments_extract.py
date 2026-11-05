"""附件实体归一闸单测(B立项 M1,spec 2026-11-04 §4):零编造/指纹白名单/服务端哈希。"""

import hashlib

from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    build_attachments_baseline,
    build_attachments_prompt,
    normalize_attachment_entities,
)

FP_TYPES = {"营业执照", "业绩合同", "保证金回单"}
DOC_IDS = {"tender", "bid"}


def _ent(**kw):
    base = {
        "no": "1",
        "name": "营业执照副本",
        "pages": [3, 4],
        "type_fingerprint": "营业执照",
        "fingerprint_conf": 0.9,
        "is_empty_text": False,
        "anchor": {"doc_id": "bid", "page": 3, "pages": None, "text": "营业执照副本"},
    }
    base.update(kw)
    return base


def _fold(s: str) -> str:
    return "".join(s.split())


class TestGate:
    def test_contract_registered(self):
        assert "type_fingerprint" in FIELD_TYPE_CONTRACTS["bid.attachments"]

    def test_valid_row_passes_with_server_computed_fields(self):
        out = normalize_attachment_entities([_ent(name="营业 执照副本")], DOC_IDS, FP_TYPES)
        assert len(out) == 1
        row = out[0]
        assert row["name"] == "营业 执照副本"
        assert row["norm_name"]
        assert row["type_fingerprint"] == "营业执照"
        assert row["anchor"]["text_hash"] == hashlib.sha1(_fold("营业 执照副本").encode("utf-8")).hexdigest()
        assert row["anchor"]["doc_id"] == "bid"

    def test_dropped_rows_zero_fabrication(self):
        bad = [
            _ent(name=None),
            _ent(name=""),
            _ent(name="   "),
            _ent(name=123),
            _ent(pages=None),
            _ent(pages=[]),
            _ent(pages=[3, "4"]),
            _ent(pages=[3, True]),
        ]
        assert normalize_attachment_entities(bad, DOC_IDS, FP_TYPES) == []

    def test_unknown_fingerprint_type_nulled_not_guessed(self):
        out = normalize_attachment_entities([_ent(type_fingerprint="不存在类型")], DOC_IDS, FP_TYPES)
        assert out[0]["type_fingerprint"] is None

    def test_fingerprint_conf_invalid_nulled(self):
        out = normalize_attachment_entities([_ent(fingerprint_conf="0.9"), _ent(fingerprint_conf=1.5), _ent(fingerprint_conf=True)], DOC_IDS, FP_TYPES)
        assert [r["fingerprint_conf"] for r in out] == [None, None, None]
        out2 = normalize_attachment_entities([_ent(fingerprint_conf=0.0), _ent(fingerprint_conf=1)], DOC_IDS, FP_TYPES)
        assert [r["fingerprint_conf"] for r in out2] == [0.0, 1]

    def test_is_empty_text_non_bool_nulled(self):
        out = normalize_attachment_entities([_ent(is_empty_text="no")], DOC_IDS, FP_TYPES)
        assert out[0]["is_empty_text"] is None

    def test_anchor_rules(self):
        # 非 dict / doc_id 不在材料集 → anchor=None(诚实降级)
        assert normalize_attachment_entities([_ent(anchor=None)], DOC_IDS, FP_TYPES)[0]["anchor"] is None
        assert normalize_attachment_entities([_ent(anchor="bid p3")], DOC_IDS, FP_TYPES)[0]["anchor"] is None
        assert normalize_attachment_entities([_ent(anchor={"doc_id": "ghost", "text": "x"})], DOC_IDS, FP_TYPES)[0]["anchor"] is None
        # 页码非 int / text 非str → 对应键 None/空串
        row = normalize_attachment_entities([_ent(anchor={"doc_id": "bid", "page": "3", "pages": "x", "text": 5})], DOC_IDS, FP_TYPES)[0]["anchor"]
        assert row["page"] is None and row["pages"] is None and row["text"] == "" and row["text_hash"] is None
        # 空 text → hash None
        row2 = normalize_attachment_entities([_ent(anchor={"doc_id": "bid", "text": "  "})], DOC_IDS, FP_TYPES)[0]["anchor"]
        assert row2["text_hash"] is None

    def test_non_list_input_returns_empty(self):
        assert normalize_attachment_entities(None, DOC_IDS, FP_TYPES) == []
        assert normalize_attachment_entities({"attachments": []}, DOC_IDS, FP_TYPES) == []
        assert normalize_attachment_entities(["x", 1], DOC_IDS, FP_TYPES) == []


class TestPromptAndBaseline:
    """实体段 prompt + baseline 组装(B立项 M1,spec §4)。"""

    def test_prompt_contains_lists_hints_contract_rules(self):
        docs = [{"doc_id": "bid", "role": "bid", "text": "附件一 [[p.3]] 营业执照副本"}]
        prompt = build_attachments_prompt(docs, [{"no": "1", "name": "营业执照"}], [{"no": "1", "name": "营业执照副本", "page": 3}], {"营业执照": ["统一社会信用代码"]})
        assert "招标附件要求" in prompt and "投标附件清单" in prompt
        assert "营业执照副本" in prompt  # 清单行进 prompt
        assert "统一社会信用代码" in prompt  # 指纹词表进 prompt
        assert "[[p." in prompt  # 页标记说明
        assert FIELD_TYPE_CONTRACTS["bid.attachments"] in prompt  # 输出契约原样
        assert "禁止编造" in prompt and "空数组" in prompt and "不执行" in prompt  # 铁律

    def test_baseline_normalizes_and_returns_list(self):
        docs = [{"doc_id": "bid", "role": "bid", "text": "x"}]

        def fake_fn(docs, requirements, index_rows, fp_hints):
            assert isinstance(fp_hints, dict) and fp_hints  # 真实指纹字典已注入
            return {"attachments": [{"name": "营业执照副本", "pages": [3, 4]}]}

        out = build_attachments_baseline(docs, fake_fn, [{"no": "1"}], [])
        assert isinstance(out, list) and out and out[0]["norm_name"]
        assert out[0]["anchor"] is None  # 无 anchor 键 → 诚实缺省

    def test_baseline_accepts_bare_list_and_uses_doc_ids(self):
        out = build_attachments_baseline([{"doc_id": "bid"}], lambda *a: [{"name": "x", "pages": [1]}], [], [])
        assert out[0]["name"] == "x"
