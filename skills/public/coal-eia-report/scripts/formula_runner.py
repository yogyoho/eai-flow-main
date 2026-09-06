#!/usr/bin/env python3
"""coal-eia-report v2（T2 重写） — formula_runner.py：冻结计算层（步骤2，门2 的数据面）。

D5（docs/designs/coal-eia-report-v2.md）：calc 5 脚本以 geo formula_runner 架构重写为 Decimal
计算函数——CLI 六命令面（execute/freeze[progress run-stage]/check/trace/impacted/update 顺序铁律）、
值+display+source 槽位注册表、write_state 终检全部保持 geo 语义；改的只有算子层：
geo 的地勘品位/资源量/经济链 → 环评 5 域：

  subsidence     概率积分法：W_max=q·m·cosα·1000（逐煤层）+ 逐矿层间叠加（Σ）；r=H/tanβ。
                 能力边界（设计拍板，月儿湾实证 U/W=0.44≠b=0.3）：倾斜/曲率/水平移动/水平变形/
                 沉陷面积=开采沉陷软件成果走表单转录（software_results），禁公式硬凑；
                 动态预计/等值线/逐点值=软件黑箱。
  fracture_zone  导水裂隙带/垮落带：《三下规范》套用公式四类（坚硬/中硬/软弱/极软弱，取+偏差
                 最不利口径）+ 垮落带 MT/T1091-2008 附录D 类乘系数（上界）。唯一无既有 calc
                 脚本的纯新写域——回归=样例正文数值人工回代（月儿湾 19.33/20.51、四季屯
                 14.58/24.22/15.22/26.50/19.96/19.16 全部精确复现，见回归测试）。
                 厚煤层（M>3.5m）矿大经验公式分支：样例公式体 OLE 不可转录 → 记 anomaly 人工复核。
  capacity:air   A 值法环境容量（GB/T 13201-91，对齐 calc_capacity.py air 分支）。
  capacity:water 一维模型容量（对齐 calc_capacity.py water 分支）。
  water_balance  水量平衡（供/需/回用/排水，对齐 calc_water_balance.py；supply 缺表单时按
                 逐矿涌水量 XS12 口径合成）。
  noise          多源叠加：单源传播衰减（point 20lgr+11 / line 10lg(r/7.5)，对齐 calc_noise.py）
                 + 10·lg Σ10^(Li/10) 能量合成；达标距离=合成曲线二分反解。
  air_screen     点源估算（Holland 抬升+Briggs 城市扩散参数+高斯烟羽轴线，对齐 calc_air_screen.py）。
                 仅适用锅炉烟气点源；煤炭转储运/筛分扬尘为面源——走 reference_values 源强取值，
                 禁硬套点源模型（XS7/能力边界）。

舍入定稿（spec + references/formulas.json rounding_policy）：decimal.Decimal + quantize
(ROUND_HALF_EVEN)——禁 float round()。中间量全 Decimal（prec 50）不落舍入，出口统一 quantize；
链式下游（噪声能量合成/逐矿叠加）复用未舍入中间量，避免二次舍入漂移。超越运算（cos/log10/
10^x/exp/√/x^0.89）全部 Decimal 原生或 Taylor，禁 float 混算。

回归基准：scripts/calc/ 5 脚本（只读，禁改）——backend/tests/test_coal_eia_calc_regression.py
对每脚本取 3 组代表参数同参同果（容差=原脚本 float 出口舍入界 0.5·10^-dp）；fracture_zone
回代组单列。红线：缺输入记 anomaly 绝不编造；空白表单与缺失等价（bug-2223 同构）。

退出码：0 干净 / 1 错误 / 2 需人工 / 3 完成带异常必读 anomalies
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from decimal import Decimal, localcontext
from decimal import ROUND_HALF_EVEN
from pathlib import Path

import chapter_planner

EXIT_OK, EXIT_ERROR, EXIT_MANUAL, EXIT_ANOMALY = 0, 1, 2, 3
D0 = Decimal("0")
D10 = Decimal(10)
HUNDRED, THOUSAND, WAN = Decimal(100), Decimal(1000), Decimal(10000)
# consistency.py（勿动模块）geo-era 合约段仍引用 fr.CATS——保留兼容符号；
# coal stage 槽位（L9.*）不匹配时其检查自然空转，不影响环评 5 域。
CATS = ("TM", "KZ", "TD")

# ── Decimal 超越运算基元（prec 50/60，禁 float 混算）────────────────────────

_PI50 = Decimal("3.1415926535897932384626433832795028841971693993751")


def q(x: Decimal, dp: str) -> Decimal:
    """ROUND_HALF_EVEN quantize。dp 例: '0.01' / '1' / '0.1'。"""
    return x.quantize(Decimal(dp), rounding=ROUND_HALF_EVEN)


def is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def dec(v) -> Decimal:
    """宽松转 Decimal；空/None/非数 → NaN（调用方过滤）。"""
    try:
        d = Decimal(str(v).strip())
        return d if d.is_finite() else Decimal("nan")
    except Exception:
        return Decimal("nan")


def _cos_deg(alpha_deg: Decimal) -> Decimal:
    """Decimal 余弦（度）——域归约到 [0,90°] 后 Taylor 级数（prec 60）。供 W_max=q·m·cosα。"""
    with localcontext() as ctx:
        ctx.prec = 60
        x = alpha_deg % Decimal(360)
        if x > Decimal(180):
            x = Decimal(360) - x  # cos(360°−x)=cos(x)
        sign = Decimal(1)
        if x > Decimal(90):
            x = Decimal(180) - x  # cos(180°−x)=−cos(x)
            sign = -sign
        rad = x * _PI50 / Decimal(180)
        r2 = rad * rad
        term, s, n = Decimal(1), Decimal(1), 0
        while abs(term) > Decimal("1e-58"):
            n += 1
            term = -term * r2 / Decimal((2 * n - 1) * (2 * n))
            s += term
        return +s if sign > 0 else -s  # 一元 + 触发 context 规整


def _slot_label(v) -> str:
    """槽位 [] 内标签清洗：禁空白（write_state 键形终检前置）。"""
    s = str(v if v is not None else "").strip().replace(" ", "_")
    return s or "?"


def _get(form: dict, path: str):
    """点分读取：嵌套 dict 优先、扁平点号键回退（与 ingest._get_dotted 同语义）。"""
    if "." in path:
        prefix, _, sub = path.partition(".")
        v = form.get(prefix)
        if isinstance(v, dict):
            return v.get(sub)
    return form.get(path)


# ══ 纯计算层（回归面：calc/ 5 脚本同参同果 + fracture_zone 新写）════════════
# 约定：*_core 返回未舍入 Decimal（compute 链式复用）；calc_* 为回归镜像——原脚本
# 出口舍入位逐键对齐（四舍六入五逢奇进偶舍），是 test_coal_eia_calc_regression 的比对面。


# ── subsidence 概率积分法（calc_subsidence.py 镜像）─────────────────────────

def _erf_dec(x: Decimal) -> Decimal:
    """Abramowitz & Stegun 7.1.26 误差函数近似（Decimal 复制原算法，prec 50）。"""
    with localcontext() as ctx:
        ctx.prec = 50
        one = Decimal(1)
        sign = one if x >= 0 else -one
        x = abs(x)
        t = one / (one + Decimal("0.3275911") * x)
        poly = (((((Decimal("1.061405429") * t + Decimal("-1.453152027")) * t + Decimal("1.421413741")) * t
                  + Decimal("-0.284496736")) * t + Decimal("0.254829592")) * t) * (-x * x).exp()
        return sign * (one - poly)


def _subsidence_core(params: dict) -> dict:
    """概率积分法主断面极值：W_max=q·m·cosα·1000；r=H/tanβ；U=bW；i=W/r；K=1.52W/r²；ε=1.52bW/r。

    能力边界：以上仅主断面极值与 W_max 层间叠加入 freeze；逐点剖面/等值线/阶段变形指标
    =开采沉陷软件成果走表单转录（profile 仅回归镜像保留，compute 不产槽位）。
    """
    q_c, b, tan_beta = dec(params["q"]), dec(params["b"]), dec(params["tan_beta"])
    m, H, alpha = dec(params["m"]), dec(params["H"]), dec(params["alpha"])
    if not tan_beta:
        raise KeyError("subsidence 输入 tan_beta=0（主要影响角正切为零——缺参报错绝不编造）")
    with localcontext() as ctx:
        ctx.prec = 50
        w_max = q_c * m * _cos_deg(alpha) * THOUSAND  # mm
        r = H / tan_beta  # m
        out = {
            "W_max_mm": w_max,
            "r_m": r,
            "U_max_mm": b * w_max,
            "i_max_mm_per_m": w_max / r,
            "K_max_per_m_e3": Decimal("1.52") * w_max / (r * r),
            "eps_max_mm_per_m": Decimal("1.52") * b * w_max / r,
        }
    if params.get("include_profile"):
        prof_range = dec(params.get("profile_range", 3))
        prof_points = int(dec(params.get("profile_points", 61)))
        with localcontext() as ctx:
            ctx.prec = 50
            x0, x1 = -prof_range * r, prof_range * r
            dx = (x1 - x0) / Decimal(prof_points - 1)
            profile = []
            for i in range(prof_points):
                xm = x0 + Decimal(i) * dx
                arg = -xm * _PI50.sqrt() / (2 * r)
                profile.append({"x_m": xm, "W_mm": w_max / 2 * (1 + _erf_dec(arg))})
            out["profile"] = profile
    return out


def calc_subsidence(params: dict) -> dict:
    """回归镜像——calc/calc_subsidence.py 同参同果（出口 dp：2/2/2/4/6/4）。"""
    core = _subsidence_core(params)
    out = {
        "W_max_mm": q(core["W_max_mm"], "0.01"),
        "r_m": q(core["r_m"], "0.01"),
        "U_max_mm": q(core["U_max_mm"], "0.01"),
        "i_max_mm_per_m": q(core["i_max_mm_per_m"], "0.0001"),
        "K_max_per_m_e3": q(core["K_max_per_m_e3"], "0.000001"),
        "eps_max_mm_per_m": q(core["eps_max_mm_per_m"], "0.0001"),
    }
    if "profile" in core:
        out["profile"] = [{"x_m": q(p["x_m"], "0.01"), "W_mm": q(p["W_mm"], "0.01")} for p in core["profile"]]
    return out


# ── fracture_zone 导水裂隙带/垮落带（纯新写——无既有 calc 脚本）───────────────
# 套用公式（《建筑物、水体、铁路及主要井巷煤柱留设与压煤开采规范》附录四，缓倾斜 α<54°，
# 单层一次采全高；M=累计采厚 m）：Hf = 100M/(aM+b) ± dev；样例口径取 +dev（最不利/安全）。
# 回代实证（回归测试单列）：软弱 100M/(3.1M+5.0)+4.0 → 月儿湾 1煤 M=1.46→19.33、3煤 M=1.69→20.51、
# 四季屯 6上/6下/7/8/10 煤 24.22/15.22/26.50/19.96/19.16 全部精确；极软弱 100M/(5.0M+8.0)+3.0
# → 四季屯 3煤 M=2.2→14.58 精确。
# 垮落带 Hc：MT/T1091-2008 附录D 类乘系数（四季屯样例表 3.2-21 转录：坚硬(4~5)M/中硬(3~4)M/
# 软弱·极软弱(1~2)M）取上界；四季屯表 3.2-24 软弱 Hc=2.0M 精确回代（2.2→4.40）。
# TODO(回代缺口)：厚煤层（M>3.5m）矿大（北京）『两带』经验公式与 MT/T1091 附录D 裂隙带公式——
# 样例公式体 OLE 不可转录，compute 层记 anomaly 提示软件/实测复核，禁凭记忆补系数。

_FRAC_FORMULAS: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    # 类: (a, b, ±dev, Hc 类乘系数上界) —— Hf 渐近极限=100/a
    "坚硬": (Decimal("1.2"), Decimal("2.0"), Decimal("8.9"), Decimal(5)),
    "中硬": (Decimal("1.6"), Decimal("3.6"), Decimal("5.6"), Decimal(4)),
    "软弱": (Decimal("3.1"), Decimal("5.0"), Decimal("4.0"), Decimal(2)),
    "极软弱": (Decimal("5.0"), Decimal("8.0"), Decimal("3.0"), Decimal(2)),
}


def _frac_class(text: str) -> str | None:
    """覆岩岩性描述 → 规范四类（极软弱优先于软弱匹配）。"""
    t = str(text or "")
    if "极软弱" in t or "极软" in t:
        return "极软弱"
    for cls in ("软弱", "中硬", "坚硬"):
        if cls in t:
            return cls
    return None


def _fracture_zone_core(params: dict) -> dict:
    M = dec(params["M"])
    cls = str(params["lithology"])
    if cls not in _FRAC_FORMULAS:
        raise KeyError(f"fracture_zone 岩性类别非法: {cls!r}（合法: 坚硬/中硬/软弱/极软弱）")
    a, b, dev, hc_mult = _FRAC_FORMULAS[cls]
    if not M or M <= 0:
        raise KeyError("fracture_zone 输入 M（累计采厚）非正——缺参报错绝不编造")
    with localcontext() as ctx:
        ctx.prec = 50
        hf_base = HUNDRED * M / (a * M + b)
        return {"lithology": cls, "M": M, "Hf_base": hf_base, "Hf_dev": dev, "Hf": hf_base + dev,
                "Hc": hc_mult * M, "Hf_limit": HUNDRED / a}


def calc_fracture_zone(params: dict) -> dict:
    """导水裂隙带（含冒落带）/垮落带最大高度（m，2dp；Hf=套用公式+dev 最不利口径）。"""
    core = _fracture_zone_core(params)
    return {"lithology": core["lithology"], "M": q(core["M"], "0.01"),
            "Hf_base": q(core["Hf_base"], "0.01"), "Hf_dev": core["Hf_dev"],
            "Hf": q(core["Hf"], "0.01"), "Hc": q(core["Hc"], "0.01"),
            "Hf_limit": q(core["Hf_limit"], "0.01")}


# ── capacity 环境容量（calc_capacity.py 镜像：A 值法 air + 一维模型 water）───

def _capacity_core(params: dict) -> dict:
    calc_type = str(params.get("type", "")).lower()
    with localcontext() as ctx:
        ctx.prec = 50
        if calc_type == "air":
            S, cs, cb = dec(params["area_km2"]), dec(params["target_conc_ugm3"]), dec(params["background_conc_ugm3"])
            a_val = dec(params.get("A_value", 4.5))
            delta = cs - cb
            if delta < 0:
                delta = D0  # 原脚本口径：负余量截 0
            qa_10kt = a_val * delta * S.sqrt()  # 万吨/年
            return {"type": "air", "capacity_10kt_per_year": qa_10kt, "capacity_tons_per_year": qa_10kt * WAN,
                    "delta_C": delta, "sqrt_area": S.sqrt(), "A_value": a_val}
    if calc_type == "water":
        with localcontext() as ctx:
            ctx.prec = 50
            Q, cs, cb = dec(params["river_flow_m3s"]), dec(params["target_conc_mgL"]), dec(params["background_conc_mgL"])
            k = dec(params.get("decay_coefficient", 0))
            delta = cs - cb
            if delta < 0:
                delta = D0
            w_basic = Decimal("86.4") * Q * delta / THOUSAND  # 吨/天（稀释容量）
            w_self = k * cs * Decimal("86.4") * Q / THOUSAND / (1 + k) if k > 0 else D0  # 原脚本线性近似
            w_total = w_basic + w_self
            return {"type": "water", "capacity_tons_per_day": w_total, "capacity_tons_per_year": w_total * Decimal(365),
                    "dilution_tpd": w_basic, "selfpurify_tpd": w_self, "delta_C": delta, "decay": k}
    raise KeyError(f"capacity 类型非法: {calc_type!r}（请使用 'air' 或 'water'）")


def calc_capacity(params: dict) -> dict:
    """回归镜像——calc/calc_capacity.py 同参同果（air: 4/2dp；water: 4/2dp；缺参返 error 键）。"""
    try:
        core = _capacity_core(params)
    except KeyError as e:
        missing = [k for k in ("area_km2", "target_conc_ugm3", "background_conc_ugm3") if k not in params] \
            if str(params.get("type", "")).lower() == "air" else \
            [k for k in ("river_flow_m3s", "target_conc_mgL", "background_conc_mgL") if k not in params]
        return {"error": f"缺少必要参数: {', '.join(missing)}" if missing else str(e)}
    if core["type"] == "air":
        return {"type": "air", "method": "A值法",
                "capacity_10kt_per_year": q(core["capacity_10kt_per_year"], "0.0001"),
                "capacity_tons_per_year": q(core["capacity_tons_per_year"], "0.01"),
                "details": {"A_value": core["A_value"],
                            "area_km2": dec(params["area_km2"]),
                            "target_conc_ugm3": dec(params["target_conc_ugm3"]),
                            "background_conc_ugm3": dec(params["background_conc_ugm3"]),
                            "delta_C_ugm3": q(core["delta_C"], "0.01"),
                            "sqrt_area": q(core["sqrt_area"], "0.0001")}}
    return {"type": "water", "method": "一维模型",
            "capacity_tons_per_day": q(core["capacity_tons_per_day"], "0.0001"),
            "capacity_tons_per_year": q(core["capacity_tons_per_year"], "0.01"),
            "details": {"river_flow_m3s": dec(params["river_flow_m3s"]),
                        "target_conc_mgL": dec(params["target_conc_mgL"]),
                        "background_conc_mgL": dec(params["background_conc_mgL"]),
                        "delta_C_mgL": q(core["delta_C"], "0.0001"),
                        "dilution_capacity_tpd": q(core["dilution_tpd"], "0.0001"),
                        "self_purification_capacity_tpd": q(core["selfpurify_tpd"], "0.0001"),
                        "decay_coefficient_per_day": core["decay"]}}


# ── water_balance 水量平衡（calc_water_balance.py 镜像）─────────────────────

def _water_balance_core(params: dict) -> dict:
    def _sum(items: list) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 50
            return sum((dec(it.get("volume_m3d", 0)) for it in items), D0)

    supply, demand = _sum(params.get("supply", [])), _sum(params.get("demand", []))
    reuse, discharge = _sum(params.get("reuse", [])), _sum(params.get("discharge", []))
    denom = demand + reuse
    reuse_rate = (reuse / denom * HUNDRED) if denom > 0 else D0
    balance = supply - demand
    ratio = (supply / demand) if demand > 0 else Decimal("Infinity")
    loss = (supply + reuse) - (demand + discharge)
    return {"total_supply": supply, "total_demand": demand, "total_reuse": reuse, "total_discharge": discharge,
            "reuse_rate": reuse_rate, "balance": balance, "ratio": ratio, "loss": loss}


def calc_water_balance(params: dict) -> dict:
    """回归镜像——calc/calc_water_balance.py 同参同果（2/2/2/2/4/2dp；ratio 除零→∞）。"""
    core = _water_balance_core(params)
    ratio = core["ratio"] if not core["ratio"].is_finite() else q(core["ratio"], "0.0001")
    return {"total_supply_m3d": q(core["total_supply"], "0.01"), "total_demand_m3d": q(core["total_demand"], "0.01"),
            "total_reuse_m3d": q(core["total_reuse"], "0.01"), "total_discharge_m3d": q(core["total_discharge"], "0.01"),
            "reuse_rate_pct": q(core["reuse_rate"], "0.01"), "balance_m3d": q(core["balance"], "0.01"),
            "balance_ratio": ratio, "water_loss_m3d": q(core["loss"], "0.01")}


# ── noise 声级合成/传播衰减（calc_noise.py 镜像 + 多源叠加扩展）──────────────

def _level_at(level: Decimal, stype: str, dist: Decimal, atm: Decimal, ground: Decimal) -> Decimal:
    """单源距离衰减（与 calc_noise.py 同式）：point Lp=Lw−20lgr−11−Δ；line Lp=Lw−10lg(r/7.5)−Δ。"""
    with localcontext() as ctx:
        ctx.prec = 50
        att = (dist.log10() * Decimal(20)) + Decimal(11) if stype == "point" else (dist / Decimal("7.5")).log10() * D10
        return level - att - atm - ground


def _sum_levels(levels: list[Decimal]) -> Decimal:
    """声级能量合成 10·lg Σ10^(Li/10)（未舍入——链式纪律）。"""
    with localcontext() as ctx:
        ctx.prec = 50
        return sum((D10 ** (lv / D10) for lv in levels), D0).log10() * D10


def _compliance_distance(levels: list[Decimal], stype: str, limit: Decimal,
                         atm: Decimal, ground: Decimal, background: Decimal | None) -> Decimal | None:
    """多源合成达标最大距离：L(r) 单调不增 → 二分反解（prec 50）。None=全距离达标或 1e7 m 仍超标。"""
    with localcontext() as ctx:
        ctx.prec = 50

        def over(r: Decimal) -> bool:
            ls = [_level_at(lv, stype, r, atm, ground) for lv in levels]
            if background is not None:
                ls.append(background)
            return _sum_levels(ls) > limit

        lo, hi = Decimal("0.01"), Decimal("10000000")
        if not over(lo) or over(hi):
            return None
        for _ in range(200):
            mid = (lo + hi) / 2
            if over(mid):
                lo = mid
            else:
                hi = mid
        return hi


def _noise_core(params: dict) -> dict:
    stype = str(params["source_type"])
    level, atm, gnd = dec(params["source_level_dBA"]), dec(params.get("atmospheric_absorption", 0)), dec(params.get("ground_factor", 0))
    preds = []
    for d in params["distances_m"]:
        dv = dec(d)
        if dv <= 0:
            continue
        preds.append({"distance_m": dv, "predicted": _level_at(level, stype, dv, atm, gnd)})

    def max_dist(limit: Decimal) -> Decimal:
        # 原脚本闭式反解：point 20lgr=Lw−limit−11−Δ；line 10lg(r/7.5)=Lw−limit−Δ
        with localcontext() as ctx:
            ctx.prec = 50
            eff = level - limit - (Decimal(11) if stype == "point" else D0) - atm - gnd
            if eff <= 0:
                return Decimal("Infinity")
            if stype == "point":
                return D10 ** (eff / Decimal(20))
            return (D10 ** (eff / D10)) * Decimal("7.5")

    return {"source_type": stype, "level": level, "predictions": preds, "max_dist": max_dist,
            "day": dec(params.get("day_limit_dBA", 60)), "night": dec(params.get("night_limit_dBA", 50))}


def calc_noise(params: dict) -> dict:
    """回归镜像——calc/calc_noise.py 同参同果（距离/声级 1dp；达标距离 1dp 或 ∞）。"""
    core = _noise_core(params)
    preds = [{"distance_m": q(p["distance_m"], "0.1"), "predicted_dBA": q(p["predicted"], "0.1"),
              "day_compliant": p["predicted"] <= core["day"], "night_compliant": p["predicted"] <= core["night"]}
             for p in core["predictions"]]

    def _qd(limit: Decimal) -> Decimal:
        d = core["max_dist"](limit)
        return d if not d.is_finite() else q(d, "0.1")

    return {"source_type": core["source_type"], "source_level_dBA": core["level"], "predictions": preds,
            "max_compliant_distance_day_m": _qd(core["day"]), "max_compliant_distance_night_m": _qd(core["night"]),
            "reference_standard": "GB12348", "day_limit_dBA": core["day"], "night_limit_dBA": core["night"]}


# ── air_screen 锅炉点源估算（calc_air_screen.py 镜像；仅点源适用——XS7）──────

_PG_SZ_COEFF: dict[str, Decimal] = {"A": Decimal("0.20"), "B": Decimal("0.12"), "C": Decimal("0.08"),
                                    "D": Decimal("0.06"), "E": Decimal("0.03"), "F": Decimal("0.016")}
_SZ_D = Decimal("0.89")
_PROFILE_DISTANCES = (50, 100, 200, 300, 500, 800, 1000, 1500, 2000, 3000, 5000, 8000, 10000, 15000, 20000, 30000, 50000)


def _air_screen_core(params: dict) -> dict:
    Q, Hs = dec(params["emission_rate_gs"]), dec(params["stack_height_m"])
    D_, vs, Ts = dec(params["stack_diameter_m"]), dec(params["exit_velocity_ms"]), dec(params["exit_temp_K"])
    Ta = dec(params.get("ambient_temp_K", 293.15))
    u = dec(params.get("wind_speed_ms", 3.0))
    stability = str(params.get("stability_class", "D")).upper()
    if stability not in _PG_SZ_COEFF:
        stability = "D"
    with localcontext() as ctx:
        ctx.prec = 50
        if u <= 0:
            u = Decimal("0.5")  # 原脚本除零防护
        delta_t = Ts - Ta
        # Holland 抬升：ΔH=(vs·D/u)·(1.5+2.68e-3·ΔT·D/u)
        d_h = vs * D_ / u * (Decimal("1.5") + Decimal("0.00268") * delta_t * D_ / u)
        if d_h < 0:
            d_h = D0
        h_eff = Hs + d_h
        c0 = _PG_SZ_COEFF[stability]

        def conc(x_m: Decimal) -> Decimal:
            # Briggs 城市 σy=0.32x/√(1+0.0004x)；σz=c·x^0.89；C=Q·1e6/(π·σy·σz·u)·exp(−H²/2σz²)
            sigma_y = Decimal("0.32") * x_m / (1 + Decimal("0.0004") * x_m).sqrt()
            sigma_z = c0 * (x_m ** _SZ_D)
            if sigma_y <= 0 or sigma_z <= 0 or u <= 0:
                return D0
            return Q * Decimal("1e6") / (_PI50 * sigma_y * sigma_z * u) * (-h_eff * h_eff / (2 * sigma_z * sigma_z)).exp()

        x_min, x_max, n = Decimal(100), Decimal(50000), 500
        dx = (x_max - x_min) / Decimal(n - 1)  # =100.0 精确——与原脚本同一搜索网格
        max_conc, max_dist = D0, D0
        for i in range(n):
            xm = x_min + Decimal(i) * dx
            c = conc(xm)
            if c > max_conc:
                max_conc, max_dist = c, xm
        profile = [{"distance_m": Decimal(d), "conc": conc(Decimal(d))} for d in _PROFILE_DISTANCES]
        return {"plume_rise": d_h, "effective_height": h_eff, "stability": stability, "wind": u,
                "max_conc": max_conc, "max_conc_distance": max_dist, "profile": profile}


def calc_air_screen(params: dict) -> dict:
    """回归镜像——calc/calc_air_screen.py 同参同果（抬升/有效高 2dp；浓度 4dp；距离 1dp）。"""
    core = _air_screen_core(params)
    return {"plume_rise_m": q(core["plume_rise"], "0.01"), "effective_height_m": q(core["effective_height"], "0.01"),
            "stability_class": core["stability"], "wind_speed_ms": core["wind"],
            "max_conc_ugm3": q(core["max_conc"], "0.0001"), "max_conc_distance_m": q(core["max_conc_distance"], "0.1"),
            "concentration_profile": [{"distance_m": p["distance_m"], "concentration_ugm3": q(p["conc"], "0.0001")}
                                      for p in core["profile"]]}


# ── data/ 装载（geo 语义原样）────────────────────────────────────────────────

class Data:
    """data/ 只读装载。impacted dry-run 在内存副本上覆盖（零写盘）。"""

    def __init__(self, data_dir: Path, stage: dict):
        self.dir = data_dir
        self.stage = stage
        self.forms: dict[str, dict] = {}
        self.csvs: dict[str, list[dict]] = {}
        for fam, spec in stage.get("forms", {}).items():
            if not spec.get("file"):
                continue  # projection 等 ghost 族（file=null）——无落盘载体
            p = data_dir / spec["file"]
            if not p.exists():
                continue
            if spec.get("format") == "csv" or "columns" in spec:
                with open(p, encoding="utf-8-sig", newline="") as f:
                    self.csvs[fam] = [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]
            else:
                self.forms[fam] = json.loads(p.read_text(encoding="utf-8"))

    def fam_by_prefix(self, prefix: str) -> str | None:
        for fam, spec in self.stage.get("forms", {}).items():
            if spec.get("file") and spec["file"].split("_", 1)[0] == prefix:
                return fam
        return None

    def form(self, fam: str) -> dict:
        return self.forms.get(fam) or {}


def override_data(data: Data, field: str, value: str) -> Data:
    """field 语法：'13.q'（JSON 字段，点分子键扁平直写——compute _get 兼容读回）或 '13a:列名'（CSV 整列）。"""
    if ":" in field and "." not in field:
        _, col = field.split(":", 1)
        for rows in data.csvs.values():
            for row in rows:
                if col in row:
                    row[col] = value
        return data
    prefix, key = field.split(".", 1)
    fam = data.fam_by_prefix(prefix)
    data.forms.setdefault(fam, {})[key] = float(value) if is_num(value) else value
    return data


# ── 计算编排（5 域 → 槽位注册表）────────────────────────────────────────────

def compute(data: Data) -> tuple[dict, list[str]]:
    """全量计算 → (values: 槽位注册表, anomalies)。槽位 key 与 stages/planning_eia.json 的
    formulas 声明/{{SLOT:}} 引用逐一对齐（subsidence/fracture_zone/capacity:water/capacity:air/
    noise/air_screen/water_balance——不自创键名）。"""
    V: dict[str, dict] = {}
    anomalies: list[str] = []

    def emit(key: str, val: Decimal, dp: str, unit: str, source: str, extra: dict | None = None) -> None:
        # bug-3036 同构：计算层不产垃圾槽位——非有限值就地抛错（键形/空 display 由 write_state 终检把关）。
        d = q(val, dp)
        if not d.is_finite():
            raise ValueError(f"emit 拒绝非有限值 {key}={val}（dp={dp}）——检查上游输入缺参/除零")
        V[key] = {"value": float(d), "display": f"{d}", "unit": unit, "source": source, **(extra or {})}

    # ── 13 表单守卫（bug-2223 同构：空白表单=缺失）──
    sp = data.form("subsidence_params")
    if sp and not (dec(sp.get("q")).is_finite() and dec(sp.get("b")).is_finite() and dec(sp.get("tan_beta")).is_finite()):
        sp = None
    per_mine = (sp or {}).get("per_mine") or []

    # ── D1 subsidence 概率积分法（W_max 层间叠加；变形/面积=软件转录，能力边界）──
    if sp:
        if not per_mine:
            anomalies.append("13_subsidence_params.per_mine 缺失/空——subsidence 链未计算（缺参不编造）")
        mine_tot: dict[str, Decimal] = {}
        for i, row in enumerate(per_mine):
            m_, h_, al_ = dec(row.get("m")), dec(row.get("H")), dec(row.get("alpha"))
            if not (m_.is_finite() and h_.is_finite() and al_.is_finite()):
                anomalies.append(f"subsidence_params.per_mine[{i}] m/H/alpha 缺失或非数——行跳过（缺参不编造）")
                continue
            mine_key = str(row.get("mine") or f"矿{i + 1}")
            lbl = f"{_slot_label(mine_key)}|{_slot_label(row.get('seam') or f'层{i + 1}')}"
            # 重复采动：flag 驱动派生值（q/tnβ 重复采动取值），禁手填双值（D4/param_source 枚举配套）
            q_eff, tb_eff = dec(sp["q"]), dec(sp["tan_beta"])
            if bool(row.get("repeat_mining")):
                q_rep, tb_rep = dec(sp.get("q_repeat_mining")), dec(sp.get("tan_beta_repeat_mining"))
                if q_rep.is_finite():
                    q_eff = q_rep
                else:
                    anomalies.append(f"subsidence {lbl} 重复采动=true 但 q_repeat_mining 未录入——按单次采动基值计算（需人工复核）")
                if tb_rep.is_finite():
                    tb_eff = tb_rep
                else:
                    anomalies.append(f"subsidence {lbl} 重复采动=true 但 tan_beta_repeat_mining 未录入——按基值计算（需人工复核）")
            core = _subsidence_core({"q": q_eff, "b": dec(sp["b"]), "tan_beta": tb_eff, "m": m_, "H": h_, "alpha": al_})
            emit(f"subsidence.W_max[{lbl}]", core["W_max_mm"], "0.01", "mm", "formula:subsidence",
                 {"inputs": {"q": float(q_eff), "m": float(m_), "alpha": float(al_), "repeat_mining": bool(row.get("repeat_mining"))}})
            emit(f"subsidence.r[{lbl}]", core["r_m"], "0.01", "m", "formula:subsidence",
                 {"inputs": {"H": float(h_), "tan_beta": float(tb_eff)}})
            mine_tot[mine_key] = mine_tot.get(mine_key, D0) + core["W_max_mm"]  # 层间叠加=ΣW_max（概率积分法线性叠加）
        for mine_key, w in sorted(mine_tot.items()):
            emit(f"subsidence.W_max[{_slot_label(mine_key)}]", w, "0.01", "mm", "formula:subsidence", {"口径": "逐矿层间叠加(Σ煤层)"})
        if mine_tot:
            emit("subsidence.W_max", max(mine_tot.values()), "0.01", "mm", "formula:subsidence", {"口径": "全矿区最大（XS4 max 口径）"})
            emit("subsidence.W_max[min]", min(mine_tot.values()), "0.01", "mm", "formula:subsidence", {"口径": "全矿区最小（XS4 min_max_pair）"})
        # 能力边界（月儿湾实证 U/W=0.44≠b——禁公式硬凑）：倾斜/曲率/水平移动/水平变形/沉陷面积=软件成果转录
        sw = sp.get("software_results") or {}
        for k, slot, unit, dp in (("i_max", "subsidence.i_max", "mm/m", "0.0001"),
                                  ("eps_max", "subsidence.eps_max", "mm/m", "0.0001"),
                                  ("K_max", "subsidence.K_max", "10^-3/m", "0.000001"),
                                  ("U_max", "subsidence.U_max", "mm", "0.01"),
                                  ("subsidence_area_km2", "subsidence.subsidence_area_km2", "km2", "0.01")):
            v = dec(sw.get(k))
            if v.is_finite():
                emit(slot, v, dp, unit, "form:subsidence_params(开采沉陷软件成果转录——能力边界禁公式硬凑)")
        if per_mine and not sw:
            anomalies.append("subsidence_params.software_results 未转录——subsidence.i_max/eps_max/K_max/U_max/"
                             "subsidence_area_km2 槽位未冻结（倾斜/曲率/水平变形/沉陷面积=软件成果走表单，禁公式硬凑——能力边界）")
    else:
        anomalies.append("13_subsidence_params 缺失/空白——subsidence/fracture_zone 链未计算（缺参不编造）")

    # ── D2 fracture_zone 导水裂隙带/垮落带（三下规范套用公式；XS5）──
    if sp and per_mine:
        lith_form = sp.get("overburden_lithology")
        hf_max = hc_max = None
        for i, row in enumerate(per_mine):
            m_ = dec(row.get("m"))
            if not m_.is_finite():
                continue  # 行级缺失已在上链记 anomaly
            al_ = dec(row.get("alpha"))
            if al_.is_finite() and al_ > 54:
                anomalies.append(f"fracture_zone per_mine[{i}] 倾角 {al_}°>54°——套用公式限缓倾斜/倾斜（<54°），急倾斜需规范急倾斜公式（人工复核）")
            cls = _frac_class(row.get("lithology") or lith_form)
            if cls is None:
                anomalies.append(f"fracture_zone per_mine[{i}] 覆岩岩性无法归类（{row.get('lithology') or lith_form!r}）"
                                 "——行跳过（合法: 坚硬/中硬/软弱/极软弱；缺参不编造）")
                continue
            core = _fracture_zone_core({"M": m_, "lithology": cls})
            lbl = f"{_slot_label(row.get('mine') or f'矿{i + 1}')}|{_slot_label(row.get('seam') or f'层{i + 1}')}"
            emit(f"fracture_zone.fracture_height[{lbl}]", core["Hf"], "0.01", "m", "formula:fracture_zone",
                 {"inputs": {"M": float(m_), "lithology": cls, "formula": f"100M/({core['lithology']}系数)±dev，取+dev 最不利"}})
            emit(f"fracture_zone.collapse_height[{lbl}]", core["Hc"], "0.01", "m", "formula:fracture_zone",
                 {"inputs": {"M": float(m_), "lithology": cls, "formula": "MT/T1091-2008 附录D 类乘系数上界"}})
            if m_ > Decimal("3.5"):
                anomalies.append(f"fracture_zone {lbl} 采厚 {m_}m>3.5m——厚煤层『两带』矿大经验公式分支未录入（样例 OLE 不可转录），"
                                 "套用公式外推值需开采沉陷/水文软件或实测两带成果复核")
            hf_max = core["Hf"] if hf_max is None else max(hf_max, core["Hf"])
            hc_max = core["Hc"] if hc_max is None else max(hc_max, core["Hc"])
        if hf_max is not None:
            emit("fracture_zone.fracture_height", hf_max, "0.01", "m", "formula:fracture_zone", {"口径": "全矿区最大（XS5）"})
            emit("fracture_zone.collapse_height", hc_max, "0.01", "m", "formula:fracture_zone", {"口径": "全矿区最大"})

    # ── D4 water 域：capacity:water + water_balance + mine_inflow（XS12）──
    wf = data.form("water")
    inflow_total = D0
    if wf.get("mine_inflow"):
        for i, r0 in enumerate(wf["mine_inflow"]):
            v = dec(r0.get("inflow_m3_d"))
            if not v.is_finite():
                anomalies.append(f"water.mine_inflow[{i}] inflow_m3_d 缺失/非数——行跳过")
                continue
            lbl = _slot_label(r0.get("mine") or f"矿{i + 1}")
            emit(f"water.mine_inflow[{lbl}]", v, "0.01", "m3/d", "form:14_water(XS12 涌水口径 canon)")
            inflow_total += v
            if not r0.get("measured") and not str(r0.get("analog_source") or "").strip():
                anomalies.append(f"water.mine_inflow[{lbl}] 非实测且无 analog_source——XS12 类比来源标注必填")
        if inflow_total:
            emit("water.mine_inflow", inflow_total, "0.01", "m3/d", "form:14_water(XS12 涌水口径 canon)", {"口径": "全矿区合计"})

    rw = wf.get("receiving_water") or {}
    cw_q, cw_cs, cw_cb = dec(_get(rw, "river_flow_m3s")), dec(_get(rw, "target_conc_mgL")), dec(_get(rw, "background_conc_mgL"))
    cw_k = dec(rw.get("decay_coefficient"))
    cw_k = cw_k if cw_k.is_finite() else D0  # 原脚本默认 0
    if cw_q.is_finite() and cw_q > 0 and cw_cs.is_finite() and cw_cb.is_finite():
        core = _capacity_core({"type": "water", "river_flow_m3s": cw_q, "target_conc_mgL": cw_cs,
                               "background_conc_mgL": cw_cb, "decay_coefficient": cw_k})
        emit("capacity:water.capacity", core["capacity_tons_per_day"], "0.0001", "吨/天", "formula:capacity:water",
             {"inputs": {"river_flow_m3s": float(cw_q), "target_conc_mgL": float(cw_cs),
                         "background_conc_mgL": float(cw_cb), "decay_coefficient": float(cw_k)}})
        emit("capacity:water.capacity_t_y", core["capacity_tons_per_year"], "0.01", "吨/年", "formula:capacity:water")
        emit("capacity:water.dilution_tpd", core["dilution_tpd"], "0.0001", "吨/天", "formula:capacity:water")
        emit("capacity:water.selfpurify_tpd", core["selfpurify_tpd"], "0.0001", "吨/天", "formula:capacity:water")
    else:
        anomalies.append("14_water.receiving_water 不完整（river_flow/target_conc/background）——capacity:water 槽位未计算（缺参不编造）")

    bal = wf.get("balance") or {}
    dm = wf.get("demand") or {}
    supply_items = bal.get("supply") or ([{"name": "矿井涌水合计(XS12)", "volume_m3d": inflow_total}] if inflow_total else [])
    demand_items = bal.get("demand") or [{"name": k, "volume_m3d": dec(dm.get(k))}
                                         for k in ("production", "domestic", "ecological") if dec(dm.get(k)).is_finite()]
    reuse_items, discharge_items = bal.get("reuse") or [], bal.get("discharge") or []
    if supply_items and demand_items:
        core = _water_balance_core({"supply": supply_items, "demand": demand_items,
                                    "reuse": reuse_items, "discharge": discharge_items})
        emit("water_balance.supply", core["total_supply"], "0.01", "m3/d", "formula:water_balance",
             {"口径": "balance.supply 表；缺表单时按逐矿涌水量 XS12 口径合成"})
        emit("water_balance.demand", core["total_demand"], "0.01", "m3/d", "formula:water_balance",
             {"口径": "balance.demand 表；缺表单时按 demand.production/domestic/ecological 合成"})
        emit("water_balance.deficit", core["balance"], "0.01", "m3/d", "formula:water_balance",
             {"口径": "supply−demand，正=盈余负=不足（冻结值禁手填）"})
        emit("water_balance.reuse", core["total_reuse"], "0.01", "m3/d", "formula:water_balance")
        emit("water_balance.reuse_rate", core["reuse_rate"], "0.01", "%", "formula:water_balance")
        emit("water_balance.loss", core["loss"], "0.01", "m3/d", "formula:water_balance",
             {"口径": "(supply+reuse)−(demand+discharge)，蒸发/损耗折入（水量平衡表内部自洽口径）"})
        if core["ratio"].is_finite():
            emit("water_balance.balance_ratio", core["ratio"], "0.01", "supply/demand", "formula:water_balance")
        ev = dec(bal.get("evaporation"))
        if ev.is_finite():
            emit("water_balance.evaporation", ev, "0.01", "m3/d", "form:14_water(水平衡表转录)")
    else:
        anomalies.append("14_water 需水/供水输入不完整——water_balance.supply/demand/deficit 槽位未计算（差额禁手填，缺参不编造）")

    # ── D3a capacity:air A 值法（GB/T 13201-91 待核实纪律）──
    af = data.form("air")
    cap_in = af.get("capacity_inputs") or {}
    ca_s, ca_cs, ca_cb, ca_a = dec(_get(cap_in, "area")), dec(_get(cap_in, "target_conc")), dec(_get(cap_in, "background")), dec(_get(cap_in, "a_value"))
    if ca_s.is_finite() and ca_s > 0 and ca_cs.is_finite() and ca_cb.is_finite() and ca_a.is_finite():
        core = _capacity_core({"type": "air", "area_km2": ca_s, "target_conc_ugm3": ca_cs,
                               "background_conc_ugm3": ca_cb, "A_value": ca_a})
        emit("capacity:air.capacity", core["capacity_10kt_per_year"], "0.0001", "万吨/年", "formula:capacity:air",
             {"inputs": {"area_km2": float(ca_s), "target_conc_ugm3": float(ca_cs),
                         "background_conc_ugm3": float(ca_cb), "A_value": float(ca_a),
                         "note": "A 值 GB/T 13201-91【待核实】纪律；目标浓度查 GB 3095 limit_tables"}})
        emit("capacity:air.capacity_t_a", core["capacity_tons_per_year"], "0.01", "吨/年", "formula:capacity:air")
    else:
        anomalies.append("15_air.capacity_inputs 不完整（area/target_conc/background/a_value）——capacity:air 槽位未计算"
                         "（A 值 GB/T 13201-91 待核实，缺参不编造）")

    # ── D5 noise 多源叠加（单源衰减对齐 calc_noise + 能量合成）──
    nf = data.form("noise")
    if nf.get("sources"):
        lim = nf.get("limits") or {}
        day_lim = dec(lim.get("day"))
        if not day_lim.is_finite():
            day_lim = dec(lim.get("day_limit_dBA"))
        night_lim = dec(lim.get("night"))
        if not night_lim.is_finite():
            night_lim = dec(lim.get("night_limit_dBA"))
        atm, gnd = dec(nf.get("atmospheric_absorption") or 0), dec(nf.get("ground_factor") or 0)
        bg = dec((nf.get("background") or {}).get("level"))
        bg = bg if bg.is_finite() else None
        groups: dict[str, list[tuple[str, Decimal]]] = {"point": [], "line": []}
        for i, s0 in enumerate(nf["sources"]):
            lv, st = dec(s0.get("level")), str(s0.get("type") or "").strip()
            stn = {"point": "point", "点源": "point", "line": "line", "线源": "line"}.get(st)
            if not lv.is_finite() or stn is None:
                anomalies.append(f"noise.sources[{i}] level 缺失或 type 非法（{st!r}，合法: 点源/线源）——行跳过")
                continue
            groups[stn].append((str(s0.get("source") or f"源{i + 1}"), lv))
        dists = nf.get("distances") or {}

        def _dist_list(v) -> list[Decimal]:
            return [dec(x) for x in (v if isinstance(v, list) else [v])]

        def _grp_levels(grp: str, d: Decimal) -> list[Decimal]:
            ls = [_level_at(lv, grp, d, atm, gnd) for _, lv in groups[grp]]
            if bg is not None:
                ls.append(bg)  # 背景能量合成（D4：背景值非本区实测必须带类比来源标注）
            return ls

        eval_dist: dict[str, Decimal] = {}
        for grp in ("point", "line"):
            if not groups[grp]:
                continue
            dl = [d for d in _dist_list(dists.get(grp)) if d.is_finite() and d > 0]
            if not dl:
                anomalies.append(f"noise.distances.{grp} 缺失/非法——noise.{grp}_level 槽位未计算")
                continue
            eval_dist[grp] = min(dl)  # 主槽位取最近距离（最不利声级）；全距列进表槽位
            for d in dl:
                emit(f"noise.{grp}_level[{_slot_label(d)}m]", _sum_levels(_grp_levels(grp, d)), "0.1", "dB(A)",
                     "formula:noise", {"distance_m": float(d), "sources": [n for n, _ in groups[grp]]})
            emit(f"noise.{grp}_level", _sum_levels(_grp_levels(grp, eval_dist[grp])), "0.1", "dB(A)",
                 "formula:noise", {"distance_m": float(eval_dist[grp]), "sources": [n for n, _ in groups[grp]],
                                   "口径": "多源能量合成 10·lgΣ10^(Li/10)" + ("（含背景）" if bg is not None else "")})
        if groups["point"] and (day_lim.is_finite() or night_lim.is_finite()):
            pt_levels = [lv for _, lv in groups["point"]]
            for tag, lim_v in (("day", day_lim), ("night", night_lim)):
                if not lim_v.is_finite():
                    continue
                r = _compliance_distance(pt_levels, "point", lim_v, atm, gnd, bg)
                if r is None:
                    far = _sum_levels(_grp_levels("point", Decimal("10000000")))
                    anomalies.append(f"noise 点源组合成声级在评估范围{'内已全程低于' if far <= lim_v else '外仍高于'}"
                                     f"{tag}限值 {lim_v} dB(A)——{'无超标距离' if far <= lim_v else '有限达标距离不存在（全程超标，人工复核布局）'}")
                else:
                    emit(f"noise.compliance_distance_{tag}", r, "0.1", "m", "formula:noise",
                         {"limit_dBA": float(lim_v), "口径": "多源合成曲线二分反解"})
            main_lim, main_tag = (night_lim, "night") if night_lim.is_finite() else (day_lim, "day")
            r = _compliance_distance(pt_levels, "point", main_lim, atm, gnd, bg)
            if r is not None:
                emit("noise.compliance_distance", r, "0.1", "m", "formula:noise",
                     {"limit_dBA": float(main_lim), "口径": f"点源组 vs {main_tag} 限值（GB 12348 厂界）"})
    else:
        anomalies.append("16_noise.sources 缺失/空——noise 槽位未计算（缺参不编造）")

    # ── D3b air_screen 锅炉点源（仅点源适用——XS7/能力边界：扬尘面源禁硬套）──
    boilers = af.get("boilers") or []
    if boilers:
        met = af.get("meteorology") or {}
        u_def = dec(met.get("wind_speed"))
        u_def = u_def if u_def.is_finite() else Decimal("3.0")  # 原脚本筛选默认风
        st_def = str(met.get("stability") or "D").upper()
        g_max, g_dist, g_label = None, None, ""
        for i, b0 in enumerate(boilers):
            hs, d_, vs, ts = dec(b0.get("stack_h")), dec(b0.get("stack_d")), dec(b0.get("stack_v")), dec(b0.get("stack_t"))
            if ts.is_finite() and ts < 200:
                ts = ts + Decimal("273.15")  # 烟温常以℃录入——<200 判为℃→K（formulas.json 单位约定）
            if not (hs.is_finite() and d_.is_finite() and vs.is_finite() and ts.is_finite()):
                anomalies.append(f"air boilers[{i}] stack_h/d/v/stack_t 缺失或非数——行跳过（缺参不编造）")
                continue
            blbl = _slot_label(b0.get("name") or f"锅炉{i + 1}")
            u = dec(b0.get("wind_speed_ms"))
            u = u if u.is_finite() else u_def
            st = str(b0.get("stability_class") or st_def).upper()
            polls = b0.get("pollutants") or {}
            direct = False
            if not polls and b0.get("emission_rate_gs") is not None:
                polls = {"排放速率": b0["emission_rate_gs"]}  # 直给速率（回归接口形）
                direct = True
            if not polls:
                anomalies.append(f"air boilers[{i}]（{blbl}）pollutants/emission_rate_gs 均缺——air_screen 行跳过")
                continue
            rise_done = False
            for pname, cval in polls.items():
                c_val = dec(cval)
                if not c_val.is_finite():
                    continue
                if direct:
                    q_gs = c_val
                else:
                    # Q(g/s)=C(mg/m³)×V(m³/s)/1000；V=π/4·d²·v（出口流速×截面）
                    with localcontext() as ctx2:
                        ctx2.prec = 50
                        v_flow = _PI50 / 4 * d_ * d_ * vs
                        q_gs = c_val * v_flow / THOUSAND
                core = _air_screen_core({"emission_rate_gs": q_gs, "stack_height_m": hs, "stack_diameter_m": d_,
                                         "exit_velocity_ms": vs, "exit_temp_K": ts, "wind_speed_ms": u, "stability_class": st})
                pl = f"{blbl}|{_slot_label(pname)}"
                emit(f"air_screen.max_ground_conc[{pl}]", core["max_conc"], "0.0001", "ug/m3", "formula:air_screen",
                     {"inputs": {"Q_g_s": float(q(q_gs, "0.0001")), "stability": core["stability"],
                                 "wind_speed_ms": float(core["wind"])}})
                emit(f"air_screen.max_conc_distance[{pl}]", core["max_conc_distance"], "0.1", "m", "formula:air_screen")
                if not rise_done:
                    # 抬升/有效高与污染物无关——首个污染物核心结果即代表（Holland 公式体单一事实源）
                    emit(f"air_screen.plume_rise[{blbl}]", core["plume_rise"], "0.01", "m", "formula:air_screen")
                    emit(f"air_screen.effective_height[{blbl}]", core["effective_height"], "0.01", "m", "formula:air_screen")
                    rise_done = True
                if g_max is None or core["max_conc"] > g_max:
                    g_max, g_dist, g_label = core["max_conc"], core["max_conc_distance"], pl
        if g_max is not None:
            emit("air_screen.max_ground_conc", g_max, "0.0001", "ug/m3", "formula:air_screen", {"口径": f"全锅炉×污染物最大（{g_label}）"})
            emit("air_screen.max_conc_distance", g_dist, "0.1", "m", "formula:air_screen", {"口径": "对应最大落地距离"})
    else:
        anomalies.append("15_air.boilers 缺失/空——air_screen 槽位未计算（仅锅炉点源适用；扬尘面源走源强取值禁硬套点源模型——XS7/能力边界）")

    # ── 派生值（禁手填——stage {{SLOT:}} 引用，source=derived）──
    sw_form = data.form("solid_waste")
    mp = data.form("mine_plan")
    rate, scale = dec(sw_form.get("gangue_rate")), dec(mp.get("total_scale_mt_a_after"))
    if rate.is_finite() and scale.is_finite() and scale > 0:
        # 矸石产生量(万t/a)=产率%×总规模Mt/a（1 Mt=100 万t：rate/100×scale×100）
        emit("solid_waste.gangue_generation", rate / HUNDRED * scale * HUNDRED, "0.01", "万t/a", "derived:solid_waste",
             {"inputs": {"gangue_rate_pct": float(rate), "total_scale_mt_a": float(scale)}, "口径": "产率×总规模——派生值禁手填"})
    elif sw_form:
        anomalies.append("solid_waste.gangue_rate 或 mine_plan.total_scale_mt_a_after 缺失——solid_waste.gangue_generation 派生槽位未计算")

    inv = data.form("investment")
    env, tot = dec(inv.get("env_investment")), dec(inv.get("total_investment"))
    if env.is_finite() and tot.is_finite() and tot > 0:
        emit("investment.env_investment_ratio", env / tot * HUNDRED, "0.01", "%", "derived:investment",
             {"inputs": {"env_investment_wy": float(env), "total_investment_wy": float(tot)}, "口径": "派生值禁手填（XS9）"})
    elif env.is_finite():
        anomalies.append("investment.total_investment 未列——env_investment_ratio 派生槽位 skip 非 fail（XS9，横城实证）")

    return V, anomalies


# ── 状态落盘/差分 ────────────────────────────────────────────────────────────

# 槽位键形（bug-3036）：C9.outlier_threshold / L8.C_orebody[①] / capacity:water.capacity（环评
# 域公式 id 含冒号——stages/planning_eia.json formulas 声明原样）；
# 拒绝循环变量名（"key"/"val"/…）与表达式串（含空白/运算符）——LLM 直写特征形状。
_SLOT_KEY_RE = re.compile(r"^[A-Za-z][\w:]*(?:\.\w+)*(?:\[[^\]\s]+\])?$")
_JUNK_KEYS = {"key", "val", "value", "x", "tmp", "result", "display", "unit", "source"}


def write_state(path: Path, values: dict, anomalies: list[str]) -> None:
    # 落盘前终检（bug-3036）：键形、空/缺失 display、非对象槽位、非有限数值就地拦——冻结层
    # （唯一写者=本脚本）不得产出 LLM 直写特征形状。allow_nan=False 使 NaN/Inf 序列化即抛。
    for key, slot in values.items():
        if key in _JUNK_KEYS or not _SLOT_KEY_RE.match(key):
            raise ValueError(f"槽位键形非法 {key!r}（形如 subsidence.W_max / capacity:water.capacity / noise.point_level[50m]；bug-3036）")
        if not isinstance(slot, dict):
            raise ValueError(f"槽位 {key} 非对象——emit 是唯一合法形状来源（bug-3036）")
        disp = slot.get("display")
        if disp is None or not str(disp).strip():
            raise ValueError(f"槽位 {key} display 为空——空槽位禁入冻结层（bug-3036）")
    doc = {"version": 2, "values": values, "anomalies": anomalies}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def diff_values(old: dict, new: dict) -> dict[str, str]:
    """值差分：{key: "old → new"}（变化/新增/删除全计）。"""
    out: dict[str, str] = {}
    for k in sorted(set(old) | set(new)):
        a = old.get(k, {}).get("value")
        b = new.get(k, {}).get("value")
        if a != b:
            out[k] = f"{a if a is not None else '(无)'} → {b if b is not None else '(删)'}"
    return out


def affected_formulas(changes: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for k in changes:
        fid = k.split(".", 1)[0].split("[", 1)[0]
        if fid not in ids:
            ids.append(fid)
    return sorted(ids)


# ── 子命令（CLI 面与 geo 逐字一致——execute/check/trace/impacted/update）─────

def _load(args) -> Data:
    return Data(Path(args.data_dir), _stage_of(args))


def _stage_of(args) -> dict:
    return json.loads(Path(args.stage).read_text(encoding="utf-8"))


def cmd_execute(args) -> int:
    # bug-2223: --output 与 --state-dir 二选一（state-dir 写 {dir}/formula_state.json）
    if args.output:
        out = Path(args.output)
    elif args.state_dir:
        out = Path(args.state_dir) / "formula_state.json"
    else:
        print("[formula] 错误: execute 需要 --output <文件> 或 --state-dir <目录> 之一", file=sys.stderr)
        return EXIT_ERROR
    try:
        values, anomalies = compute(_load(args))
        write_state(out, values, anomalies)
    except KeyError as e:
        print(f"[formula] 错误: {e}", file=sys.stderr)
        return EXIT_ERROR
    except ValueError as e:
        # 复核修复（bug-3058）：write_state 终检不再裸 traceback——给出可动手指引。
        print(f"[formula] 错误: {e}", file=sys.stderr)
        print("[formula] 提示: 键形非法多因 data/ 源数据标签含空白或特殊字符——清洗源数据（ingest.py file/forms）后重跑 execute；冻结层禁止手改", file=sys.stderr)
        return EXIT_ERROR
    print(f"STATE_READY: {out} slots={len(values)} anomalies={len(anomalies)}")
    for a in anomalies:
        print(f"  ANOMALY: {a}")
    return EXIT_ANOMALY if anomalies else EXIT_OK


def cmd_check(args) -> int:
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    frozen = {k: v.get("value") for k, v in state.get("values", {}).items()}
    issues: list[dict] = []
    try:
        fresh, _ = compute(_load(args))
        recomputed = {k: v.get("value") for k, v in fresh.items()}
        for k in sorted(set(frozen) | set(recomputed)):  # 自洽重算：冻结值必须逐值相等
            if frozen.get(k) != recomputed.get(k):
                sev = "fail" if k in frozen and k in recomputed else "warn"
                issues.append({"severity": sev, "check": "state_selfcheck", "detail": f"{k}: 冻结 {frozen.get(k)} vs 重算 {recomputed.get(k)}"})
    except KeyError as e:
        issues.append({"severity": "fail", "check": "state_selfcheck", "detail": f"重算失败: {e}"})
    if args.anchors:  # 锚点回归（eval 回放断言）
        anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8")) if args.anchors.endswith(".json") else json.loads(args.anchors)
        for k, expected in anchors.items():
            got = frozen.get(k)
            if got is None:
                issues.append({"severity": "fail", "check": "anchor", "detail": f"{k}: 状态中不存在"})
            elif abs(dec(got) - dec(expected)) > Decimal("0.005"):
                issues.append({"severity": "fail", "check": "anchor", "detail": f"{k}: 期望 {expected} 实得 {got}"})
            else:
                issues.append({"severity": "pass", "check": "anchor", "detail": f"{k}={got} ✓"})
    out = {"issues": issues, "summary": {s: sum(1 for i in issues if i["severity"] == s) for s in ("pass", "warn", "fail")}}
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"CHECK_READY: {args.output}")
    for i in issues:
        print(f"  [{i['severity'].upper()}] {i['check']}: {i['detail']}")
    return EXIT_ERROR if out["summary"]["fail"] else (EXIT_MANUAL if out["summary"]["warn"] else EXIT_OK)


def cmd_trace(args) -> int:
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    defs = {f["id"]: f for f in json.loads(Path(args.formulas).read_text(encoding="utf-8"))["formulas"]}
    traces = [{
        "formula_id": (fid := key.split(".", 1)[0].split("[", 1)[0]),
        "slot": key, "name": defs.get(fid, {}).get("name", "?"),
        "expr": defs.get(fid, {}).get("expr", "?"),
        "value": v.get("value"), "display": v.get("display"), "unit": v.get("unit"),
        "precision": defs.get(fid, {}).get("precision", "?"),
        "source": v.get("source"), "inputs": v.get("inputs", {}),
    } for key, v in sorted(state.get("values", {}).items())]
    out = {"traces": traces}
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"TRACE_READY: {args.output} traces={len(traces)}")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return EXIT_OK


def _dryrun_diff(args) -> tuple[dict, list[str], list[str]]:
    data = _load(args)
    base = json.loads(Path(args.state).read_text(encoding="utf-8")).get("values", {})
    new_values, anomalies = compute(override_data(data, args.field, args.value))
    changes = diff_values(base, new_values)
    return changes, affected_formulas(changes), anomalies


def cmd_impacted(args) -> int:
    changes, fids, _ = _dryrun_diff(args)
    chapters: list[str] = []
    prefix = args.field.split(".", 1)[0].split(":", 1)[0]
    fam = _load(args).fam_by_prefix(prefix)
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        chapters = chapter_planner.impacted_chapters(fids, [fam] if fam else [], manifest)
    result = {"param": args.field, "value": args.value, "changes": changes,
              "affected_formulas": fids, "affected_chapters": chapters}
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"IMPACTED_READY: {args.output}")
    print(out)
    return EXIT_OK


def cmd_update(args) -> int:
    # 顺序铁律：先 impacted 后 update——--impacted-file 必须与本轮实际差分一致，否则拒绝执行
    if not args.impacted_file or not Path(args.impacted_file).exists():
        print("[formula] 错误: update 要求 --impacted-file（先跑 impacted，顺序铁律——bug-2199 回归防线）", file=sys.stderr)
        return EXIT_ERROR
    prior = json.loads(Path(args.impacted_file).read_text(encoding="utf-8"))
    changes, fids, _ = _dryrun_diff(args)
    if sorted(prior.get("affected_formulas", [])) != fids:
        print(f"[formula] 错误: impacted 文件与实际差分不一致（文件 {prior.get('affected_formulas')} vs 实际 {fids}）——重跑 impacted", file=sys.stderr)
        return EXIT_ERROR
    stage = _stage_of(args)
    import ingest
    if ":" in args.field and "." not in args.field:  # CSV 整列改参
        prefix, col = args.field.split(":", 1)
        fam = next(f for f, s in stage["forms"].items() if s["file"].split("_", 1)[0] == prefix)
        rows = _load(args).csvs[fam]
        with open(Path(args.data_dir) / stage["forms"][fam]["file"], "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(stage["forms"][fam]["columns"])
            for r in rows:
                w.writerow([args.value if k == col else v for k, v in r.items()])
        ingest.register_file(Path(args.data_dir), stage["forms"][fam]["file"], fam, stage["forms"][fam].get("required", True), "csv")
    else:  # JSON 字段改参
        prefix, key = args.field.split(".", 1)
        fam = next(f for f, s in stage["forms"].items() if s["file"].split("_", 1)[0] == prefix)
        ingest.write_form_values(args.stage, args.data_dir, fam, {key: float(args.value) if is_num(args.value) else args.value})
    values, anomalies = compute(_load(args))
    write_state(Path(args.output), values, anomalies)
    print(f"STATE_READY: {args.output} slots={len(values)}")
    print(f"UPDATED: {args.field} = {args.value}")
    print(f"CHANGED_FORMULAS: {fids}")
    print(f"CHANGED_CHAPTERS: {prior.get('affected_chapters', [])}")
    for k, v in changes.items():
        print(f"  {k}: {v}")
    return EXIT_ANOMALY if anomalies else EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2（T2 环评 5 域 Decimal 重写）— 冻结计算层（Decimal/ROUND_HALF_EVEN）")
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("execute", help="读 data/ 全量计算 → formula_state.json")
    e.add_argument("--stage", required=True)
    e.add_argument("--data-dir", required=True)
    # bug-2223 质量收口: --output/--state-dir argparse 互斥组
    eg = e.add_mutually_exclusive_group()
    eg.add_argument("--output", help="状态文件完整路径（与 --state-dir 二选一）")
    eg.add_argument("--state-dir", help="状态目录（写 {state-dir}/formula_state.json，与 --output 二选一；bug-2223）")
    e.set_defaults(func=cmd_execute)

    c = sub.add_parser("check", help="自洽重算 + 锚点回归")
    c.add_argument("--stage", required=True)
    c.add_argument("--data-dir", required=True)
    c.add_argument("--state", required=True)
    c.add_argument("--anchors", help="锚点 JSON（内联字符串或 .json 文件）")
    c.add_argument("--output")
    c.set_defaults(func=cmd_check)

    t = sub.add_parser("trace", help="每公式输入/输出/舍入轨迹")
    t.add_argument("--state", required=True)
    t.add_argument("--formulas", required=True, help="references/formulas.json")
    t.add_argument("--output")
    t.set_defaults(func=cmd_trace)

    i = sub.add_parser("impacted", help="改参 dry-run 值差分（零写盘；先于 update）")
    i.add_argument("--stage", required=True)
    i.add_argument("--data-dir", required=True)
    i.add_argument("--state", required=True)
    i.add_argument("--field", required=True, help="如 13.q 或 13a:列名")
    i.add_argument("--value", required=True)
    i.add_argument("--manifest", help="chapter_manifest.json（反查章节）")
    i.add_argument("--output")
    i.set_defaults(func=cmd_impacted)

    u = sub.add_parser("update", help="经 ingest 写参 → 重算 → 变更摘要（--impacted-file 必填）")
    u.add_argument("--stage", required=True)
    u.add_argument("--data-dir", required=True)
    u.add_argument("--state", required=True)
    u.add_argument("--field", required=True)
    u.add_argument("--value", required=True)
    u.add_argument("--impacted-file", required=True)
    u.add_argument("--output", required=True)
    u.set_defaults(func=cmd_update)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
