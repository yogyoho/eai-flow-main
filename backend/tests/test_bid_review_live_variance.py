"""M2-M4 活体方差回采脚本纯函数测试(EAI-CUSTOM 2026-11-06)。

方差口径的测量核:跨跑逐键相等性 + fields 内容 sha1 指纹。脚本本体零生产代码,
烧配额的活体跑由调用方执行;本测试不触模型。
"""

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bid_review_live_variance.py"
sys.path.insert(0, str(_SCRIPT.parent))
_spec = importlib.util.spec_from_file_location("bid_review_live_variance", _SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_variance_report_stable_and_flapped():
    flat = [
        {"m2_sections.n": 6, "m3_tables.boq_rows": 5},
        {"m2_sections.n": 6, "m3_tables.boq_rows": 4},
    ]
    v = mod._variance(flat)
    assert v["m2_sections.n"] == {"values": [6, 6], "stable": True}
    assert v["m3_tables.boq_rows"] == {"values": [5, 4], "stable": False}


def test_field_fps_content_sensitivity():
    """sha1 内容指纹:同键内容变 → 指纹变;list 键带 n 长度。"""
    a = mod._field_fps({"bid.boq_rows": [{"price": 1}]})
    b = mod._field_fps({"bid.boq_rows": [{"price": 2}]})
    assert a["bid.boq_rows"]["sha"] != b["bid.boq_rows"]["sha"]
    assert a["bid.boq_rows"]["n"] == 1
    c = mod._field_fps({"tender.currency": "CNY"})
    assert c["tender.currency"]["n"] is None  # 非 list 键无长度


def test_flatten_dotted_keys():
    flat = mod._flatten({"m2_sections": {"n": 3, "is_empty_true": 1}, "m4_performance": {"entries": 2}})
    assert flat == {"m2_sections.n": 3, "m2_sections.is_empty_true": 1, "m4_performance.entries": 2}
