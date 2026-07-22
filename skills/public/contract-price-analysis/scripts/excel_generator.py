"""Generate a 6-sheet Excel report with charts via xlsxwriter.

Workbook layout:
  1. 汇总总表     — one row per cluster: category, name, count, mean/max/min/median/std, outlier count
  2. 分项明细     — every line item: name, spec, params, price, source contract, date, supplier
  3. 图表-价格分布 — bar chart of mean price per cluster
  4. 图表-价格趋势 — line chart of mean price per cluster (placeholder for time series)
  5. 图表-供应商对比 — bar chart of mean price per supplier
  6. 图表-区间分布 — column chart of price-range bucket counts

Each ``group`` dict is:
  {"name": str, "category": str, "stats": {...}, "items": [{...}, ...]}
"""

import xlsxwriter

_CHART_SHEETS = [
    ("图表-价格分布", "各组均价", "cluster", "mean"),
    ("图表-价格趋势", "各组均价趋势", "cluster", "mean"),
    ("图表-供应商对比", "各供应商均价", "supplier", "mean"),
    ("图表-区间分布", "价格区间分布", "bucket", "count"),
]


def generate_excel(groups: list[dict], output_path: str) -> str:
    workbook = xlsxwriter.Workbook(output_path)
    header_fmt = workbook.add_format({"bold": True, "bg_color": "#F2F2F2", "border": 1})
    money_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
    text_fmt = workbook.add_format({"border": 1})
    outlier_fmt = workbook.add_format({"bg_color": "#FFC7CE", "border": 1})

    _write_summary(workbook, groups, header_fmt, money_fmt, text_fmt)
    _write_items(workbook, groups, header_fmt, money_fmt, text_fmt, outlier_fmt)
    _write_price_distribution(workbook, groups, header_fmt)
    _write_price_trend(workbook, groups, header_fmt)
    _write_supplier_comparison(workbook, groups, header_fmt)
    _write_range_distribution(workbook, groups, header_fmt)

    workbook.close()
    return output_path


def _write_summary(workbook, groups, header_fmt, money_fmt, text_fmt):
    ws = workbook.add_worksheet("汇总总表")
    headers = ["类别", "代表名称", "样本数", "均值", "最大值", "最小值", "中位数", "标准差", "异常值数", "异常阈值"]
    for c, h in enumerate(headers):
        ws.write(0, c, h, header_fmt)
    for r, g in enumerate(groups, start=1):
        s = g["stats"]
        ws.write(r, 0, g["category"], text_fmt)
        ws.write(r, 1, g["name"], text_fmt)
        ws.write(r, 2, s.get("count", 0), text_fmt)
        for c, key in enumerate(["mean", "max", "min", "median", "std"], start=3):
            ws.write_number(r, c, s.get(key) or 0, money_fmt)
        ws.write(r, 8, s.get("outlier_count", 0), text_fmt)
        ws.write_number(r, 9, s.get("outlier_threshold") or 0, money_fmt)
    ws.freeze_panes(1, 2)


def _write_items(workbook, groups, header_fmt, money_fmt, text_fmt, outlier_fmt):
    ws = workbook.add_worksheet("分项明细")
    headers = ["货物名称", "规格型号", "技术参数", "单价", "来源合同", "签订日期", "供应商", "是否异常"]
    for c, h in enumerate(headers):
        ws.write(0, c, h, header_fmt)
    row = 1
    for g in groups:
        for it in g["items"]:
            is_outlier = bool(it.get("is_outlier"))
            ws.write(row, 0, it.get("goods_name", ""), text_fmt)
            ws.write(row, 1, it.get("spec_model", ""), text_fmt)
            ws.write(row, 2, _stringify_params(it.get("tech_params")), text_fmt)
            _price = it.get("unit_price")
            if _price is None:
                # needs_review item (glued/implausible) — no number until a human confirms
                ws.write(row, 3, "待核验", text_fmt)
            else:
                ws.write_number(row, 3, _price, money_fmt)
            ws.write(row, 4, it.get("source_contract_no", ""), text_fmt)
            ws.write(row, 5, it.get("sign_date", ""), text_fmt)
            ws.write(row, 6, it.get("supplier", ""), text_fmt)
            ws.write(row, 7, "是" if is_outlier else "", outlier_fmt if is_outlier else text_fmt)
            row += 1
    ws.freeze_panes(1, 0)


def _write_price_distribution(workbook, groups, header_fmt):
    ws = workbook.add_worksheet("图表-价格分布")
    ws.write(0, 0, "组", header_fmt)
    ws.write(0, 1, "均值", header_fmt)
    for r, g in enumerate(groups, start=1):
        ws.write(r, 0, g["name"])
        ws.write_number(r, 1, g["stats"].get("mean") or 0)
    chart = workbook.add_chart({"type": "bar"})
    chart.add_series({
        "name": "各组均价",
        "categories": ["图表-价格分布", 1, 0, len(groups), 0],
        "values": ["图表-价格分布", 1, 1, len(groups), 1],
    })
    chart.set_title({"name": "各组均价分布"})
    ws.insert_chart("D2", chart)


def _write_price_trend(workbook, groups, header_fmt):
    ws = workbook.add_worksheet("图表-价格趋势")
    ws.write(0, 0, "组", header_fmt)
    ws.write(0, 1, "均值", header_fmt)
    for r, g in enumerate(groups, start=1):
        ws.write(r, 0, g["name"])
        ws.write_number(r, 1, g["stats"].get("mean") or 0)
    chart = workbook.add_chart({"type": "line"})
    chart.add_series({
        "name": "各组均价趋势",
        "categories": ["图表-价格趋势", 1, 0, len(groups), 0],
        "values": ["图表-价格趋势", 1, 1, len(groups), 1],
    })
    chart.set_title({"name": "各组均价趋势"})
    ws.insert_chart("D2", chart)


def _write_supplier_comparison(workbook, groups, header_fmt):
    ws = workbook.add_worksheet("图表-供应商对比")
    # Aggregate mean price per supplier (needs_review items have
    # unit_price=None and are excluded from the mean).
    supplier_totals: dict[str, list[float]] = {}
    for g in groups:
        for it in g["items"]:
            price = it.get("unit_price")
            if price is None:
                continue
            sup = it.get("supplier") or "未知"
            supplier_totals.setdefault(sup, []).append(price)
    ws.write(0, 0, "供应商", header_fmt)
    ws.write(0, 1, "均价", header_fmt)
    row = 1
    for sup, prices in sorted(supplier_totals.items()):
        ws.write(row, 0, sup)
        ws.write_number(row, 1, round(sum(prices) / len(prices), 2))
        row += 1
    chart = workbook.add_chart({"type": "column"})
    n = len(supplier_totals)
    chart.add_series({
        "name": "各供应商均价",
        "categories": ["图表-供应商对比", 1, 0, n, 0],
        "values": ["图表-供应商对比", 1, 1, n, 1],
    })
    chart.set_title({"name": "各供应商均价对比"})
    ws.insert_chart("D2", chart)


def _write_range_distribution(workbook, groups, header_fmt):
    ws = workbook.add_worksheet("图表-区间分布")
    # Bucket all item prices into 6 equal-width buckets between min and max.
    all_prices = [
        it.get("unit_price") for g in groups for it in g["items"] if it.get("unit_price") is not None
    ]
    if not all_prices:
        ws.write(0, 0, "区间", header_fmt)
        ws.write(0, 1, "数量", header_fmt)
        return
    lo, hi = min(all_prices), max(all_prices)
    if hi == lo:
        hi = lo + 1
    step = (hi - lo) / 6
    buckets = [0] * 6
    for p in all_prices:
        idx = min(int((p - lo) / step), 5)
        buckets[idx] += 1
    ws.write(0, 0, "区间", header_fmt)
    ws.write(0, 1, "数量", header_fmt)
    for i, count in enumerate(buckets):
        lo_b = round(lo + i * step, 2)
        hi_b = round(lo + (i + 1) * step, 2)
        ws.write(i + 1, 0, f"{lo_b}-{hi_b}")
        ws.write_number(i + 1, 1, count)
    chart = workbook.add_chart({"type": "column"})
    chart.add_series({
        "name": "价格区间分布",
        "categories": ["图表-区间分布", 1, 0, 6, 0],
        "values": ["图表-区间分布", 1, 1, 6, 1],
    })
    chart.set_title({"name": "价格区间分布"})
    ws.insert_chart("D2", chart)


def _stringify_params(params) -> str:
    if not params:
        return ""
    if isinstance(params, dict):
        return ", ".join(f"{k}={v}" for k, v in params.items())
    return str(params)
