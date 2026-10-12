"""Machine gates for the translation pipeline (EAI-CUSTOM, T4).

设计构件 2/5（前提 5 三轴机检 + R7 修正）:
  数值轴 = 占位符注册表对账 + 全文多重集归一化比对（并行运行）
  结构轴 = block 数量/类型 parity diff
  术语轴 = force 术语译文命中 + forbid（不译清单）原样保留

数字 run 范围 = ASCII 数字序列；CJK 数字 v1 出闸（R7/SC-6）。
归一化按入库语言字段选约定（fr/en），mixed 退化为字符串级相等。
占位符 token = ⟦#N⟧ 围栏（R7/C-2：不可能与正文碰撞）。
"""

import re
from dataclasses import dataclass, field

# ── 占位符机制 ────────────────────────────────────────────────────────

_DIGIT_RUN_RE = re.compile(r"\d[\d.,'  ]*\d|\d")
# 多重集提取的按约定数字 regex（R2-5 确定性规则：分组分隔符只认「sep+恰好3位」，
# 头部 \d+ 贪婪保证 4 位以上纯数字不被 \d{1,3} 截断——黄金集冒烟实测两连坑）
_FR_NUMBER_RE = re.compile(r"\d+(?:[  .']\d{3})*(?:,\d+)?")
_EN_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_PLACEHOLDER_RE = re.compile(r"⟦#(\d+)⟧")


@dataclass
class Registry:
    """数字 run 位置注册表：source 中的第 N 个数字 run。"""

    values: list[str] = field(default_factory=list)

    def register(self, value: str) -> str:
        self.values.append(value)
        return f"⟦#{len(self.values) - 1}⟧"


def extract_placeholders(text: str, registry: Registry) -> str:
    """把 text 中的 ASCII 数字 run 替换为 ⟦#N⟧ 占位符并登记。"""

    def _sub(m: re.Match) -> str:
        return registry.register(m.group(0))

    return _DIGIT_RUN_RE.sub(_sub, text)


def reinject_placeholders(text: str, registry: Registry) -> str:
    """按位回注：⟦#N⟧ → registry.values[N]。缺失/越界按原样保留（数值轴会抓到）。"""

    def _sub(m: re.Match) -> str:
        idx = int(m.group(1))
        if idx < len(registry.values):
            return registry.values[idx]
        return m.group(0)

    return _PLACEHOLDER_RE.sub(_sub, text)


def placeholder_drift(source_text: str, translated_text: str) -> list[str]:
    """注册表对账：译文中残留/丢失的占位符（结构性的数值错位信号）。"""
    src_count = len(_PLACEHOLDER_RE.findall(source_text))
    dst_count = len(_PLACEHOLDER_RE.findall(translated_text))
    drift: list[str] = []
    if src_count != dst_count:
        drift.append(f"placeholder count {src_count} -> {dst_count}")
    return drift


# ── 归一化（数值多重集比对前置步骤）──────────────────────────────────


_CURRENCY_RE = re.compile(r"(USD|EUR|CNY|RMB|GBP|JPY|AUD|CAD|CHF|\$|€|£|¥|US\$)", re.IGNORECASE)
_FULLWIDTH_RE = str.maketrans("０１２３４５６７８９（）．，", "0123456789().,")


def _normalize_number_token(token: str, lang: str) -> str:
    """单个数字 token 的确定性归一（R2-5：按语言约定，不做启发式猜读）。"""
    t = token.translate(_FULLWIDTH_RE).strip()
    t = _CURRENCY_RE.sub("", t).strip()
    if lang == "fr":
        # fr: 空格=千分位（删）、句点=千分位（删）、逗号=小数点（归一 '.'）
        t = t.replace(" ", "").replace(" ", "").replace("'", "").replace(".", "")
        t = t.replace(",", ".")
    else:
        # en/zh/mixed 约定：逗号=千分位（删）、句点=小数点
        t = t.replace(",", "").replace(" ", "").replace(" ", "").replace("'", "")
    # 尾部小数点清理（'1234.' → '1234'）
    if t.endswith("."):
        t = t[:-1]
    return t


_NEG_MARK = "§NEG§"


def _paren_negative_normalize(text: str) -> str:
    """括号负数 → 标记负号（财务惯例）；标记在多重集提取时并入 token，不污染普通连字符范围。"""
    return re.sub(r"\((\s*[\d.,'  ]+\s*)\)", _NEG_MARK + r"\1", text)


def normalized_number_multiset(text: str, lang: str) -> list[str]:
    """提取文本中的 ASCII 数字 run 并按语言约定归一 → 多重集（排序列表）。"""
    text = _paren_negative_normalize(text)
    number_re = _FR_NUMBER_RE if lang == "fr" else _EN_NUMBER_RE
    out = []
    for m in number_re.finditer(text):
        prefix = text[: m.start()]
        if prefix.endswith(_NEG_MARK):
            token = "-" + m.group(0)  # 括号负数（财务惯例）→ 负号并入 token
        elif prefix[-1:].isascii() and prefix[-1:].isalpha():
            continue  # 标识符邻接（Q3/T3/§4）——中译常作「第三」，非数值语义，排除
        else:
            token = m.group(0)
        norm = _normalize_number_token(token, lang)
        if norm:
            out.append(norm)
    return sorted(out)


def numeric_multiset_violations(source_text: str, translated_text: str, lang: str) -> list[str]:
    """数值轴：归一化后源/译多重集差异（R2-7：全文比对，覆盖自由文本残留数字）。

    约定各用各的：源文按其语言约定（fr 逗号小数），译文按 zh/en 渲染约定
    （设计构件 2：zh 产出按 en 约定）——两侧归一到数值意义后比对。
    """
    src_convention = lang if lang in {"fr", "en"} else "en"
    src = normalized_number_multiset(source_text, src_convention)
    dst = normalized_number_multiset(translated_text, "en")
    if src == dst:
        return []
    missing = sorted(set(src) - set(dst))
    extra = sorted(set(dst) - set(src))
    msgs = []
    if missing:
        msgs.append(f"missing in translation: {missing[:8]}")
    if extra:
        msgs.append(f"unexpected in translation: {extra[:8]}")
    return msgs


# ── 结构轴 ────────────────────────────────────────────────────────────


def structure_parity_violations(source_types: list[str], translated_types: list[str]) -> list[str]:
    """block 数量/类型 parity diff（设计构件 5 结构轴）。"""
    msgs: list[str] = []
    if len(source_types) != len(translated_types):
        msgs.append(f"block count {len(source_types)} -> {len(translated_types)}")
    for i, (s, t) in enumerate(zip(source_types, translated_types)):
        if s != t:
            msgs.append(f"block {i} type {s} -> {t}")
    return msgs


# ── 术语轴 ────────────────────────────────────────────────────────────


def terminology_violations(
    source_text: str,
    translated_text: str,
    force_terms: dict[str, str],
    dont_translate: set[str],
) -> list[str]:
    """术语轴：force 术语必须以指定译法出现；forbid 术语必须在译文中原样保留。"""
    msgs: list[str] = []
    for src_term, target in force_terms.items():
        if src_term.lower() in source_text.lower() and target not in translated_text:
            msgs.append(f"force term '{src_term}' -> '{target}' missing in translation")
    for term in dont_translate:
        if term in source_text and term not in translated_text:
            msgs.append(f"dont-translate term '{term}' altered in translation")
    return msgs


# ── 汇总 ──────────────────────────────────────────────────────────────


def run_numeric_axis(
    source_text: str,
    translated_text: str,
    lang: str,
    placeholder_source_text: str | None = None,
) -> list[str]:
    """数值轴 = 注册表对账（占位符残留）+ 全文多重集比对（R2-7 并行运行）。"""
    violations: list[str] = []
    if placeholder_source_text is not None:
        violations.extend(placeholder_drift(placeholder_source_text, translated_text))
    violations.extend(numeric_multiset_violations(source_text, translated_text, lang))
    return violations
