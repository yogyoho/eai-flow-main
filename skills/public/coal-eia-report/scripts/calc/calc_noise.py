#!/usr/bin/env python3
"""
噪声衰减计算 (Noise Attenuation Calculation)

计算点声源和线声源在不同距离处的噪声衰减值，并与 GB12348 标准限值进行达标分析。

输入参数 (通过 --params JSON):
    source_type          : 声源类型 ("point" 或 "line")
    source_level_dBA     : 声源声级 (dB(A))
    distances_m          : 计算距离列表 (m)，如 [50, 100, 200]
    atmospheric_absorption : 大气吸收衰减 (dB，可选，默认0)
    ground_factor        : 地面衰减因子 (dB，可选，默认0)
    day_limit_dBA        : 昼间限值 (dB(A)，可选，默认60)
    night_limit_dBA      : 夜间限值 (dB(A)，可选，默认50)

输出:
    predictions : [{distance_m, predicted_dBA, day_compliant, night_compliant}]
    max_compliant_distance_day_m   : 昼间达标最大距离 (m)
    max_compliant_distance_night_m : 夜间达标最大距离 (m)
"""

import argparse
import json
import math
import sys


def calc_noise(params: dict) -> dict:
    source_type = params["source_type"]
    source_level = params["source_level_dBA"]
    distances = params["distances_m"]

    atm_absorption = params.get("atmospheric_absorption", 0.0)
    ground_factor = params.get("ground_factor", 0.0)
    day_limit = params.get("day_limit_dBA", 60.0)
    night_limit = params.get("night_limit_dBA", 50.0)

    predictions = []

    for d in distances:
        if d <= 0:
            continue

        if source_type == "point":
            # 点声源: Lp = Lw - 20*log10(r) - 11 - ΔLatm - ΔLground
            attenuation = 20.0 * math.log10(d) + 11.0
        else:
            # 线声源: Lp = Lw - 10*log10(r/7.5) - ΔLatm - ΔLground
            attenuation = 10.0 * math.log10(d / 7.5)

        predicted = source_level - attenuation - atm_absorption - ground_factor

        day_ok = predicted <= day_limit
        night_ok = predicted <= night_limit

        predictions.append({
            "distance_m": round(d, 1),
            "predicted_dBA": round(predicted, 1),
            "day_compliant": day_ok,
            "night_compliant": night_ok,
        })

    # 计算达标最大距离（反向求解）
    def max_compliant_distance(limit_dba: float) -> float:
        """求解满足 predicted <= limit 的最大距离。"""
        if source_type == "point":
            # Lp = Lw - 20*log10(r) - 11 - ΔLatm - ΔLground
            # limit = source_level - 20*log10(r) - 11 - atm - ground
            # 20*log10(r) = source_level - limit - 11 - atm - ground
            effective = source_level - limit_dba - 11.0 - atm_absorption - ground_factor
            if effective <= 0:
                return float("inf")  # 任何距离都达标
            r = 10.0 ** (effective / 20.0)
            return round(r, 1)
        else:
            # Lp = Lw - 10*log10(r/7.5) - ΔLatm - ΔLground
            # 10*log10(r/7.5) = source_level - limit - atm - ground
            effective = source_level - limit_dba - atm_absorption - ground_factor
            if effective <= 0:
                return float("inf")
            ratio = 10.0 ** (effective / 10.0)
            r = ratio * 7.5
            return round(r, 1)

    result = {
        "source_type": source_type,
        "source_level_dBA": source_level,
        "predictions": predictions,
        "max_compliant_distance_day_m": max_compliant_distance(day_limit),
        "max_compliant_distance_night_m": max_compliant_distance(night_limit),
        "reference_standard": "GB12348",
        "day_limit_dBA": day_limit,
        "night_limit_dBA": night_limit,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="噪声衰减计算")
    parser.add_argument("--params", type=str, required=True, help="输入参数 JSON 字符串")
    parser.add_argument("--output", type=str, default="json", choices=["json", "text"], help="输出格式")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"参数JSON解析失败: {e}"}), file=sys.stderr)
        sys.exit(1)

    # 参数校验
    required = ["source_type", "source_level_dBA", "distances_m"]
    missing = [k for k in required if k not in params]
    if missing:
        print(json.dumps({"error": f"缺少必要参数: {', '.join(missing)}"}), file=sys.stderr)
        sys.exit(1)

    if params["source_type"] not in ("point", "line"):
        print(json.dumps({"error": "source_type 必须为 'point' 或 'line'"}), file=sys.stderr)
        sys.exit(1)

    result = calc_noise(params)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        lines = [
            f"声源类型: {result['source_type']}",
            f"声源声级: {result['source_level_dBA']} dB(A)",
            f"参考标准: {result['reference_standard']}",
            f"昼间限值: {result['day_limit_dBA']} dB(A)",
            f"夜间限值: {result['night_limit_dBA']} dB(A)",
            "",
            "距离衰减预测:",
        ]
        for p in result["predictions"]:
            day_str = "达标" if p["day_compliant"] else "超标"
            night_str = "达标" if p["night_compliant"] else "超标"
            lines.append(
                f"  {p['distance_m']:.0f}m: {p['predicted_dBA']:.1f} dB(A) "
                f"(昼间{day_str}, 夜间{night_str})"
            )
        lines.append("")
        d_day = result["max_compliant_distance_day_m"]
        d_night = result["max_compliant_distance_night_m"]
        lines.append(f"昼间达标最大距离: {'∞' if d_day == float('inf') else f'{d_day} m'}")
        lines.append(f"夜间达标最大距离: {'∞' if d_night == float('inf') else f'{d_night} m'}")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
