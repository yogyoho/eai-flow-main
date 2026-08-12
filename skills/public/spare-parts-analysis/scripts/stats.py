# EAI-CUSTOM: forked from contract-price-analysis/scripts/stats.py(域无关,逐字)。
"""一组单价的聚合统计。

描述性统计(count/mean/min/max/median/std)+ 离群点计数,用稳健 IQR(箱线图)法
而非 mean+3*std。均值/标准差法会被掩盖——单个极端价格抬高 std 把自己藏起来——故
IQR(围栏 = Q3 + 1.5*IQR)用来把真正异常的价格浮出来供复核。
"""

import statistics
from typing import Optional


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolation percentile of an already-sorted list (p in [0,1])。"""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_vals):
        return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
    return sorted_vals[f]


def compute_stats(prices: list[float]) -> dict:
    if not prices:
        return {
            "count": 0,
            "mean": None,
            "min": None,
            "max": None,
            "median": None,
            "std": None,
            "outlier_count": 0,
            "outlier_threshold": None,
        }

    sorted_prices = sorted(prices)
    q1 = _percentile(sorted_prices, 0.25)
    q3 = _percentile(sorted_prices, 0.75)
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outliers = sum(1 for p in prices if p < lower_fence or p > upper_fence)

    std = statistics.pstdev(prices) if len(prices) > 1 else 0.0
    return {
        "count": len(prices),
        "mean": round(statistics.mean(prices), 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "median": round(statistics.median(prices), 2),
        "std": round(std, 2),
        "outlier_count": outliers,
        "outlier_threshold": round(upper_fence, 2),
    }
