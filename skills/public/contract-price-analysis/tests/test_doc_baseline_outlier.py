"""F3b 文档基线分层 — _build_groups_db 离群判定的文档基线修正。

三个判定面(spec 2026-09-20):
1. 上浦式整文档中靶: 文档基线(文档内 ok/corrected 价中位)偏离簇中位 >= 12%
   → 整文档不逐行标红 + stats.baseline_notes 写 doc_baseline_exempt 注记;
2. 合同内真异常: 非豁免文档且文档内样本 >= 4 → 相对文档自身 Q3+1.5*IQR 改判,
   单行异常仍标红(保住"合同内抓错"能力);样本 < 4 沿用簇判定;
3. 反向失效治理: 簇 ok/corrected 样本 n<3 时 IQR 恒塌缩、数学上永不报离群
   → 写 insufficient_sample 簇级注记,别让"没判"冒充"查过没问题"。

fixture 数字全部按 stats._percentile 线性插值手算核过(见各测试内注释)。
"""

import itertools

from scripts.cli import _build_groups_db
from scripts.clustering.engine import ClusterResult

_SEQ = itertools.count()


def _item(price, doc, status="ok", name="螺纹钢"):
    return {
        "id": f"{doc}-{next(_SEQ)}",
        "goods_name": name,
        "tech_params": {},
        "category": None,
        "unit_price": price,
        "validation_status": status,
        "document_id": doc,
        "document_name": f"doc-{doc}.pdf",
    }


def _one_cluster(items, name="螺纹钢"):
    """把 items 全塞进一个簇(label=0)并跑 _build_groups_db。"""
    result = ClusterResult(labels=[0] * len(items), representatives={0: name})
    groups = _build_groups_db(result, items)
    assert len(groups) == 1
    return groups[0]


# 四文档混簇: docA=上浦式高价位整文档(3 行,≥豁免样本下限;整文档基线显著
# 偏离簇中位);docB=对齐簇中位、含一条 10x 真异常;docC/docD=小样本对齐文档
# (沿用簇判定)。簇 14 价: sorted=[4750, 4800×7, 4850×2, 7000, 7050, 7100,
# 48000] → median=4800,q1=4800,q3=6462.5 → 簇 fence≈8956。
FOUR_DOC_ITEMS = (
    [_item(p, "docA") for p in (7000, 7050, 7100)]
    + [_item(p, "docB") for p in (4800, 4800, 4800, 4800, 4800, 48000)]
    + [_item(p, "docC") for p in (4800, 4850)]
    + [_item(p, "docD") for p in (4750, 4800, 4850)]
)


def test_whole_doc_price_regime_exempt_with_note():
    """上浦式整文档中靶 → 不标红 + doc_baseline_exempt 注记。"""
    group = _one_cluster(list(FOUR_DOC_ITEMS))
    stats = group["stats"]
    assert stats["median"] == 4800

    doc_a = [m for m in group["items"] if m["document_id"] == "docA"]
    # 基线 7050 偏离簇中位 4800 达 46.9% ≥ 12% 且样本 3 ≥ 下限 → 整文档豁免。
    assert all(not m["is_outlier"] for m in doc_a)

    notes = stats["baseline_notes"]
    exempt = [n for n in notes if n["type"] == "doc_baseline_exempt"]
    assert len(exempt) == 1
    assert exempt[0]["document_id"] == "docA"
    assert exempt[0]["document_name"] == "doc-docA.pdf"
    assert exempt[0]["baseline"] == 7050.0
    assert exempt[0]["cluster_median"] == 4800
    assert exempt[0]["deviation"] == round(2250 / 4800, 4)
    assert exempt[0]["rows_exempt"] == 3
    assert "12%" in exempt[0]["message"]

    # 簇级 outlier_count 与最终逐行判定同步(只剩 48000 一条真异常)
    assert stats["outlier_count"] == 1


def test_exempt_needs_min_doc_sample():
    """豁免样本下限: 2 行文档的中位被任一单行拖着走,立不住"价位体系"——
    其高价行不得借豁免逃判,必须落回簇判定被抓。"""
    # docE=(4800, 12000): 若无下限,基线中位 8400 偏离 4800 达 75% → 假豁免,
    # 12000 逃判;有下限 → 不豁免,落回簇判定。
    items = (
        [_item(p, "docA") for p in (7000, 7050, 7100)]
        + [_item(p, "docB") for p in (4800, 4800, 4800, 4800, 4800, 48000)]
        + [_item(p, "docE") for p in (4800, 12000)]
        + [_item(p, "docD") for p in (4750, 4800, 4850)]
    )
    group = _one_cluster(items)
    exempt_ids = {
        n["document_id"] for n in group["stats"]["baseline_notes"] if n["type"] == "doc_baseline_exempt"
    }
    assert exempt_ids == {"docA"}  # docE 不在豁免名单
    doc_e = [m for m in group["items"] if m["document_id"] == "docE"]
    assert [m["unit_price"] for m in doc_e if m["is_outlier"]] == [12000]


def test_in_contract_anomaly_still_flagged():
    """合同内真异常: 非豁免文档 n>=4 → 相对文档自身 IQR 改判,单行仍标红。"""
    group = _one_cluster(list(FOUR_DOC_ITEMS))
    by_doc = {}
    for m in group["items"]:
        by_doc.setdefault(m["document_id"], []).append(m)

    # docB 基线 4800 偏离 0 → 不豁免;文档内 6 价 → doc fence: [4800×5, 48000]
    # q1=q3=4800 → IQR=0 → fence=4800 → 48000 标红,对齐行不标。
    doc_b = by_doc["docB"]
    flagged = [m for m in doc_b if m["is_outlier"]]
    assert len(flagged) == 1
    assert flagged[0]["unit_price"] == 48000

    # docC(2 价)/docD(3 价) 样本 < 4 → 沿用簇 fence 4925 → 全不标。
    for doc in ("docC", "docD"):
        assert all(not m["is_outlier"] for m in by_doc[doc])


def test_small_doc_above_cluster_fence_still_flagged():
    """小样本文档(n<4)走簇判定兜底: 文档内高价行仍被簇 fence 抓住。"""
    items = (
        [_item(p, "docA") for p in (7000, 7050, 7100)]  # 豁免档
        + [_item(p, "docB") for p in (4800, 4800, 4800, 4800, 4800, 48000)]
        # docE 小文档,含一条 12000 高价行: 簇 14 价 sorted=[4750, 4800×7,
        # 4850, 7000, 7050, 7100, 12000, 48000] → q3≈7037.5, fence≈10394
        # → 12000 标红(docE 中位 8400 偏离大但样本 2 < 下限,豁免不成立)。
        + [_item(p, "docE") for p in (4800, 12000)]
        + [_item(p, "docD") for p in (4750, 4800, 4850)]
    )
    group = _one_cluster(items)
    doc_e = [m for m in group["items"] if m["document_id"] == "docE"]
    flagged = [m for m in doc_e if m["is_outlier"]]
    assert [m["unit_price"] for m in flagged] == [12000]
    assert group["stats"]["outlier_count"] == 2  # 12000 + 48000


def test_deviation_threshold_boundary():
    """偏离阈值边界: 0.125 豁免,0.1146 不豁免(只差一档注记,判定均不动红)。"""
    # 簇 29 价: 4800×20 + 48000 + 5350×4 + 5400×4 → median=4800。
    # docX 基线 5400 → dev=600/4800=0.125 ≥ 0.12 → 豁免+注记;
    # docY 基线 5350 → dev=550/4800≈0.1146 < 0.12 → 不豁免、无注记,
    # 文档内 4 价全同值 → doc fence=5350 → 行级也全不标。
    items = (
        [_item(p, "docB") for p in [4800] * 20 + [48000]]
        + [_item(5400, "docX") for _ in range(4)]
        + [_item(5350, "docY") for _ in range(4)]
    )
    group = _one_cluster(items)
    notes = group["stats"]["baseline_notes"]
    exempt_ids = {n["document_id"] for n in notes if n["type"] == "doc_baseline_exempt"}
    assert exempt_ids == {"docX"}

    by_doc = {}
    for m in group["items"]:
        by_doc.setdefault(m["document_id"], []).append(m)
    assert all(not m["is_outlier"] for m in by_doc["docX"])
    assert all(not m["is_outlier"] for m in by_doc["docY"])
    assert [m["unit_price"] for m in by_doc["docB"] if m["is_outlier"]] == [48000]


def test_cluster_with_lt3_prices_gets_insufficient_note():
    """n=2 簇: IQR 恒塌缩数学上永不报离群 → 样本不足注记,而非静默无离群。"""
    group = _one_cluster([_item(100, "docS"), _item(100, "docS")])
    stats = group["stats"]
    assert stats["count"] == 2
    notes = stats["baseline_notes"]
    insufficient = [n for n in notes if n["type"] == "insufficient_sample"]
    assert len(insufficient) == 1
    assert insufficient[0]["count"] == 2
    assert "样本不足" in insufficient[0]["message"]
    assert all(not m["is_outlier"] for m in group["items"])
    # 无基线豁免档(单文档基线=簇中位)
    assert not [n for n in notes if n["type"] == "doc_baseline_exempt"]


def test_single_doc_cluster_no_exempt_note():
    """单文档簇: 文档基线=簇中位,永不豁免——回归守卫旧路径不变味。"""
    group = _one_cluster([_item(p, "only") for p in (100, 200, 300, 9999)])
    notes = group["stats"].get("baseline_notes", [])
    assert not [n for n in notes if n["type"] == "doc_baseline_exempt"]
    # 文档内 4 价: sorted=[100,200,300,9999] → q1=175, q3=2724.75
    # → fence≈6549 → 9999 标红(合同内抓错能力)。
    assert [m["unit_price"] for m in group["items"] if m["is_outlier"]] == [9999]


def test_needs_review_rows_excluded_from_doc_baseline():
    """needs_review 行归组但价不入文档基线分布(与簇统计口径一致)。"""
    items = (
        [_item(p, "docB") for p in (4800, 4800, 4800, 4800, 4800, 48000)]
        + [_item(p, "docA") for p in (7000, 7050, 7100)]
        + [_item(None, "docA", status="needs_review")]
    )
    group = _one_cluster(items)
    doc_a = [m for m in group["items"] if m["document_id"] == "docA"]
    # needs_review 行(价 None)不参与基线,也不被标红
    nr = [m for m in doc_a if m["validation_status"] == "needs_review"]
    assert len(nr) == 1 and nr[0]["is_outlier"] is False
    assert all(not m["is_outlier"] for m in doc_a)
    exempt = [n for n in group["stats"]["baseline_notes"] if n["type"] == "doc_baseline_exempt"]
    assert exempt[0]["rows_exempt"] == 4  # 整文档行数含 needs_review
