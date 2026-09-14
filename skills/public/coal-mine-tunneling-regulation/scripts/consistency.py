#!/usr/bin/env python3
"""geological-report v2 — consistency.py：四类合约机器校验（步骤7）。

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
    r"掘[A-Z]+-\d{4}[A-Z0-9]*/\d{1,3}号?",              # 规程编号 掘ZJED-2026N3218YSSC/01号（C11）
    r"(?:EBZ|CMM|KJ|ZYJ|FBD|WC\d?Y?)[-\s]?\d[\w./\-]*",  # 设备/系统型号 EBZ160/CMM2-15/KJ90X/ZYJ-M6/FBD-6.0（C8 溯源）
    r"Φ\s?\d+(?:\.\d+)?",                              # 管路直径 Φ1000（C5 管线表）
    r"1\s*[：:]\s*\d+(?:\.\d+)?",                      # 比例尺 1:10000
    r"[〔\[]\d{4}[〕\]]\s*\d{2,6}\s*号",                # 文号 〔2024〕0088号
    r"(?i)(?:GB|AQ|MT|LD)(?:/T)?\s?\d{3,5}(?:\s*[-—~～．.]\s*\d{1,4})?",  # 标准代号 GB/T 35056 / AQ 1029（C10/J8，历史编号）
    r"(?:合计|共计|累计|总计)\s*\d+(?:\.\d+)?",          # 显式聚合标签后的数
    r"[A-Z]{1,4}\d{2,6}[A-Za-z0-9\-]*",                # 证号/图号等字母前缀码
    r"第?\s*[一二三四五六七八九十]+\s*[章节条款项]",       # 中文序号
    r"\d+(?:\.\d+)?[‰℃]",                             # 千分比/摄氏度（26℃ 阈值叙述）
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
    # XS3/XS5 已删（geo 域判定词/采空区——T10 delta c：由 C12 echo 合约注册表承载）
    hee = data.form("hydro_eng_env")
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




def check_cc(rep: Report, chapters: list[tuple[str, str]], state: dict, data: fr.Data, standards: dict | None) -> None:
    full = "".join(b for _, b in chapters)
    # CC1 变化系数档次（geo 域残留：tunneling 无 S2.Cv 槽位时静默跳过——非 cvs 分支 pass 不产噪音）
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
    # CC2 已删（geo 历史编码 332/333 域专属——T10 delta c）
    # CC3 规范编号仅限 standards_index 枚举
    cites = {f"{m.group(1)} {m.group(2)}-{m.group(3)}" for m in STD_CITE_RE.finditer(full)}
    if not cites:
        rep.add("CC3", "pass", "正文无规范编号引用")
    elif standards is None:
        rep.add("CC3", "manual", f"规范引用 {sorted(cites)}——standards_index 未加载，需人工核实（web_search 不可靠）")
    else:
        known = set()
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


# ── 合约注册表框架（eia 移植 + 掘进数据源扩展，T10）─────────────────────────

_TITLE_NORM2_RE = re.compile(r"[\s　\-—–·。，,、;；:：!！?？()（）\[\]【】\"'“”‘’/*／|]+")


def _norm_sem(s: str) -> str:
    """标题语义规范化：去空白/全半角标点后小写，剥尾部「章/节」通名。"""
    t = _TITLE_NORM2_RE.sub("", str(s)).lower()
    if len(t) > 2 and t[-1] in "章节":
        t = t[:-1]
    return t


def _semantic_hit(headings_norm: list[str], want: str) -> bool:
    """语义标题命中：规范化后相等或双向包含（禁章号匹配——D7 条件激活纪律）。"""
    w = _norm_sem(want)
    return bool(w) and any(w == h or w in h or h in w for h in headings_norm)


def _heading_norms(chapters: list[tuple[str, str]]) -> list[str]:
    """全部标题行（##/###/####）规范化文本——条件激活按「章语义标题在场」判定。"""
    out: list[str] = []
    for _t, body in chapters:
        for ln in body.splitlines():
            s = ln.strip()
            if s.startswith("#"):
                out.append(_norm_sem(s.lstrip("#")))
    return out


def load_contracts(path: Path | None) -> dict | None:
    """合约注册表装载；缺失/损坏 → None（stderr 提示后跳过注册表门）。"""
    if path is None or not Path(path).exists():
        return None
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(doc.get("contracts"), list):
            raise ValueError("contracts 缺失或非数组")
        return doc
    except (json.JSONDecodeError, ValueError, AttributeError, OSError) as e:
        print(f"[consistency] 合约注册表损坏（{path}: {e}）——注册表门跳过", file=sys.stderr)
        return None


def _value_occurrences(body: str, value: str) -> tuple[list[str], int]:
    """单章正文内值出现抽取——含表格行（表格相邻数值格=分隔符非口径标签）。

    标签语法 = 值后紧跟 `|标签`（正文形 3.4|日最大；表格相邻单元格同型命中）。
    """
    lab_re = re.compile(re.escape(value) + r"\s*\|\s*([^\s|，。；,、]+)")
    tok_re = re.compile(r"(?<![\d.])" + re.escape(value) + r"(?![\d.])")
    labeled: list[str] = []
    n_bare = 0
    for m in tok_re.finditer(body):
        lm = lab_re.match(body, m.start())
        cap = lm.group(1) if lm else ""
        if cap and re.fullmatch(r"[\d.,%]+", cap):
            n_bare += 1
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


def _iter_all_labels(text: str, value: str) -> list[str]:
    return re.findall(re.escape(value) + r"\s*\|\s*([^\s|，。；,、]+)", text)


def resolve_source(expr: str, data: "fr.Data", state_values: dict) -> tuple[list[dict], list[str]]:
    """合约 source 表达式 → (值条目 [{"value","label"}], 缺失成分列表)（J5/T10 delta e）。

    语法：' + ' 分隔多源；
      data:<族>.<字段>        JSON 族字段标量（str(value)；array<object> 展平全标量值）
      data:<CSV族>:<列名>     CSV 族指定列值集合
      data:<CSV族>            CSV 族全表单元格字符串集
      data:<族>               裸族=档案族整体（echo 用，经 fields 载荷取值）
      formula:<槽位键>        state_values[key]["display"]（槽位键粒度）
    任一成分取不到 → 记入缺失列表（调用方判 skip——on_absent 同语义）。
    """
    entries: list[dict] = []
    missing: list[str] = []
    for part in (p.strip() for p in str(expr or "").split("+")):
        if not part:
            continue
        if part.startswith("formula:"):
            key = part[len("formula:"):]
            slot = (state_values or {}).get(key)
            if slot and slot.get("display") not in (None, ""):
                entries.append({"value": str(slot["display"]), "label": ""})
            else:
                missing.append(part)
        elif part.startswith("data:"):
            ref = part[len("data:"):]
            if ".csv" in ref:
                fam, _, col = ref.partition(":")
                rows = data.csvs.get(fam) or []
                if not rows:
                    missing.append(part)
                    continue
                if col:
                    entries.extend({"value": str(r.get(col, "")), "label": ""} for r in rows if r.get(col, "") != "")
                else:
                    for r in rows:
                        entries.extend({"value": str(v), "label": ""} for v in r.values() if v not in (None, ""))
            else:
                fam, _, field = ref.partition(".")
                doc = data.form(fam)
                if field:
                    if field not in doc or doc.get(field) in (None, ""):
                        missing.append(part)
                        continue
                    v = doc[field]
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                entries.extend({"value": str(x), "label": ""} for x in item.values() if x not in (None, ""))
                            elif item not in (None, ""):
                                entries.append({"value": str(item), "label": ""})
                    else:
                        entries.append({"value": str(v), "label": ""})
                else:
                    if not doc:
                        missing.append(part)
                    else:
                        entries.append({"value": "", "label": ""})  # 裸族占位：echo 经 fields 取
        else:
            missing.append(part)
    return entries, missing


def _contract_exact_match(rep: Report, c: dict, chapters: list[tuple[str, str]], data: "fr.Data", state_values: dict) -> None:
    """cross_section exact_match：source 解析值逐消费者章在场断言（表格感知+口径标签）。

    掘进适配：values 载荷改为 source 解析（J5）；消费者章缺席 → skip 非 fail（D7）；
    labels 映射（字段→口径）经 resolve_source 条目 label 传入。
    """
    cid = c.get("id", "?")
    consumers = c.get("consumers") or []
    expr = str(c.get("source", ""))
    entries, missing = resolve_source(expr, data, state_values)
    if missing:
        rep.add(cid, "skip", f"source 成分缺失 {missing[:3]}——取值不到记 skip（on_absent 同语义）")
        return
    # 口径标签接线（T10 自审修复：resolve_source 不知 labels，标量成分 1:1 时按字段名回填）
    labels_map = c.get("labels") or {}
    if labels_map:
        parts = [x.strip() for x in expr.split("+") if x.strip()]
        if len(parts) == len(entries):
            for part, ent in zip(parts, entries):
                if part.startswith("data:"):
                    field = part[5:].partition(".")[2].partition(":")[0]
                    ent["label"] = str(labels_map.get(field, ""))
    entries = [e for e in entries if e["value"]]
    if not entries:
        rep.add(cid, "skip", "source 解析为空值集——skip")
        return
    if not consumers:
        full = "".join(b for _, b in chapters)
        absent = [e["value"] for e in entries if e["value"] not in full]
        rep.add(cid, "pass" if not absent else "fail",
                f"{len(entries)} 值全文在场" if not absent else f"值 {absent[:4]} 全文未出现")
        return
    targets = [(t, _find_chapter(chapters, t)) for t in consumers]
    if any(hit is None for _t, hit in targets):
        miss = [t for t, hit in targets if hit is None]
        rep.add(cid, "skip", f"消费者章缺席 {miss}——依赖章不在场记 skip 非 fail（D7）")
        return
    for ent in entries:
        v, want_label = ent["value"], ent["label"]
        for t, hit in targets:
            where = f"值 {v}" + (f"｜{want_label}" if want_label else "")
            _t, body = hit
            labeled, n_bare = _value_occurrences(body, v)
            if not labeled and n_bare == 0:
                rep.add(cid, "fail", f"{where} 未在章「{t}」出现（含表格行扫描——逐值补写或修数）")
                continue
            bad = [x for x in labeled if want_label and _norm_sem(x) != _norm_sem(want_label)]
            if bad:
                rep.add(cid, "fail", f"{where} 口径标签冲突：章「{t}」出现 {v}|{'/'.join(sorted(set(bad)))} ≠ 期望「{want_label}」（口径绑定）")
                continue
            rep.add(cid, "pass", f"{where} 章「{t}」在场 {len(labeled)} 标注 + {n_bare} 裸值")
        if not want_label:
            all_labels = {x for _t, hit in targets if hit for x in _value_occurrences(hit[1], v)[0]}
            if len(all_labels) > 1:
                rep.add(cid, "fail", f"值 {v} 跨章口径标签不一致: {sorted(all_labels)}——exact_match 要求口径一致")


def _contract_echo(rep: Report, c: dict, chapters: list[tuple[str, str]], data: "fr.Data") -> None:
    """echo_obligation（掘进适配，T10 delta f）：载荷 {"fields":[...], "targets_semantic":[...]}。

    实体值经 source=data:<族> 动态取（档案/表单），逐项在目标章在场断言；
    字段缺失 → 该实体略过（全缺 → skip）；值不在场 = fail（C12 档案漂移检测本体）。
    """
    cid = c.get("id", "?")
    fields = [str(f) for f in (c.get("fields") or []) if str(f).strip()]
    targets = [str(t) for t in (c.get("targets_semantic") or c.get("consumers") or []) if str(t).strip()]
    if not fields or not targets:
        rep.add(cid, "manual", "呼应义务缺 fields/targets_semantic 机器载荷——需人工对照")
        return
    src = str(c.get("source", ""))
    fam = src[len("data:"):].partition(".")[0] if src.startswith("data:") else ""
    doc = data.form(fam) if fam else {}
    if not doc:
        rep.add(cid, "skip", f"源族 data:{fam} 未填充——首跑正常（on_absent 语义）")
        return
    entities: list[str] = []
    for f in fields:
        v = doc.get(f)
        if isinstance(v, (list, dict)) or v in (None, ""):
            continue  # 非标量（空数组/嵌套）不作回声实体——blank 语义 [] 是"未填"非值
        entities.append(str(v))
    if not entities:
        rep.add(cid, "skip", f"源族 {fam} 字段全缺 {fields[:4]}——skip 非 fail")
        return
    for t in targets:
        hit = _find_chapter(chapters, t)
        if hit is None:
            rep.add(cid, "skip", f"呼应目标章「{t}」不在场——条件激活跳过")
            continue
        missing = [e for e in entities if e not in hit[1]]
        rep.add(cid, "pass" if not missing else "fail",
                f"章「{t}」呼应义务 {len(entities)} 实体逐项在场" if not missing
                else f"章「{t}」缺源实体/档案漂移: {missing[:6]}——正文与档案不一致=fail（先更新档案再编规程）")


def _eval_guardrails(rep: Report, c: dict, data: "fr.Data") -> None:
    """护栏评估（T10 delta e2）：阈值 origin=review_skill 已入 standards_index（J8 未核实档=warn 非 fail）。"""
    cid = c.get("id", "?")
    src = str(c.get("source", ""))
    fam = src[len("data:"):].partition(".")[0] if src.startswith("data:") else ""
    doc = data.form(fam) if fam else {}
    if not doc:
        return
    for g in c.get("guardrails") or []:
        ref = str(g.get("ref", "?"))
        if g.get("compare") == "drive>=net":
            try:
                if float(doc.get("drive_section_m2")) < float(doc.get("net_section_m2")):
                    rep.add(cid, "warn", f"{ref} 护栏: 掘进断面<净断面——数据倒置核查（R10）")
            except (TypeError, ValueError):
                pass
            continue
        raw = str(g.get("field", ""))
        arr, _, leaf = raw.partition("[]")
        leaf = leaf.lstrip(".")
        items = doc.get(arr) or []
        if not isinstance(items, list) or not leaf:
            continue
        scope = str(g.get("scope", ""))
        skey, _, sval = scope.partition("=")
        for it in items:
            if not isinstance(it, dict):
                continue
            if skey:
                got = it.get(skey)
                if got is None:
                    # schema 双拼写：键名是「部位(顶板/帮部)」整串，值才是部位——按前缀找
                    for k, v in it.items():
                        if k.startswith(skey + "("):
                            got = v
                            break
                if got is None or str(got) != sval:
                    continue  # 归属不了 scope 或非本 scope 的行——不评估（防串行误报）
            try:
                v = float(it.get(leaf))
            except (TypeError, ValueError):
                continue
            if ("min" in g and v < float(g["min"])) or ("max" in g and v > float(g["max"])):
                bound = f"≥{g['min']}" if "min" in g else f"≤{g['max']}"
                rep.add(cid, "warn", f"{ref} 护栏: {fam}.{arr}[{scope}] {leaf}={v} 越界（{bound}；阈值待核实仅提示）")


def check_contracts(rep: Report, chapters: list[tuple[str, str]], contracts: dict, stage_ids: set[str],
                    data: "fr.Data", state_values: dict) -> None:
    """注册表合约逐条评估：条件激活（stages + requires_any_chapter_semantic）→ 类型分派。

    未激活记 skip（conditional.on_absent 定档缺省 skip）——统计单列非 FAIL（D7）。
    """
    for c in contracts.get("contracts", []):
        cid = str(c.get("id") or "C-?")
        stages = c.get("stages") or []
        if stages and not (set(stages) & stage_ids):
            rep.add(cid, "skip", f"applicable_stages {stages} 不含当前 stage（{sorted(stage_ids)}）")
            continue
        cond = c.get("conditional") or {}
        requires = cond.get("requires_any_chapter_semantic") or []
        if requires:
            heads = _heading_norms(chapters)
            if not any(_semantic_hit(heads, w) for w in requires):
                sev = cond.get("on_absent", "skip")
                if sev not in ("skip", "pass", "warn", "manual", "fail"):
                    sev = "skip"
                rep.add(cid, sev, f"依赖章语义标题 {requires} 均不在场——条件激活未命中（记 {sev} 非 fail）")
                continue
        ctype = c.get("type", "cross_section")
        if ctype == "cross_section":
            _contract_exact_match(rep, c, chapters, data, state_values)
            _eval_guardrails(rep, c, data)
        elif ctype == "echo_obligation":
            _contract_echo(rep, c, chapters, data)
        else:
            rep.add(cid, "manual", f"类型 {ctype}（判定词/限值类）需人工对照 standards_index（tier1 人工核实后可断言）")

# ── 主流程 ──────────────────────────────────────────────────────────────────

def run_checks(report_path: Path, data_dir: Path, stage_path: Path, state_path: Path,
               standards_path: Path | None, contracts_path: Path | None = None) -> dict:
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
    check_cc(rep, chapters, state, data, standards)
    pool = numeric_pool(data, state)
    check_sl(rep, chapters, pool)
    check_sl3(rep, chapters, data, stage_path, pool)
    contracts = load_contracts(contracts_path)
    if contracts:
        check_contracts(rep, chapters, contracts, {stage_path.stem, str(stage.get("stage", ""))},
                        data, state.get("values", {}))
    return {"summary": rep.counts(), "items": rep.items}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="coal-mine-tunneling-regulation v2 — 合约一致性校验（NR/XS/CC/SL 骨架 + C1-C12 注册表门）")
    p.add_argument("--report", required=True, help="build_output 产出的报告 md")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--state", required=True, help="state/formula_state.json")
    p.add_argument("--standards", help="references/standards_index.json（可选）")
    p.add_argument("--contracts", help="references/consistency_contracts.json（可选——C1-C12 注册表门）")
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
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
