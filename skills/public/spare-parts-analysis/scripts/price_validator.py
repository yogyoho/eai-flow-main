# EAI-CUSTOM: forked from contract-price-analysis/scripts/price_validator.py(域无关,逐字)。
"""Price cell validation for scanned-contract OCR output。

扫描件 OCR 价格格的两个坑:
  1. 粘连数字——相邻格并成一个串("824.79 1.20" = 工程量+单价;"9697.45556.99" = 税金+含税单价)。
  2. 误识数字——扫描的 120000 可能变 12000 或 12O0O0;错误值仍看着合理,静默污染价格统计。

策略:
  - 单数字 → ok(量级 <0.01 → needs_review)。
  - 两数字带空格分隔("824.79 1.20")→ 干净粘连:OCR 把 工程量+单价(或 税金+含税单价)
    并起来,量/税在左。取末位作单价(L→R 阅读序)→ ok,带可审计"粘连拆分(取末位)"原因。
    统计只用单独的含税列,故错拆最多污染仅审计用的不含税值。
  - 无分隔拼接("9697.45556.99")或 >2 数字 → 太歧义 → needs_review。

离群点检测不在此做。早先的表级"偏离列中位数 >10x"检查已删:它把每项对表中所有备件价格
的中位数比(螺栓 1.31/个 vs 阀门 511/台),于是每个本就便宜或贵的备件都被误标 needs_review
(75% 误报)。真正的离群(某客户对同一备件报 10x)在聚类层检测——_build_groups_db 按簇
(同备件同伴)跑 compute_stats 并置 is_outlier。那才是正确的比较组。
"""

import re

_NUM = re.compile(r"\d+(?:\.\d+)?")
# A number, then whitespace, then another number — a cleanly SEPARATED 2-glue.
_SPACE_GLUE = re.compile(r"\d(?:\.\d+)?\s+\d")


def split_glued(text: str) -> list:
    """Find all numbers in a (possibly glued) cell. '824.79 1.20' -> [824.79, 1.2]。"""
    if not text:
        return []
    return [float(x) for x in _NUM.findall(text.replace(",", "").replace(",", ""))]


def parse_qty(text: str):
    """Extract a leading quantity number; None if none。"""
    nums = split_glued(text or "")
    return nums[0] if nums else None


def validate_price(raw: str, peers: list = None):
    """Return (cleaned_price | None, validation_status, reason)。

    validation_status: ok | needs_review。量级异常和歧义粘连入 needs_review。
    干净空格分隔的 2 数粘连自动拆(末位 = 单价,可审计)。``peers`` 被忽略——离群检测
    移到聚类层(见模块 docstring)。
    """
    nums = split_glued(raw or "")
    if not nums:
        return None, "needs_review", "无数字"
    if len(nums) == 1:
        val = nums[0]
        if val < 0.01:
            return val, "needs_review", "量级异常 (<0.01)"
        return val, "ok", ""
    # Cleanly separated 2-number glue: take the LAST as the unit price.
    if len(nums) == 2 and _SPACE_GLUE.search(raw or ""):
        val = nums[-1]
        if val <= 0:
            return None, "needs_review", "粘连末位≤0: %s" % nums
        return val, "ok", "粘连拆分(取末位): %s" % nums
    # >2 numbers, or no-separator concatenation (split_glued misparses dot-runs)
    return None, "needs_review", "数字粘连: %s" % nums
