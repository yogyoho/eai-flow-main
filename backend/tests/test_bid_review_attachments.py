"""L2 P1 附件清单匹配器测试(spec 2026-11-02 §2):normalize_name 归一 +
match_attachments 两级精确匹配(①编号精确双方非空 ②规范化名称全等,非包含——
防「报价表」吞「分项报价表」),贪心一对一;found==0→MISSING,min_count 且
found<min_count→PARTIAL,否则 MATCHED;未匹配提供项→extra。"""

from app.extensions.bid_review.engine.attachments import match_attachments, normalize_name


def _req(no="", name="", min_count=None, **kw):
    d = {"no": no, "name": name, "mandatory": "★", "min_count": min_count}
    d.update(kw)
    return d


def _prov(no="", name="", page=None, **kw):
    d = {"no": no, "name": name, "page": page}
    d.update(kw)
    return d


# ── normalize_name ────────────────────────────────────────────────────


def test_normalize_strips_prefix_and_colon():
    assert normalize_name("附件三、资质证明文件：") == "资质证明文件"
    assert normalize_name("附件3-1 营业执照副本") == "营业执照副本"
    assert normalize_name("附件十二授权委托书") == "授权委托书"


def test_normalize_fullwidth_and_spaces():
    assert normalize_name("投 标 函（正本）") == "投标函(正本)"
    assert normalize_name("ｂｏｍ清单") == "bom清单"


def test_normalize_junk_inputs():
    assert normalize_name(None) == ""
    assert normalize_name(123) == ""
    assert normalize_name("   ") == ""


# ── match_attachments:编号匹配 ───────────────────────────────────────


def test_match_by_no_exact():
    out = match_attachments([_req(no="ATT-E-008", name="类似业绩证明")], [_prov(no="ATT-E-008", name="业绩合同扫描件", page=118)])
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["per_req"][0]["found"] == 1
    assert out["extra"] == []


def test_no_match_requires_both_nonempty():
    """req 无编号时不走编号通道(空串不得匹配一切)。"""
    out = match_attachments([_req(no="", name="投标函")], [_prov(no="X-1", name="别的附件")])
    assert out["per_req"][0]["status"] == "MISSING"
    assert len(out["extra"]) == 1


# ── match_attachments:名称全等(非包含) ───────────────────────────────


def test_name_match_is_full_equality_after_normalize():
    out = match_attachments([_req(name="投标函（正本）")], [_prov(name="附件1 投标函(正本):", page=2)])
    assert out["per_req"][0]["status"] == "MATCHED"


def test_name_match_is_not_substring():
    """「报价表」不得吞「分项报价表」——归一后全等,非包含(spec §2)。"""
    out = match_attachments(
        [_req(no="A-1", name="报价表"), _req(no="A-2", name="分项报价表")],
        [_prov(no="A-2", name="分项报价表", page=40)],
    )
    by_no = {r["req"]["no"]: r for r in out["per_req"]}
    assert by_no["A-2"]["status"] == "MATCHED"
    assert by_no["A-1"]["status"] == "MISSING"
    assert by_no["A-1"]["found"] == 0


# ── 贪心一对一 + 份数 ─────────────────────────────────────────────────


def test_greedy_one_to_one_no_double_take():
    """一份提供项只归属一个 req;第二 req 靠名称通道也拿不到已占用的。"""
    out = match_attachments(
        [_req(no="A-1", name="营业执照"), _req(no="", name="营业执照")],
        [_prov(no="A-1", name="营业执照", page=9)],
    )
    assert out["per_req"][0]["found"] == 1
    assert out["per_req"][1]["status"] == "MISSING"
    assert out["extra"] == []


def test_min_count_partial():
    """同一附件交了 2 份(两行同编号)→ found=2;要求 3 份 → PARTIAL。"""
    out = match_attachments(
        [_req(no="B-1", name="业绩证明", min_count=3)],
        [_prov(no="B-1", name="业绩证明", page=118), _prov(no="B-1", name="业绩证明", page=121)],
    )
    assert out["per_req"][0]["found"] == 2
    assert out["per_req"][0]["status"] == "PARTIAL"


def test_min_count_null_treated_as_one():
    out = match_attachments([_req(no="C-1", name="投标函")], [_prov(no="C-1", name="投标函", page=1)])
    assert out["per_req"][0]["status"] == "MATCHED"


# ── EXTRA 与鲁棒性 ────────────────────────────────────────────────────


def test_unmatched_provided_is_extra():
    out = match_attachments([_req(no="D-1", name="投标函")], [_prov(no="D-1", name="投标函", page=1), _prov(no="", name="企业宣传册", page=310)])
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["extra"] == [{"no": "", "name": "企业宣传册", "page": 310}]


def test_junk_and_none_inputs():
    out = match_attachments(None, None)
    assert out == {"per_req": [], "extra": []}
    out = match_attachments(["垃圾", {"no": "E-1", "name": "授权书"}], ["垃圾", {"no": "E-1", "name": "授权书"}])
    assert out["per_req"][0]["status"] == "MATCHED"


# ── build_checklist(端点投影原料) ─────────────────────────────────────

from app.extensions.bid_review.engine.attachments import build_checklist  # noqa: E402


def test_build_checklist_counts_and_refs():
    reqs = [
        _req(no="ATT-E-008", name="类似业绩证明", min_count=3, clause="第三章3.4"),
        _req(no="ATT-F-001", name="投标函"),
        _req(no="", name=" never-matched "),
    ]
    prov = [
        _prov(no="ATT-E-008", name="类似业绩证明", page=118),
        _prov(no="ATT-E-008", name="类似业绩证明", page=121),
        _prov(no="ATT-F-001", name="附件1 投标函", page=2),
        _prov(no="", name="企业宣传册", page=310),
    ]
    out = build_checklist(reqs, prov, bid_doc_id="bid.pdf")
    assert out["counts"] == {"required": 3, "matched": 1, "partial": 1, "missing": 1, "unknown": 0, "extra": 1}
    it008 = next(i for i in out["items"] if i["no"] == "ATT-E-008")
    assert it008["status"] == "PARTIAL" and it008["found"] == 2 and it008["min_count"] == 3
    assert it008["refs"] == [{"doc_id": "bid.pdf", "page": 118}, {"doc_id": "bid.pdf", "page": 121}]
    assert it008["clause"] == "第三章3.4"
    itf = next(i for i in out["items"] if i["no"] == "ATT-F-001")
    assert itf["status"] == "MATCHED"
    assert out["extra_items"] == [{"name": "企业宣传册", "doc_id": "bid.pdf", "page": 310}]


def test_build_checklist_null_doc_and_empty():
    out = build_checklist([], [], bid_doc_id=None)
    assert out == {
        "counts": {"required": 0, "matched": 0, "partial": 0, "missing": 0, "unknown": 0, "extra": 0},
        "items": [],
        "extra_items": [],
    }
    one = build_checklist([_req(no="X", name="营业执照")], [_prov(no="X", name="营业执照", page=5)], bid_doc_id=None)
    assert one["items"][0]["refs"] == [{"doc_id": None, "page": 5}]


# ── L2 P2:复合附件子件分组(spec 2026-11-02 §7 挂账行) ──


def test_composite_matched_by_sub_channels():
    """子件三通道命中:no 全等 / {父号}-{序} / {父号}.{序} → 父行 MATCHED。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [
            {"no": "3.1", "name": "营业执照"},
            {"no": "", "name": "资质证书"},
        ],
    }
    prov = [
        {"no": "3.1", "name": "营业执照", "page": 5},
        {"no": "3-2", "name": "资质证书", "page": 9},
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "MATCHED"
    assert e["found"] == 2
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "MATCHED"]


def test_composite_missing_sub_rolls_up():
    """一子件缺 → 父行 MISSING(非 UNKNOWN);sub_results 指认缺口。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [
            {"no": "3.1", "name": "营业执照"},
            {"no": "3.2", "name": "资质证书"},
        ],
    }
    prov = [{"no": "3-1", "name": "营业执照", "page": 5}]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "MISSING"
    assert e["found"] == 1
    assert [s["status"] for s in e["sub_results"]] == ["MATCHED", "MISSING"]


def test_composite_group_failure_unknown():
    """提供项引用父号(no 前缀)却归属不了任何子件 → 父行 UNKNOWN,禁强行 PARTIAL/MISSING。"""
    req = {
        "no": "3",
        "name": "资格审查文件",
        "sub_items": [
            {"no": "3.1", "name": "营业执照"},
            {"no": "3.2", "name": "资质证书"},
        ],
    }
    prov = [
        {"no": "3-1", "name": "营业执照", "page": 5},
        {"no": "3-9", "name": "完税证明", "page": 40},
    ]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"
    assert e["found"] == 1  # 可归属部分仍计数
    assert match_attachments([req], prov)["extra"] == []  # 完税证明归组进父件,不再计 extra


def test_composite_zero_reference_is_missing_not_unknown():
    """完全没提供(零引用)→ 诚实 MISSING,不算分组失败。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]}
    e = match_attachments([req], [])["per_req"][0]
    assert e["status"] == "MISSING"


def test_composite_orphan_by_parent_name():
    """无父号时名称命中父名却归属不了子件 → UNKNOWN。"""
    req = {"no": "", "name": "资格审查文件", "sub_items": [{"no": "", "name": "营业执照"}]}
    prov = [{"no": "", "name": "资格审查文件（合并版）", "page": 7}]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["status"] == "UNKNOWN"


def test_flat_and_composite_mixed_pool_no_steal():
    """平件两级贪心先行,复合件只从剩余池归组;互不偷项。"""
    reqs = [
        {"no": "A-1", "name": "营业执照"},  # 平件,名称与 3 的子件同名
        {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]},
    ]
    prov = [
        {"no": "A-1", "name": "营业执照", "page": 2},
        {"no": "3-1", "name": "营业执照", "page": 5},
    ]
    out = match_attachments(reqs, prov)
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["per_req"][1]["status"] == "MATCHED"
    assert out["extra"] == []


# ── L2 P2:核对表投影 UNKNOWN/sub_results + 复合门加固 ──────────────────


def test_build_checklist_unknown_and_sub_results():
    """投影:UNKNOWN 进 counts.unknown;复合行带 sub_results;平件 sub_results=[]。"""
    reqs = [
        {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "3.1", "name": "营业执照"}]},
        {"no": "A-1", "name": "投标函"},
    ]
    prov = [{"no": "3-9", "name": "完税证明", "page": 40}, {"no": "A-1", "name": "投标函", "page": 2}]
    out = build_checklist(reqs, prov, bid_doc_id="投标文件.docx")
    assert out["counts"]["unknown"] == 1
    assert out["counts"]["required"] == 2
    assert out["items"][0]["sub_results"] == [{"no": "3.1", "name": "营业执照", "found": 0, "status": "MISSING"}]
    assert out["items"][1]["sub_results"] == []


def test_malformed_sub_items_falls_back_to_flat():
    """sub_items 非 dict 列表(LLM 脏值,如字符串)→ 不认复合件,平件编号通道命中,
    不得落进复合通道产出「MATCHED,found=0」矛盾态(或不连通名孤儿误判 UNKNOWN)。"""
    out = build_checklist(
        [{"no": "F-1", "name": "资质证书", "sub_items": "F-1 资质证书"}],
        [{"no": "F-1", "name": "资质证书", "page": 5}],
    )
    it = out["items"][0]
    assert it["status"] == "MATCHED"
    assert it["found"] == 1
    assert it["sub_results"] == []
    assert out["counts"]["unknown"] == 0


def test_composite_sub_dot_form_sole_channel():
    """{父号}.{序} 点式通道独立成立:子件自身 no 为空(①通道死)、名称完全不同
    (③通道死),仅靠位置点式命中;父行不得 UNKNOWN/MISSING。"""
    req = {"no": "3", "name": "资格审查文件", "sub_items": [{"no": "", "name": "完全不同的名称"}]}
    prov = [{"no": "3.1", "name": "另一名称", "page": 7}]
    e = match_attachments([req], prov)["per_req"][0]
    assert e["found"] == 1
    assert e["sub_results"][0]["status"] == "MATCHED"
    assert e["status"] == "MATCHED"
    assert match_attachments([req], prov)["extra"] == []
