"""P1 几何层: rebuild_grid 聚类四场景 + 胶合病征 + 缓存 tokens 容错 +
cli 病征触发两版比对(计划 Task 2/3/4;spec 2026-09-19 §2)。"""

import json
from types import SimpleNamespace

from scripts.cli import _extract_from_tables, _table_ok_rate
from scripts.geometry_rebuild import has_glue_symptom, rebuild_grid
from scripts.seed_library import DEFAULT_TABLE_SEEDS

SEEDS = DEFAULT_TABLE_SEEDS

_TOK_H = 0.02  # 统一 token 高度(页归一化) → 带宽=0.6*0.02=0.012, 并格阈值=0.006


def _tok(text, x1, x2, y1, y2=None):
    return {"text": text, "box": [x1, y1, x2, y2 if y2 is not None else y1 + _TOK_H], "score": 0.99}


# 7 列骨架 x 带(相邻列间隙 0.02 > 带宽 0.012 → 各列独立成带)
_X = [(0.02, 0.06), (0.08, 0.20), (0.22, 0.26), (0.28, 0.36), (0.38, 0.46), (0.48, 0.56), (0.58, 0.70)]
# 3 行 y 带顶(行间隙 0.04 >> 带宽)
_Y = [0.10, 0.16, 0.22]


def _grid_tokens(texts):
    """texts[r][c] 文本矩阵 → 逐格 token(None 跳格);box 略缩进格带内。"""
    out = []
    for r, row in enumerate(texts):
        for c, txt in enumerate(row):
            if txt is None:
                continue
            x1, x2 = _X[c]
            out.append(_tok(txt, x1 + 0.001, x2 - 0.001, _Y[r]))
    return out


# ── Task 3: rebuild_grid 四场景 ──────────────────────────────────────────────


def test_rebuild_multi_row_header():
    """场景1: '调整后' token 纵跨2行带 → 顶部两行该列内容同置
    (下游 _collapse_header 负责合并,此处只要求 token 各落其带)。"""
    texts = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", None, "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", None, "989.75"],
    ]
    toks = _grid_tokens(texts)
    x1, x2 = _X[5]
    toks.append(_tok("调整后", x1 + 0.001, x2 - 0.001, 0.10, 0.18))  # 高 token, 纵跨 r0+r1
    rows, cbbs = rebuild_grid(toks)
    assert rows is not None
    assert len(rows) == 2
    assert rows[0][5] == "调整后"
    assert rows[1][5] == "调整后"
    assert cbbs[0][5] == [x1 + 0.001, 0.10, x2 - 0.001, 0.18]  # 与 token 框同构
    assert rows[1][1] == "平整场地"


def test_rebuild_splits_glued_tokens():
    """场景2: 同列带内两 token x-gap >= 带宽*0.5 → 两格('3466 84605.06' 胶合
    天然消失);对照: 撕裂小数 x-gap < 阈值 → 并回一格。"""
    texts = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "名称A", "m2", None, "1.07", "1.20", "989.75"],
        ["2", "名称B", "m3", None, "8.27", "9.00", "3654.81"],
    ]
    toks = _grid_tokens(texts)
    # r1 工程量带: 胶合对 gap 0.010 >= 0.006 并格阈值 → 两格
    toks.append(_tok("3466", 0.285, 0.305, _Y[1]))
    toks.append(_tok("84605.06", 0.315, 0.355, _Y[1]))
    # r2 工程量带: 撕裂对 gap 0.001 < 0.006 → 并一格 '83.91'
    toks.append(_tok("83.", 0.285, 0.300, _Y[2]))
    toks.append(_tok("91", 0.301, 0.315, _Y[2]))
    rows, _cbbs = rebuild_grid(toks)
    assert rows is not None
    assert rows[1][3:5] == ["3466", "84605.06"]
    assert rows[1][5] == "1.07"
    assert rows[2][3] == "83.91"
    assert rows[2][4] == "8.27"


def test_rebuild_colspan_placeholder():
    """场景3: 一个 token 横跨2列带 → colspan: 占左格,右格占位空串
    (与 PP-Structure 展开语义一致)。"""
    texts = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", None, None, "1.20", "989.75"],  # c3/c4 被合并格覆盖
    ]
    toks = _grid_tokens(texts)
    toks.append(_tok("含税小计", 0.281, 0.459, _Y[1]))  # 横跨 c3[0.28,0.36]+c4[0.38,0.46]
    rows, _cbbs = rebuild_grid(toks)
    assert rows is not None
    assert rows[1][3] == "含税小计"
    assert rows[1][4] == ""  # 占位空串
    assert rows[1][5] == "1.20"


def test_rebuild_stable_columns_under_drift():
    """场景4: 三行同类 token x-center 微漂(±带宽*0.2) → 仍落同一列索引。"""
    x3 = [(0.02, 0.06), (0.08, 0.20), (0.22, 0.26)]
    toks = []
    grid = [("项目名称", "工程量", "单位"), ("货物甲", "1.20", "m2"), ("货物乙", "9.00", "m3")]
    for r, cells in enumerate(grid):
        drift = (r - 1) * 0.2 * 0.012  # ±带宽*0.2
        for c, txt in enumerate(cells):
            toks.append(_tok(txt, x3[c][0] + 0.001 + drift, x3[c][1] - 0.001 + drift, _Y[r]))
    rows, _cbbs = rebuild_grid(toks)
    assert rows is not None
    assert [row[1] for row in rows] == ["工程量", "1.20", "9.00"]


def test_rebuild_rejects_degenerate():
    """列数 < 3 或无 token → (None, None) 放弃(调用方退回原表)。"""
    assert rebuild_grid([]) == (None, None)
    assert rebuild_grid(None) == (None, None)
    toks = [_tok("a", 0.05, 0.10, 0.10), _tok("b", 0.15, 0.20, 0.10), _tok("c", 0.05, 0.10, 0.16)]
    assert rebuild_grid(toks) == (None, None)  # 仅两列


def test_has_glue_symptom():
    """P-1: 含 ≥2 个空格分隔可解析数字的行 → True;纯文本/独立数值格 → False。"""
    assert has_glue_symptom([["品名", "3466 84605.06"]]) is True
    assert has_glue_symptom([["纯文本行", "无数字"]]) is False
    assert has_glue_symptom([["824.79", "1.20"]]) is False  # 独立格不触发
    assert has_glue_symptom([]) is False


# ── Task 2: skill 侧 token 接收 + 缓存 v2 容错 ───────────────────────────────


def test_from_cache_tolerates_missing_tokens():
    """旧缓存无 tokens 键 → 空列表(零回归);新缓存往返保留 tokens。"""
    from scripts.document_parser import from_cache, to_cache

    legacy = {"tables": [{"page_no": 1, "table_idx": 0, "rows": [["a"]]}], "page_texts": {}}
    tables, _pt, _fixed = from_cache(legacy)
    assert tables[0].tokens == []

    from scripts.document_parser import TableExtract

    t = TableExtract(
        page_no=1, table_idx=0, bbox=[0, 0, 1, 1], rows=[["a"]], cell_bboxes=[],
        page_preview_b64="", tokens=[{"text": "a", "box": [0.1, 0.1, 0.2, 0.2], "score": 0.9}],
    )
    data = json.loads(json.dumps(to_cache([t], {})))  # JSON 严进严出
    t2, _pt, _fixed = from_cache(data)
    assert t2[0].tokens == t.tokens


def test_norm_tokens_normalizes_to_page():
    """OCR 服务 tokens(页绝对像素) → 页归一化 0~1(与 cell_bboxes 同规格);
    缺页宽高/旧服务无 tokens → 空列表(几何层自然放弃)。"""
    from scripts.document_parser import _norm_tokens

    raw = [{"text": "83.91", "box": [100, 50, 200, 70], "score": 0.98}]
    out = _norm_tokens(raw, 1000, 500)
    assert out[0]["box"] == [0.1, 0.1, 0.2, 0.14]
    assert out[0]["text"] == "83.91"
    assert _norm_tokens(raw, 0, 0) == []
    assert _norm_tokens(None, 1000, 500) == []


# ── Task 4: cli 病征触发 + 两版比对 ──────────────────────────────────────────


def _tbl(rows, page_no=1, table_idx=0, conf=0.9, tokens=None):
    ns = SimpleNamespace(
        page_no=page_no, table_idx=table_idx, rows=rows, cell_bboxes=None,
        page_preview_b64="", mean_confidence=conf,
    )
    if tokens is not None:
        ns.tokens = tokens
    return ns  # 无 tokens 属性 = 旧缓存表(几何层零干预路径)


def test_table_ok_rate():
    assert _table_ok_rate([]) == 0.0
    items = [{"validation_status": "ok"}, {"validation_status": "needs_review"}, {"validation_status": "ok"}]
    assert abs(_table_ok_rate(items) - 2 / 3) < 1e-9


def test_geometry_probe_triggers_on_nr_and_wins():
    """触发 fixture: 原表行2单价格被费用碎片 53.00 占位 → 行内无自洽结构 →
    needs_review(NR 0.5 > 0.30 触发 P-2);tokens 重建出干净网格(9.00×406.09≈
    3654.81 算术自洽)→ ok 率 1.0 > 0.5 → 采纳重建版,geometry_rebuilt 置位。"""
    orig_rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "53.00", "3654.81"],
    ]
    rebuilt_texts = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
    ]
    items, meta = _extract_from_tables(
        [_tbl(orig_rows, tokens=_grid_tokens(rebuilt_texts))], "s3://b/k.pdf", SEEDS
    )
    assert meta["geometry_rebuilt"] is True
    assert meta["geometry_rebuilt_tables"][0]["page"] == 1
    assert meta["geometry_rebuilt_tables"][0]["table_idx"] == 0
    assert len(items) == 2
    assert all(it["validation_status"] == "ok" for it in items)
    assert items[1]["goods_name"] == "回填方"
    assert items[1]["unit_price"] == 9.00


def test_geometry_probe_zero_intervention_on_healthy_table():
    """零干预 fixture: 桂北式健康表 + tokens(无任一病征) → 不重建,
    与无 tokens 运行逐项一致(bug-3400/3409 fixture 比特不变路径)。"""
    rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
    ]
    items_with, meta_with = _extract_from_tables([_tbl(rows, tokens=_grid_tokens(rows))], "s3://b/k.pdf", SEEDS)
    items_wo, meta_wo = _extract_from_tables([_tbl(rows)], "s3://b/k.pdf", SEEDS)
    assert meta_with.get("geometry_rebuilt") is None
    assert meta_wo.get("geometry_rebuilt") is None
    assert items_with == items_wo
    assert len(items_with) == 2
    assert all(it["validation_status"] == "ok" for it in items_with)
