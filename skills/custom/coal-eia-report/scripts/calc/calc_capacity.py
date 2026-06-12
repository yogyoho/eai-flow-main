#!/usr/bin/env python3
"""
环境容量估算 (Environmental Capacity Estimation)

支持大气和水体环境容量估算：
- 大气环境容量：采用 A 值法，Qa = A × (Cs - Cb) × √S
- 水体环境容量：采用一维模型，W = 86.4 × Q × (Cs - Cb) / 1000 (吨/天)

输入参数 (通过 --params JSON):

大气 (type="air"):
    area_km2           : 评价区域面积 (km²)
    target_conc_ugm3   : 目标浓度上限 (μg/m³)，即标准限值
    background_conc_ugm3: 背景浓度 (μg/m³)
    A_value            : 地区A值 (可选，默认4.5)

水体 (type="water"):
    river_flow_m3s     : 河流流量 (m³/s)
    target_conc_mgL    : 目标浓度上限 (mg/L)，即水质标准
    background_conc_mgL: 背景浓度 (mg/L)
    decay_coefficient  : 综合衰减系数 (1/d，可选，默认0)

输出:
    type          : 类型 (air/water)
    capacity_tons : 环境容量 (吨/年 for air, 吨/天 for water)
    details       : 计算明细
"""

import argparse
import json
import math
import sys


def calc_air_capacity(params: dict) -> dict:
    """A值法大气环境容量: Qa = A × (Cs - Cb) × √S"""
    S = params["area_km2"]
    Cs = params["target_conc_ugm3"]
    Cb = params["background_conc_ugm3"]
    A = params.get("A_value", 4.5)

    delta_C = Cs - Cb
    if delta_C < 0:
        delta_C = 0.0

    # Qa 单位: 万吨/年 (A值法标准输出)
    # A 的单位使得 Qa = A * ΔC * √S 直接得到 10^4 吨/年
    Qa_10kt_per_year = A * delta_C * math.sqrt(S)
    Qa_tons_per_year = Qa_10kt_per_year * 10000.0

    return {
        "type": "air",
        "method": "A值法",
        "capacity_10kt_per_year": round(Qa_10kt_per_year, 4),
        "capacity_tons_per_year": round(Qa_tons_per_year, 2),
        "details": {
            "A_value": A,
            "area_km2": S,
            "target_conc_ugm3": Cs,
            "background_conc_ugm3": Cb,
            "delta_C_ugm3": round(delta_C, 2),
            "sqrt_area": round(math.sqrt(S), 4),
        },
    }


def calc_water_capacity(params: dict) -> dict:
    """一维水体环境容量: W = 86.4 × Q × (Cs - Cb) / 1000 (吨/天)"""
    Q = params["river_flow_m3s"]
    Cs = params["target_conc_mgL"]
    Cb = params["background_conc_mgL"]
    k = params.get("decay_coefficient", 0.0)

    delta_C = Cs - Cb
    if delta_C < 0:
        delta_C = 0.0

    # 基本容量（不考虑自净）
    W_basic = 86.4 * Q * delta_C / 1000.0  # 吨/天

    # 考虑自净容量
    # 自净容量 = 86.4 * Q * Cb * (1 - exp(-k * x / u)) / 1000
    # 简化：W = W_basic * (1 + k/k0)，这里 k0 取参考值
    # 实际项目通常直接用 W = 86.4 * Q * (Cs - Cb) / 1000
    # 如果提供衰减系数，增加自净修正: W_total = W_basic + 86.4 * Q * Cb * k / (86.4 * u) (简化)
    # 简化处理：总容量 = 稀释容量 + 自净容量
    W_self_purify = 0.0
    if k > 0:
        # 自净容量 = k * Cs * V / 1000 (简化)
        # 用河段体积近似：V = Q * t (t=1天) => 简化为 W_self = k * Cs * 86.4 * Q / 1000 / k_norm
        # 简单处理：用衰减系数做线性修正
        W_self_purify = k * Cs * 86.4 * Q / 1000.0 / (1.0 + k)  # 近似

    W_total = W_basic + W_self_purify

    # 年容量 (吨/年)
    W_annual = W_total * 365.0

    return {
        "type": "water",
        "method": "一维模型",
        "capacity_tons_per_day": round(W_total, 4),
        "capacity_tons_per_year": round(W_annual, 2),
        "details": {
            "river_flow_m3s": Q,
            "target_conc_mgL": Cs,
            "background_conc_mgL": Cb,
            "delta_C_mgL": round(delta_C, 4),
            "decay_coefficient_per_day": k,
            "dilution_capacity_tpd": round(W_basic, 4),
            "self_purification_capacity_tpd": round(W_self_purify, 4),
        },
    }


def calc_capacity(params: dict) -> dict:
    calc_type = params.get("type", "").lower()

    if calc_type == "air":
        # 参数校验
        required = ["area_km2", "target_conc_ugm3", "background_conc_ugm3"]
        missing = [k for k in required if k not in params]
        if missing:
            return {"error": f"缺少必要参数: {', '.join(missing)}"}
        return calc_air_capacity(params)

    elif calc_type == "water":
        # 参数校验
        required = ["river_flow_m3s", "target_conc_mgL", "background_conc_mgL"]
        missing = [k for k in required if k not in params]
        if missing:
            return {"error": f"缺少必要参数: {', '.join(missing)}"}
        return calc_water_capacity(params)

    else:
        return {"error": f"不支持的类型 '{calc_type}'，请使用 'air' 或 'water'"}


def main():
    parser = argparse.ArgumentParser(description="环境容量估算")
    parser.add_argument("--params", type=str, required=True, help="输入参数 JSON 字符串")
    parser.add_argument("--output", type=str, default="json", choices=["json", "text"], help="输出格式")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"参数JSON解析失败: {e}"}), file=sys.stderr)
        sys.exit(1)

    if "type" not in params:
        print(json.dumps({"error": "缺少必要参数: type (air/water)"}), file=sys.stderr)
        sys.exit(1)

    result = calc_capacity(params)

    if "error" in result:
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["type"] == "air":
            lines = [
                f"=== 大气环境容量 ({result['method']}) ===",
                f"区域面积: {result['details']['area_km2']} km²",
                f"A值: {result['details']['A_value']}",
                f"目标浓度: {result['details']['target_conc_ugm3']} μg/m³",
                f"背景浓度: {result['details']['background_conc_ugm3']} μg/m³",
                f"浓度差值: {result['details']['delta_C_ugm3']} μg/m³",
                f"环境容量: {result['capacity_10kt_per_year']} 万吨/年",
                f"          {result['capacity_tons_per_year']} 吨/年",
            ]
        else:
            lines = [
                f"=== 水体环境容量 ({result['method']}) ===",
                f"河流流量: {result['details']['river_flow_m3s']} m³/s",
                f"目标浓度: {result['details']['target_conc_mgL']} mg/L",
                f"背景浓度: {result['details']['background_conc_mgL']} mg/L",
                f"稀释容量: {result['details']['dilution_capacity_tpd']} 吨/天",
                f"自净容量: {result['details']['self_purification_capacity_tpd']} 吨/天",
                f"环境容量: {result['capacity_tons_per_day']} 吨/天",
                f"          {result['capacity_tons_per_year']} 吨/年",
            ]
        print("\n".join(lines))


if __name__ == "__main__":
    main()
