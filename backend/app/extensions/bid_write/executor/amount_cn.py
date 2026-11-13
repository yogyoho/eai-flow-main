"""金额中文大写双向转换(批二十 M1,EAI-CUSTOM 2026-11-13)——SK-BL-002/PS-004
固定函数(含零/整/角分规则)。审查端 expr.py::_number_to_words 取整到元且角分 v2
未做、跨端私有,不复用;本模块为写作端自足实现,canonical 形=本模块 num_to_cn
产出(双向断言口径:生成侧大写必须 canonical,非 canonical=FAIL)。"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

_CN_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNIT4 = {"拾": 10, "佰": 100, "仟": 1000}
_SEG = {"亿": 100_000_000, "万": 10_000}
_CN_DIGIT_MAP = {c: i for i, c in enumerate(_CN_DIGITS)}

_Q2 = Decimal("0.01")


def _four(n: int) -> str:
    """0..9999 → 中文段(金额惯例:壹拾;段内零合并,如 105=壹佰零伍)。"""
    d3, rem = divmod(n, 1000)
    d2, rem = divmod(rem, 100)
    d1, d0 = divmod(rem, 10)
    out: list[str] = []
    pending_zero = False
    for d, unit in ((d3, "仟"), (d2, "佰"), (d1, "拾")):
        if d == 0:
            if out:
                pending_zero = True
        else:
            if pending_zero:
                out.append("零")
                pending_zero = False
            out.append(_CN_DIGITS[d] + unit)
    if d0:
        if pending_zero:
            out.append("零")
        out.append(_CN_DIGITS[d0])
    return "".join(out)


def num_to_cn(value) -> str:
    """金额数字→中文大写(元/角/分,ROUND_HALF_UP 2 位;零=零元整;负数非法——
    金额断言面恒非负)。形如:2000000→贰佰万元整;100005000→壹亿零伍仟元;
    1.5→壹元伍角整;1.05→壹元零伍分;0.05→伍分。"""
    d = Decimal(str(value)).quantize(_Q2, rounding=ROUND_HALF_UP)
    if d < 0:
        raise ValueError(f"金额断言面恒非负,得 {value}")
    yuan = int(d)
    cents = int((d - yuan) * 100)
    jiao, fen = divmod(cents, 10)
    if yuan == 0 and jiao == 0 and fen == 0:
        return "零元整"

    yi, rest = divmod(yuan, 100_000_000)
    wan, ge = divmod(rest, 10_000)
    segs = [(yi, "亿"), (wan, "万"), (ge, "")]
    parts: list[str] = []
    for idx, (val, unit) in enumerate(segs):
        if val == 0:
            continue
        if parts and any(v == 0 for v, _ in segs[:idx]):
            parts.append("零")
        parts.append(_four(val) + unit)

    out: list[str] = []
    if yuan:
        out.append("".join(parts) + "元")
    if jiao == 0 and fen == 0:
        out.append("整")
    else:
        if jiao:
            out.append(_CN_DIGITS[jiao] + "角")
            if fen == 0:
                out.append("整")
        if fen:
            if jiao == 0 and yuan:
                out.append("零")
            out.append(_CN_DIGITS[fen] + "分")
    return "".join(out)


def _cn_int(s: str) -> int:
    """中文大写整数段→int(仅 canonical 形:数字+拾佰仟配对、亿万分段)。"""
    total = 0
    cur = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "零":
            i += 1
        elif ch in _CN_DIGIT_MAP:
            d = _CN_DIGIT_MAP[ch]
            if i + 1 < len(s) and s[i + 1] in _UNIT4:
                cur += d * _UNIT4[s[i + 1]]
                i += 2
            else:
                cur += d
                i += 1
        elif ch in _SEG:
            total += cur * _SEG[ch]
            cur = 0
            i += 1
        else:
            raise ValueError(f"非法大写字符 {ch!r}")
    return total + cur


# canonical 形文法(=num_to_cn 产出域):[元段]元? [角段]角? [零]?[分段]分? 整?
# canonical 约束:零 间隔只在"有元无角有分";整 必须挂在元/角后;三分支至少其一
_CN_TAIL = re.compile(
    r"^(?:(?P<yuan>[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]+)元)?"
    r"(?:(?P<jiao>[壹贰叁肆伍陆柒捌玖])角)?"
    r"(?:(?P<zl>零)?(?P<fen>[壹贰叁肆伍陆柒捌玖])分)?"
    r"(?P<zheng>整)?$"
)


def cn_to_num(text: str) -> Decimal:
    """中文大写金额→Decimal 元(2 位)。仅接受 canonical 形(num_to_cn 产出域,
    fullmatch 文法+约束);解析失败 raise ValueError(校验器按 FAIL 处理,不静默)。"""
    s = str(text).strip()
    m = _CN_TAIL.fullmatch(s)
    if m is None:
        raise ValueError(f"非 canonical 中文金额形: {text!r}")
    yuan_s, jiao_s, fen_s = m.group("yuan"), m.group("jiao"), m.group("fen")
    if not (yuan_s or jiao_s or fen_s):
        raise ValueError(f"空金额形: {text!r}")
    if m.group("zheng") and not (yuan_s or jiao_s):
        raise ValueError(f"整 必须挂在元/角之后: {text!r}")
    if jiao_s and not fen_s and not m.group("zheng"):
        raise ValueError(f"角后须整或分: {text!r}")
    if m.group("zl") and jiao_s:
        raise ValueError(f"零 间隔仅用于有元无角: {text!r}")
    yuan = _cn_int(yuan_s) if yuan_s else 0
    v = Decimal(yuan)
    if jiao_s:
        v += Decimal(_CN_DIGIT_MAP[jiao_s]) / 10
    if fen_s:
        v += Decimal(_CN_DIGIT_MAP[fen_s]) / 100
    return v.quantize(_Q2)
