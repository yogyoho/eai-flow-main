"""Price cell validation for scanned-contract OCR output.

Two concerns specific to OCR'd prices:
  1. Glued numbers — adjacent cells merge into one string
     ("824.79 1.20" = 工程量+单价; "9697.45556.99" = 税金+含税单价).
  2. Misrecognized digits — a scanned 120000 can become 12000 or 12O0O0; the
     wrong value still looks plausible, so it silently corrupts price stats.

Policy: do NOT auto-split glued numbers (guessing which is the price is wrong
half the time) — flag them needs_review for a human + traceback. Apply
plausibility checks (magnitude, cross-row outlier) to single numbers.
"""

import re
import statistics

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
    a human confirms via traceback).
    """
    nums = split_glued(raw or "")
    if not nums:
        return None, "needs_review", "无数字"
    if len(nums) > 1:
        return None, "needs_review", "数字粘连: %s" % nums
    val = nums[0]
    if val < 0.01:
        return val, "needs_review", "量级异常 (<0.01)"
    if peers:
        positive = [p for p in peers if p and p > 0]
        if positive:
            med = statistics.median(positive)
            if med > 0 and (val > med * 10 or val < med / 10):
                return val, "needs_review", "偏离同列中位 (>10x)"
    return val, "ok", ""
