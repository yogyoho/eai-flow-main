"""category 全链: 模型列存在 + init_schema 幂等 ALTER + 聚类样本拼分类 + 落库kwarg。"""

import inspect

from scripts.models import CpaItem


def test_cpa_item_has_category_column():
    assert "category" in CpaItem.__table__.columns
    assert CpaItem.__table__.columns["category"].nullable


def test_init_schema_alters_existing_tables():
    from scripts import db

    src = inspect.getsource(db.init_schema)
    assert "ADD COLUMN IF NOT EXISTS category" in src


def test_cluster_sample_excludes_category():
    """聚类样本文本 = 名称+规格(2026-10-22 设计修订: 分类不再拼入)。

    旧版把 category 拼进文本导致短货名被同分类长字符串淹没——真机 81 条
    mega 簇(电源线↔监控模块 相似度 0.72 纯靠分类贡献)。分类区分改由
    engine 的类目 AND 门限独立比较;本测试固化「分类不影响样本文本,
    规格影响」的新契约(旧断言在设计变更时漏改,回归中发现)。"""
    from scripts.cli import _cluster_sample_text

    # 分类不进样本: 同名货物不同分类 → 样本相同(分簇交给 engine 类目门限)
    assert _cluster_sample_text("现浇构件钢筋", None, {"category": "建筑工程"}) == \
           _cluster_sample_text("现浇构件钢筋", None, {"category": "屋面"})
    # 规格进样本: 同名不同规格 → 样本不同
    assert _cluster_sample_text("钢筋", "HRB400E Φ 8mm", None) != \
           _cluster_sample_text("钢筋", "HRB400E Φ 20mm", None)
    # 裸名兜底 + tech_params 非 dict 容错
    assert _cluster_sample_text("钢筋", None, None) == "钢筋"
    assert _cluster_sample_text("钢筋", None, "junk") == "钢筋"


def test_persist_one_doc_writes_category_kwarg():
    """落库契约: item 的 category 键必须进 CpaItem 构造参数。"""
    from scripts.cli import _persist_one_doc

    src = inspect.getsource(_persist_one_doc)
    assert '"category": it.get("category")' in src or "'category': it.get('category')" in src


def test_seed_category_tail_direct():
    """seed_category_tail 直测(质量审查 fold-in): 尾部分类行(不产item)必须可见;
    x-path 缺键安全。"""
    from scripts.table_classifier import seed_category_tail

    rows = [
        ["序号", "项目名称", "单位", "工程量", "不含税单价", "含税单价", "含税合价"],
        ["12", "现浇构件钢筋", "t", "63.55", "1131.55", "1205.84", "76631.13"],
        ["", "屋面", "", "", "", "", ""],
    ]
    roles = {"name": 1, "qty": 3, "unit": 2, "price_unit": 5, "price_total": 6, "price_untaxed": 4}
    assert seed_category_tail(rows, roles, 1, None, None, None) == "屋面"
    assert seed_category_tail(rows[:2], roles, 1, None, None, None) is None
    assert seed_category_tail(rows, roles, 1, None, None, "装饰") == "屋面"   # cat_in 被新分类行覆盖
    assert seed_category_tail(rows[:2], roles, 1, None, None, "装饰") == "装饰"  # 无分类行时透传
