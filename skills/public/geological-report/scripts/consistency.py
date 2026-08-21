#!/usr/bin/env python3
"""geological-report v2 — consistency.py：四类合约机器校验（步骤7）。

读 build_output 产出的报告全文 + formula_state + data/ → consistency_check.json。
四类合约（references/consistency_contracts.json 22 条的机器可执行面）：
  NR  编号规则    NR1 表/图号连续唯一（样例「表512」笔误防线）；NR2 小节号+段内序号
                  严格递增（样例 8.6.1 (1)(1)(2) 错乱防线）；NR3 截止日期/矿区名等
                  全局唯一同源
  XS  数字一致    槽位引用逐章 exact_match（不同章节同一数字必须同显示）；±2% 近似
                  未精确 = 疑似改写 warn；XS3 判定词逐字在场；XS5 采空区两值在场
  FC  公式链      L9 小计=总计、L11/L12 重算、E 链关系、B1 声明差 ≤0.05pp、
                  C9=均值×倍数、S1 分组自洽
  CC  编码约束    CC1 变化系数档次（standards_index 在库自动判，缺库→manual）；
                  CC2 历史编码禁现代化改写（332/333/111b/122b 红线 P4）；
                  CC3 规范编号只允许 standards_index 枚举（禁 LLM 记忆）
  SL  槽位/溯源   SL1 {{SLOT:}}/{{TABLE:}} 残留=0（FAIL 阻断 present_files）；
                  SL2 正文数值全部可溯源到 data/ 或 formula_state（12 以下小整数、
                  年份、日期、编号白名单豁免）

severity: pass / warn / manual / fail。退出码 fail>0→1，manual>0→2，warn>0→3，否则 0。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import formula_runner as fr

EXIT_OK, EXIT_FAIL, EXIT_MANUAL, EXIT_WARN = 0, 1, 2, 3
SMALL_INT_EXEMPT = 12  # 1..12 序数/计数豁免（"3 个因素"类叙述）
NEAR_MISS = Decimal("0.02")  # ±2% 内但非精确 = 疑似同源改写

# ── 数值池（SL2 溯源目标）───────────────────────────────────────────────────

def numeric_pool(data: fr.Data, state: dict) -> set[Decimal]:
    pool: set[Decimal] = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            d = fr.dec(v)
            if d.is_finite():
                pool.add(d)
        elif isinstance(v, str):
            d = fr.dec(v)
            if d.is_finite():
                pool.add(d)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for doc in data.forms.values():
        walk(doc)
    for rows in data.csvs.values():
        for row in rows:
            walk(list(row.values()))
    for v in state.get("values", {}).values():
        d = fr.dec(v.get("value"))
        if d.is_finite():
            pool.add(d)
    return pool


WHITELIST_PATTERNS = [
    r"\d{4}[-年/.]\d{1,2}[-月/.]\d{1,2}日?",          # 日期
    r"\d{4}年",                                        # 年份
    r"[表图]\s*\d+\s*[-–—]\s*\d+",                     # 表8-2 / 图6-1
    r"\d+\.\d+\.\d+(?:\.\d+)*",                        # 小节号 8.6.1
    r"(?m)^\s*[-*]\s*\d+(?:\.\d+)*\s",                 # 目录/列表行首编号
    r"(?m)^#{1,4}\s*\d+(?:\.\d+)*\s",                  # 标题编号
    r"[0-9a-f]{40,}",                                  # SHA-256 摘要（合规附录）
    r"(?:ZK|TC|PD|KD|YD|CM|XL)[-\s]?\d+",              # 工程编号
    r"(?:DZ|GB|HG|YD|MT|TD)/[A-Z]?\s*\d+(?:[.\-–]\d+)+",  # 规范编号
    r"[A-Z]{1,4}\d{3,6}[A-Za-z0-9\-]*",                # 证号/图号等字母前缀码
    r"\d+(?:\.\d+)?°(?:\d{1,2}′?)?(?:\d{1,2}″?)?[NSEW]",  # 经纬度
    r"\d+(?:\.\d+)?[‰]",                               # 千分比（叙述罕见，直接豁免）
    r"第?\s*[一二三四五六七八九十]+\s*[章节条款]",         # 中文序号
    # 历史分类编码（332/333/111b/122b/2M22/331/334、B+C+D）——红线 P4 要求原样保留，
    # 属结构性编码而非量测数值，豁免溯源（否则 CC2 保留义务与 SL2 打架）
    r"(?<![\dA-Za-z.])(?:1[0-9]{2}b?|2[MS][0-9]{2}|3[0-9]{2}|[A-E]\+[A-E](?:\+[A-E])?)(?![\dA-Za-z.])",
]

WHITELIST_RE = [re.compile(p) for p in WHITELIST_PATTERNS]
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
SEC_HEAD_RE = re.compile(r"^#{1,4}\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?\s")
CAPTION_RE = re.compile(r"^([表图])\s*(\d+)\s*[-–—]\s*(\d+)")
REF_RE = re.compile(r"([表图])\s*(\d+)\s*[-–—]\s*(\d+)")
STD_CITE_RE = re.compile(r"([A-Z]{1,4}(?:/[A-Z])?)\s*(\d{3,5})\s*[-–—]\s*(\d{4})")
HIST_MODERN_RE = re.compile(r"(33[23]|111b|122b|B\+C\+D)[^)。；\n]{0,6}[（(][^)）]{0,16}(现|相当|等同|对应)")
DATE_NEAR_RE = re.compile(r"截止[^。；\n]{0,24}?(\d{4}[-年/.]?\d{1,2}[-月/.]?\d{1,2}日?)")


def split_chapters(text: str) -> list[tuple[str, str]]:
    """按 `## ` 标题切段 → [(标题行, 段文本)]；无标题整体一段。"""
    parts = re.split(r"(?m)^(## .+)$", text)
    if len(parts) == 1:
        return [("(全文)", text)]
    out = []
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i] + parts[i + 1]))
    return out


def numbered_chapters(chapters: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """仅编号正文章（`## 1 …`）——SL/XS 只扫 LLM 叙述章，前置部分与合规附录为脚本直出豁免。"""
    return [(t, b) for t, b in chapters if re.match(r"## \d", t)]


# ── 四类检查 ────────────────────────────────────────────────────────────────

class Report:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, cid: str, sev: str, detail: str) -> None:
        self.items.append({"contract": cid, "severity": sev, "detail": detail})

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for i in self.items if i["severity"] == s) for s in ("pass", "warn", "manual", "fail")}


def check_nr(rep: Report, chapters: list[tuple[str, str]]) -> None:
    # NR1 表/图号：声明（行首）唯一；引用 ⊆ 声明
    declared: dict[str, str] = {}
    dup: list[str] = []
    cited: set[str] = set()
    for title, body in chapters:
        for line in body.splitlines():
            m = CAPTION_RE.match(line.strip())
            if m:
                tok = f"{m.group(1)}{m.group(2)}-{m.group(3)}"
                if tok in declared and declared[tok] != title:
                    dup.append(tok)
                declared[tok] = title
            for m in REF_RE.finditer(line):
                cited.add(f"{m.group(1)}{m.group(2)}-{m.group(3)}")
    rep.add("NR1", "pass" if not dup else "fail", f"表/图号声明 {len(declared)} 个，重号 {dup or '无'}")
    dangling = sorted(c for c in cited if c not in declared)
    if dangling:
        rep.add("NR1", "warn", f"引用了未声明的表/图号: {dangling[:8]}")
    # NR2 小节号：章内严格递增
    for title, body in chapters:
        prev: tuple[int, ...] | None = None
        for line in body.splitlines():
            m = SEC_HEAD_RE.match(line)
            if not m:
                continue
            cur = tuple(int(x) for x in m.groups() if x)
            if prev is not None and cur[: len(prev)] == prev and len(cur) == len(prev) + 1:
                pass  # 正常下钻
            elif prev is not None and len(cur) == len(prev) and cur <= prev:
                rep.add("NR2", "fail", f"{title}: 小节号非递增 {prev} → {cur}")
            prev = cur
        # 段内 (1)(2)… 序号严格 +1（按出现顺序）
        seq_expect = None
        for m in re.finditer(r"[（(](\d+)[)）][^。]{0,200}", body):
            n = int(m.group(1))
            if seq_expect is not None and n != seq_expect:
                if n == 1:  # 新列表重启
                    seq_expect = 2
                    continue
                rep.add("NR2", "warn", f"{title}: 段内序号跳变（期望 {seq_expect} 实得 {n}）——样例 8.6.1 (1)(1)(2) 同型")
                seq_expect = n + 1
            else:
                seq_expect = n + 1
    rep.add("NR2", "pass", "小节/序号扫描完成")


def check_xs(rep: Report, chapters: list[tuple[str, str]], state: dict, data: fr.Data) -> None:
    chapters = numbered_chapters(chapters)
    # 槽位引用 exact_match：任一章节引用了槽位显示值记为「引用」；±2% 近似未精确 = warn
    near_misses: list[str] = []
    for title, body in chapters:
        for tok in NUM_RE.findall(body):
            d = fr.dec(tok)
            if not d.is_finite():
                continue
            for key, v in state.get("values", {}).items():
                sv = fr.dec(v.get("value"))
                if not sv or not sv.is_finite():
                    continue
                if d == sv:
                    break
                if abs(d - sv) / abs(sv) < NEAR_MISS:
                    near_misses.append(f"{title}: 「{tok}」≈ {key}={v['display']}（未精确引用）")
    for nm in near_misses[:10]:
        rep.add("XS2", "warn", nm)
    if not near_misses:
        rep.add("XS2", "pass", "槽位引用无近似改写")
    # XS3 判定词逐字在场
    hee = data.form("hydro_eng_env")
    verdicts = hee.get("type_verdicts") or {}
    for k in ("hydro_type", "engineering_type", "environment_type", "combined_type"):
        want = verdicts.get(k)
        if not want:
            continue
        full = "".join(b for _, b in chapters)
        rep.add("XS3", "pass" if want in full else "fail", f"{k}: 「{want}」{'在场' if want in full else '未逐字出现——口径不一致'}")
    # XS5 采空区两值在场
    goaf = hee.get("engineering.goaf") or {}  # schema 扁平点号键
    if goaf.get("count") is not None:
        full = "".join(b for _, b in chapters)
        for k in ("count", "volume_wm3"):
            tok = str(goaf.get(k))
            rep.add("XS5", "pass" if tok in full else "fail", f"采空区 {k}={tok} {'在场' if tok in full else '缺'}")


def check_fc(rep: Report, state: dict, data: fr.Data) -> None:
    V = state.get("values", {})

    def val(key: str) -> Decimal | None:
        v = V.get(key)
        return fr.dec(v.get("value")) if v and fr.dec(v.get("value")).is_finite() else None

    # FC1 小计=总计（±0.05 万吨/t 修约容差）
    tot = val("L9.total_ore_wt")
    if tot is not None:
        s = sum((val(f"L9.{c}_ore_wt") or fr.D0 for c in fr.CATS), fr.D0)
        rep.add("FC1", "pass" if abs(tot - s) <= Decimal("0.05") else "fail", f"矿石量总计 {tot} vs 小计和 {s}")
    tm_ = val("L9.total_metal_t")
    if tm_ is not None:
        s = sum((val(f"L9.{c}_metal_t") or fr.D0 for c in fr.CATS), fr.D0)
        rep.add("FC1", "pass" if abs(tm_ - s) <= Decimal("1") else "fail", f"金属量总计 {tm_} vs 小计和 {s}")
    # FC2 L10 仅在有历史备案时存在
    has_l10 = any(k.startswith("L10.") for k in V)
    has_prior = bool(data.form("prior_estimate").get("split_extent"))
    rep.add("FC2", "pass" if has_l10 == has_prior else "fail",
            f"L10 槽位存在={has_l10} vs 15 历史备案存在={has_prior}（无备案不得产 0 值差量）")
    # FC3 S1 分组自洽 n_all ≥ n_industrial + n_low
    n_all, n_i, n_l = val("S1.n"), val("S1.n_industrial"), val("S1.n_low")
    if n_all is not None:
        ok = n_all >= (n_i or fr.D0) + (n_l or fr.D0)
        rep.add("FC3", "pass" if ok else "fail", f"S1 n_all={n_all} ≥ n_ind={n_i} + n_low={n_l}")
    # FC4 C9 = 均值×倍数
    p13 = data.form("industrial_params")
    if p13 and val("C9.outlier_threshold") is not None:
        want = fr.dec(p13["deposit_avg_grade"]) * fr.dec(p13["outlier_multiple"])
        got = val("C9.outlier_threshold")
        rep.add("FC4", "pass" if abs(want - got) <= Decimal("0.01") else "fail", f"C9 {got} vs {want}")
    # FC5 L12 验证误差 |err| ≤ 5%（超差须评述）
    errs = [v for k, v in V.items() if k.startswith("L12.err[") and fr.dec(v.get("value")).is_finite()]
    over = [k for k, v in V.items() if k.startswith("L12.err[") and abs(fr.dec(v.get("value"))) > Decimal(5)]
    if errs:
        rep.add("FC5", "pass" if not over else "warn", f"L12 误差率 {len(errs)} 项，超 ±5%: {over or '无'}")
    # FC6 L11 重算
    pag, po = val("L11.P_Ag_total_kg"), val("L9.total_ore_wt")
    if pag is not None and val("L11.ag_grade") is not None and po is not None:
        # L9.total_ore_wt 是工业矿口径；total_kg 用工业+低品位 —— 重算按其 own inputs 不可得，
        # 校验 industrial 口径（差值=低品位贡献，结构上 total ≥ industrial）
        pi = val("L11.P_Ag_industrial_kg")
        if pi is not None:
            want = po * fr.WAN * val("L11.ag_grade") / fr.THOUSAND
            rep.add("FC6", "pass" if abs(want - pi) <= Decimal(1) else "fail", f"L11 工业伴生Ag {pi} vs 重算 {want.quantize(Decimal('1'))}")
    # FC7 E 链关系
    eco = data.form("economics")
    if eco:
        c_u, c_m = val("E1.C_usable"), val("E2.C_mined")
        dil = fr.dec(eco.get("rates", {}).get("dilution_rate", 0)) / fr.HUNDRED
        if c_u is not None and c_m is not None:
            want = c_u * (1 - dil)
            rep.add("FC7", "pass" if abs(want - c_m) <= Decimal("0.01") else "fail", f"E2.C_mined {c_m} vs {want.quantize(Decimal('0.01'))}")
        p_conc = val("E4.price_conc")
        if p_conc is not None:
            conc = eco.get("concentrate", {})
            prices = eco.get("prices", {})
            want = fr.dec(prices.get("cu_yuan_t", 0)) * fr.dec(conc.get("grade_cu_pct", 0)) / fr.HUNDRED \
                + (fr.dec(prices.get("ag_yuan_kg", 0)) or fr.dec(prices.get("ag_yuan_per_g", 0)) * fr.THOUSAND) / fr.THOUSAND * fr.dec(conc.get("grade_ag_gpt", 0))
            rep.add("FC7", "pass" if abs(want - p_conc) <= Decimal(1) else "fail", f"E4 {p_conc} vs {want.quantize(Decimal('1'))}")
    # FC8 L13 占比
    st = val("L13.share_TM")
    if st is not None:
        ok = 0 <= st <= 100 and st <= (val("L13.share_TM_KZ") or Decimal(101))
        rep.add("FC8", "pass" if ok else "fail", f"L13 share_TM={st} ∈ [0,100] 且 ≤ share_TM_KZ")
    # B1C 声明 vs 计算
    for k, v in V.items():
        if k.startswith("B1.recovery[") and v.get("declared_recovery") is not None:
            d, c = fr.dec(v["declared_recovery"]), fr.dec(v["value"])
            rep.add("B1C", "pass" if abs(d - c) <= Decimal("0.05") else "fail", f"{k}: 声明 {d} vs 计算 {c}")


def check_cc(rep: Report, chapters: list[tuple[str, str]], state: dict, data: fr.Data, standards: dict | None) -> None:
    full = "".join(b for _, b in chapters)
    # CC1 变化系数档次
    p13 = data.form("industrial_params")
    rng = (p13.get("grade_variation_coeff_range") or []) if p13 else []
    cvs = [fr.dec(v.get("value")) for k, v in state.get("values", {}).items() if k.startswith("S2.Cv[") and fr.dec(v.get("value")).is_finite()]
    if not cvs:
        pass
    elif len(rng) >= 2:
        lo, hi = fr.dec(rng[0]), fr.dec(rng[1])
        out = [str(c) for c in cvs if not (lo <= c <= hi)]
        rep.add("CC1", "pass" if not out else "warn", f"S2 变化系数 {len(cvs)} 项，出档 [{lo},{hi}]: {out or '无'}")
    else:
        rep.add("CC1", "manual", "13.grade_variation_coeff_range 未填——需人工对照勘查类型档次")
    if p13 and standards is not None:
        mult = p13.get("outlier_multiple")
        tiers = standards if isinstance(standards, list) else standards.get("tier1", standards.get("items", []))
        allowed = set()
        for t in tiers if isinstance(tiers, list) else []:
            for x in re.findall(r"特高品位[^。]{0,40}?(\d+)\s*[-～至]\s*(\d+)\s*倍", str(t.get("text", t.get("summary", "")))):
                allowed.update(range(int(x[0]), int(x[1]) + 1))
        if allowed:
            rep.add("CC1", "pass" if mult in allowed else ("manual" if not allowed else "fail"),
                    f"特高品位倍数 {mult}；standards_index 允许 {sorted(allowed)}" if mult not in allowed else f"特高品位倍数 {mult} 在标准档内")
        else:
            rep.add("CC1", "manual", "standards_index 无特高品位倍数条款——需人工对照")
    elif p13:
        rep.add("CC1", "manual", "standards_index 未加载——特高品位倍数需人工对照")
    # CC2 历史编码禁现代化改写
    bad = HIST_MODERN_RE.findall(full)
    rep.add("CC2", "pass" if not bad else "fail", f"历史编码现代化改写: {bad[:5] or '无'}（红线 P4）")
    # CC3 规范编号仅限 standards_index 枚举
    cites = {f"{m.group(1)} {m.group(2)}-{m.group(3)}" for m in STD_CITE_RE.finditer(full)}
    if not cites:
        rep.add("CC3", "pass", "正文无规范编号引用")
    elif standards is None:
        rep.add("CC3", "manual", f"规范引用 {sorted(cites)}——standards_index 未加载，需人工核实（web_search 不可靠）")
    else:
        known = set()
        for t in (standards if isinstance(standards, list) else standards.get("tier1", standards.get("items", []))):
            if isinstance(t, dict):
                known.add(str(t.get("code", "")))
                known.add(f"{t.get('code','')} {t.get('year','')}".strip())
        unknown = sorted(c for c in cites if c.replace(" ", "") not in {k.replace(" ", "") for k in known if k})
        rep.add("CC3", "pass" if not unknown else "fail", f"规范引用 {sorted(cites)}；未入库: {unknown or '无'}")


def check_sl(rep: Report, chapters: list[tuple[str, str]], pool: set[Decimal]) -> None:
    full = "".join(b for _, b in numbered_chapters(chapters))
    # SL1 槽位残留 = 0
    residue = re.findall(r"\{\{(?:SLOT|TABLE):[^}]*\}\}", full)
    rep.add("SL1", "pass" if not residue else "fail", f"{{{{SLOT:}}}}/{{{{TABLE:}}}} 残留 {len(residue)} 处" + (f": {residue[:5]}" if residue else ""))
    # SL2 数值溯源
    stripped = full
    for rx in WHITELIST_RE:
        stripped = rx.sub(" ", stripped)
    unknown: list[str] = []
    for tok in NUM_RE.findall(stripped):
        d = fr.dec(tok)
        if not d.is_finite():
            continue
        if d == d.to_integral_value() and abs(d) <= SMALL_INT_EXEMPT:
            continue
        if 1900 <= d <= 2100 and d == d.to_integral_value():
            continue
        if d not in pool:
            unknown.append(tok)
    if unknown:
        rep.add("SL2", "fail", f"不可溯源数值 {len(unknown)} 处: {unknown[:12]}（须定位到 data/ 或公式输出，绝不编造）")
    else:
        rep.add("SL2", "pass", "正文数值全部可溯源")


def check_nr3(rep: Report, chapters: list[tuple[str, str]], data: fr.Data) -> None:
    full = "".join(b for _, b in chapters)
    dates = {m.group(1) for m in DATE_NEAR_RE.finditer(full)}
    rep.add("NR3", "pass" if len(dates) <= 1 else "fail", f"估算截止日期出现 {sorted(dates) or '（未出现）'}")
    proj = data.form("project")
    for k, label in (("project_name", "矿区名"), ("undertaking_unit", "编制单位")):
        want = proj.get(k)
        if want:
            rep.add("NR3", "pass" if want in full else "warn", f"{label}「{want}」{'在场' if want in full else '未出现（与表单不一致？）'}")
    ten = data.form("tenement")
    lic = (ten or {}).get("tenement_no")
    if lic:
        rep.add("NR3", "pass" if lic in full else "warn", f"探矿权证号「{lic}」{'在场' if lic in full else '未出现'}")


# ── 主流程 ──────────────────────────────────────────────────────────────────

def run_checks(report_path: Path, data_dir: Path, stage_path: Path, state_path: Path,
               standards_path: Path | None) -> dict:
    text = report_path.read_text(encoding="utf-8")
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    data = fr.Data(data_dir, stage)
    standards = json.loads(standards_path.read_text(encoding="utf-8")) if standards_path and standards_path.exists() else None
    chapters = split_chapters(text)
    rep = Report()
    check_nr(rep, chapters)
    check_nr3(rep, chapters, data)
    check_xs(rep, chapters, state, data)
    check_fc(rep, state, data)
    check_cc(rep, chapters, state, data, standards)
    check_sl(rep, chapters, numeric_pool(data, state))
    return {"summary": rep.counts(), "items": rep.items}


def main() -> int:
    p = argparse.ArgumentParser(description="geological-report v2 — 四类合约一致性校验")
    p.add_argument("--report", required=True, help="build_output 产出的报告 md")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--state", required=True, help="state/formula_state.json")
    p.add_argument("--standards", help="references/standards_index.json（可选）")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = run_checks(Path(args.report), Path(args.data_dir), Path(args.stage), Path(args.state),
                        Path(args.standards) if args.standards else None)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["summary"]
    print(f"CONSISTENCY_READY: {args.output} pass={s['pass']} warn={s['warn']} manual={s['manual']} fail={s['fail']}")
    for i in result["items"]:
        if i["severity"] != "pass":
            print(f"  [{i['severity'].upper()}] {i['contract']}: {i['detail']}")
    if s["fail"]:
        return EXIT_FAIL
    if s["manual"]:
        return EXIT_MANUAL
    if s["warn"]:
        return EXIT_WARN
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
