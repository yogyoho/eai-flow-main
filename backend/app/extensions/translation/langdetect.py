"""Lightweight language detection for the translation pipeline (EAI-CUSTOM).

纯函数，无外部依赖。设计构件 4：入库时字段 source_lang ∈ {en, fr, zh, mixed}。
判定不了（文本太短/信号冲突）→ mixed（worker 阶段全文再判，扫描件走 OCR 后文本）。
"""

import re

_CJK_RE = re.compile(r"[一-鿿]")
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÿ]")

# 法语信号：强特征字符 + 高频功能词（英语也有的词不计分）
_FRENCH_HINTS = re.compile(r"[éèêëàâçîïôûùœÉÈÊÀÂÇÎÏÔÛÙ]|\b(le|la|les|des|une|est|dans|pour|avec|sur|que|qui|aux|cette|sont)\b", re.IGNORECASE)
_ENGLISH_HINTS = re.compile(r"\b(the|and|of|to|in|for|with|is|are|that|this|on|from|by|as|at|be|have)\b", re.IGNORECASE)

_CJK_THRESHOLD = 0.15  # CJK 字符占字母比 ≥15% 判中文


def detect_language(text: str) -> str:
    """en / fr / zh / mixed。文本过短或信号冲突 → mixed（宁可混，不可错路由）。"""
    if not text:
        return "mixed"
    latin_count = len(_ALPHA_RE.findall(text))
    cjk_count = len(_CJK_RE.findall(text))
    # CJK 判定独立于拉丁计数（纯中文文本 latin_count=0 也必须判 zh）
    if cjk_count > 0 and cjk_count / max(latin_count, 1) >= _CJK_THRESHOLD:
        return "zh"
    if latin_count == 0:
        return "mixed"
    french_hits = len(_FRENCH_HINTS.findall(text))
    english_hits = len(_ENGLISH_HINTS.findall(text))
    if french_hits == 0 and english_hits == 0:
        return "mixed"
    total = french_hits + english_hits
    # 信号比接近（<60/40）→ mixed；否则强信号方胜出
    if max(french_hits, english_hits) / total < 0.6:
        return "mixed"
    return "fr" if french_hits > english_hits else "en"
