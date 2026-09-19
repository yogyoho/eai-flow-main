"""P2 LLM 兜底: annotate_roles 列语义标注 + try_llm_fallback 验收门 +
cli 触发 wiring(计划 Task 6/7;spec 2026-09-19 §3)。

铁律(spec §1): LLM 只标注列语义,永不生成价格数值——条目值一律由确定性
提取+仲裁产生。缺省(--llm-* 不传 / service 未配三元组)层关闭,行为零变化。"""

from types import SimpleNamespace

import scripts.llm_fallback as llm_fallback
from scripts.cli import _extract_from_tables
from scripts.llm_fallback import ROLE_ENUM, annotate_roles, try_llm_fallback
from scripts.seed_library import DEFAULT_TABLE_SEEDS

SEEDS = DEFAULT_TABLE_SEEDS
CFG = {"base_url": "http://llm.test/v1", "api_key": "sk-test", "model": "m1"}

# 无 seed 确认的表(name/价格锚均不命中任何内置 seed)→ strict seed-only 下
# 落 unmatched_tables,是 LLM 兜底的头号目标。
_ROWS_UNMATCHED = [
    ["材料名称", "工程量", "报价单价", "金额小计"],
    ["螺纹钢", "10", "3500.00", "35000.00"],
    ["水泥", "100", "400.00", "40000.00"],
]
_GOOD_MAPPING = '{"0": "name", "1": "qty", "2": "price_unit", "3": "price_total"}'


class _Resp:
    def __init__(self, content="", status=200):
        self.status_code = status
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _tbl(rows, page_no=1, table_idx=0):
    return SimpleNamespace(
        page_no=page_no,
        table_idx=table_idx,
        rows=rows,
        cell_bboxes=None,
        page_preview_b64="",
        mean_confidence=0.9,
    )


# ── Task 6: annotate_roles ───────────────────────────────────────────────────


def test_role_enum_contract():
    """角色枚举即 seed 列角色全集(与 table_classifier._ROLE_ORDER 同构)。"""
    assert ROLE_ENUM == ["name", "spec", "qty", "unit", "price_unit", "price_total", "price_untaxed"]


def test_annotate_roles_valid_mapping(monkeypatch):
    """合法映射 JSON(带 ```json 围栏/前后说明)→ {列索引: 角色};
    请求契约: POST {base}/chat/completions, temperature=0, max_tokens=500, Bearer key。"""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers or {}, json=json, timeout=timeout)
        return _Resp('好的,标注如下```json\n{"0": "name", "1": "qty", "2": "unit", "3": "price_unit", "4": "price_total"}\n```完')

    monkeypatch.setattr(llm_fallback.httpx, "post", fake_post)
    roles = annotate_roles(
        ["货物名称", "数量", "单位", "单价", "合价"],
        [["钢筋", "10", "t", "3500", "35000"]],
        "http://llm.test/v1/",
        "sk-test",
        "m1",
    )
    assert roles == {0: "name", 1: "qty", 2: "unit", 3: "price_unit", 4: "price_total"}
    assert captured["url"] == "http://llm.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["temperature"] == 0
    assert captured["json"]["max_tokens"] == 500
    assert captured["json"]["model"] == "m1"


def test_annotate_roles_bad_json_and_timeout(monkeypatch):
    """坏 JSON / 超时 → None;传输/解析失败重试 ≤1 次(共 2 次调用,spec §3)。"""
    calls = {"n": 0}

    def bad_json(url, **kw):
        calls["n"] += 1
        return _Resp("抱歉，我无法输出该内容。")

    monkeypatch.setattr(llm_fallback.httpx, "post", bad_json)
    assert annotate_roles(["名称", "单价"], [["x", "1"]], "http://x", None, "m") is None
    assert calls["n"] == 2

    def timeout(url, **kw):
        calls["n"] += 1
        raise llm_fallback.httpx.TimeoutException("timed out")

    monkeypatch.setattr(llm_fallback.httpx, "post", timeout)
    assert annotate_roles(["名称", "单价"], [["x", "1"]], "http://x", None, "m") is None
    assert calls["n"] == 4


def test_annotate_roles_requires_name_and_price(monkeypatch):
    """缺 name 或 (price_unit|price_total) → None;角色枚举外的值丢弃不致命。"""
    monkeypatch.setattr(llm_fallback.httpx, "post", lambda url, **kw: _Resp('{"1": "qty"}'))
    assert annotate_roles(["数量"], [["3"]], "http://x", None, "m") is None

    monkeypatch.setattr(
        llm_fallback.httpx,
        "post",
        lambda url, **kw: _Resp('{"0": "name", "1": "qty", "2": "颜色", "3": "price_total"}'),
    )
    roles = annotate_roles(["名称", "数量", "颜色", "合价"], [["a", "1", "红", "2"]], "http://x", None, "m")
    assert roles == {0: "name", 1: "qty", 3: "price_total"}


# ── Task 6: try_llm_fallback 验收门 ──────────────────────────────────────────


def test_try_llm_fallback_adopts_good_mapping(monkeypatch):
    """合法映射 → 确定性提取+仲裁后行级 ok 率 1.0 ≥0.90 → 采纳;
    产出条目值由确定性提取产生(名称/单价即表内字面值),meta 带 llm_roles。"""
    monkeypatch.setattr(llm_fallback.httpx, "post", lambda url, **kw: _Resp(_GOOD_MAPPING))
    items, active, meta = try_llm_fallback(_tbl(_ROWS_UNMATCHED), SEEDS, "s3://b/k.pdf", CFG)
    assert items is not None and len(items) == 2
    assert all(it["validation_status"] == "ok" for it in items)
    assert items[0]["goods_name"] == "螺纹钢"
    assert items[0]["unit_price"] == 3500.0
    assert items[0]["quantity"] == 10.0
    assert meta["llm_roles"] == {0: "name", 1: "qty", 2: "price_unit", 3: "price_total"}
    assert active is not None  # 续表继承上下文(LLM 角色可传给续页)


def test_try_llm_fallback_gate_rejects_low_ok_rate(monkeypatch):
    """验收门: 错映射(单价标到非数值备注列)→ validate 失败且行内算术不可恢复
    → 零可用条目 → ok 率 0 <0.90 → 不采纳 (None, None, {})。"""
    rows_unrecoverable = [
        ["材料名称", "备注", "合格证明", "金额"],
        ["螺纹钢", "合格", "有", "35000.00"],
        ["水泥", "合格", "有", "40000.00"],
    ]
    monkeypatch.setattr(
        llm_fallback.httpx, "post", lambda url, **kw: _Resp('{"0": "name", "1": "price_unit"}')
    )
    items, active, meta = try_llm_fallback(_tbl(rows_unrecoverable), SEEDS, "s3://b/k.pdf", CFG)
    assert items is None
    assert active is None
    assert meta == {}


def test_try_llm_fallback_unreachable_returns_none(monkeypatch):
    """LLM 不可达 → (None, None, {}),不阻塞管线(spec §6)。"""

    def unreachable(url, **kw):
        raise llm_fallback.httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm_fallback.httpx, "post", unreachable)
    items, active, meta = try_llm_fallback(_tbl(_ROWS_UNMATCHED), SEEDS, "s3://b/k.pdf", CFG)
    assert items is None and active is None and meta == {}


def test_try_llm_fallback_requires_cfg_and_header():
    """层关闭(llm_cfg=None)或无表头(续表)→ 直接放弃,零 LLM 调用。"""
    items, active, meta = try_llm_fallback(_tbl(_ROWS_UNMATCHED), SEEDS, "s3://b/k.pdf", None)
    assert items is None and active is None and meta == {}
    headerless = _tbl([["螺纹钢", "10", "3500.00", "35000.00"]])  # 无表头数据行
    items, active, meta = try_llm_fallback(headerless, SEEDS, "s3://b/k.pdf", CFG)
    assert items is None and active is None and meta == {}


# ── Task 7: cli 触发 wiring ──────────────────────────────────────────────────


def test_cli_unmatched_table_adopted_via_llm(monkeypatch):
    """unmatched 表 + llm_cfg → 采纳路径: 条目正常提取落库、unmatched_tables
    移除、parse_meta.llm_roles 留痕(trigger=unmatched)。"""
    monkeypatch.setattr(llm_fallback.httpx, "post", lambda url, **kw: _Resp(_GOOD_MAPPING))
    items, meta = _extract_from_tables([_tbl(_ROWS_UNMATCHED)], "s3://b/k.pdf", SEEDS, llm_cfg=CFG)
    assert len(items) == 2
    assert all(it["validation_status"] == "ok" for it in items)
    assert meta["unmatched_tables"] == []  # 采纳表从 unmatched_tables 移除
    assert meta["goods_tables"] == 1
    assert meta["rows_extracted"] == 2
    entry = meta["llm_roles"][0]
    assert entry["page"] == 1
    assert entry["table_idx"] == 0
    assert entry["roles"] == {"0": "name", "1": "qty", "2": "price_unit", "3": "price_total"}
    assert entry["trigger"] == "unmatched"
    assert meta["matched_seeds"] == {"LLM兜底": 1}


def test_cli_unmatched_llm_rejected_keeps_unmatched_entry(monkeypatch):
    """门拒绝(错映射到非数值列,不可恢复)→ 整表维持 unmatched 现状,无
    llm_roles 留痕。"""
    rows_unrecoverable = [
        ["材料名称", "备注", "合格证明", "金额"],
        ["螺纹钢", "合格", "有", "35000.00"],
        ["水泥", "合格", "有", "40000.00"],
    ]
    monkeypatch.setattr(
        llm_fallback.httpx, "post", lambda url, **kw: _Resp('{"0": "name", "1": "price_unit"}')
    )
    items, meta = _extract_from_tables([_tbl(rows_unrecoverable)], "s3://b/k.pdf", SEEDS, llm_cfg=CFG)
    assert items == []
    assert len(meta["unmatched_tables"]) == 1
    assert "llm_roles" not in meta
    assert meta["goods_tables"] == 0


def test_cli_llm_layer_off_zero_behavior_change(monkeypatch):
    """llm_cfg=None(缺省)→ 零 LLM 调用,行为与不带参数的现状逐项一致。"""

    def boom(url, **kw):
        raise AssertionError("LLM 层关闭时不得发起调用")

    monkeypatch.setattr(llm_fallback.httpx, "post", boom)
    items_off, meta_off = _extract_from_tables([_tbl(_ROWS_UNMATCHED)], "s3://b/k.pdf", SEEDS)
    items_none, meta_none = _extract_from_tables(
        [_tbl(_ROWS_UNMATCHED)], "s3://b/k.pdf", SEEDS, llm_cfg=None
    )
    assert items_off == items_none == []
    assert len(meta_off["unmatched_tables"]) == len(meta_none["unmatched_tables"]) == 1
    assert "llm_roles" not in meta_off and "llm_roles" not in meta_none


def test_cli_matched_nr_gt_50_adopted_via_llm(monkeypatch):
    """matched 表 NR>0.50 且几何不可用(无 tokens)→ LLM 兜底采纳:
    碎表头把 seed 含税单价锚钉在税率列(值 13/6 无行内自洽 → 全行 NR),
    LLM 按数据列样本纠正映射 → 算术自洽 1.0 ≥0.90 → 条目替换为 ok,
    llm_roles 留痕(trigger=matched_nr)。"""
    rows = [
        # 表头 5 列;数据行 7 列(数据行多出 单位/不含税单价 两列——rapid-table
        # 表头碎片化形态): seed price_unit 锚(含税单价,列3)取到税率值 13/6。
        ["序号", "项目名称", "工程量", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "13", "824.79", "1.20", "989.75"],
        ["2", "回填方", "m3", "6", "406.09", "9.00", "3654.81"],
    ]
    monkeypatch.setattr(
        llm_fallback.httpx,
        "post",
        lambda url, **kw: _Resp('{"1": "name", "4": "qty", "5": "price_unit", "6": "price_total"}'),
    )
    items, meta = _extract_from_tables([_tbl(rows)], "s3://b/k.pdf", SEEDS, llm_cfg=CFG)
    assert len(items) == 2
    assert all(it["validation_status"] == "ok" for it in items)
    assert items[0]["goods_name"] == "平整场地"
    assert items[0]["unit_price"] == 1.20
    assert items[0]["quantity"] == 824.79
    assert meta["llm_roles"][0]["trigger"] == "matched_nr"
    assert meta["llm_roles"][0]["roles"] == {
        "1": "name",
        "4": "qty",
        "5": "price_unit",
        "6": "price_total",
    }
    # 原表计数已在(命中路径),替换只调 rows_extracted 差额
    assert meta["matched_seeds"] == {"工程量清单计价表": 1}
    assert meta["rows_extracted"] == 2


def test_cli_matched_healthy_table_zero_llm(monkeypatch):
    """matched 健康表(NR=0)→ 不触发 LLM(即使层开启)。"""

    def boom(url, **kw):
        raise AssertionError("健康表不得发起 LLM 调用")

    monkeypatch.setattr(llm_fallback.httpx, "post", boom)
    rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
    ]
    items, meta = _extract_from_tables([_tbl(rows)], "s3://b/k.pdf", SEEDS, llm_cfg=CFG)
    assert len(items) == 2
    assert all(it["validation_status"] == "ok" for it in items)
    assert "llm_roles" not in meta


def test_cli_build_llm_cfg():
    """--llm-* 三元组 → cfg dict;缺省/任一缺失 → None=层关闭。"""
    from scripts.cli import _build_llm_cfg

    assert _build_llm_cfg(None, None, None) is None
    assert _build_llm_cfg("http://x", None, "m") is None
    assert _build_llm_cfg("http://x", "k", "m") == {
        "base_url": "http://x",
        "api_key": "k",
        "model": "m",
    }
