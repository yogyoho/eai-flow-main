#!/usr/bin/env python3
"""coal-eia-report v2 — consistency.py：四类合约机器校验（步骤7）+ 环评合约注册表门（T1b）。

读 build_output 产出的报告全文 + formula_state + data/ → consistency_check.json。
四类合约（XS/FC/CC/NR/SL 25 条——含 T4 页面实测增补 SL3/FC9/XS6）：
  NR  编号规则    NR1 表/图号连续唯一（样例「表512」笔误防线）；NR2 小节号+段内序号
                  严格递增（样例 8.6.1 (1)(1)(2) 错乱防线）；NR3 截止日期/矿区名等
                  全局唯一同源
  XS  数字一致    槽位引用逐章 exact_match（不同章节同一数字必须同显示）；±2% 近似
                  未精确 = 疑似改写 warn；XS3 判定词逐字在场；XS5 采空区两值在场；
                  XS6 同一中文指标标签跨章数值必须唯一
  FC  公式链      L9 小计=总计、L11/L12 重算、E 链关系、B1 声明差 ≤0.05pp、
                  C9=均值×倍数、S1 分组自洽、FC9 potential 量级 10×带宽 sanity
  CC  编码约束    CC1 变化系数档次（standards_index 在库自动判，缺库→manual）；
                  CC2 历史编码禁现代化改写（332/333/111b/122b 红线 P4）；
                  CC3 规范编号只允许 standards_index 枚举（禁 LLM 记忆）
  SL  槽位/溯源   SL1 {{SLOT:}}/{{TABLE:}} 残留=0（宽匹配含畸形括号形，FAIL 阻断
                  present_files）；SL2 正文数值全部可溯源到 data/ 或 formula_state
                  （12 以下小整数、年份、日期、编号白名单豁免）；SL3 范文指纹抽检
                  （样例库数值/地质单元专名禁凭空进入正文，N18）

环评合约注册表门（T1b 改造点①—③，spec「两层模型改造点清单」consistency.py 行 +
D4 口径标签绑定；注册表经 --contracts 注入，缺省 = references/consistency_contracts.json
在册即自动启用——该文件由 T4 维护，本脚本只读）：
  ① 条件激活    每条合约带 stages（applicable_stages，stage 文件 stem 或 stage 名）+
                conditional.requires_any_section_semantic（依赖章/节按语义标题在场才激活；
                标题语义匹配禁章号——要素章序 4 种排布实证）。未激活记 **skip** 行
                （统计口径单列，非 FAIL 非 PASS）；conditional.on_absent 定档（缺省 skip）。
  ② 表格感知抽取 环评数字主体在表格（实测最高 91% 段落在表）——exact_match 候选值抽取
                扫全部行含 md 表格行（|…|），不只正文段。
  ③ 口径标签校验 值引用可带口径标签（如 154|修编后 / 144|修编前，表格内=相邻单元格同型）；
                合约绑定标签时：异标签在场 = 口径冲突 FAIL；双口径并存时的无标签引用 =
                跨口径歧义 FAIL；合约未绑标签时跨章多标签并存 = 口径不一致 FAIL。
合约机器载荷：values:[{value,label?}]（exact_match）/ entities+targets_semantic
（echo_obligation 呼应义务，D11）；载荷缺席降级 manual（T4 注册表描述态→机器态随表单落地补全）。

severity: pass / warn / manual / skip / fail。退出码 fail>0→1，manual>0→2，warn>0→3，否则 0
（skip 不影响退出码）。
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
            # bug-3060：真实数据串大量内嵌数字（文号「〔2024〕0088号」、同位素年龄「1689±32Ma」、
            # 历史工作量「钻探15600m」）——只试整串转数会漏，SL2/SL3 对正文引用这些数字全部误报
            # 不可溯源。凡 data/ 串里出现的数字本身就是溯源凭据，逐个入池。
            for m in re.finditer(r"\d+(?:\.\d+)?", v):
                d2 = fr.dec(m.group(0))
                if d2.is_finite():
                    pool.add(d2)
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
    r"1\s*[：:]\s*\d+(?:\.\d+)?",                      # 比例尺 1:10000 / 1:2000（bug-3060 真实数据实测）
    r"[〔\[]\d{4}[〕\]]\s*\d{2,6}\s*号",                # 文号 〔2024〕0088号
    r"(?i)(?:GB|DZ|YS|HY|QB|Ch|TB)[A-Z]*(?:\s*/\s*[A-Z]+)+\s*\d{3,5}(?:\s*[-—~～]\s*\d{2,4})?",  # 标准代号 DZ/T 0141
    r"(?:合计|共计|累计|总计)\s*\d+(?:\.\d+)?",          # 显式聚合标签后的数（合计560m——分项和，P0-1 审计要求的呈现形态）
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
        # skip = 条件激活未命中的合约（统计口径单列，T1b 改造点①——非 FAIL 非 PASS 不计 rc）
        return {s: sum(1 for i in self.items if i["severity"] == s) for s in ("pass", "warn", "manual", "skip", "fail")}


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
    # XS6 跨章同指标冲突（N27，T4 页面实测同一「平均品位」两章两值）：槽位显示值前方的
    # 中文标签跨章必须绑定唯一数值；小整数（≤12）豁免——（1）（2）序号噪声非指标。
    lab_re = re.compile(r"([一-鿿]{2,})\s*$")
    label_map: dict[str, set[str]] = {}
    for _t, body in chapters:
        for key, v in state.get("values", {}).items():
            sv = fr.dec(v.get("value"))
            disp = str(v.get("display", ""))
            if not disp or not sv.is_finite():
                continue
            if sv == sv.to_integral_value() and abs(sv) <= SMALL_INT_EXEMPT:
                continue
            for m in re.finditer(r"(?<![\d.])" + re.escape(disp) + r"(?![\d.])", body):
                lm = lab_re.search(body[max(0, m.start() - 12): m.start()])
                if lm:
                    label_map.setdefault(lm.group(1), set()).add(disp)
    conflict = {lab: sorted(ds) for lab, ds in sorted(label_map.items()) if len(ds) > 1}
    # bug-3060 降档 fail→warn：label_map 只收集【槽位 display】的出现（手写数根本进不了本图——
    # 那类伪造是 SL2 的辖区）；槽位纯化报告里同标签绑不同 display = 不同口径槽位（分矿体/分类别/
    # 全区）的合法并立，真实数据下 fail 全为误报（实测 7 组全是 L8/L9/S1 族内分 scope）。N27 的
    # 「手写冲突」保护由 SL2（不可溯源数值）承担。降为口径复核提示。
    rep.add("XS6", "pass" if not conflict else "warn",
            "跨章同指标标签数值唯一" if not conflict else f"同标签多值（口径复核提示——均为槽位注入，非冲突）: {conflict}")


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
            # bug-3059：绝对 1 kg 容差只在小矿规模成立——大矿 L9 分类量各自 0.01 万吨四舍五入，
            # 组合噪声随规模线性放大（899 万吨级实测 48738 vs 48726，差 0.02%）。改相对容差 0.1%
            #（下限 1 kg）——真错值（错品位/错矿石量）差 % 级，门的缉假力不受损。
            tol = max(Decimal(1), abs(pi) * Decimal("0.001"))
            rep.add("FC6", "pass" if abs(want - pi) <= tol else "fail", f"L11 工业伴生Ag {pi} vs 重算 {want.quantize(Decimal('1'))}（容差 {tol.quantize(Decimal('0.1'))} kg）")
    # FC7 E 链关系
    eco = data.form("economics")
    if eco:
        c_u, c_m = val("E1.C_usable"), val("E2.C_mined")
        dil = fr.dec((eco.get("rates") or {}).get("dilution_rate", 0)) / fr.HUNDRED  # P5 ledger A：显式 null 子对象守卫（or {}）
        if c_u is not None and c_m is not None:
            want = c_u * (1 - dil)
            rep.add("FC7", "pass" if abs(want - c_m) <= Decimal("0.01") else "fail", f"E2.C_mined {c_m} vs {want.quantize(Decimal('0.01'))}")
        p_conc = val("E4.price_conc")
        if p_conc is not None:
            conc = eco.get("concentrate") or {}  # P5 ledger A：显式 null 子对象守卫（or {}）
            prices = eco.get("prices") or {}  # P5 ledger A：同款守卫
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
    # FC9 经济量级 sanity（N26，T4 页面实测 33209 亿元级虚高穿透）：potential 类槽位
    # 与 L9金属量×E4精矿价格/(品位/100) 独立重算对表（10× 带宽）；单位从槽位 unit 字段
    # 或键后缀判（亿/yi→1e8、万/wan/wy→1e4），判不出不猜、跳过该键；输入不全整体跳过不误伤。
    tm9, pc9 = val("L9.total_metal_t"), val("E4.price_conc")
    gcu9 = fr.dec(((data.form("economics") or {}).get("concentrate") or {}).get("grade_cu_pct") or 0)
    pot = {k: v for k, v in V.items() if "potential" in k and fr.dec(v.get("value")).is_finite()}
    if pot and tm9 is not None and pc9 and gcu9:
        implied = tm9 * pc9 / (gcu9 / fr.HUNDRED)  # 元
        bads = []
        for k, v in pot.items():
            unit = str(v.get("unit") or "")
            mult = Decimal(10**8) if ("亿" in unit or k.endswith("_yi")) else \
                Decimal(10**4) if ("万" in unit or k.endswith(("_wan", "_wy"))) else Decimal(1)
            r = fr.dec(v["value"]) * mult / implied
            if not (Decimal("0.1") <= r <= Decimal(10)):
                bads.append(f"{k}={v['display']}")
        rep.add("FC9", "pass" if not bads else "fail",
                f"potential 量级 sanity {len(pot)} 项 vs 独立重算（10×带宽）: 超带 {bads or '无'}")
    elif pot:
        rep.add("FC9", "pass", f"potential 槽位 {len(pot)} 个但量级输入不全——跳过（缺 L9/E4/品位）")


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
        # bug-3060：实文件顶层键是 standards（14 条 {code,title,...}）——旧取值链 tier1/items 双双落空
        # → 允许倍数集恒空（CC1 误判 manual/fail）。加 standards 首选。
        tiers = standards if isinstance(standards, list) else standards.get("standards", standards.get("tier1", standards.get("items", [])))
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
        # bug-3060：同 CC1——顶层键 standards 优先（tier1/items 为旧形状兼容）。
        for t in (standards if isinstance(standards, list) else standards.get("standards", standards.get("tier1", standards.get("items", [])))):
            if isinstance(t, dict):
                known.add(str(t.get("code", "")))
                known.add(f"{t.get('code','')} {t.get('year','')}".strip())
        unknown = sorted(c for c in cites if c.replace(" ", "") not in {k.replace(" ", "") for k in known if k})
        rep.add("CC3", "pass" if not unknown else "fail", f"规范引用 {sorted(cites)}；未入库: {unknown or '无'}")


def check_sl3(rep: Report, chapters: list[tuple[str, str]], data: fr.Data, stage_path: Path, pool: set[Decimal]) -> None:
    """SL3 范文指纹抽检（N18，T4 页面实测范文数值/专名污染正文）：样例库 ≥100 的数值
    不得凭空出现在正文——数值必须在 numeric_pool（fail，数值是硬事实）；「××组/群」
    地质单元名须见于 data/（warn，专名上下文性强不当硬门）。样例库缺失降级 warn 跳过。"""
    samples_dir = stage_path.parents[1] / "samples" / stage_path.stem
    if not samples_dir.is_dir():
        rep.add("SL3", "warn", f"样例库缺失 {samples_dir.name}——范文指纹抽检跳过")
        return
    snums: set[Decimal] = set()
    snames: set[str] = set()
    for p in samples_dir.glob("*.md"):
        st = p.read_text(encoding="utf-8")
        snums.update(d for tok in NUM_RE.findall(st) if (d := fr.dec(tok)).is_finite() and abs(d) >= 100)
        snames.update(re.findall(r"[一-鿿]{1,4}(?:组|群)", st))
    if not snums and not snames:
        rep.add("SL3", "warn", "样例库无数值/专名指纹——范文指纹抽检跳过")
        return
    full = "".join(b for _, b in numbered_chapters(chapters))
    stripped = full
    for rx in WHITELIST_RE:
        stripped = rx.sub(" ", stripped)
    leaked = sorted({tok for tok in NUM_RE.findall(stripped) if fr.dec(tok) in snums and fr.dec(tok) not in pool})
    rep.add("SL3", "pass" if not leaked else "fail",
            f"范文数值指纹抽检（样例库 {len(snums)} 个≥100 数值）: 泄漏 {leaked or '无'}")
    if snames:
        blob = json.dumps(data.forms, ensure_ascii=False, default=str) + json.dumps(data.csvs, ensure_ascii=False, default=str)
        strange = sorted(n for n in snames if n in full and n not in blob)
        if strange:
            rep.add("SL3", "warn", f"范文专名疑带入正文（data/ 无此名）: {strange[:6]}")


def check_sl(rep: Report, chapters: list[tuple[str, str]], pool: set[Decimal]) -> None:
    full = "".join(b for _, b in numbered_chapters(chapters))
    # SL1 槽位残留 = 0（宽匹配，N19：双括号严匹配曾漏「{SLOT:k}」单开括号与
    # 「{{SLOT:k}单位}」错配收形共 93 处穿透进终稿——凡 \{+SLOT:/TABLE: 一律残留）
    residue = re.findall(r"\{+(?:SLOT|TABLE):[^{}]*(?:\}+[^{}\n]*\}|\}*)", full)
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


# ── 环评合约注册表门（T1b 改造点①条件激活 / ②表格感知抽取 / ③口径标签校验）──────────
# 注册表 --contracts 注入（缺省 references/consistency_contracts.json——T4 维护，本脚本只读）。

_TITLE_NORM2_RE = re.compile(r"[\s　\-—–·。，,、;；:：!！?？()（）\[\]【】\"'“”‘’/*／|]+")


def _norm_sem(s: str) -> str:
    """标题语义规范化：去空白/全半角标点/装饰符后小写，剥尾部「章/节」通名
    （注册表 consumers 写「结论章」、报告章题「结论与建议」→「结论」⊆「结论与建议」命中）。"""
    t = _TITLE_NORM2_RE.sub("", str(s)).lower()
    if len(t) > 2 and t[-1] in "章节":
        t = t[:-1]
    return t


def _semantic_hit(headings_norm: list[str], want: str) -> bool:
    """语义标题命中：规范化后相等或双向包含（禁章号匹配——要素章序 4 种排布实证）。"""
    w = _norm_sem(want)
    return bool(w) and any(w == h or w in h or h in w for h in headings_norm)


def _heading_norms(chapters: list[tuple[str, str]]) -> list[str]:
    """全部标题行（##/###/####）规范化文本——条件激活按「章/节语义标题在场」判定。"""
    out: list[str] = []
    for _t, body in chapters:
        for ln in body.splitlines():
            s = ln.strip()
            if s.startswith("#"):
                out.append(_norm_sem(s.lstrip("#")))
    return out


def load_contracts(path: Path | None) -> dict | None:
    """合约注册表装载；缺失/损坏 → None（stderr 提示后跳过注册表门——与 standards 同语义）。"""
    if path is None or not Path(path).exists():
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(doc.get("contracts"), list):
            raise ValueError("contracts 缺失或非数组")
        return doc
    except (json.JSONDecodeError, ValueError, AttributeError, OSError) as e:
        print(f"[consistency] 合约注册表损坏（{path}: {e}）——注册表门跳过（geo 内建合约不受影响）", file=sys.stderr)
        return None


def _value_occurrences(body: str, value: str) -> tuple[list[str], int]:
    """单章正文内值出现抽取——**含表格行**（T1b 改造点②：数字主体在表格，最高 91% 段落在表）。

    返回（带口径标签清单, 无标签次数）。标签语法 = 值后紧跟 `|标签`（正文形 154|修编后）；
    表格内相邻单元格同型（| 154 | 修编前 | → `154\\s*\\|\\s*修编前` 同式命中——单元格分隔符
    与标签分隔符同形，语义恰好一致：紧邻右格即口径）。数值带边界守卫（144 不吃 1440/1.144）；
    相邻格是纯数值（| 86 | 1200 |）判为表格分隔非口径标签 → 记无标签。
    """
    lab_re = re.compile(re.escape(value) + r"\s*\|\s*([^\s|，。；,、]+)")
    tok_re = re.compile(r"(?<![\d.])" + re.escape(value) + r"(?![\d.])")
    labeled: list[str] = []
    n_bare = 0
    for m in tok_re.finditer(body):
        lm = lab_re.match(body, m.start())
        cap = lm.group(1) if lm else ""
        if cap and re.fullmatch(r"[\d.,%]+", cap):
            n_bare += 1  # 表格相邻数值单元格 = 分隔符非口径标签
        elif cap:
            labeled.append(cap)
        else:
            n_bare += 1
    return labeled, n_bare


def _find_chapter(chapters: list[tuple[str, str]], want: str) -> tuple[str, str] | None:
    w = _norm_sem(want)
    for t, b in chapters:
        ht = _norm_sem(t.lstrip("#").lstrip("0123456789. "))
        if w and ht and (w == ht or w in ht or ht in w):
            return t, b
    return None


def _contract_exact_match(rep: Report, c: dict, chapters: list[tuple[str, str]]) -> None:
    """cross_section exact_match（T1b ②③）：values[{value,label?}] 逐消费者章在场断言。

    合约绑标签：异标签在场 = 口径冲突 FAIL；双口径并存时裸值 = 跨口径歧义 FAIL；
    合约未绑标签：跨章多标签并存 = 口径不一致 FAIL。候选值抽取含表格行。
    """
    cid = c.get("id", "?")
    consumers = c.get("consumers") or []
    values = c.get("values") or []
    if not values:
        rep.add(cid, "manual", "合约未提供机器可校验 values 载荷（T4 注册表描述态→机器态待表单落地）——需人工对照")
        return
    targets = [(t, _find_chapter(chapters, t)) for t in consumers]
    # 全消费者章文本 = 双口径并存判定域（裸值歧义跨章成立）
    domain = "".join(hit[1] for _t, hit in targets if hit)
    for ent in values:
        v = str(ent.get("value", "")).strip()
        if not v:
            continue
        want_label = (ent.get("label") or "").strip()
        for t, hit in targets:
            where = f"值 {v}" + (f"｜{want_label}" if want_label else "")
            if hit is None:
                rep.add(cid, "fail", f"{where} 目标章「{t}」不在场——exact_match 无从核验（章缺失或题不符）")
                continue
            _title, body = hit
            labeled, n_bare = _value_occurrences(body, v)
            if not labeled and n_bare == 0:
                rep.add(cid, "fail", f"{where} 未在章「{t}」出现（候选值抽取含表格行——逐值补写或修数）")
                continue
            bad_labels = [x for x in labeled if want_label and _norm_sem(x) != _norm_sem(want_label)]
            if bad_labels:
                rep.add(cid, "fail", f"{where} 口径标签冲突：章「{t}」出现 {v}|{'/'.join(sorted(set(bad_labels)))} ≠ 期望「{want_label}」（D4 口径绑定）")
                continue
            if n_bare and want_label:
                other = {x for x in labeled if _norm_sem(x) != _norm_sem(want_label)}
                dual = other | {x for x in _iter_all_labels(domain, v) if _norm_sem(x) != _norm_sem(want_label)}
                if dual:
                    rep.add(cid, "fail", f"{where} 章内裸值 {n_bare} 处且全书并存口径 {sorted(dual)}——无标签跨口径歧义 FAIL（逐处补 |{want_label}）")
                    continue
            rep.add(cid, "pass", f"{where} 章「{t}」在场 {len(labeled)} 标注 + {n_bare} 裸值" + ("" if not want_label or not n_bare else "（全书无冲突口径，裸值容忍）"))
        if not want_label:
            all_labels = {x for t, hit in targets if hit for x in _value_occurrences(hit[1], v)[0]}
            if len(all_labels) > 1:
                rep.add(cid, "fail", f"值 {v} 跨章口径标签不一致: {sorted(all_labels)}——跨章 exact_match 要求口径一致（D4）")


def _iter_all_labels(text: str, value: str) -> list[str]:
    return re.findall(re.escape(value) + r"\s*\|\s*([^\s|，。；,、]+)", text)


def _contract_echo(rep: Report, c: dict, chapters: list[tuple[str, str]]) -> None:
    """echo_obligation 呼应义务（D11）：源清单实体逐项在目标章在场断言（XS5 在场模式，章级门）。

    载荷 entities + targets_semantic；反向断言（目标章出现源清单外实体）需源清单边界语义，
    一期不做（防误报——措施章自有实体远多于识别章清单）。
    """
    cid = c.get("id", "?")
    entities = [str(e) for e in (c.get("entities") or []) if str(e).strip()]
    targets = [str(t) for t in (c.get("targets_semantic") or c.get("consumers") or []) if str(t).strip()]
    if not entities or not targets:
        rep.add(cid, "manual", "呼应义务缺 entities/targets_semantic 机器载荷——需人工对照（源清单实体逐项在场）")
        return
    for t in targets:
        hit = _find_chapter(chapters, t)
        if hit is None:
            rep.add(cid, "fail", f"呼应目标章「{t}」不在场——义务链断裂（源→目标章缺失）")
            continue
        missing = [e for e in entities if e not in hit[1]]
        rep.add(cid, "pass" if not missing else "fail",
                f"章「{t}」呼应义务 {len(entities)} 实体逐项在场" if not missing else f"章「{t}」缺源清单实体: {missing[:6]}——影响识别→措施/风险→应急/预测→结论呼应义务（D11）")


def check_contracts(rep: Report, chapters: list[tuple[str, str]], contracts: dict, stage_ids: set[str]) -> None:
    """注册表合约逐条评估：条件激活（stages + requires_any_section_semantic）→ 类型分派。

    未激活记 skip（conditional.on_absent 定档，缺省 skip）——统计口径单列非 FAIL
    （openpit 无沉陷章/可选章缺席/回顾识别互换双模式同理，设计 2026-09-06 拍板）。
    """
    for c in contracts.get("contracts", []):
        cid = str(c.get("id") or "CC-EIA-?")
        stages = c.get("stages") or []
        if stages and not (set(stages) & stage_ids):
            rep.add(cid, "skip", f"applicable_stages {stages} 不含当前 stage（{sorted(stage_ids)}）——条件激活跳过")
            continue
        cond = c.get("conditional") or {}
        requires = cond.get("requires_any_section_semantic") or []
        if requires:
            heads = _heading_norms(chapters)
            if not any(_semantic_hit(heads, w) for w in requires):
                sev = cond.get("on_absent", "skip")
                if sev not in ("skip", "pass", "warn", "manual", "fail"):
                    sev = "skip"
                rep.add(cid, sev, f"依赖章/节语义标题 {requires} 均不在场——条件激活未命中（记 {sev} 非 fail）")
                continue
        ctype = c.get("type", "cross_section")
        if ctype == "cross_section":
            _contract_exact_match(rep, c, chapters)
        elif ctype == "echo_obligation":
            _contract_echo(rep, c, chapters)
        else:
            # code_constraint：判定词/限值类——限值查 standards_index 需 tier1 人工核实，一期人工对照
            rep.add(cid, "manual", f"类型 {ctype}（判定词/限值类）需人工对照 standards_index（tier1 人工核实后可断言）")


# ── 主流程 ──────────────────────────────────────────────────────────────────

def run_checks(report_path: Path, data_dir: Path, stage_path: Path, state_path: Path,
               standards_path: Path | None, contracts_path: Path | None = None) -> dict:
    text = report_path.read_text(encoding="utf-8")
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    data = fr.Data(data_dir, stage)
    standards = json.loads(standards_path.read_text(encoding="utf-8")) if standards_path and standards_path.exists() else None
    contracts = load_contracts(contracts_path)
    chapters = split_chapters(text)
    rep = Report()
    check_nr(rep, chapters)
    check_nr3(rep, chapters, data)
    check_xs(rep, chapters, state, data)
    check_fc(rep, state, data)
    check_cc(rep, chapters, state, data, standards)
    pool = numeric_pool(data, state)
    check_sl(rep, chapters, pool)
    check_sl3(rep, chapters, data, stage_path, pool)
    if contracts:
        # 当前 stage 身份 = 文件 stem（注册表 stages 惯例，如 planning_eia）∪ stage JSON stage 名
        check_contracts(rep, chapters, contracts, {stage_path.stem, str(stage.get("stage", ""))})
    return {"summary": rep.counts(), "items": rep.items}


def main() -> int:
    p = argparse.ArgumentParser(description="coal-eia-report v2 — 四类合约一致性校验 + 环评合约注册表门（条件激活/表格感知/口径标签）")
    p.add_argument("--report", required=True, help="build_output 产出的报告 md")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--state", required=True, help="state/formula_state.json")
    p.add_argument("--standards", help="references/standards_index.json（可选）")
    p.add_argument("--contracts", help="references/consistency_contracts.json（可选——环评注册表门，T4 维护）")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = run_checks(Path(args.report), Path(args.data_dir), Path(args.stage), Path(args.state),
                        Path(args.standards) if args.standards else None,
                        Path(args.contracts) if args.contracts else None)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["summary"]
    print(f"CONSISTENCY_READY: {args.output} pass={s['pass']} warn={s['warn']} manual={s['manual']} skip={s.get('skip', 0)} fail={s['fail']}")
    for i in result["items"]:
        if i["severity"] not in ("pass", "skip"):
            print(f"  [{i['severity'].upper()}] {i['contract']}: {i['detail']}")
    skips = [i for i in result["items"] if i["severity"] == "skip"]
    if skips:
        print(f"  [SKIP x{len(skips)}] 条件激活未命中（单列统计非 FAIL）: " + "; ".join(f"{i['contract']}: {i['detail'][:48]}" for i in skips[:6]))
    if s["fail"]:
        return EXIT_FAIL
    if s["manual"]:
        return EXIT_MANUAL
    if s["warn"]:
        return EXIT_WARN
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
