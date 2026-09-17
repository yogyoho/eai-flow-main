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


def test_cluster_sample_appends_category():
    """同名货物不同分类必须分簇: 样本文本 = 名称+分类(设计 §1.3)。"""
    from scripts.cli import _cluster_sample_text

    assert _cluster_sample_text("现浇构件钢筋", {"category": "建筑工程"}) != \
           _cluster_sample_text("现浇构件钢筋", {"category": "屋面"})
    assert _cluster_sample_text("钢筋", {}) == "钢筋"


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
