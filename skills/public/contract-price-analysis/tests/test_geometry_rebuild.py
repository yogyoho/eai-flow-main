"""P1 几何层: rebuild_grid 聚类四场景 + 胶合病征 + 缓存 tokens 容错 +
cli 病征触发两版比对(计划 Task 2/3/4;spec 2026-09-19 §2)。"""

import json
from pathlib import Path
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
# 行 y 带顶(行间隙 0.04 >> 带宽);r3 供合计行 fixture(P-4);8 行供 r7/r8 漂移 fixture
_Y = [0.10 + 0.06 * i for i in range(8)]


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


# ── P-4 合计闭环病征(Σ(q×u) vs 打印合计;wf 待办 2026-09-20) ──────────────────


def test_totals_closure_gap_helper():
    """病征度量: Σ(q×u) vs 最好候选打印合计;无合计行/全缺量 → None。

    spec ±0.2% 候选语义 + 自定绝对下限 100元: 闭表(分位级舍入差,绝对
    0.002元)与无候选同样返回 None=不作病征;量合计与总计同印时取相对
    更近的候选(候选集语义)。"""
    from scripts.cli import _totals_closure_gap

    rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["", "合计", "", "", "", "", "4644.56"],
    ]
    items_closed = [
        {"quantity": 824.79, "unit_price": 1.20},
        {"quantity": 406.09, "unit_price": 9.00},
    ]
    # 闭到分位舍入差(绝对 0.002元 < 100元下限)→ 不作病征
    assert _totals_closure_gap(rows, items_closed) is None
    items_broken = [
        {"quantity": 824.79, "unit_price": 1.20},
        {"quantity": 406.09, "unit_price": 53.00},  # 错值行照样算术"可用"——闭环破
    ]
    assert _totals_closure_gap(rows, items_broken) > 0.005
    assert _totals_closure_gap(rows[:2], items_closed) is None  # 无合计行
    assert _totals_closure_gap(rows, [{"quantity": None, "unit_price": 1.20}]) is None


def test_totals_closure_gap_candidate_and_abs_floor():
    """候选集语义: 合计行同印量合计与金额合计,Σ 靠近量合计也算闭(不病征);
    绝对下限: 小表相对偏差大但绝对差 <100元 → None,同形态 ≥100元 → 病征。"""
    from scripts.cli import _totals_closure_gap

    rows_multi = [
        ["序号", "项目名称", "单位", "工程量", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "9.00", "3654.81"],
        ["", "合计", "", "1230.88", "", "4644.56"],  # 同印量合计 1230.88
    ]
    items = [
        {"quantity": 824.79, "unit_price": 1.20},
        {"quantity": 406.09, "unit_price": 9.00},
    ]
    assert _totals_closure_gap(rows_multi, items) is None  # 命中金额候选 → 静默
    rows_small = [
        ["序号", "项目名称", "含税单价", "含税合价"],
        ["1", "平整场地", "1.20", "490.00"],
        ["", "合计", "", "500.00"],  # Σ=490: rel 2% 但绝对差 10元 < 100元
    ]
    assert _totals_closure_gap(rows_small, [{"quantity": 408.33, "unit_price": 1.20}]) is None
    rows_mid = [
        ["序号", "项目名称", "含税单价", "含税合价"],
        ["1", "场地", "1.20", "600.00"],
        ["", "合计", "", "500.00"],  # Σ=600: rel 20%,绝对差 100元 ≥ 下限 → 病征
    ]
    assert _totals_closure_gap(rows_mid, [{"quantity": 500.0, "unit_price": 1.20}]) > 0.002


def test_geometry_probe_p4_triggers_and_marks_symptom():
    """P-4 触发: 原表 r2 单价 53.00(NR 0.5 亦过阈)+合计行 4644.56 闭环破 →
    P4 入 symptoms;重建版闭环恢复且 ok 率更高 → 采纳。"""
    orig_rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "53.00", "3654.81"],
        ["", "合计", "", "", "", "", "4,644.56"],
    ]
    rebuilt_texts = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
        ["", "合计", "", "", "", "", "4,644.56"],
    ]
    items, meta = _extract_from_tables(
        [_tbl(orig_rows, tokens=_grid_tokens(rebuilt_texts))], "s3://b/k.pdf", SEEDS
    )
    assert meta["geometry_rebuilt"] is True
    symptoms = meta["geometry_rebuilt_tables"][0]["symptoms"]
    assert "P4" in symptoms
    assert len(items) == 2  # 合计行不入库
    assert all(it["validation_status"] == "ok" for it in items)
    assert items[1]["unit_price"] == 9.00


def test_geometry_probe_p4_silent_on_closed_table():
    """零干预守卫: 提取正确、合计闭环(偏差<0.5%)的表不因 P-4 触发重建,
    与无 tokens 运行逐项一致。"""
    rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
        ["2", "回填方", "m3", "406.09", "8.27", "9.00", "3654.81"],
        ["", "合计", "", "", "", "", "4,644.56"],
    ]
    items_with, meta_with = _extract_from_tables([_tbl(rows, tokens=_grid_tokens(rows))], "s3://b/k.pdf", SEEDS)
    items_wo, meta_wo = _extract_from_tables([_tbl(rows)], "s3://b/k.pdf", SEEDS)
    assert meta_with.get("geometry_rebuilt") is None
    assert meta_wo.get("geometry_rebuilt") is None
    assert items_with == items_wo
    assert len(items_with) == 2


# ── P-4 活体形态: 木饰面 p2/t0 行网格漂移(bug-3427,wf 待办 2026-09-20) ────────
# fixture=容器 OCR 缓存 52bce87c… p2/t0 真实行(截前10列,tests/fixtures/):
# r7 深灰色大理石 综合单价/含税总价 空值,真值(535, 71732.8)漂到 r8;r8 真值
# (258, 95978.58)漂到 r9;r9 真值(258, 2479.38)与 r10 自值胶成 '258 572'/
# '2479.38 11880.44';r12 真值(542, 17717.98)漂到 r13 与 '2217.2' 同格。
# 印刷小计 8440883.64 = 27 行真值合计(独立算术锚)。漂移差值近抵消: 提取
# Σ(q×u)=8,472,197.61,与打印小计相对偏差仅 0.371%——旧 0.5% 阈下 P-4 永不
# 触发;0.2% 候选语义下命中。该真表的表头跨列表格(cellspan)+稀疏合计行使
# rebuild_grid 列带塌缩(输出锯齿行,roles 左移),重建版行级算术不成立 →
# 两版比对如实落败取原版(诚实 needs_review);影子管线不带闭环重推后,
# 『闭环≠正确』的假 ok 率无法买通采纳门。真值归位交由 --re-ocr 后的新
# 网格/行级仲裁与活体验收裁决。

_FIXTURE = Path(__file__).parent / "fixtures" / "msm_p2_drift_rows.json"
_MSM_DRIFT_ROWS = json.loads(_FIXTURE.read_text(encoding="utf-8"))

# 真值归位映射(行量×综合单价=含税总价 可独立验证): 综合单价/含税总价 回行
_MSM_REALIGN = {
    7: {8: "535", 9: "71732.8"},
    8: {8: "258", 9: "95978.58"},
    9: {8: "258", 9: "2479.38"},
    10: {8: "572", 9: "11880.44"},
    12: {8: "542", 9: "17717.98"},
    13: {9: "2217.2"},
}

# 10 列 x 带(列间隙 0.02 > 带宽 0.012 → 各列独立成带);token 宽=真实 OCR
# 文本行宽(带内居中窄框,非整格)。
_MSM_X = [
    (0.02, 0.05), (0.07, 0.24), (0.26, 0.40), (0.42, 0.46), (0.48, 0.56),
    (0.58, 0.64), (0.66, 0.70), (0.72, 0.78), (0.80, 0.86), (0.88, 0.96),
]


def _msm_tokens(matrix):
    """对齐文本矩阵 → 页归一化窄框 tokens(行距 0.06 >> 带宽;缺格=空 cell)。"""
    toks = []
    for r, row in enumerate(matrix):
        y1 = 0.10 + 0.06 * r
        for c, txt in enumerate(row):
            if not str(txt or "").strip():
                continue
            x1, x2 = _MSM_X[c]
            cx, w = (x1 + x2) / 2, x2 - x1
            hw = min(w * 0.30, 0.006 * max(1, len(str(txt))))
            toks.append({"text": str(txt), "box": [cx - hw, y1, cx + hw, y1 + 0.02], "score": 0.99})
    return toks


def _msm_realigned_matrix():
    matrix = [list(r) for r in _MSM_DRIFT_ROWS]
    for ri, cols in _MSM_REALIGN.items():
        for c, txt in cols.items():
            matrix[ri][c] = txt
    return matrix


def _raw_extract(rows, page_no=2):
    """closure_refill=False 的裸提取(病征层/恢复前的诚实状态)。"""
    from scripts.cli import _matched_table_pass
    from scripts.table_classifier import match_seed
    from scripts.seed_library import normalize_seeds

    seeds = normalize_seeds(SEEDS)
    hit = match_seed(rows, seeds)
    tbl = _tbl(rows, page_no=page_no)
    items, meta = [], {
        "tables_found": 0, "goods_tables": 0, "continuation_tables": 0,
        "rows_extracted": 0, "skipped": {}, "unmatched_tables": [], "matched_seeds": {},
    }
    _matched_table_pass(tbl, "s3://b/msm.pdf", hit, None, None, {}, items, meta, closure_refill=False)
    return items, meta


def test_p4_gap_fires_on_real_msm_drift_form():
    """恢复前: P-4 病征在真漂移形态上命中——Σ(q×u)=8,472,197.61 vs 打印小计
    8,440,883.64 → 相对偏差 0.371% > 0.2%(旧 0.5% 阈永不触发,bug-3427 逃检根因);
    量合计 35421.48 同印不干扰(候选集语义)。"""
    from scripts.cli import _totals_closure_gap

    items, _meta = _raw_extract(_MSM_DRIFT_ROWS)
    got = sum(it["quantity"] * it["unit_price"] for it in items if it.get("quantity") and it.get("unit_price"))
    assert abs(got - 8472197.61) < 0.01
    gap = _totals_closure_gap(_MSM_DRIFT_ROWS, items)
    assert gap is not None and gap > 0.002


def test_p4_msm_real_form_drift_pairs_recovered():
    """真表形态恢复: r7 深灰色大理石 u=535(不再 NULL)/r8 水磨石浅色光面
    u=258,均 ok(行漂移对位恢复);r9-r27 值不动;Σ(q×u)=印刷小计
    8,440,883.64 精确闭环;27 行全 ok;无需重建(恢复先于病征消费掉间隙)。"""
    items, meta = _extract_from_tables([_tbl(_MSM_DRIFT_ROWS, page_no=2)], "s3://b/msm.pdf", SEEDS)
    assert meta.get("geometry_rebuilt") is None
    assert len(items) == 27
    assert all(it["validation_status"] == "ok" for it in items)
    by_row = {it["source_row_idx"]: it for it in items}
    assert by_row[7]["unit_price"] == 535.0 and by_row[7]["price_reason"] == "行漂移对位恢复"
    assert by_row[8]["unit_price"] == 258.0 and by_row[8]["price_reason"] == "行漂移对位恢复"
    assert by_row[9]["unit_price"] == 258.0 and by_row[10]["unit_price"] == 572.0
    assert by_row[12]["unit_price"] == 542.0 and by_row[13]["unit_price"] == 460.0
    got = sum(it["quantity"] * it["unit_price"] for it in items)
    assert abs(got - 8440883.64) <= 0.002 * 8440883.64


# ── P-4 机制正向形态: 同型漂移 + 列一致网格(tokens 归位 → 重建胜出) ──────────
# 真值同取木饰面 r7-r10 五行(值可比对活体数据);网格全行满格(无 cellspan
# 表头/稀疏合计行)→ rebuild_grid 列带不塌缩,验证『P-4 命中 → 重建归位 →
# 两版比对采纳』机制本身。印刷合计 183,060.95 = 5 行真值合计(量合计
# 1361.26 同印,候选集语义)。

_P4V = [
    ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
    ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ["2", "深灰色大理石", "m2", "134.08", "473.45", "", ""],
    ["3", "水磨石浅色光面", "m2", "372.01", "228.32", "535", "71732.8"],
    ["4", "水磨石深色光面台面", "m2", "9.61", "228.32", "258", "95978.58"],
    ["5", "白色大理石", "m2", "20.77", "506.19", "258 572", "2479.38 11880.44"],
    ["", "合计", "", "1361.26", "", "", "183,060.95"],
]
_P4V_ALIGNED = [
    ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
    ["1", "平整场地", "m2", "824.79", "1.07", "1.20", "989.75"],
    ["2", "深灰色大理石", "m2", "134.08", "473.45", "535", "71732.8"],
    ["3", "水磨石浅色光面", "m2", "372.01", "228.32", "258", "95978.58"],
    ["4", "水磨石深色光面台面", "m2", "9.61", "228.32", "258", "2479.38"],
    ["5", "白色大理石", "m2", "20.77", "506.19", "572", "11880.44"],
    ["", "合计", "", "1361.26", "", "", "183,060.95"],
]


def test_geometry_probe_p4_drift_shape_reassign_recovers():
    """同型漂移(P4V,列一致网格)无 tokens 亦恢复: r2(『r7』)u=535 不再 NULL、
    r3(『r8』)u=258——对位恢复不需要 tokens;Σ 闭环 ±0.2%;r4 总价格被漂占
    (真值 u 已对)如实 needs_review 不强改。"""
    items, meta = _extract_from_tables([_tbl(_P4V)], "s3://b/msm.pdf", SEEDS)
    assert meta.get("geometry_rebuilt") is None
    assert len(items) == 5
    by_name = {it["goods_name"]: it for it in items}
    assert by_name["深灰色大理石"]["unit_price"] == 535.0
    assert by_name["深灰色大理石"]["price_reason"] == "行漂移对位恢复"
    assert by_name["水磨石浅色光面"]["unit_price"] == 258.0
    assert by_name["水磨石浅色光面"]["price_reason"] == "行漂移对位恢复"
    assert by_name["水磨石深色光面台面"]["unit_price"] == 258.0
    assert by_name["白色大理石"]["unit_price"] == 572.0
    got = sum(it["quantity"] * it["unit_price"] for it in items)
    assert abs(got - 183060.95) <= 0.002 * 183060.95


def test_geometry_probe_p4_bad_anchor_gate_keeps_honest():
    """采纳门(全有或全无): 打印合计锚错误(190,000≠真值合计 183,060.95)→
    对位恢复整链回滚(诚实 needs_review 不动);tokens 复刻漂移网格 → 重建
    平手取原版,geometry_rebuilt 不置位——双层都不以假闭环放水。"""
    bad_anchor = [list(r) for r in _P4V]
    bad_anchor[-1] = ["", "合计", "", "1361.26", "", "", "190,000.00"]
    items, meta = _extract_from_tables(
        [_tbl(bad_anchor, tokens=_grid_tokens([list(r) for r in _P4V]))], "s3://b/msm.pdf", SEEDS
    )
    assert meta.get("geometry_rebuilt") is None
    by_name = {it["goods_name"]: it for it in items}
    assert by_name["深灰色大理石"]["unit_price"] is None
    assert by_name["深灰色大理石"]["validation_status"] == "needs_review"
    assert by_name["水磨石浅色光面"]["unit_price"] == 535.0
    assert by_name["水磨石浅色光面"]["validation_status"] == "needs_review"
    assert not any(it.get("price_reason") == "行漂移对位恢复" for it in items)
