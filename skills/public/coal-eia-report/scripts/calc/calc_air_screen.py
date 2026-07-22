#!/usr/bin/env python3
"""
AERSCREEN简化大气估算 (Simplified AERSCREEN Air Quality Screening)

基于高斯烟羽模型进行简化大气环境影响估算，采用 Holland 烟气抬升公式和
Briggs 扩散参数（城市条件），通过数值搜索计算最大地面浓度及落地距离。

输入参数 (通过 --params JSON):
    emission_rate_gs : 排放速率 (g/s)
    stack_height_m   : 烟囱高度 (m)
    stack_diameter_m : 烟囱出口内径 (m)
    exit_velocity_ms : 烟气出口流速 (m/s)
    exit_temp_K      : 烟气温度 (K)
    ambient_temp_K   : 环境温度 (K，可选，默认293.15)
    wind_speed_ms    : 风速 (m/s，可选，默认3.0)
    stability_class  : 大气稳定度等级 (A~F，可选，默认D)

输出:
    plume_rise_m         : 烟气抬升高度 (m)
    effective_height_m   : 有效烟囱高度 (m)
    max_conc_ugm3        : 最大地面浓度 (μg/m³)
    max_conc_distance_m  : 最大落地浓度距离 (m)
    concentration_profile: [{distance_m, concentration_ugm3}]
"""

import argparse
import json
import math
import sys


# Briggs 城市扩散参数 (x 单位: 米, 输出 σ 单位: 米)
# σy = a * x / (1 + 0.0004*x)^0.5
# σz 参考 P-G 曲线查表值 (简化幂函数拟合, x 单位米)
# 这里使用标准的 Briggs 城市公式
def _briggs_sigma_y(x_m: float) -> float:
    """Briggs 城市横向扩散参数 σy (m)。x_m 为下风向距离 (m)。"""
    return 0.32 * x_m * (1.0 + 0.0004 * x_m) ** (-0.5)


# σz 使用 Pasquill-Gifford 查表拟合的简化幂函数
# σz = c * x^d (x in m), 不同稳定度不同系数
# 参考 HJ 2.2-2018 推荐值
PG_SZ_COEFF = {
    "A": {"c": 0.20, "d": 0.89, "cap": float("inf")},
    "B": {"c": 0.12, "d": 0.89, "cap": float("inf")},
    "C": {"c": 0.08, "d": 0.89, "cap": float("inf")},
    "D": {"c": 0.06, "d": 0.89, "cap": float("inf")},
    "E": {"c": 0.03, "d": 0.89, "cap": float("inf")},
    "F": {"c": 0.016, "d": 0.89, "cap": float("inf")},
}


def calc_plume_rise(vs: float, D: float, u: float, delta_T: float) -> float:
    """
    Holland 烟气抬升公式:
    ΔH = (vs*D/u) * (1.5 + 2.68e-3 * ΔT * D / u)
    """
    if u <= 0:
        u = 0.5  # 避免除零
    base = vs * D / u
    correction = 1.5 + 2.68e-3 * delta_T * D / u
    return max(base * correction, 0.0)


def calc_sigma(stability: str, x_m: float) -> tuple:
    """计算城市扩散参数 (返回 σy, σz 单位 m)。x_m 为下风向距离 (m)。"""
    sigma_y = _briggs_sigma_y(x_m)
    params = PG_SZ_COEFF.get(stability, PG_SZ_COEFF["D"])
    sigma_z = params["c"] * (x_m ** params["d"])
    if sigma_z > params["cap"] and params["cap"] != float("inf"):
        sigma_z = params["cap"]
    return sigma_y, sigma_z


def gaussian_ground_conc(Q_gs: float, u: float, H_eff: float,
                         sigma_y: float, sigma_z: float) -> float:
    """
    高斯烟羽地面轴线浓度 (μg/m³):
    C = Q / (π * σy * σz * u) * exp(-H²/(2σz²))
    Q 单位转换: g/s -> μg/s = 1e6
    """
    if sigma_y <= 0 or sigma_z <= 0 or u <= 0:
        return 0.0
    Q_ugs = Q_gs * 1e6  # g/s -> μg/s
    exponent = -0.5 * (H_eff / sigma_z) ** 2
    C = Q_ugs / (math.pi * sigma_y * sigma_z * u) * math.exp(exponent)
    return C


def calc_air_screen(params: dict) -> dict:
    Q = params["emission_rate_gs"]
    Hs = params["stack_height_m"]
    D = params["stack_diameter_m"]
    vs = params["exit_velocity_ms"]
    Ts = params["exit_temp_K"]
    Ta = params.get("ambient_temp_K", 293.15)
    u = params.get("wind_speed_ms", 3.0)
    stability = params.get("stability_class", "D").upper()

    if stability not in PG_SZ_COEFF:
        stability = "D"

    delta_T = Ts - Ta

    # 1. 烟气抬升
    delta_H = calc_plume_rise(vs, D, u, delta_T)
    H_eff = Hs + delta_H

    # 2. 数值搜索最大地面浓度
    # 在 100m ~ 50000m 范围内搜索
    x_min_m = 100.0
    x_max_m = 50000.0
    n_search = 500

    max_conc = 0.0
    max_conc_dist = 0.0
    profile = []

    dx = (x_max_m - x_min_m) / (n_search - 1)
    for i in range(n_search):
        x_m = x_min_m + i * dx
        sigma_y, sigma_z = calc_sigma(stability, x_m)
        C = gaussian_ground_conc(Q, u, H_eff, sigma_y, sigma_z)
        if C > max_conc:
            max_conc = C
            max_conc_dist = x_m

    # 3. 生成浓度剖面（对数间距采样）
    profile_distances = [
        50, 100, 200, 300, 500, 800, 1000, 1500, 2000, 3000,
        5000, 8000, 10000, 15000, 20000, 30000, 50000
    ]
    for d in profile_distances:
        sigma_y, sigma_z = calc_sigma(stability, d)
        C = gaussian_ground_conc(Q, u, H_eff, sigma_y, sigma_z)
        profile.append({
            "distance_m": d,
            "concentration_ugm3": round(C, 4),
        })

    result = {
        "plume_rise_m": round(delta_H, 2),
        "effective_height_m": round(H_eff, 2),
        "stability_class": stability,
        "wind_speed_ms": u,
        "max_conc_ugm3": round(max_conc, 4),
        "max_conc_distance_m": round(max_conc_dist, 1),
        "concentration_profile": profile,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="AERSCREEN简化大气估算")
    parser.add_argument("--params", type=str, required=True, help="输入参数 JSON 字符串")
    parser.add_argument("--output", type=str, default="json", choices=["json", "text"], help="输出格式")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"参数JSON解析失败: {e}"}), file=sys.stderr)
        sys.exit(1)

    # 参数校验
    required = ["emission_rate_gs", "stack_height_m", "stack_diameter_m",
                "exit_velocity_ms", "exit_temp_K"]
    missing = [k for k in required if k not in params]
    if missing:
        print(json.dumps({"error": f"缺少必要参数: {', '.join(missing)}"}), file=sys.stderr)
        sys.exit(1)

    result = calc_air_screen(params)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        lines = [
            f"烟气抬升高度: {result['plume_rise_m']:.2f} m",
            f"有效烟囱高度: {result['effective_height_m']:.2f} m",
            f"大气稳定度: {result['stability_class']}",
            f"风速: {result['wind_speed_ms']:.1f} m/s",
            f"最大地面浓度: {result['max_conc_ugm3']:.4f} μg/m³",
            f"最大落地距离: {result['max_conc_distance_m']:.0f} m",
            "",
            "浓度剖面:",
        ]
        for p in result["concentration_profile"]:
            lines.append(f"  {p['distance_m']:>6d}m: {p['concentration_ugm3']:.4f} μg/m³")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
