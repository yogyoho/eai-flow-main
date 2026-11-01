"""L2 P1 附件清单匹配器测试(spec 2026-11-02 §2):normalize_name 归一 +
match_attachments 两级精确匹配(①编号精确双方非空 ②规范化名称全等,非包含——
防「报价表」吞「分项报价表」),贪心一对一;found==0→MISSING,min_count 且
found<min_count→PARTIAL,否则 MATCHED;未匹配提供项→extra。"""

from app.extensions.bid_review.engine.attachments import normalize_name, match_attachments


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
    out = match_attachments([_req(no="ATT-E-008", name="类似业绩证明")],
                            [_prov(no="ATT-E-008", name="业绩合同扫描件", page=118)])
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
    out = match_attachments([_req(no="D-1", name="投标函")],
                            [_prov(no="D-1", name="投标函", page=1), _prov(no="", name="企业宣传册", page=310)])
    assert out["per_req"][0]["status"] == "MATCHED"
    assert out["extra"] == [{"no": "", "name": "企业宣传册", "page": 310}]


def test_junk_and_none_inputs():
    out = match_attachments(None, None)
    assert out == {"per_req": [], "extra": []}
    out = match_attachments(["垃圾", {"no": "E-1", "name": "授权书"}], ["垃圾", {"no": "E-1", "name": "授权书"}])
    assert out["per_req"][0]["status"] == "MATCHED"
