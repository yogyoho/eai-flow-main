#!/usr/bin/env python3
"""
概率积分法沉陷预测 (Probability Integration Method for Subsidence Prediction)

基于中国煤矿开采沉陷预测中广泛使用的概率积分法，计算地表最大下沉、水平移动、
倾斜变形、曲率变形和水平变形等指标，并可输出下沉剖面曲线数据。

输入参数 (通过 --params JSON):
    q         : 下沉系数 (0.5~1.0，典型值0.78)
    b         : 水平移动系数 (0.2~0.4，典型值0.3)
    tan_beta  : 主要影响角正切 (1.5~2.5，典型值2.2)
    m         : 开采厚度 (m)
    H         : 开采深度 (m)
    alpha     : 煤层倾角 (度)
    s_offset  : 拐点偏距 (m，可选，默认0)
    include_profile : 是否输出剖面数据 (bool，可选，默认false)
    profile_range  : 剖面计算范围，单位r的倍数 (可选，默认3)
    profile_points : 剖面采样点数 (可选，默认61)

输出:
    W_max     : 最大下沉值 (mm)
    r         : 主要影响半径 (m)
    U_max     : 最大水平移动 (mm)
    i_max     : 最大倾斜变形 (mm/m)
    K_max     : 最大曲率 (10^-3/m)
    eps_max   : 最大水平变形 (mm/m)
    profile   : 下沉剖面 [{x, W}] (当include_profile=true时)
"""

import argparse
import json
import math
import sys


def erf_approx(x: float) -> float:
    """近似计算误差函数 erf(x)，使用 Abramowitz & Stegun 7.1.26 公式。"""
    sign = 1.0 if x >= 0 else -1.0
    x = abs(x)
    # 系数
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911

    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return sign * y


def calc_subsidence(params: dict) -> dict:
    q = params["q"]
    b = params["b"]
    tan_beta = params["tan_beta"]
    m = params["m"]
    H = params["H"]
    alpha_deg = params["alpha"]

    s_offset = params.get("s_offset", 0.0)
    include_profile = params.get("include_profile", False)
    profile_range = params.get("profile_range", 3)
    profile_points = params.get("profile_points", 61)

    # 角度转弧度
    alpha_rad = math.radians(alpha_deg)
    cos_alpha = math.cos(alpha_rad)

    # 核心计算
    W_max = q * m * cos_alpha * 1000.0  # mm
    r = H / tan_beta  # m
    U_max = b * W_max  # mm
    i_max = W_max / r  # mm/m
    K_max = 1.52 * W_max / (r * r)  # 10^-3/m (实际为 mm/m^2)
    eps_max = 1.52 * b * W_max / r  # mm/m

    result = {
        "W_max_mm": round(W_max, 2),
        "r_m": round(r, 2),
        "U_max_mm": round(U_max, 2),
        "i_max_mm_per_m": round(i_max, 4),
        "K_max_per_m_e3": round(K_max, 6),
        "eps_max_mm_per_m": round(eps_max, 4),
    }

    if include_profile:
        profile = []
        x_start = -profile_range * r
        x_end = profile_range * r
        dx = (x_end - x_start) / (profile_points - 1)
        for i in range(profile_points):
            x = x_start + i * dx
            # W(x) = W_max/2 * [1 + erf(-x*sqrt(pi)/(2r))]
            arg = -x * math.sqrt(math.pi) / (2.0 * r)
            W_x = W_max / 2.0 * (1.0 + erf_approx(arg))
            profile.append({
                "x_m": round(x, 2),
                "W_mm": round(W_x, 2),
            })
        result["profile"] = profile

    return result


def main():
    parser = argparse.ArgumentParser(description="概率积分法沉陷预测")
    parser.add_argument("--params", type=str, required=True, help="输入参数 JSON 字符串")
    parser.add_argument("--output", type=str, default="json", choices=["json", "text"], help="输出格式")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"参数JSON解析失败: {e}"}), file=sys.stderr)
        sys.exit(1)

    # 参数校验
    required = ["q", "b", "tan_beta", "m", "H", "alpha"]
    missing = [k for k in required if k not in params]
    if missing:
        print(json.dumps({"error": f"缺少必要参数: {', '.join(missing)}"}), file=sys.stderr)
        sys.exit(1)

    result = calc_subsidence(params)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        lines = [
            f"最大下沉值 W_max = {result['W_max_mm']:.2f} mm",
            f"主要影响半径 r = {result['r_m']:.2f} m",
            f"最大水平移动 U_max = {result['U_max_mm']:.2f} mm",
            f"最大倾斜变形 i_max = {result['i_max_mm_per_m']:.4f} mm/m",
            f"最大曲率 K_max = {result['K_max_per_m_e3']:.6f} ×10⁻³/m",
            f"最大水平变形 ε_max = {result['eps_max_mm_per_m']:.4f} mm/m",
        ]
        print("\n".join(lines))


if __name__ == "__main__":
    main()
