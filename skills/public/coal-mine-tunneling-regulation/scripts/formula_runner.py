#!/usr/bin/env python3
"""coal-mine-tunneling-regulation v2 — formula_runner.py：冻结计算层（步骤2，门2 的数据面·通风域）。

舍入定稿（spec + formulas.json rounding_policy）：decimal.Decimal + quantize
(ROUND_HALF_EVEN)——「四舍六入五逢奇进偶舍」逐字对应；禁 float round()。
槽位内部风量统一 m³/min（正文如需 m³/s 由 display 层换算）；中间量 float 计算，
出口统一 Decimal quantize，避免二次舍入漂移。

CLI 五命令面与 water/geo 对齐：
  execute  读 data/ → 全量计算 → formula_state.json（冻结；无时间戳——字节级幂等）
  check    自洽重算 + 锚点回归(--anchors，容差 0.005)
  trace    每公式 {定义/输入/输出/舍入} → traces.json
  impacted 改参 dry-run 值差分 → 受影响公式+章节（先于 update，顺序铁律，零写盘）
  update   经 ingest 写 data/ → 重算 → 变更摘要（--impacted-file 必填且与本轮差分
           一致——防「跳过 impacted 直接 update」，bug-2199 同构防线）

红线：缺输入记 anomaly 跳过该子项，绝不编造（bug-2223 同构）；needs_verification
系数（Q1 系数100 / Q3 5.44 / Q4 风速带 / F2 线性近似 / F4 风阻 R）未过 tier1 人工
核实前恒记 anomaly，计算结果仅作参考值。

退出码：0 干净 / 1 错误 / 2 需人工 / 3 完成带异常必读 anomalies
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import chapter_planner

EXIT_OK, EXIT_ERROR, EXIT_MANUAL, EXIT_ANOMALY = 0, 1, 2, 3


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
    """field 语法：'02.gas_emission_daily'（JSON 字段）或 '10:风险等级'（CSV 整列）。"""
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
    """全量计算 → (values: 槽位注册表, anomalies)。（D5 一期仅通风域）"""
    values, anomalies = {}, []

    def emit(key: str, val: float, dp: int, unit: str, source: str, extra: dict | None = None) -> None:
        # 与 geo emit 同形：非有限值（NaN/Inf 会经 json 混进冻结层）就地抛错；
        # 出口统一 Decimal.quantize(ROUND_HALF_EVEN)，dp=小数位数。
        if not math.isfinite(val):
            raise ValueError(f"非有限计算结果: {key}={val}")
        q = Decimal(str(val)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_EVEN)
        slot = {"value": float(q), "display": f"{q}", "unit": unit, "source": source}
        if extra:
            slot.update(extra)
        values[key] = slot

    vent = data.form("ventilation")
    geo = data.form("geology")
    road = data.form("roadway")

    q_gas, khg = geo.get("gas_emission_daily"), geo.get("khg")
    if q_gas in (None, "") or khg in (None, ""):
        anomalies.append("Q1 缺瓦斯绝对涌出量或不均衡系数（geology.gas_emission_daily/khg）——按瓦斯涌出量法跳过")
    else:
        emit("Q1.need_by_gas", 100.0 * float(q_gas) * float(khg), 2, "m³/min", "formula:Q1",
             {"inputs": {"q": float(q_gas), "K": float(khg)}, "note": "系数100待核实"})

    n = vent.get("persons_per_shift")
    if n in (None, ""):
        anomalies.append("Q2 缺每班最多人数（ventilation.persons_per_shift）——按人数法跳过")
    else:
        emit("Q2.need_by_persons", 4.0 * float(n), 2, "m³/min", "formula:Q2", {"inputs": {"N": float(n)}})

    kw = vent.get("diesel_power_total_kw") or 0
    if float(kw) > 0:
        emit("Q3.need_by_diesel", 5.44 * float(kw), 2, "m³/min", "formula:Q3", {"inputs": {"P": float(kw)}})
        anomalies.append("Q3 柴油机车需风量系数 5.44 m³/min·kW【待人工核实】——结果仅作参考值")

    cands = [values[k]["value"] for k in ("Q1.need_by_gas", "Q2.need_by_persons", "Q3.need_by_diesel") if k in values]
    if not cands:
        anomalies.append("Q0 无任何需风量子项可计算——门2 后协商补数据，禁估算")
    else:
        q0 = max(cands)
        basis = [k for k, v in (("Q1", values.get("Q1.need_by_gas", {}).get("value")),
                                 ("Q2", values.get("Q2.need_by_persons", {}).get("value")),
                                 ("Q3", values.get("Q3.need_by_diesel", {}).get("value"))) if v == q0]
        emit("Q0.need_final", q0, 2, "m³/min", "formula:Q0", {"basis": "+".join(basis)})

    s = road.get("drive_section_m2")
    s_err = False  # 断面非正数=源数据错误——质量评审 I2：Q4/F1/F2/F4 整块跳过（风量域计算全无意义）
    if s in (None, ""):
        anomalies.append("Q4/F1 缺掘进断面（roadway.drive_section_m2）——风速验算与风筒距离跳过")
    elif float(s) <= 0:
        s_err = True
        anomalies.append(f"Q4/F1 掘进断面非正数（roadway.drive_section_m2={s}）——检查源数据")
    else:
        s = float(s)
        emit("Q4.v_min_q", 60.0 * 0.25 * s, 2, "m³/min", "formula:Q4", {"inputs": {"S": s, "v": 0.25}})
        emit("Q4.v_max_q", 60.0 * 8.0 * s, 2, "m³/min", "formula:Q4", {"inputs": {"S": s, "v": 8.0}})
        emit("Q4.v_min_check", values["Q4.v_min_q"]["value"], 2, "m³/min", "formula:Q4")
        emit("Q4.v_max_check", values["Q4.v_max_q"]["value"], 2, "m³/min", "formula:Q4")
        emit("F1.duct_gap_m", 5.0 * math.sqrt(s), 2, "m", "formula:F1")
        if "Q0.need_final" in values:
            q0 = values["Q0.need_final"]["value"]
            if not (values["Q4.v_min_q"]["value"] <= q0 <= values["Q4.v_max_q"]["value"]):
                anomalies.append(f"门2阻断：需风量 {q0} 超出风速验算区间 "
                                 f"[{values['Q4.v_min_q']['value']}, {values['Q4.v_max_q']['value']}]（R2 带 0.25~8 m/s）——需协商调断面或分风")

    i, ld = vent.get("duct_leak_rate_per100m"), vent.get("air_supply_distance_m")
    if not s_err and "Q0.need_final" in values and i not in (None, "") and ld not in (None, ""):
        qf = values["Q0.need_final"]["value"] * (1.0 + (float(i) / 100.0) * (float(ld) / 100.0))
        emit("F2.fan_need", qf, 2, "m³/min", "formula:F2",
             {"inputs": {"i": float(i), "Ld": float(ld)}, "note": "线性近似待核实"})
        anomalies.append("F2 漏风折算采用线性近似【待核实】——与连乘式的差异未过 tier1")
    elif not s_err and "Q0.need_final" in values:
        # 质量评审 I1：缺参不得静默跳过（rc=0 唯一可达路径堵漏）——Q0 缺失不重复记（Q0 自身已有）
        anomalies.append("F2 缺 duct_leak_rate_per100m/air_supply_distance_m（ventilation.*）——漏风折算跳过")

    length, seg = road.get("design_length_m"), vent.get("duct_section_length_m")
    if length not in (None, "") and seg not in (None, "") and float(seg) > 0:
        emit("F3.duct_count", math.ceil(float(length) / float(seg)), 0, "节", "formula:F3")
    else:
        anomalies.append("F3 缺设计长度或每节长度——风筒节数跳过（C5 无法对账 ch4 管线表）")

    # F4 通风阻力（J12：spec D5 项，风阻系数待核实 → 恒记 anomaly，仅参考值）
    if not s_err and "Q0.need_final" in values and ld not in (None, ""):
        r_coef = 0.01  # 【待核实】占位系数 N·s²/m⁸——核实前结果仅参考
        q_m3s = values["Q0.need_final"]["value"] / 60.0
        emit("F4.drag_head", r_coef * float(ld) * q_m3s * q_m3s, 1, "Pa", "formula:F4",
             {"inputs": {"R": r_coef, "Ld": float(ld)}, "note": "R 待核实"})
        anomalies.append("F4 通风阻力风阻系数 R【待人工核实】——结果仅作参考值，禁写入正文当设计依据")
    elif not s_err and "Q0.need_final" in values:
        anomalies.append("F4 缺 air_supply_distance_m——通风阻力跳过")

    return values, anomalies


# ── 状态落盘/差分 ───────────────────────────────────────────────────────────

# 槽位键形（bug-3036）：Q1.need_by_gas / F4.drag_head / Q3.need_by_diesel[1] 形；
# 拒绝循环变量名（"key"/"val"/…）与表达式串（含空白/运算符）——LLM 直写特征形状。
_SLOT_KEY_RE = re.compile(r"^[A-Za-z]\w*(?:\.\w+)*(?:\[[^\]\s]+\])?$")
_JUNK_KEYS = {"key", "val", "value", "x", "tmp", "result", "display", "unit", "source"}


def write_state(path: Path, values: dict, anomalies: list[str]) -> None:
    # 落盘前终检（bug-3036）：键形、空/缺失 display、非对象槽位、非有限数值就地拦——冻结层
    # （唯一写者=本脚本）不得产出 LLM 直写特征形状。allow_nan=False 使 NaN/Inf 序列化即抛
    # （Python 默认写出裸 NaN 是非法 JSON，下游 json.loads 虽容忍但交付链不认）。
    for key, slot in values.items():
        if key in _JUNK_KEYS or not _SLOT_KEY_RE.match(key):
            raise ValueError(f"槽位键形非法 {key!r}（形如 Q1.need_by_gas / F4.drag_head；bug-3036）")
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


# ── 子命令 ──────────────────────────────────────────────────────────────────

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
        # 复核修复（bug-3058）：write_state 终检（键形/display/非有限值）不再裸 traceback——
        # 键形非法多因数据标签含空白/特殊字符（如钻孔号 "ZK 0701"）或缺 display，给出可动手指引。
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="coal-mine-tunneling-regulation v2 — 冻结计算层·通风域（Decimal/ROUND_HALF_EVEN）")
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("execute", help="读 data/ 全量计算 → formula_state.json")
    e.add_argument("--stage", required=True)
    e.add_argument("--data-dir", required=True)
    # bug-2223 质量收口: --output/--state-dir argparse 互斥组（both → usage 错误 rc=2，不再 --output 静默胜出）；
    # "二者皆缺"仍走 cmd_execute 内的显式报错（rc=1），错误信息更可读
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
    i.add_argument("--field", required=True, help="如 02.gas_emission_daily（JSON 字段）或 10:风险等级（CSV 整列）")
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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
