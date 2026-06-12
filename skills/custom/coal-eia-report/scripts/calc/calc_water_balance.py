#!/usr/bin/env python3
"""
水量平衡计算 (Water Balance Calculation)

对矿井/选煤厂等项目的给排水系统进行水量平衡分析，包括供水量、用水量、
回用水量和排水量的统计汇总，计算回用率和平衡差。

输入参数 (通过 --params JSON):
    supply   : 供水项列表 [{name, volume_m3d}]
    demand   : 用水项列表 [{name, volume_m3d}]
    reuse    : 回用项列表 [{name, volume_m3d}]
    discharge: 排水项列表 [{name, volume_m3d}]

输出:
    total_supply_m3d    : 总供水量 (m³/d)
    total_demand_m3d    : 总用水量 (m³/d)
    total_reuse_m3d     : 总回用水量 (m³/d)
    total_discharge_m3d : 总排水量 (m³/d)
    reuse_rate_pct      : 回用率 (%)
    balance_m3d         : 平衡差 (m³/d)，正数表示盈余，负数表示不足
    balance_ratio       : 平衡比 (supply/demand)
    details             : 各分类明细
"""

import argparse
import json
import sys


def sum_items(items: list) -> float:
    """计算水量项目列表的总量。"""
    return sum(item.get("volume_m3d", 0.0) for item in items)


def calc_water_balance(params: dict) -> dict:
    supply = params.get("supply", [])
    demand = params.get("demand", [])
    reuse = params.get("reuse", [])
    discharge = params.get("discharge", [])

    total_supply = sum_items(supply)
    total_demand = sum_items(demand)
    total_reuse = sum_items(reuse)
    total_discharge = sum_items(discharge)

    # 回用率 = reuse / (demand + reuse) × 100%
    denominator = total_demand + total_reuse
    reuse_rate = (total_reuse / denominator * 100.0) if denominator > 0 else 0.0

    # 平衡差 = supply - demand (正=盈余, 负=不足)
    balance = total_supply - total_demand

    # 平衡比
    balance_ratio = (total_supply / total_demand) if total_demand > 0 else float("inf")

    # 验证: supply + reuse ≈ demand + discharge + loss
    # 理论上: total_supply + total_reuse = total_demand + total_discharge
    total_input = total_supply + total_reuse
    total_output = total_demand + total_discharge
    loss = total_input - total_output

    result = {
        "total_supply_m3d": round(total_supply, 2),
        "total_demand_m3d": round(total_demand, 2),
        "total_reuse_m3d": round(total_reuse, 2),
        "total_discharge_m3d": round(total_discharge, 2),
        "reuse_rate_pct": round(reuse_rate, 2),
        "balance_m3d": round(balance, 2),
        "balance_ratio": round(balance_ratio, 4),
        "water_loss_m3d": round(loss, 2),
        "details": {
            "supply": [
                {"name": item["name"], "volume_m3d": item["volume_m3d"]}
                for item in supply
            ],
            "demand": [
                {"name": item["name"], "volume_m3d": item["volume_m3d"]}
                for item in demand
            ],
            "reuse": [
                {"name": item["name"], "volume_m3d": item["volume_m3d"]}
                for item in reuse
            ],
            "discharge": [
                {"name": item["name"], "volume_m3d": item["volume_m3d"]}
                for item in discharge
            ],
        },
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="水量平衡计算")
    parser.add_argument("--params", type=str, required=True, help="输入参数 JSON 字符串")
    parser.add_argument("--output", type=str, default="json", choices=["json", "text"], help="输出格式")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"参数JSON解析失败: {e}"}), file=sys.stderr)
        sys.exit(1)

    result = calc_water_balance(params)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        lines = [
            "=== 水量平衡表 ===",
            "",
            "【供水】",
        ]
        for item in result["details"]["supply"]:
            lines.append(f"  {item['name']}: {item['volume_m3d']:.1f} m³/d")
        lines.append(f"  小计: {result['total_supply_m3d']:.1f} m³/d")
        lines.append("")
        lines.append("【用水】")
        for item in result["details"]["demand"]:
            lines.append(f"  {item['name']}: {item['volume_m3d']:.1f} m³/d")
        lines.append(f"  小计: {result['total_demand_m3d']:.1f} m³/d")
        lines.append("")
        lines.append("【回用】")
        for item in result["details"]["reuse"]:
            lines.append(f"  {item['name']}: {item['volume_m3d']:.1f} m³/d")
        lines.append(f"  小计: {result['total_reuse_m3d']:.1f} m³/d")
        lines.append("")
        lines.append("【排水】")
        for item in result["details"]["discharge"]:
            lines.append(f"  {item['name']}: {item['volume_m3d']:.1f} m³/d")
        lines.append(f"  小计: {result['total_discharge_m3d']:.1f} m³/d")
        lines.append("")
        lines.append(f"回用率: {result['reuse_rate_pct']:.1f}%")
        lines.append(f"平衡差: {result['balance_m3d']:.1f} m³/d")
        lines.append(f"平衡比: {result['balance_ratio']:.4f}")
        lines.append(f"水量损失: {result['water_loss_m3d']:.1f} m³/d")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
