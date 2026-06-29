"""Price cell validation for scanned-contract OCR output.

Two concerns specific to OCR'd prices:
  1. Glued numbers — adjacent cells merge into one string
     ("824.79 1.20" = 工程量+单价; "9697.45556.99" = 税金+含税单价).
  2. Misrecognized digits — a scanned 120000 can become 12000 or 12O0O0; the
     wrong value still looks plausible, so it silently corrupts price stats.

Policy: do NOT auto-split glued numbers (guessing which is the price is wrong
half the time) — flag them needs_review for a human + traceback. Apply a
magnitude check to single numbers.

Outlier detection is NOT done here. An earlier table-wide "deviates >10x from
the column median" check was removed: it compared each item against the median
of ALL goods' prices in the table (平整场地 1.31/m² vs 多孔砖墙 511/m³), so every
legitimately cheap or expensive good was false-flagged needs_review (75% of
flags). Real outliers (one supplier charging 10x for the SAME goods) are
detected at cluster level — `_build_groups_db` runs compute_stats per cluster
(same-goods peers) and sets is_outlier. That is the correct comparison group.
``peers`` is kept in the signature for call-site compatibility but ignored.
"""

import re

_NUM = re.compile(r"\d+(?:\.\d+)?")


def split_glued(text: str) -> list:
    """Find all numbers in a (possibly glued) cell. '824.79 1.20' -> [824.79, 1.2]."""
    if not text:
        return []
    return [float(x) for x in _NUM.findall(text.replace(",", "").replace(",", ""))]


def parse_qty(text: str):
    """Extract a leading quantity number; None if none."""
    nums = split_glued(text or "")
    return nums[0] if nums else None


def validate_price(raw: str, peers: list = None):
    """Return (cleaned_price | None, validation_status, reason).

    validation_status: ok | needs_review. Glued/multi-number cells and
    implausible magnitudes go to needs_review (excluded from mean stats until
    a human confirms via traceback). ``peers`` is ignored — outlier detection
    moved to cluster level (see module docstring).
    """
    nums = split_glued(raw or "")
    if not nums:
        return None, "needs_review", "无数字"
    if len(nums) > 1:
        return None, "needs_review", "数字粘连: %s" % nums
    val = nums[0]
    if val < 0.01:
        return val, "needs_review", "量级异常 (<0.01)"
    return val, "ok", ""
