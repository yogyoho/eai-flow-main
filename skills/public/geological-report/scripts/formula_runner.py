#!/usr/bin/env python3
"""geological-report v2 — formula_runner.py：冻结计算层（步骤2，门2 的数据面）。

舍入定稿（spec + formulas.json rounding_policy）：decimal.Decimal + quantize
(ROUND_HALF_EVEN)——样例 8.4.6「四舍六入五逢奇进偶舍」逐字对应；禁 float round()。
中间量全 Decimal，出口统一 quantize；下游公式（E 链/L10）直接复用未舍入中间量，
避免二次舍入漂移。

与 water 版差异（有意非漂移）：water 复用 backend formula_engine（float eval），地质域
是表格型计算（逐样品/逐块段/分类汇总）且舍入红线要求 Decimal——故本脚本 stdlib 自包含，
不 import backend（沙箱任意布局可跑）。CLI 五命令面与 water 对齐：
  execute  读 data/ → 全量计算 → formula_state.json（冻结；无时间戳——字节级幂等）
  check    自洽重算 + B1 容差(0.05pp) + 锚点回归(--anchors)
  trace    每公式 {定义/输入/输出/舍入} → traces.json
  impacted 改参 dry-run 值差分 → 受影响公式+章节（先于 update，顺序铁律，零写盘）
  update   经 ingest 写 data/ → 重算 → 变更摘要（--impacted-file 必填且与本轮差分
           一致——防「跳过 impacted 直接 update」，bug-2199 同构防线）

红线：缺输入报错绝不编造；无历史备案（15 缺失）→ L10 整体跳过记 anomaly，不产 0 值。

退出码：0 干净 / 1 错误 / 2 需人工 / 3 完成带异常必读 anomalies
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

import chapter_planner

EXIT_OK, EXIT_ERROR, EXIT_MANUAL, EXIT_ANOMALY = 0, 1, 2, 3
D0 = Decimal("0")
HUNDRED, THOUSAND, WAN = Decimal(100), Decimal(1000), Decimal(10000)
CATS = ("TM", "KZ", "TD")


def q(x: Decimal, dp: str) -> Decimal:
    """ROUND_HALF_EVEN quantize。dp 例: '0.01' / '1' / '0.1'。"""
    return x.quantize(Decimal(dp), rounding=ROUND_HALF_EVEN)


def mean(xs: list[Decimal]) -> Decimal:
    return sum(xs, D0) / Decimal(len(xs)) if xs else D0


def stdev_n1(xs: list[Decimal]) -> Decimal:
    n = len(xs)
    if n < 2:
        return D0
    m = mean(xs)
    return (sum(((x - m) ** 2 for x in xs), D0) / Decimal(n - 1)).sqrt()


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


# ── data/ 装载 ──────────────────────────────────────────────────────────────

class Data:
    """data/ 只读装载。impacted dry-run 在内存副本上覆盖（零写盘）。"""

    def __init__(self, data_dir: Path, stage: dict):
        self.dir = data_dir
        self.stage = stage
        self.forms: dict[str, dict] = {}
        self.csvs: dict[str, list[dict]] = {}
        for fam, spec in stage.get("forms", {}).items():
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
            if spec["file"].split("_", 1)[0] == prefix:
                return fam
        return None

    def form(self, fam: str) -> dict:
        return self.forms.get(fam) or {}


def override_data(data: Data, field: str, value: str) -> Data:
    """field 语法：'13.deposit_avg_grade'（JSON 字段）或 '13a:体重_t_m3'（CSV 整列）。"""
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


# ── 计算层 ──────────────────────────────────────────────────────────────────

def compute(data: Data) -> tuple[dict, list[str]]:
    """全量计算 → (values: 槽位注册表, anomalies)。"""
    V: dict[str, dict] = {}
    anomalies: list[str] = []

    def emit(key: str, val: Decimal, dp: str, unit: str, source: str, extra: dict | None = None) -> None:
        d = q(val, dp)
        V[key] = {"value": float(d), "display": f"{d}", "unit": unit, "source": source, **(extra or {})}

    # ── C9 特高品位下限 ──
    p13 = data.form("industrial_params")
    if p13:
        emit("C9.outlier_threshold", dec(p13["deposit_avg_grade"]) * dec(p13["outlier_multiple"]), "0.01", "%", "formula:C9",
             {"inputs": {"deposit_avg_grade": float(dec(p13["deposit_avg_grade"])), "outlier_multiple": int(dec(p13["outlier_multiple"]))}})
    else:
        anomalies.append("13_industrial_params 缺失——C9/S1/L 链/E 链跳过（缺参不编造）")

    # ── S1 小体重统计（表8-1）──
    s1_density: dict[str, Decimal] = {}  # ''(全)/'_industrial'/'_low' → 平均体重
    if "bulk_density" in data.csvs and p13:
        boundary, min_ind = dec(p13["boundary_grade_cu"]), dec(p13["min_industrial_grade_cu"])
        thr = dec(p13["deposit_avg_grade"]) * dec(p13["outlier_multiple"])
        rows = data.csvs["bulk_density"]
        kept = [(g, d, m) for g, d, m in (
            (dec(r.get("品位Cu_pct")), dec(r.get("体重_t_m3")), dec(r.get("湿度_pct") or 0)) for r in rows
        ) if g.is_finite() and d.is_finite() and boundary <= g < thr]
        dropped = len(rows) - len(kept)
        if dropped:
            anomalies.append(f"13a 过滤剔除 {dropped} 行（低于边界品位 {boundary}% 或≥特高阈值 {thr}%）")
        for tag, grp in (("", kept), ("_industrial", [x for x in kept if x[0] >= min_ind]), ("_low", [x for x in kept if boundary <= x[0] < min_ind])):
            if not grp:
                continue
            emit(f"S1.n{tag}", Decimal(len(grp)), "1", "件", "formula:S1")
            emit(f"S1.avg_density{tag}", mean([x[1] for x in grp]), "0.01", "t/m3", "formula:S1")
            emit(f"S1.avg_grade{tag}", mean([x[0] for x in grp]), "0.01", "%", "formula:S1")
            emit(f"S1.avg_moisture{tag}", mean([x[2] for x in grp]), "0.01", "%", "formula:S1")
            s1_density[tag] = mean([x[1] for x in grp])

    # ── 08a 单工程统计（L3/L4/S2）+ L11 伴生银品位来源 ──
    ag_grade: Decimal | None = None
    if "sample_assays" in data.csvs and p13:
        min_ind = dec(p13["min_industrial_grade_cu"])
        works: dict[tuple[str, str], list[dict]] = {}
        for r in data.csvs["sample_assays"]:
            works.setdefault((r.get("工程号", "?"), r.get("矿体编号", "?")), []).append(r)
        per_work: dict[tuple[str, str], Decimal] = {}
        ag_l, ag_la = D0, D0  # Σ(样长×Ag), Σ样长 —— 工业品位样
        for (work, ore), rs in sorted(works.items()):
            # ponytail: 08a 无钻孔方位/倾角列——样长即真厚（L1 需 α/β/γ，备注列可扩展）
            lens = [dec(r.get("样长_m")) for r in rs]
            pairs = [(l, c) for l, c in ((dec(r.get("样长_m")), dec(r.get("品位Cu_pct"))) for r in rs) if l.is_finite() and c.is_finite()]
            if any(l.is_finite() for l in lens):
                emit(f"L3.T[{work}|{ore}]", sum((l for l in lens if l.is_finite()), D0), "0.01", "m", "formula:L3")
            if pairs:
                sl = sum((l for l, _ in pairs), D0)
                per_work[(work, ore)] = sum((l * c for l, c in pairs), D0) / sl
                emit(f"L4.C[{work}|{ore}]", per_work[(work, ore)], "0.01", "%", "formula:L4")
                for r in rs:
                    l, c, a = dec(r.get("样长_m")), dec(r.get("品位Cu_pct")), dec(r.get("品位Ag_gpt"))
                    if l.is_finite() and c.is_finite() and a.is_finite() and c >= min_ind:
                        ag_l += l * a
                        ag_la += l
        by_ore: dict[str, list[Decimal]] = {}
        for (_, ore), c in per_work.items():
            by_ore.setdefault(ore, []).append(c)
        for ore, cs in sorted(by_ore.items()):
            m = mean(cs)
            emit(f"S2.Cv[{ore}]", (stdev_n1(cs) / m * HUNDRED) if m else D0, "0.01", "%", "formula:S2")
        if ag_la:
            ag_grade = ag_l / ag_la
            emit("L11.ag_grade", ag_grade, "0.01", "g/t", "formula:L11",
                 {"note": "伴生Ag品位=08a工业品位样样长加权（伴生类别随主元素组合样）"})
        anomalies.append("08a 统计按「样长=真厚」口径（L1 角度参数未采集）——角度数据补齐后需重算")

    # ── 14 块段/汇总链 L7-L9 ──
    bm = data.form("block_model")
    rows: list[dict] = []  # {orebody, category, grade_class, ore_t, metal_t, grade}
    if bm:
        if bm.get("granularity", "B") == "A" and bm.get("blocks"):
            d_ind = s1_density.get("_industrial")
            d_low = s1_density.get("_low")
            d_all = s1_density.get("")
            for b in bm["blocks"]:
                S, M, C = dec(b["area_s_m2"]), dec(b["avg_thickness_m"]), dec(b["grade_c_pct"])
                if not (S.is_finite() and M.is_finite() and C.is_finite()):
                    continue
                # D 选取：S1 分组统计优先（SC-3 改小体重传导路径）；无 S1 用块段自带值
                Dsel = (d_ind if b.get("grade_class", "工业") != "低品位" else d_low) or d_all or dec(b.get("bulk_density"))
                if Dsel is None or not Dsel.is_finite():
                    anomalies.append(f"块段 {b.get('block_no')}: 无体重可用（13a/S1 与块段自带值皆缺）——链在此截断")
                    rows.clear()
                    break
                qt = S * M * Dsel  # L7: V=S×M, Q=V×D
                rows.append({"orebody": b["orebody"], "category": b["category"], "grade_class": b.get("grade_class", "工业"),
                             "ore_t": qt, "metal_t": qt * C / HUNDRED, "grade": C})
        elif bm.get("aggregates"):
            for a in bm["aggregates"]:
                rows.append({"orebody": a["orebody"], "category": a["category"], "grade_class": a.get("grade_class", "工业"),
                             "ore_t": dec(a["ore_qty_wt"]) * WAN, "metal_t": dec(a["metal_t"]), "grade": dec(a.get("grade_pct", 0))})

    def agg(sel: list[dict]) -> tuple[Decimal, Decimal, Decimal]:
        ore = sum((r["ore_t"] for r in sel), D0)
        metal = sum((r["metal_t"] for r in sel), D0)
        return ore, metal, (metal / ore * HUNDRED if ore else D0)

    ind_stats: dict[str, tuple[Decimal, Decimal]] = {}  # cat -> (ore_t, metal_t) 工业矿
    low_stats: dict[str, tuple[Decimal, Decimal]] = {}
    if rows:
        ind = [r for r in rows if r["grade_class"] == "工业"]
        low = [r for r in rows if r["grade_class"] != "工业"]
        tot_ore, tot_metal, tot_grade = agg(ind)
        emit("L9.total_ore_wt", tot_ore / WAN, "0.01", "万吨", "formula:L9")
        emit("L9.total_metal_t", tot_metal, "1", "t", "formula:L9")
        emit("L9.total_grade", tot_grade, "0.01", "%", "formula:L9")
        for cat in CATS:
            co, cm, cg = agg([r for r in ind if r["category"] == cat])
            ind_stats[cat] = (co, cm)
            emit(f"L9.{cat}_ore_wt", co / WAN, "0.01", "万吨", "formula:L9")
            emit(f"L9.{cat}_metal_t", cm, "1", "t", "formula:L9")
            emit(f"L9.{cat}_grade", cg, "0.01", "%", "formula:L9")
        for cat in ("KZ", "TD"):
            co, cm, _ = agg([r for r in low if r["category"] == cat])
            low_stats[cat] = (co, cm)
            emit(f"L9.low_{cat}_ore_wt", co / WAN, "0.01", "万吨", "formula:L9")
            emit(f"L9.low_{cat}_metal_t", cm, "1", "t", "formula:L9")
        lo, lm, lg = agg(low)
        emit("L9.low_total_ore_wt", lo / WAN, "0.01", "万吨", "formula:L9")
        emit("L9.low_total_metal_t", lm, "1", "t", "formula:L9")
        emit("L9.low_total_grade", lg, "0.01", "%", "formula:L9")
        # L8 矿体平均品位（矿石量加权）
        by_oreb: dict[str, tuple[Decimal, Decimal]] = {}
        for r in ind:
            o, m = by_oreb.get(r["orebody"], (D0, D0))
            by_oreb[r["orebody"]] = (o + r["ore_t"], m + r["metal_t"])
        for oreb, (o, m) in sorted(by_oreb.items()):
            emit(f"L8.C_orebody[{oreb}]", m / o * HUNDRED if o else D0, "0.01", "%", "formula:L8")

        # ── L10 四口径增量（仅有 15 历史备案时）──
        prior = data.form("prior_estimate")
        if prior.get("split_extent") and prior.get("code_mapping"):
            split = prior["split_extent"]

            def prior_ore(cats: list[str]) -> Decimal:  # 万吨
                return sum((dec((split.get(code) or {}).get("ore_wt", 0)) for code, cat in prior["code_mapping"].items() if cat in cats), D0)

            def prior_metal(cats: list[str]) -> Decimal:  # t
                return sum((dec((split.get(code) or {}).get("metal_t", 0)) for code, cat in prior["code_mapping"].items() if cat in cats), D0)

            for label, stats, cats in [
                ("ind_TM_KZ", ind_stats, ["TM", "KZ"]),
                ("ind_TD", ind_stats, ["TD"]),
                ("low_KZ", low_stats, ["KZ"]),
                ("low_TD", low_stats, ["TD"]),
            ]:
                if not any(c in stats for c in cats):
                    continue
                co = sum((stats[c][0] for c in cats if c in stats), D0) / WAN
                cm = sum((stats[c][1] for c in cats if c in stats), D0)
                po = prior_ore(cats)
                emit(f"L10.delta_ore_wt[{label}]", co - po, "0.01", "万吨", "formula:L10",
                     {"prior_ore_wt": float(q(po, "0.01"))})
                emit(f"L10.delta_metal_t[{label}]", cm - prior_metal(cats), "1", "t", "formula:L10")
            anomalies.append("L10 尚难利用口径：历史备案若无对应分类，增量≈本次全量（呈现层并排列示不做分类减法——走查 §5.1）")
        elif not prior:
            anomalies.append("无 15_prior_estimate——L10 差值链整体跳过（新立项目正常路径，门2 差值步骤同步跳过）")

        # ── L11 伴生银金属量（kg = 万吨×10⁴ × g/t ÷ 1000）──
        if ag_grade is not None and ag_grade.is_finite():
            emit("L11.P_Ag_industrial_kg", tot_ore * ag_grade / THOUSAND, "1", "kg", "formula:L11")
            emit("L11.P_Ag_total_kg", (tot_ore + sum((v[0] for v in low_stats.values()), D0)) * ag_grade / THOUSAND, "1", "kg", "formula:L11")
        elif p13 and p13.get("byproduct_ag_indicator") is not None:
            anomalies.append("L11 用 13.byproduct_ag_indicator（指标值非加权品位）；08a 补 Ag 列后重算")
            emit("L11.P_Ag_industrial_kg", tot_ore * dec(p13["byproduct_ag_indicator"]) / THOUSAND, "1", "kg", "formula:L11")
        # 两者皆无 → L11 跳过（降级路径：呈现层 [待确认] 槽位）

        # ── L12 验证误差率 ──
        for r in data.form("verification").get("rows", []):
            qh = dec(r.get("ore_qty_wt")) * WAN
            if qh:
                emit(f"L12.err[{r.get('orebody', '?')}|{r.get('category', '?')}]",
                     (tot_ore - qh) / qh * HUNDRED, "0.01", "%", "formula:L12")

        # ── L13 占比（金属量口径）──
        if tot_metal:
            emit("L13.share_TM", ind_stats.get("TM", (D0, D0))[1] / tot_metal * HUNDRED, "0.01", "%", "formula:L13")
            emit("L13.share_TM_KZ", (ind_stats.get("TM", (D0, D0))[1] + ind_stats.get("KZ", (D0, D0))[1]) / tot_metal * HUNDRED, "0.01", "%", "formula:L13")
    elif "block_model" not in data.forms:
        anomalies.append("14_block_model 缺失——L7-L13 资源量链未计算")

    # ── W1 涌水量比拟法 ──
    hee = data.form("hydro_eng_env")
    ia = hee.get("hydro.inflow_analogy")  # schema 扁平点号键
    if ia:
        Q0min, Q0max = dec(ia["Q0_min"]), dec(ia["Q0_max"])
        F, F0, S, S0 = dec(ia["F"]), dec(ia["F0"]), dec(ia["S"]), dec(ia["S0"])
        if not F0 or not S0:
            raise KeyError("W1 输入 F0/S0 为 0（比拟法分母为零——缺参报错绝不编造）")
        k = (F / F0) * (S / S0).sqrt()
        emit("W1.Q_min", Q0min * k, "1", "m3/d", "formula:W1", {"k_factor": float(q(k, "0.0001"))})
        emit("W1.Q_max", Q0max * k, "1", "m3/d", "formula:W1")
        if Q0max and Q0min:  # 互不洽探测（样例 908/5531 bug-2210 同型防线）
            r_in, r_out = Q0min / Q0max, (Q0min * k) / (Q0max * k)
            if abs(r_in - r_out) > Decimal("0.001"):
                anomalies.append(f"W1 输出比值互不洽（{r_in:.4f} ≠ {r_out:.4f}）——以公式重算为准")

    # ── B1 选矿平衡（回收率 = 产率×精矿品位/入浮品位）──
    ben = data.form("beneficiation")
    lc = ben.get("locked_cycle") or {}
    feed = dec(lc.get("feed_grade_cu") or ben.get("feed_grade_cu"))
    for prod in lc.get("products") or []:
        y, g = dec(prod.get("yield")), dec(prod.get("grade_cu", prod.get("grade")))
        if feed.is_finite() and feed and y.is_finite() and g.is_finite():
            emit(f"B1.recovery[{prod.get('name', '?')}]", y * g / feed, "0.01", "%", "formula:B1",
                 {"declared_recovery": prod.get("recovery_cu", prod.get("recovery"))})

    # ── E 经济链 ──
    eco = data.form("economics")
    if eco and ind_stats:
        kcat = {c: dec(eco.get("credibility", {}).get(c, 1.0)) for c in CATS}
        rates = eco.get("rates", {})
        loss = dec(rates.get("loss_rate", 0)) / HUNDRED
        dil = dec(rates.get("dilution_rate", 0)) / HUNDRED
        q_u = sum((ind_stats[c][0] * kcat[c] for c in CATS if c in ind_stats), D0)
        m_u = sum((ind_stats[c][1] * kcat[c] for c in CATS if c in ind_stats), D0)
        c_u = m_u / q_u * HUNDRED if q_u else D0
        emit("E1.Q_usable_wt", q_u / WAN, "0.01", "万吨", "formula:E1")
        emit("E1.C_usable", c_u, "0.01", "%", "formula:E1")
        q_m, c_m = q_u * (1 - loss), c_u * (1 - dil)
        emit("E2.Q_mined_wt", q_m / WAN, "0.01", "万吨", "formula:E2")
        emit("E2.C_mined", c_m, "0.01", "%", "formula:E2")
        conc = eco.get("concentrate", {})
        gCu, gAg = dec(conc.get("grade_cu_pct", 0)), dec(conc.get("grade_ag_gpt", 0))
        rCu = dec(eco.get("recovery", {}).get("recovery_cu", eco.get("recovery", {}).get("cu", 0))) / HUNDRED
        conc_t = q_m * (c_m / HUNDRED) * rCu / (gCu / HUNDRED) if gCu and rCu else None
        if conc_t is not None:
            emit("E3.conc_output_t", conc_t, "1", "t", "formula:E3")
        prices = eco.get("prices", {})
        pCu = dec(prices.get("cu_yuan_t", 0))
        pAg_kg = dec(prices.get("ag_yuan_kg", 0)) or dec(prices.get("ag_yuan_per_g", 0)) * THOUSAND
        price_conc = pCu * gCu / HUNDRED + pAg_kg / THOUSAND * gAg
        emit("E4.price_conc", price_conc, "1", "元/t精矿", "formula:E4",
             {"cu_part": float(q(pCu * gCu / HUNDRED, "1")), "ag_part": float(q(pAg_kg / THOUSAND * gAg, "1"))})
        ag_kg = dec(V["L11.P_Ag_total_kg"]["value"]) if "L11.P_Ag_total_kg" in V else D0
        emit("E5.gross_potential_yi", (m_u / WAN * pCu + ag_kg * pAg_kg) / WAN, "0.01", "亿元", "formula:E5")
        costs = eco.get("costs", {})
        unit_cost = sum((dec(costs.get(k, 0)) for k in ("mining_yuan_t", "beneficiation_yuan_t", "other_yuan_t")), D0)
        if conc_t is not None:
            emit("E6.static_profit_wy", (conc_t * price_conc - q_m * unit_cost) / WAN, "1", "万元", "formula:E6")
        if eco.get("capacity_10kt_a"):
            cap = dec(eco["capacity_10kt_a"]) * WAN
            emit("E7.years_added", q_u / cap if cap else D0, "0.1", "年", "formula:E7")

    return V, anomalies


# ── 状态落盘/差分 ───────────────────────────────────────────────────────────

def write_state(path: Path, values: dict, anomalies: list[str]) -> None:
    doc = {"version": 2, "values": values, "anomalies": anomalies}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


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


# ── 子命令 ──────────────────────────────────────────────────────────────────

def _load(args) -> Data:
    return Data(Path(args.data_dir), _stage_of(args))


def _stage_of(args) -> dict:
    return json.loads(Path(args.stage).read_text(encoding="utf-8"))


def cmd_execute(args) -> int:
    try:
        values, anomalies = compute(_load(args))
    except KeyError as e:
        print(f"[formula] 错误: {e}", file=sys.stderr)
        return EXIT_ERROR
    write_state(Path(args.output), values, anomalies)
    print(f"STATE_READY: {args.output} slots={len(values)} anomalies={len(anomalies)}")
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
    for k, v in state.get("values", {}).items():  # B1 声明 vs 计算（容差 0.05pp）
        if k.startswith("B1.recovery[") and v.get("declared_recovery") is not None:
            declared, calc = dec(v["declared_recovery"]), dec(v["value"])
            if abs(declared - calc) > Decimal("0.05"):
                issues.append({"severity": "fail", "check": "B1C", "detail": f"{k}: 声明 {declared} vs 计算 {calc}（容差 0.05pp）"})
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
    p = argparse.ArgumentParser(description="geological-report v2 — 冻结计算层（Decimal/ROUND_HALF_EVEN）")
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("execute", help="读 data/ 全量计算 → formula_state.json")
    e.add_argument("--stage", required=True)
    e.add_argument("--data-dir", required=True)
    e.add_argument("--output", required=True)
    e.set_defaults(func=cmd_execute)

    c = sub.add_parser("check", help="自洽重算 + B1 容差 + 锚点回归")
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
    i.add_argument("--field", required=True, help="如 13.deposit_avg_grade 或 13a:体重_t_m3")
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
