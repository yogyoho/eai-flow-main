"""SK-PS 计算内核(批二十 M1-e,EAI-CUSTOM 2026-11-13)——§2.2 硬约束兑现:
算术全部代码完成零 LLM,明细表唯一事实源(开标一览/汇总/投标函金额全派生);
Decimal 算术(qty/单价入口 str 化,零浮点累加)中间 4 位落表 2 位 ROUND_HALF_UP;
单价=人工输入,**缺→None 留空**(降级 D0 留空标注,禁止自动出价/近似修正);
行序=boq 序,qty/unit 原样透传(数量一致面:生成器不改招标清单)。
含税列(amount_with_tax)暂不入 ctx 形——校验器/导出面未消费,M2 导出批按需补。
纯函数零 IO 零时钟(20× 确定性验收面组成件)。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.extensions.bid_write.executor.amount_cn import num_to_cn

_TWO = Decimal("0.01")


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _num(v: Decimal):
    """落表数:整数值出 int(=green 形),否则 float 2 位。"""
    q = v.quantize(_TWO, rounding=ROUND_HALF_UP)
    return int(q) if q == q.to_integral_value() else float(q)


def calc_price_sheet(boq_items: list[dict] | None, unit_prices: dict | None, *, price_mode: str = "不含税", tax_rate: float = 0.13, note: str = "", price_adjust_mechanism: bool = True) -> dict:
    rows: list[dict] = []
    total = Decimal("0")
    for it in boq_items or []:
        price = (unit_prices or {}).get(str(it.get("id")))
        base = {"id": it.get("id"), "name": it.get("name"), "qty": it.get("qty"), "unit": it.get("unit")}
        if price is None:
            rows.append({**base, "unit_price": None, "amount": None})
            continue
        amount = (_dec(price) * _dec(it.get("qty"))).quantize(_TWO, rounding=ROUND_HALF_UP)
        total += amount
        rows.append({**base, "unit_price": _num(_dec(price)), "amount": _num(amount)})
    return {
        "rows": rows,
        "detail_total": _num(total),
        "summary_total": _num(total),
        "open_letter_total": _num(total),
        "amount_cn": num_to_cn(_num(total)),
        "price_mode": price_mode,
        "tax_rate": tax_rate,
        "note": note,
        "price_adjust_mechanism": bool(price_adjust_mechanism),
        "pending_items": [],
    }
